"""Deterministic, auditable NYPL Class A cohort research for annual trend questions.

These are exact-key *candidate associations*, not legally verified copyright renewals.
All figures are taken from the current DuckDB snapshot at runtime.
"""
from __future__ import annotations
import re
from typing import Callable

CLASS_A = "regexp_matches(regnum, '^A[0-9]+$')"
ANNUAL_SQL = f"""SELECT reg_year AS year, COUNT(*) AS registration_rows,
 COUNT(DISTINCT regnum) AS distinct_keys,
 SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_rows,
 ROUND(100.0 * SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS link_pct
 FROM reg_status WHERE reg_year BETWEEN 1931 AND 1963 AND {CLASS_A}
 GROUP BY reg_year ORDER BY reg_year"""
PERIOD_SQL = f"""SELECT CASE WHEN reg_year <= 1952 THEN '1931–1952' ELSE '1953–1963' END AS period,
 COUNT(*) AS registration_rows,
 COUNT(DISTINCT regnum) AS distinct_keys,
 SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_rows,
 ROUND(100.0 * SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS link_pct
 FROM reg_status WHERE reg_year BETWEEN 1931 AND 1963 AND {CLASS_A}
 GROUP BY 1 ORDER BY 1"""
COVERAGE_SQL = f"""SELECT reg_year AS year, COUNT(*) AS registration_rows,
 COUNT(DISTINCT source_file) AS distinct_source_files,
 COUNT(DISTINCT regnum) AS distinct_keys,
 SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_rows
 FROM reg_status WHERE reg_year BETWEEN 1951 AND 1954 AND {CLASS_A}
 GROUP BY reg_year ORDER BY reg_year"""


def is_annual_book_query(question: str) -> bool:
    q = (question or '').lower()
    return bool(re.search(r'(?:1931\s*[-–]\s*1963|by year|per year|yearly|annual|trend)', q)
                and re.search(r'\b(?:renewal|copyright|registration|linkage|link)\b', q)
                and not re.search(r'\b(?:one book|single book)\b', q))


def compute(run_sql: Callable[[str], dict]) -> dict:
    output = {}
    for name, sql in [('annual', ANNUAL_SQL), ('period', PERIOD_SQL), ('coverage', COVERAGE_SQL)]:
        data = run_sql(sql)
        if not isinstance(data, dict) or data.get('error') or data.get('truncated') or not data.get('eid'):
            return {'ok': False, 'error': f'{name}: query error or truncated data', 'details': data}
        output[name] = data
    annual = output['annual']
    if len(annual['rows']) != 33 or not all(len(r) == 5 and r[1] and r[3] <= r[1] for r in annual['rows']):
        return {'ok': False, 'error': 'Incomplete, inconsistent or unexpected annual cohort', 'details': output}
    if len(output['period']['rows']) != 2 or len(output['coverage']['rows']) != 4:
        return {'ok': False, 'error': 'Missing period or coverage diagnostics', 'details': output}
    if sum(r[1] for r in annual['rows']) != sum(r[1] for r in output['period']['rows']):
        return {'ok': False, 'error': 'Annual and period registration denominators disagree', 'details': output}
    return {'ok': True, 'queries': output}


def markdown(data: dict) -> str:
    """Render certified *data calculations*; interpretation remains explicitly provisional."""
    if not data.get('ok'):
        return ('### Research findings\nThe corrected Class A cohort could not be computed reliably. '
                'No numerical conclusion can be verified from this run.\n\n'
                '### Methodology\nThe annual analysis must use exact Class A numbers, '
                'nontruncated query results, and independent denominator checks.\n\n'
                '### Data limitations\nUnderlying query error: '
                + str(data.get('error', 'unknown')) + '\n')
    a,p,c = (data['queries'][name] for name in ('annual','period','coverage'))
    ids = [v['eid'] for v in (a,p,c)]
    periods=p['rows']
    y={r[0]:r for r in a['rows']}
    lines=['### Research findings',
      'For transcribed domestic Class A registration rows, the **candidate renewal-linkage percentage** differs across periods. '
      'It is **not** an estimate of legally verified renewals. [' + ids[1] + ']',
      '',
      '| Period | Registration rows | Rows with candidate renewal link | Linkage |',
      '|---|---:|---:|---:|']
    for period,rows,distinct,linked,pct in periods:
        lines.append(f'| {period} | {rows:,} | {linked:,} | {pct:.2f}% |')
    lines.extend(['',
      f'**1952 → 1953 discontinuity:** {y[1952][1]:,} → {y[1953][1]:,} registration rows; '
      f'{y[1952][4]:.2f}% → {y[1953][4]:.2f}% candidate linkage. [{ids[0]}]',
      'This is an **observed break**, not evidence of a change in copyright behavior. The underlying cause remains unverified.',
      '', '### Annual results',
      '| Year | Registration rows | Distinct registration numbers | Linked rows | Candidate linkage |',
      '|---|---:|---:|---:|---:|'])
    for yr,rows,distinct,linked,pct in a['rows']:
        lines.append(f'| {yr} | {rows:,} | {distinct:,} | {linked:,} | {pct:.2f}% |')
    lines.extend(['', f'Annual data: [{ids[0]}]', '',
      '### 1953 break: evidence and competing explanations',
      'The following source-file counts show the coverage of the **loaded transcription**; '
      'they do not independently establish why the break occurred.',
      '| Year | Registration rows | Distinct source files | Distinct keys | Linked rows |',
      '|---|---:|---:|---:|---:|'])
    for yr,rows,files,keys,linked in c['rows']:
        lines.append(f'| {yr} | {rows:,} | {files} | {keys:,} | {linked:,} |')
    lines.extend(['',f'Coverage diagnostic: [{ids[2]}]', '',
      '**Hypotheses requiring further testing:** differences in transcription coverage, inclusion of different record types, '
      'registration-year vs. catalog-year assignment, and exact-key linkage failures. '
      'None is established as the cause by these three queries.', '',
      '### Methodology',
      "- Cohort: `reg_year` 1931–1963 and `regexp_matches(regnum, '^A[0-9]+$')`; "
      'this excludes AF, AFO, AI and other prefixes.',
      '- Denominator: number of rows in `reg_status` meeting that cohort filter. Distinct registration numbers are shown separately.',
      '- Numerator: rows with non-null `renewal_id` in the joined transcription. A candidate association is not a confirmed legal renewal.',
      f'- Reproducible SQL and data rows are stored as evidence [{ids[0]}] [{ids[1]}] [{ids[2]}].',
      '', '### Data limitations',
      '- Transcription, OCR, source coverage, overlapping entries, and key matching may bias both numerator and denominator.',
      '- A missing candidate link is **not** proof of nonrenewal or public-domain status.',
      '- This is a registration-row analysis, not a count of distinct books or a causal study of historical publishing.',
      '', '_Not legal advice. Records: NYPL Catalog of Copyright Entries transcriptions._'])
    return '\n'.join(lines)
