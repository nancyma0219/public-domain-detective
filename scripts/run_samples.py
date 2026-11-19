"""Run the README's three sample queries twice: through the agent, and through the same model with
no tools and no system prompt. Writes samples.md, ready to paste into the README.

    gcloud auth application-default login
    uv run scripts/run_samples.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import litellm  # noqa: E402
from agents import set_tracing_disabled  # noqa: E402

from research import LEAD_MODEL, investigate  # noqa: E402

set_tracing_disabled(True)

SAMPLES = [
    "Is Strangers on a Train by Patricia Highsmith in the public domain in the U.S.?",
    "Is The Price of Salt by Patricia Highsmith (published as Claire Morgan, 1952) in the public domain in the U.S.? Can I find a free copy?",
    "For U.S. books registered between 1931 and 1963, how did the share that was renewed change by year, and how much should I trust those numbers?",
]


def baseline(question: str) -> str:
    """The same model the Lead and Writer use: no tools, no system prompt."""
    r = litellm.completion(model=LEAD_MODEL.model, messages=[{"role": "user", "content": question}],
                           vertex_location="global", timeout=120)
    return r.choices[0].message.content


async def main():
    out = ["# Sample queries: agent vs. the same model with no tools\n"]
    for i, q in enumerate(SAMPLES, 1):
        print(f"[{i}] {q}", flush=True)
        base = await asyncio.to_thread(baseline, q)
        result = await investigate(q, [])
        trace = ROOT / f"samples_trace_{i}.json"
        trace.write_text(json.dumps(result["tool_calls"], indent=2, default=str))
        out += [f"## {i}. {q}\n",
                "<table><tr><th>No tools, no system prompt</th><th>Public Domain Detective</th></tr><tr><td>\n",
                base.strip(), "\n</td><td>\n", result["response"].strip(), "\n</td></tr></table>\n",
                f"_{result['rounds']} round(s), {result['researchers']} researchers, {len(result['tool_calls'])} tool calls "
                f"(trace: `{trace.name}`)_\n"]
    (ROOT / "samples.md").write_text("\n".join(out))
    print("wrote samples.md")


if __name__ == "__main__":
    asyncio.run(main())
