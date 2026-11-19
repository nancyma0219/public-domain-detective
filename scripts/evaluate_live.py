"""Run one (or all) Public Domain Detective live /chat evaluations.

No model calls occur unless this script is executed against a running server.
Results are observations, not legal ground truth. Use --all deliberately (costly).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import httpx

CASES = {
    "renewed": {
        "question": "Is Strangers on a Train by Patricia Highsmith (1950) in the public domain in the United States?",
        "expect": "renewed",
        "description": "Original registration and a matching renewal; distinguish the French translation.",
    },
    "unresolved": {
        "question": "Is The Price of Salt by Patricia Highsmith, published as Claire Morgan in 1952, in the public domain in the United States?",
        "expect": "unresolved",
        "description": "No exact-key renewal; examine alternative titles, pseudonym, and false positives.",
    },
    "variants": {
        "question": "Investigate the 1958 U.S. copyright registration and renewals for Isaac Asimov's The World of Carbon. Explain any conflicting original registration numbers or dates and whether the renewal records refer to the same edition.",
        "expect": "variants",
        "description": "Distinguish renewal ID RE277631 from its original-registration variants.",
    },
    "clarification": {
        "question": "Is my grandmother's old novel free to use?",
        "expect": "clarification",
        "description": "Should ask for title/author before researching.",
    },
    "patterns": {
        "question": "For U.S. books registered from 1931 to 1963, how did the share with matched renewals vary by year, and what are the main limitations of using these transcribed catalogs to estimate renewal rates?",
        "expect": "patterns",
        "description": "SQL-based aggregation with denominator, limitations and provenance.",
    },
}


def review(case_id, result):
    """Structural checks only; human must verify the semantics and legal conclusion."""
    calls = result.get("tool_calls") or []
    answer = result.get("response") or ""
    names = [str(c.get("name", "")) for c in calls]
    agent_names = [str(c.get("agent", "")) for c in calls]
    evidence_ids = {str(e.get("id")) for e in result.get("evidence", []) if isinstance(e, dict)}
    citations = set(re.findall(r"\[((?:REG|REN|SQL|RULE|OL|HT|PG|WD):[^\]\s,;]+)\]", answer))
    checks = {
        "no_server_error": not result.get("error") and not answer.startswith("The investigation failed:"),
        "has_response": bool(answer.strip()),
        "all_bracket_citations_in_evidence": citations.issubset(evidence_ids),
        "all_tool_calls_tagged_with_agent": all(bool(x) for x in agent_names),
    }
    expect = CASES[case_id]["expect"]
    if expect == "clarification":
        checks.update({
            "asked_for_clarification": bool(result.get("needs_clarification")),
            "no_research_launched": int(result.get("researchers") or 0) == 0,
        })
    else:
        checks.update({
            "not_clarification": not result.get("needs_clarification"),
            "researchers_launched": int(result.get("researchers") or 0) >= 2,
            "writer_and_citation_check": "check_citations" in names,
        })
    if expect in ("unresolved", "variants"):
        checks["ran_followup_round"] = int(result.get("rounds") or 0) >= 2
    if expect == "patterns":
        checks["used_sql_query"] = "query_records" in names
    return {
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
        "rounds": result.get("rounds"),
        "researchers": result.get("researchers"),
        "tool_calls": len(calls),
        "tools": names,
        "agents": sorted(set(agent_names)),
        "citations": sorted(citations),
        "manual_review_required": [
            "Confirm facts, citations, original registration and renewal keys against source rows",
            "Check response directly answers the user question and explains uncertainty",
            "Check whether follow-up investigation was justified, not simply longer",
            "Check digital availability assertions are source-scoped",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--case", choices=CASES.keys())
    target.add_argument("--all", action="store_true", help="Runs all five, may use substantial model tokens")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="evaluation/live")
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    ids = list(CASES) if args.all else [args.case]
    with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=20)) as client:
        for key in ids:
            print(f"\n=== {key}: {CASES[key]['description']} ===", flush=True)
            start = time.monotonic()
            try:
                res = client.post(args.url.rstrip("/") + "/chat", json={"message": CASES[key]["question"]})
                res.raise_for_status()
                data = res.json()
            except Exception as e:
                data = {"error": True, "response": f"HTTP/client error: {type(e).__name__}: {e}"}
            audit = review(key, data)
            record = {
                "case_id": key,
                "question": CASES[key]["question"],
                "description": CASES[key]["description"],
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic()-start, 2),
                "review": audit,
                "result": data,
            }
            (out / f"{key}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            lines = [f"# {key}", "", f"**Question:** {CASES[key]['question']}",
                     f"**Time:** {record['elapsed_seconds']} s | **Rounds:** {audit['rounds']} | **Researchers:** {audit['researchers']}",
                     "", "## Automatic structural checks", ""]
            for name, passed in audit["checks"].items():
                lines.append(f"- {'PASS' if passed else 'REVIEW'}: {name}")
            lines.extend(["", "## Final answer", "", data.get("response", ""), "", "## Manual review needed", ""])
            lines.extend(f"- {msg}" for msg in audit["manual_review_required"])
            lines.extend(["", "**Note:** A passing structural check is not legal verification or factual correctness."])
            (out / f"{key}.md").write_text("\n".join(lines), encoding="utf-8")
            print(f"Saved {out / (key+'.json')} and {out / (key+'.md')}")
            print(f"Structural checks: {audit['passed']}/{audit['total']}")
            print("Verdict excerpt:", data.get("response", "")[:210].replace("\n", " "))

if __name__ == "__main__":
    main()
