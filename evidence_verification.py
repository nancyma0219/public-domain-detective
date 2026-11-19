"""Read-only, provenance-preserving registration/renewal verification.

Uses the Parquet views already created by records.db(). A composite key match is
record evidence, not proof of copyright status or of the identity of editions.
"""
from __future__ import annotations
import records


def verify_record_link(registration_entry_id: str, max_candidates: int = 20) -> dict:
    """Inspect one registration and associated renewal candidates by original registration key.

    Args:
        registration_entry_id: Exact NYPL XML entry_id returned by search_registrations (not REG: prefix).
        max_candidates: Number of renewal rows to return, 1-50.
    """
    if not registration_entry_id or len(registration_entry_id) > 128:
        return {"error": "Provide a valid registration_entry_id from search_registrations."}
    max_candidates = max(1, min(int(max_candidates), 50))
    con = records.db()
    reg = con.execute("""
        SELECT entry_id, regnum, regdate, title, authors, source_file, source_url, match_status
        FROM reg_status WHERE entry_id = ? LIMIT 2
    """, [registration_entry_id]).fetchall()
    if not reg:
        return {"error": "Registration entry not found.", "entry_id": registration_entry_id}
    if len(reg) > 1:
        return {"status": "ambiguous_registration_id", "entry_id": registration_entry_id,
                "reason": "Multiple rows share this entry ID; inspect the original sources before linking."}
    entry_id, number, date, title, authors, file, url, prior = reg[0]
    registration = {"eid": f"REG:{entry_id}", "entry_id": entry_id,
                    "regnum": number, "regdate": date, "title": title, "authors": authors,
                    "source_file": file, "source_url": url, "match_status": prior}
    if not number or not date:
        return {"status": "invalid_registration_key", "registration": registration,
                "candidates": [], "reason": "Missing registration number or date; cannot check composite key."}
    rows = con.execute("""
        SELECT entry_id, id, rdat, oreg, odat, title, author, claimants, source_file, new_matter
        FROM renewals WHERE oreg = ? AND odat = ?
        ORDER BY id, entry_id LIMIT ?
    """, [number, date, max_candidates + 1]).fetchall()
    candidates = []
    for row in rows[:max_candidates]:
        renewal_entry_id, renewal_number, renewal_date, orig_number, orig_date, rtitle, rauthor, claimants, source, new_matter = row
        candidates.append({"eid": f"REN:{renewal_number}" if renewal_number else None,
                           "entry_id": renewal_entry_id,
                           "candidate_key": f"{renewal_number}|{orig_number}|{orig_date}|{source}",
                           "renewal_regnum": renewal_number, "renewal_date": renewal_date,
                           "original_regnum": orig_number, "original_regdate": orig_date,
                           "title": rtitle, "author": rauthor, "claimants": claimants,
                           "source_file": source, "new_matter": new_matter})
    truncated = len(rows) > max_candidates
    distinct_renewals = {r[1] for r in rows if r[1]}
    if prior == "registration_key_collision":
        status = "registration_key_collision"
    elif truncated:
        status = "incomplete_candidate_list"
    elif not candidates:
        status = "no_exact_key_match"
    elif len(distinct_renewals) > 1:
        status = "multiple_renewal_candidates"
    else:
        status = "exact_key_candidate"
    return {"status": status, "registration": registration, "candidates": candidates,
            "truncated": truncated,
            "reason": "Composite registration number and original date are compared exactly. "
                      "Title, author, edition, first publication, and applicability of copyright rules "
                      "still require independent verification. No match is not proof of nonrenewal."}
