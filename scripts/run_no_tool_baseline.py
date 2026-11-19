"""Evaluate the same Gemini Lead/Writer model without tools or system prompt.

Run from project root: uv run python scripts/run_no_tool_baseline.py
Uses configured Vertex AI ADC and records raw baseline responses. No agent tools.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from litellm import acompletion

MODEL = "vertex_ai/gemini-3.5-flash"  # match production LEAD_MODEL and WRITER_MODEL
QUESTIONS = [
    ("book", "Is Strangers on a Train by Patricia Highsmith (1950) in the public domain in the United States?"),
    ("records", "Why does Isaac Asimov's The World of Carbon have different original registration numbers associated with renewal RE277631? What is verified and unresolved?"),
    ("trends", "For U.S. Class A books registered from 1931 to 1963, how did the candidate renewal-linkage share change by year? Investigate the break near 1953."),
]

async def run_one(key: str, prompt: str):
    result = await acompletion(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        vertex_location="global",
        temperature=0,
        timeout=120,
        num_retries=2,
    )
    answer = result.choices[0].message.content
    return {"case": key, "question": prompt, "answer": answer, "model": MODEL}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evaluation/baseline")
    args = parser.parse_args()
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    results = []
    for key, question in QUESTIONS:
        print(f"Baseline: {key} ...", flush=True)
        try:
            results.append(await run_one(key, question))
        except Exception as exc:
            # Do not invent a baseline if Vertex AI auth, quota, or model availability fails.
            results.append({"case": key, "question": question, "model": MODEL,
                            "answer": None, "error": f"{type(exc).__name__}: {exc}"})
    payload = {"model": MODEL, "method": "single user message; no system prompt; no tools",
               "generated_utc": datetime.now(timezone.utc).isoformat(), "results": results}
    (target / "no_tool_answers.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# No-tool baseline: same Gemini model", "", f"Model: `{MODEL}`. Each run received only the question as a user message; no system prompt, tools or data files.", ""]
    for result in results:
        lines += [f"## {result['case']}", "", f"**Question:** {result['question']}", "",
                  "**Baseline response (unedited):**", "",
                  result.get("answer") or f"NOT MEASURED: {result.get('error', 'empty response')}", ""]
    (target / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {target / 'no_tool_answers.json'} and {target / 'comparison.md'}")
    failures = [r for r in results if not r.get("answer")]
    if failures:
        raise SystemExit(f"{len(failures)} baseline run(s) failed; see recorded errors (do not fill in fictitious answers)")

if __name__ == "__main__":
    asyncio.run(main())
