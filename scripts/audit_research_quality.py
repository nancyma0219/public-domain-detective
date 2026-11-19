"""Offline semantic quality audit for Public Domain Detective live-evaluation JSON.

Usage: python scripts/audit_research_quality.py evaluation/live [--run-db]
--run-db uses the project's records.py / local DuckDB to compute corrected indicators.
No model or network calls are performed.
"""
import argparse
import json
from pathlib import Path
import re


def _calls(result):
    return result.get('tool_calls') or []


def audit(case):
    cid = case.get('case_id')
    result = case.get('result') or {}
    response = result.get('response') or ''
    calls = _calls(result)
    tools = {c.get('name') for c in calls}
    issues = []
    def flag(code, severity, detail):
        issues.append({'code': code, 'severity': severity, 'detail': detail})
    if cid == 'clarification':
        if not result.get('needs_clarification') or result.get('rounds') != 0 or calls:
            flag('clarification_behavior','error','Ambiguous request must clarify without launching research.')
        return issues
    for source, tool in [('HathiTrust','hathitrust_lookup'),('Project Gutenberg','gutenberg_search'),('Open Library','openlibrary_search')]:
        # Claims about search results are not supported by other source types.
        if re.search(r'(?:no matching copy|no (?:matching )?(?:copy|results|records) found).{0,65}'+re.escape(source),response,re.I) or re.search(re.escape(source)+r'\s*:\s*no matching',response,re.I):
            if tool not in tools:
                flag('unqueried_source','error',f'Report says a {source} search had no match, but {tool} was never called.')
    if cid == 'patterns':
        if re.search(r'\*\*Verdict:\*\*', response):
            flag('wrong_report_template','warning','Aggregate question should present research findings, not a book-specific copyright verdict.')
        if re.search(r'\brenewal rate\b',response,re.I):
            flag('rate_label','error','Matched-link rate in transcriptions is not an observed legal renewal rate; name cohort and numerator.')
        if re.search(r'811,084 registrations with duplicate|811,084 registrations share',response,re.I):
            flag('duplicate_units','error','SQL counts 811,084 regnum GROUPS with COUNT(*)>1, not 811,084 registration ROWS.')
        if re.search(r'824,646.{0,120}(?:corrupt|invalid|bad|out.of.range)',response,re.I):
            flag('year_scope','error','Filter <1923 OR >1969 includes legitimate 1970–1977 volumes in deployment. Must separate valid out-of-scope from invalid parsed years.')
        if any(c.get('name') in {'search_registrations','search_renewals'} for c in calls):
            pass
        if re.search(r'\bClass A\b',response,re.I):
            for c in calls:
                if c.get('name')!='query_records':
                    continue
                sql=(c.get('arguments') or {}).get('sql') or ''
                if re.search(r'regnum\s+LIKE\s+[\'\"]A%[\'\"]',sql,re.I):
                    flag('class_prefix_scope','error',"SQL regnum LIKE 'A%' also includes AF, AFO, AI and other A* prefixes; use regexp ^A[0-9].")
                    break
        if 'Digitized copies and access' in response:
            flag('irrelevant_access_section','warning','Aggregate yearly research question does not ask for digitized copies; omit access section.')
        for c in calls:
            if c.get('name')=='review_research_gaps':
                try:
                    review=json.loads(c.get('output') or '{}')
                    if any(i.get('code')=='records_not_checked' for i in review.get('issues', [])):
                        flag('false_gap','warning','SQL aggregate case was flagged as needing individual registration lookup; Gap Review is not query-type aware.')
                        break
                except (ValueError,TypeError): pass
    if cid == 'variants':
        if re.search(r'fully reconciled|correct(?:ly)? (?:listed|date)|clerical transcription', response,re.I):
            flag('overclaimed_conflict_resolution','error','Variants reported as fully reconciled or OCR error without authoritative confirmation of AI5926 discrepancy.')
    if cid == 'unresolved':
        if re.search(r'No matching renewal[^\n]+\[RULE:',response,re.I):
            flag('rule_cited_for_search','error','Legal-rule citation alone does not support a negative renewal-database search.')
    return issues

