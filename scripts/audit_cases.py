"""Inspect real NYPL candidate renewals and prepare a reproducible case-audit report.

Read-only; uses this repository's deployed reg_status + renewals Parquet views.
The script DOES NOT equate a fuzzy/title hit with a verified original-work renewal.
Run: uv run python scripts/audit_cases.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import records

OUT = Path('evaluation')

CASES = [
    ('renewed', 'Strangers on a Train', 'Patricia Highsmith', 1950, 'A41904'),
    ('unresolved', 'The Price of Salt', 'Patricia Highsmith', 1952, 'A68131'),
    ('possible_conflict', 'The World of Carbon', 'Isaac Asimov', 1958, 'A352575'),
]


def candidate_relationship(row: dict, original_regnum: str, original_regdate: str | None) -> str:
    """Classify the visible linkage, *not* the legal outcome."""
    candidate_num = (row.get('orig_regnum') or '').strip().upper()
    original_num = (original_regnum or '').strip().upper()
    candidate_date = str(row.get('orig_regdate') or '')[:10]
    orig_date = str(original_regdate or '')[:10]
    if candidate_num and candidate_num == original_num:
        if orig_date and candidate_date and candidate_date == orig_date:
            return 'same_registration_number_and_date_candidate_needs_edition_review'
        return 'same_registration_number_date_missing_or_different'
    if candidate_num:
        return 'different_original_registration_number'
    return 'original_registration_number_not_transcribed'


def candidate_key(row: dict) -> tuple:
    """A renewal ID is not a unique original-registration association."""
    return (str(row.get('renewal_id') or '').strip().upper(),
            str(row.get('orig_regnum') or '').strip().upper(),
            str(row.get('orig_regdate') or '')[:10],
            str(row.get('source_file') or '').strip())


def renewal_id_conflicts(candidates: list[dict]) -> dict:
    """Return renewal IDs tied to multiple distinct original registration keys."""
    by_id = {}
    for c in candidates:
        rid = str(c.get('renewal_id') or '').strip().upper()
        if not rid:
            continue
        by_id.setdefault(rid, set()).add((str(c.get('orig_regnum') or '').strip().upper(),
                                           str(c.get('orig_regdate') or '')[:10]))
    return {rid: sorted(list(keys)) for rid, keys in by_id.items() if len(keys) > 1}


def audit_case(category, title, author, year, original_number, con):
    registration = records.search_registrations(title, author, year - 2, year + 2, limit=12)
    registrations = registration.get('results', [])
    original = [x for x in registrations if (x.get('regnum') or '').upper() == original_number.upper()]
    original_date = original[0].get('regdate') if len(original) == 1 else None
    variants = [title]
    if title == 'The Price of Salt':
        variants += ['Carol', 'Price of Salt']
    if title == 'The World of Carbon':
        variants += ['World of Carbon']
    searches = []
    for t in dict.fromkeys(variants):
        for a in [author, None]:
            result = records.search_renewals(t, a, limit=12)
            searches.append({'title': t, 'author': a,
                             'candidates_scanned': result.get('candidates_scanned'),
                             'scan_truncated': result.get('scan_truncated'),
                             'results': result.get('results', [])})
    # Independent original-registration-number lookup catches alternate-title renewals.
    rows = con.execute('''
        SELECT id, rdat, oreg, odat, title, author, claimants, source_file
        FROM renewals WHERE upper(trim(oreg)) = upper(?)
        ORDER BY rdat, id LIMIT 101
    ''', [original_number]).fetchall()
    matching_number = []
    for r in rows[:100]:
        v = dict(zip(['renewal_id','renewal_date','orig_regnum','orig_regdate',
                      'title','author','claimants','source_file'], r))
        v['relationship'] = candidate_relationship(v, original_number, original_date)
        matching_number.append(v)
    # Broader text candidate audit for 1952 specifically; exposes the records the second-round
    # search may have returned. No automatic declaration that these are irrelevant or renewed.
    other_candidates = []
    seen = set()
    for search in searches:
        for c in search['results']:
            key = candidate_key(c)
            if key in seen: continue
            seen.add(key)
            cc = dict(c)
            cc['relationship'] = candidate_relationship(cc, original_number, original_date)
            cc['candidate_key'] = '|'.join(key)
            other_candidates.append(cc)
    return {
        'category': category, 'title': title, 'author': author, 'year': year,
        'original_registration_number': original_number,
        'registration_lookup': registration, 'original_registration_candidates': original,
        'original_registration_date_if_unique': original_date,
        'renewal_title_searches': searches,
        'renewals_referring_to_original_number': matching_number,
        'original_number_lookup_truncated': len(rows) > 100,
        'distinct_title_search_candidates': other_candidates,
        'renewal_id_key_conflicts': renewal_id_conflicts(other_candidates + matching_number),
        'interpretation': (
            'A returned candidate is NOT a verified renewal of this original edition. '
            'Compare original registration number/date, title, claimants, source files and '
            'whether renewed matter relates to the same edition. No hit does not prove nonrenewal.'
        ),
    }


def markdown_report(audits):
    lines = [
        '# NYPL candidate evidence audit', '',
        'This audit examines *candidate links*, not legal clearance.',
        'For each candidate, verify the original registration number and date, identity of work and edition, and source transcription.', '',
    ]
    for c in audits:
        lines += [f"## {c['title']} ({c['year']}) — {c['category']}", '',
                  f"Original registration: `{c['original_registration_number']}`; date from candidate: `{c['original_registration_date_if_unique']}`.",
                  f"Registration candidates with number: **{len(c['original_registration_candidates'])}**; "
                  f"renewals referring to number: **{len(c['renewals_referring_to_original_number'])}**; "
                  f"unique title-search candidates: **{len(c['distinct_title_search_candidates'])}**.", '',
                  '| Renewal ID | Original registration | Original date | Title | Relationship |',
                  '|---|---|---|---|---|']
        for r in c['distinct_title_search_candidates'][:25]:
            title = str(r.get('title','')).replace('|','\\|')[:75]
            lines.append(f"| `{r.get('renewal_id','')}` | `{r.get('orig_regnum','')}` | "
                         f"`{r.get('orig_regdate','')}` | {title} | {r['relationship']} |")
        if not c['distinct_title_search_candidates']:
            lines.append('| (none in these title searches) | — | — | — | — |')
        if c.get('renewal_id_key_conflicts'):
            lines += ['', '**Same renewal ID, different original registration keys:**']
            for rid, keys in c['renewal_id_key_conflicts'].items():
                lines.append(f"- `{rid}`: " + '; '.join(f"`{num}` / `{day}`" for num, day in keys))
        lines += ['', '**Limit:** These are distinct renewal-to-original associations, not necessarily '
                  'distinct renewal filings. Title similarity, number match, and dates alone do not '
                  'establish legal status. No hit does not prove nonrenewal.', '']
    return '\n'.join(lines)


def main():
    OUT.mkdir(exist_ok=True)
    con = records.db()
    audits = [audit_case(*case, con) for case in CASES]
    json_path = OUT/'nypl_candidate_audit.json'
    md_path = OUT/'nypl_candidate_audit.md'
    json_path.write_text(json.dumps({'generated_utc': datetime.now(timezone.utc).isoformat(),
                                     'cases': audits}, ensure_ascii=False, indent=2, default=str))
    md_path.write_text(markdown_report(audits))
    print('Wrote', json_path, 'and', md_path)
    for case in audits:
        print(f"{case['title']}: {len(case['distinct_title_search_candidates'])} title-search renewal candidates; "
              f"{len(case['renewals_referring_to_original_number'])} referencing original number")

if __name__ == '__main__':
    main()
