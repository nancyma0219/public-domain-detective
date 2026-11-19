"""Deterministic, scoped post-round evidence gap review.

These are *research prompts*, not conclusions about legal copyright status.
Evidence is assessed from actual tool outputs rather than a language model's summary.
"""
from __future__ import annotations

import json
import re
from typing import Any

REMOTE = {'wikidata_author', 'openlibrary_search', 'hathitrust_lookup', 'gutenberg_search'}


def _payload(call: dict) -> dict | None:
    """Parse only complete JSON outputs; truncated outputs are not trusted."""
    raw = call.get('output')
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def review_round(calls: list[dict], *, round_no: int, max_rounds: int, mode: str = "book") -> dict[str, Any]:
    """Review one round's completed tools, produce targeted gaps for the Lead.

    Review only calls from the current research round, not the entire session.
    A missing exact join is a lead for further checking, never proof of nonrenewal.
    """
    issues: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def flag(code: str, reason: str, action: str, severity: str = 'review') -> None:
        key = (code, action)
        if key not in seen:
            seen.add(key)
            issues.append({'code': code, 'severity': severity, 'reason': reason, 'suggested_action': action})

    has_record_search = False
    has_direct_renewal_search = False
    has_supported_renewal = False
    has_ambiguous_registration = False
    has_unlinked_registration = False
    has_no_renewal_search_result = False

    for call in calls:
        tool = call.get('name', '')
        p = _payload(call)
        if p is None:
            if tool not in {'dispatch_researchers', 'check_citations'}:
                flag('uninspectable_tool_output', f'{tool} did not return complete structured JSON in the trace',
                     f'Inspect the {tool} result and do not use it as evidence of absence')
            continue
        status = p.get('status')
        if tool in REMOTE:
            if status in ('source_unavailable', 'error') or p.get('error'):
                flag('external_source_failed', f'{tool} returned {status or "an error"}',
                     f'If {tool} is material to the question, try an independent source; otherwise disclose that it was unavailable')
            elif status == 'no_results':
                # Not a conclusive gap; the absence is bounded by this search.
                flag('bounded_external_search', f'{tool} returned no matching records in this query',
                     f'Only report no hits in this {tool} search; do not conclude no copies or records exist', 'note')
        if p.get('scan_truncated'):
            flag('truncated_search', f'{tool} search was truncated',
                 'Narrow or vary the search terms; disclose that retrieval was not exhaustive')
        if tool == 'search_registrations':
            has_record_search = True
            for row in p.get('results', []):
                state = row.get('match_status')
                if state in ('multiple_renewal_candidates', 'registration_key_collision'):
                    has_ambiguous_registration = True
                if state in ('no_exact_key_match', 'invalid_registration_key'):
                    has_unlinked_registration = True
                if state == 'exact_key_candidate' and row.get('renewal_id'):
                    has_supported_renewal = True
        if tool == 'verify_record_link':
            state = p.get('status')
            if state in ('multiple_renewal_candidates', 'registration_key_collision', 'ambiguous_entry_id'):
                has_ambiguous_registration = True
            if state in ('no_exact_key_match', 'invalid_registration_key'):
                has_unlinked_registration = True
            if state == 'exact_key_candidate' and p.get('candidates'):
                has_supported_renewal = True
        if tool == 'search_renewals':
            has_direct_renewal_search = True
            if p.get('results'):
                # A text-search hit is *not* a verified registration-renewal link.
                pass
            else:
                has_no_renewal_search_result = True

    if has_ambiguous_registration:
        flag('registration_conflict', 'Registration/renewal linkage contains multiple candidates or a key collision',
             'Compare the competing original records, titles, dates, author and provenance; do not select the first candidate')
    if has_unlinked_registration and not has_supported_renewal:
        flag('renewal_unresolved', 'At least one registration lacks an exact renewal link; no verified renewal was observed',
             'Search renewal titles, author/claimant variants, pseudonyms and original registration numbers; state unresolved if no verified link emerges')
        if not has_direct_renewal_search:
            flag('renewal_search_not_attempted', 'No direct renewal search tool call was observed',
                 'Call search_renewals before concluding the renewal investigation')
        elif has_no_renewal_search_result:
            flag('renewal_search_bounded', 'Direct renewal search returned no hits',
                 'Try meaningful title/author variants when relevant and preserve nonrenewal uncertainty', 'note')
    if mode == 'aggregate':
        sql_calls = [c for c in calls if c.get('name') == 'query_records' and _payload(c) is not None]
        sqls = [(c.get('arguments') or {}).get('sql', '') for c in sql_calls]
        annual = [q for q in sqls if re.search(r'\b(?:reg_year|catalog_year)\b', q, re.I)
                  and re.search(r'\bGROUP\s+BY\b', q, re.I)]
        if not annual:
            flag('annual_cohort_missing', 'No completed annual cohort aggregation was observed',
                 'Execute a bounded year-by-year cohort SQL query and report numerator and denominator')
        elif not any(re.search(r"regexp_matches\s*\(\s*regnum\s*,\s*['\"]\^A\[0-9\]", q, re.I) for q in annual):
            flag('class_a_scope_missing', 'Annual aggregation did not demonstrate an exact Class A filter',
                 "Rerun annual SQL with regexp_matches(regnum, '^A[0-9]') and rename the metric candidate linkage rate")
        if annual and not any(re.search(r'\b(?:source_file|match_status|catalog_year|count\s*\(\s*distinct|regexp_extract)\b', q, re.I)
                               for q in sqls):
            flag('method_validation_missing', 'Only annual counts were queried; no independent cohort, provenance, or linkage validation was observed',
                 'Check source-file coverage, key duplication, matched-link definitions, or alternate year fields with SQL')
        if annual and len(sql_calls) < 3:
            flag('thin_aggregate_research', 'Only a minimal set of SQL queries was executed for a multi-decade research task',
                 'Use a follow-up query to test a material limitation or discontinuity, not merely restate yearly counts')
    if mode != 'aggregate' and not has_record_search:
        flag('records_not_checked', 'No registration lookup was observed in this round',
             'If the case concerns a specific historical work, check NYPL original records')

    actionable = [i for i in issues if i['severity'] != 'note']
    return {
        'round': round_no, 'max_rounds': max_rounds,
        'additional_round_permitted': round_no < max_rounds,
        'issues': issues,
        'actionable_issue_count': len(actionable),
        'policy': ('Only dispatch a follow-up if it could materially change the answer. '
                   'Do not dispatch solely to fix an unrelated external API failure. '
                   'If no more rounds are available, disclose unresolved gaps. '
                   'This review is NOT a copyright verdict.'),
    }
