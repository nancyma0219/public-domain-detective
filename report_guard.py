"""Conservative checks for unsupported access and research-coverage claims.

These checks catch known risky phrasings; they do not certify legal accuracy.
"""
from __future__ import annotations
import re

_NEGATION = r"(?:no|none|not\s+any|zero)"
_GENERAL = re.compile(
    rf"\b{_NEGATION}\s+(?:free\s+)?(?:public[- ]domain\s+)?(?:digital\s+|digitized\s+)?"
    r"(?:copies|ebooks|e-books|scans|versions)\s+(?:are\s+)?(?:available|exist|found\s+anywhere|online)\b",
    re.I,
)
_SHORT = re.compile(r"\bNone\s+found\.?\s*$", re.I | re.M)
_NO_RENEWAL = re.compile(r"\b(?:was\s+never\s+renewed|copyright\s+was\s+not\s+renewed|no\s+renewal\s+was\s+filed)\b", re.I)
_UNVERIFIED = re.compile(r"\b(?:no\s+renewal\s+(?:was\s+)?found|no\s+(?:exact\s+)?renewal\s+match|renewal\s+not\s+found)\b", re.I)


def verify_report_claims(report: str, ledger: dict | None = None) -> list[str]:
    """Return problems to show the Writer. Only check explicit unsafe generalizations.

    Search failure and no-hits results can never establish universal absence of copies.
    A search non-hit cannot establish non-renewal. We require an explicit proof mechanism
    outside this basic ledger before claiming historical non-renewal as a fact.
    """
    problems = []
    if _GENERAL.search(report) or _SHORT.search(report):
        problems.append(
            "Do not claim that no free/public-domain copies exist or write 'None found'. "
            "State precisely which catalog was searched and what it returned; mention sources not checked."
        )
    if _NO_RENEWAL.search(report):
        problems.append(
            "An absent renewal search hit does not prove that no renewal was filed. "
            "State 'no matching renewal found in the searched records' and preserve uncertainty."
        )
    verdict_match = re.search(r"^\*\*Verdict:\*\*\s*(.*)$", report, flags=re.I | re.M)
    if verdict_match and re.search(r"\bpublic\s+domain\b", verdict_match.group(1), re.I):
        supported = any(
            isinstance(ev, dict) and ev.get('record_type') == 'RULE'
            and isinstance(ev.get('record'), dict)
            and ev['record'].get('verdict') == 'public_domain'
            for ev in (ledger or {}).values()
        )
        if not supported:
            problems.append("Public-domain verdict requires a cited, supporting RULE result, not just an absent renewal hit.")
    return list(dict.fromkeys(problems))
