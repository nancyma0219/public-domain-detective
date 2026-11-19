"""Question-scoped evidence/claim guard for research reports.

Conservative patterns and tool-status inspection only. This is not complete semantic
verification and does not certify U.S. copyright status.
"""
from __future__ import annotations
import json
import re

AGGREGATE = re.compile(r'\b(?:by year|per year|across (?:years|decades|books)|yearly|annual|cohort|trend|patterns?|share of|rate of|percentage|statistics?|distribution|1931\s*[-–]\s*1963|compare decades)\b', re.I)


def question_mode(question: str) -> str:
    return 'aggregate' if AGGREGATE.search(question or '') else 'book'


def _payload(call: dict) -> dict | None:
    value = call.get('output')
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        obj = json.loads(value)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def check_research_claims(report: str, tool_calls: list[dict], question: str) -> list[str]:
    """Catch high-risk mismatch between an observed tool trace and the written report."""
    issues: list[str] = []
    mode = question_mode(question)
    names = {c.get('name') for c in tool_calls}
    if mode == 'aggregate':
        # Validate executed SQL instead of relying on what the Writer calls its cohort.
        annual_sql = [(c.get('arguments') or {}).get('sql', '') for c in tool_calls
                      if c.get('name') == 'query_records'
                      and re.search(r'\breg_year\b', (c.get('arguments') or {}).get('sql', ''), re.I)
                      and re.search(r'\bGROUP\s+BY\b', (c.get('arguments') or {}).get('sql', ''), re.I)]
        if annual_sql and not any(re.search(r"regexp_matches\s*\(\s*regnum\s*,\s*['\"]\^A\[0-9\]", q, re.I) for q in annual_sql):
            issues.append('Executed annual SQL does not restrict to exact Class A, regardless of the report wording. Rerun the cohort with regexp_matches(regnum, ^A[0-9]) before reporting U.S. book statistics.')
        if not annual_sql:
            issues.append('No completed SQL query computing the annual book cohort is present; do not claim a year-by-year empirical result.')
        if re.search(r'\b(?:renewal rate|renewal rates|renewal_percentage)\b', report, re.I):
            issues.append('This is a transcribed-record candidate linkage rate, not a verified legal renewal rate; correct the measurement label and state numerator and denominator.')
        if re.search(r'\b(?:caused|explains?|due to|because of)\b.{0,90}\b(?:plummet|drop|decline|rise|jump|spike)\b', report, re.I):
            issues.append('Do not claim a causal explanation for a time-series break without independent SQL evidence isolating the mechanism.')
        if re.search(r'\b(?:OCR errors|database scope shifts|missing scanned pages|treaty exemptions)\b', report, re.I) and not re.search(r'\b(?:hypothesis|possible|may|might|potential|not established)\b', report, re.I):
            issues.append('Dataset limitations should be qualified as risks or hypotheses unless a specific executed query or external source establishes them.')
        if re.search(r'^\s*\*\*Verdict:\*\*', report, re.M):
            issues.append('This is an aggregate data-analysis question. Replace the book verdict with "### Research findings", methodology, year-by-year comparisons, and limits; do not give legal verdict or confidence about a single work.')
        if re.search(r'### Digitized copies and access', report, re.I):
            issues.append('Aggregate analysis did not ask about digitized copies. Remove the access section unless the user explicitly requested it.')
        if re.search(r'\b(?:renewal rate|renewal rates)\b', report, re.I):
            issues.append('Do not call an exact-key/transcribed-database candidate-link percentage a legal renewal rate. Define numerator, denominator, cohort, and call it "candidate linkage rate".')
        if re.search(r'\b811,084\s+(?:registrations|records)\b', report):
            issues.append('811,084 is the number of duplicated regnum GROUPS in this SQL, not the number of registration rows.')
        if re.search(r'\b824,646\b', report) and re.search(r'\b(?:corrupt|invalid|bad|damaged|out.of.range)\b', report, re.I):
            issues.append('The 824,646 count comes from an incorrect catalog-year scope (<1923 or >1969); deployment also includes 1970–1977. Recompute true invalid years.')
        for call in tool_calls:
            if call.get('name') != 'query_records':
                continue
            sql = (call.get('arguments') or {}).get('sql') or ''
            if re.search(r"regnum\s+LIKE\s+['\"]A%['\"]", sql, re.I) and re.search(r'\bClass A\b', report, re.I):
                issues.append('The SQL for Class A uses regnum LIKE A%, which includes AF/AFO/AI. Rerun with regexp_matches(regnum, \'^A[0-9]\') before reporting Class A counts.')
                break
    else:
        if re.search(r'\b(?:fully reconciled|all conflicts? (?:are|were) resolved)\b', report, re.I):
            issues.append('Do not claim conflicting original registration references are fully reconciled without authoritative evidence distinguishing all references and dates.')
        if re.search(r'\b(?:clerical|OCR|transcription) error\b', report, re.I) and re.search(r'\b(?:AI5926|RE277631)\b', report):
            issues.append('An AI5926 date disagreement is observed, but the cause is unverified. Describe it as a conflicting transcription rather than proven clerical/OCR error.')
    sources = (
        ('HathiTrust', 'hathitrust_lookup'),
        ('Project Gutenberg', 'gutenberg_search'),
        ('Open Library', 'openlibrary_search'),
    )
    for source, tool in sources:
        # A claim of a completed negative search must be backed by an actual clean no-result response.
        claim = re.search(rf'(?:{re.escape(source)}\s*:\s*no\s+matching|no\s+(?:matching\s+)?(?:copy|copies|record|records|results)\s+(?:were\s+)?found\s+in\s+{re.escape(source)})', report, re.I)
        if not claim:
            continue
        attempts = [_payload(c) for c in tool_calls if c.get('name') == tool]
        if not attempts:
            issues.append(f'Report says {source} was searched with no matches, but the {tool} tool was never called. Remove the claim or conduct that search.')
        elif not any(p is not None and p.get('status') == 'no_results' for p in attempts):
            issues.append(f'Report says {source} had no matches, but no completed {tool} call returned status=no_results. Do not treat failure/truncated evidence as zero matches.')
    # Legal-rule evidence is not a citation for empirical renewal-database coverage.
    for line in report.splitlines():
        if re.search(r'\bno matching renewal\b|\bno renewal(?: registration)? (?:was )?found\b', line, re.I):
            if re.search(r'\[RULE:[^\]]+\]', line) and not re.search(r'\[SQL:[^\]]+\]', line):
                issues.append('A legal RULE citation does not substantiate a negative database search. Cite a completed, bounded SQL search evidence ID and its scope (or remove the negative assertion).')
                break
    return list(dict.fromkeys(issues))
