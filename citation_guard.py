"""Deterministic checks for cited record facts (not a substitute for legal review)."""
import re

REG_NUMBER = re.compile(r"\b(?:AFO|AF|AI|RE|R|A|B)\s*[- ]?\d{2,9}\b", re.I)
ISO_DATE = re.compile(r"\b(?:18|19|20)\d\d-\d\d-\d\d\b")
EVIDENCE = re.compile(r"\[((?:REG|REN|RULE|SQL|OL|HT|WD|PG):[^\]]+)\]")


def _ids(line):
    ids = []
    for group in EVIDENCE.findall(line):
        ids.extend(part.strip() for part in re.split(r"[,;]\s*", group))
    return ids


def _norm_num(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _values(evidence, keys):
    values = set()
    for e in evidence:
        record = e.get("record") or {}
        for key in keys:
            if record.get(key):
                values.add(str(record[key]))
    return values


def verify_citation_facts(report, ledger):
    """Flag explicit registration/renewal IDs or ISO dates unsupported by cited records.

    This intentionally checks *only* facts with deterministic structured fields.
    It never certifies a report's legal conclusion, title/edition identity, or
    natural-language assertions as true.
    """
    problems = []
    section = re.search(r"^### Evidence\s*\n(.*?)(?=^### |\Z)", report, re.S | re.M)
    if section:
        for line in section.group(1).splitlines():
            if not line.lstrip().startswith(("- ", "* ")):
                continue
            references = [ledger[i] for i in _ids(line) if i in ledger]
            if not references:
                continue
            record_refs = [r for r in references if r.get("record") and r.get("record_type") in {"REG", "REN"}]
            if not record_refs:
                continue
            numbers = {_norm_num(v) for v in _values(record_refs, (
                "regnum", "original_regnum", "orig_regnum", "renewal_id", "renewal_regnum"))}
            dates = _values(record_refs, ("regdate", "reg_date", "original_regdate", "orig_regdate", "renewal_date"))
            # Only inspect numbers for the relevant record-backed bullet: prevents
            # an uncited registration number from being silently attributed.
            for value in set(REG_NUMBER.findall(EVIDENCE.sub("", line))):
                if _norm_num(value) not in numbers:
                    problems.append(f'Unsupported registration/renewal number {value} in evidence bullet: {line[:150]}')
            for value in set(ISO_DATE.findall(EVIDENCE.sub("", line))):
                if value not in dates:
                    problems.append(f'Unsupported ISO date {value} in evidence bullet: {line[:150]}')
            regs = [r["record"] for r in record_refs if r.get("record_type") == "REG"]
            renewals = [r["record"] for r in record_refs if r.get("record_type") == "REN"]
            if regs and renewals:
                for renew in renewals:
                    orig_num = _norm_num(renew.get("original_regnum") or renew.get("orig_regnum"))
                    orig_date = renew.get("original_regdate") or renew.get("orig_regdate")
                    if orig_num and orig_date and not any(
                        orig_num == _norm_num(reg.get("regnum")) and orig_date == (reg.get("regdate") or reg.get("reg_date"))
                        for reg in regs
                    ):
                        problems.append("Cited renewal's original registration key conflicts with cited registration in evidence bullet")
    # Prevent a 'no hit' report from becoming an affirmative public-domain verdict.
    verdict = re.search(r"\*\*Verdict:\*\*([^\n]*)", report, re.I)
    if verdict and re.search(r"\b(?:probably\s+)?public\s+domain\b", verdict.group(1), re.I):
        support = [x for x in ledger.values() if x.get("record_type") == "RULE" and
                   (x.get("record") or {}).get("verdict") == "public_domain"]
        if not support:
            problems.append("Public-domain verdict lacks a supporting RULE result with verdict=public_domain; use undetermined")
    return problems