CORRECTED_SQL = {
    'cohort_strict': "SELECT reg_year, COUNT(*) AS registration_rows, COUNT(DISTINCT regnum || '|' || COALESCE(regdate,'')) AS distinct_registration_keys, COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) AS matched_candidate_rows, ROUND(100.0 * COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) / NULLIF(COUNT(*),0), 2) AS candidate_link_rate_pct FROM reg_status WHERE regexp_matches(regnum, '^A[0-9]') AND reg_year BETWEEN 1931 AND 1963 GROUP BY reg_year ORDER BY reg_year",
    'year_diagnostics': "SELECT CASE WHEN reg_year IS NULL THEN 'null' WHEN reg_year BETWEEN 1923 AND 1977 THEN 'catalog_year_range_1923_1977' WHEN reg_year BETWEEN 1800 AND 2100 THEN 'plausible_year_outside_catalog_range' ELSE 'implausible_year' END AS year_category, COUNT(*) AS registration_rows, MIN(reg_year) AS min_year, MAX(reg_year) AS max_year FROM reg_status GROUP BY 1 ORDER BY 1",
    'duplicate_units': "SELECT COUNT(*) AS duplicated_regnum_groups, COALESCE(SUM(n),0) AS rows_in_duplicated_groups, COALESCE(SUM(n-1),0) AS excess_rows_over_one_per_regnum FROM (SELECT regnum, COUNT(*) AS n FROM reg_status WHERE regnum IS NOT NULL GROUP BY regnum HAVING COUNT(*)>1)",
    'cohort_breakdown': "SELECT CASE WHEN reg_year BETWEEN 1931 AND 1952 THEN '1931–1952' WHEN reg_year BETWEEN 1953 AND 1963 THEN '1953–1963' END AS period, COUNT(*) AS registration_rows, COUNT(*) FILTER (WHERE renewal_id IS NOT NULL) AS linked_rows, ROUND(100.0*COUNT(*) FILTER (WHERE renewal_id IS NOT NULL)/NULLIF(COUNT(*),0),2) AS candidate_link_pct FROM reg_status WHERE regexp_matches(regnum,'^A[0-9]') AND reg_year BETWEEN 1931 AND 1963 GROUP BY 1 ORDER BY 1",
}


def run_db():
    import records
    results={}
    for name,sql in CORRECTED_SQL.items():
        result=records.query_records(sql)
        results[name]=result
        print(f'{name}:',result.get('error') or {'columns':result.get('columns'),'rows':result.get('rows')})
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument('input',type=Path,help='Folder of evaluation/live/*.json or a single case JSON')
    p.add_argument('--run-db',action='store_true')
    p.add_argument('--output',default='evaluation/research_quality_audit.md')
    args=p.parse_args()
    paths=sorted(args.input.glob('*.json')) if args.input.is_dir() else [args.input]
    items=[]
    for path in paths:
        data=json.loads(path.read_text(encoding='utf-8'))
        if 'case_id' not in data: continue
        issues=audit(data)
        items.append((data['case_id'],issues))
        print(f"{data['case_id']}: {len(issues)} semantic flag(s)")
        for i in issues: print(f"  [{i['severity']}] {i['code']}: {i['detail']}")
    lines=['# Research quality audit','', 'Heuristic quality flags from saved live traces; **not** independent legal fact verification.', '']
    for cid,issues in items:
        lines += [f'## {cid}', '']
        lines += [f"- **{i['severity']} — {i['code']}**: {i['detail']}" for i in issues] or ['- No known heuristic flags. Manual review still required.']
        lines += ['']
    if args.run_db:
        results=run_db()
        lines += ['## Corrected local SQL diagnostics','']
        for name,data in results.items():
            lines += [f'### {name}','',f'`{CORRECTED_SQL[name]}`','', '```json',json.dumps({'columns':data.get('columns'),'rows':data.get('rows'),'error':data.get('error')},ensure_ascii=False,indent=2),'```','']
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text('\n'.join(lines),encoding='utf-8')
    print('Saved',dest)

if __name__=='__main__':main()
