"""Offline tests: the data tools, the rules, the citation check, and the whole Lead -> parallel
Researchers -> Writer pipeline driven by a scripted model (no Gemini calls, no network).

    uv run python tests/test_pipeline.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.items import ModelResponse  # noqa: E402
from agents.models.interface import Model  # noqa: E402
from agents.usage import Usage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText  # noqa: E402

import records  # noqa: E402
import research  # noqa: E402


# --- unit checks ---------------------------------------------------------------------------------

def test_records():
    r = records.search_registrations("Strangers on a train", "Patricia Highsmith")["results"][0]
    assert r["regnum"] == "A41904" and r["renewal_id"] == "R663598", r
    salt = records.search_registrations("The price of salt", "Highsmith")["results"][0]
    assert salt["regnum"] == "A68131" and salt["renewal_id"] is None
    assert records.search_renewals("The price of salt")["results"] == []
    assert records.query_records("DROP TABLE renewals").get("error")
    assert records.query_records("SELECT * FROM read_parquet('/etc/passwd')").get("error")
    rows = records.query_records("SELECT count(*) FROM reg_status")["rows"]
    assert rows[0][0] > 1_400_000


def test_rules():
    import datetime as dt
    today = dt.date(2026, 11, 18)
    assert records.us_status(1930, today=today)["verdict"] == "public_domain"
    s = records.us_status(1950, renewed=True, renewal_year=1977, today=today)
    assert s["verdict"] == "in_copyright" and s["public_domain_from"] == "2046-01-01"
    assert records.us_status(1952, renewed=False, today=today)["verdict"] == "undetermined"
    assert records.us_status(1952, renewed=None, today=today)["verdict"] == "undetermined"
    assert records.us_status(1955, published_in_us=False, renewed=False, today=today)["verdict"] == "likely_in_copyright"
    assert records.us_status(1970, today=today)["verdict"] == "in_copyright"


def test_citations():
    ledger = {"REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD": {}, "REN:R663598": {}}
    good = "**Verdict:** x\n### Evidence\n- Registered [REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD]\n- Renewed [REN:R663598]\n### What"
    assert research.check_citations(good, ledger) == []
    bad = "**Verdict:** x\n### Evidence\n- Registered [REG:A999@1950-01-01]\n- Uncited claim\n"
    problems = research.check_citations(bad, ledger)
    assert len(problems) == 2, problems
    assert "[REG:A999" not in research.strip_unknown(bad, ledger)


# --- a scripted model ----------------------------------------------------------------------------

def _msg(text):
    return ResponseOutputMessage(id="m", type="message", role="assistant", status="completed",
                                 content=[ResponseOutputText(type="output_text", text=text, annotations=[])])


def _call(name, args, n=[0]):
    n[0] += 1
    return ResponseFunctionToolCall(id=f"fc{n[0]}", call_id=f"call{n[0]}", type="function_call",
                                    name=name, arguments=json.dumps(args))


def _last_tool_outputs(items):
    return [i for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"]


class Scripted(Model):
    """Decides its reply from who it is (system prompt) and what it has seen so far."""

    def __init__(self):
        self.researcher_starts = []

    async def get_response(self, system_instructions, input, *args, **kwargs):
        items = input if isinstance(input, list) else [{"role": "user", "content": input}]
        outputs = _last_tool_outputs(items)
        first_user = next((i.get("content") for i in items if isinstance(i, dict) and i.get("role") == "user"), "")
        sys_text = system_instructions or ""

        if sys_text.startswith("You lead"):
            if "grandmother" in str(first_user):
                return self._r([_msg("CLARIFY: Which book do you mean — can you give its title and author?")])
            if not outputs:
                return self._r([_call("dispatch_researchers", {"tasks": [
                    "Records: find the registration and renewal of 'Strangers on a Train' by Patricia Highsmith, then call check_us_status.",
                    "Bibliography: Open Library and Wikidata for 'Strangers on a Train' / Patricia Highsmith.",
                    "Access: HathiTrust and Gutenberg for 'Strangers on a Train'."]})])
            if len(outputs) == 1:  # one gap-filling round, then the cap must refuse a third
                return self._r([_call("dispatch_researchers", {"tasks": ["Records: search renewals for 'Strangers on a train' by claimant Highsmith."]})])
            if len(outputs) == 2:
                return self._r([_call("dispatch_researchers", {"tasks": ["one more"]})])
            assert "Round cap reached" in outputs[-1]["output"], outputs[-1]
            return self._r([_msg("BRIEF: Registered A41904 [REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD], renewed R663598 [REN:R663598]; "
                                 "in copyright until 2045 [RULE:1950-us-True].")])

        if sys_text.startswith("You are a copyright-records researcher"):
            if not outputs:
                self.researcher_starts.append(time.monotonic())
                await asyncio.sleep(0.3)  # lets us see whether researchers overlap
                if "Records" in first_user:
                    return self._r([_call("search_registrations", {"title": "Strangers on a train", "author": "Highsmith"}),
                                    _call("search_renewals", {"title": "Strangers on a train", "author": "Highsmith"})])
                return self._r([_call("search_registrations", {"title": "Strangers on a train"})])
            if "Records" in first_user and len(outputs) == 2:
                return self._r([_call("check_us_status", {"pub_year": 1950, "published_in_us": True, "renewed": True,
                                                          "renewal_year": 1977})])
            return self._r([_msg("Registered as A41904 [REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD]; renewed [REN:R663598].\nGaps: none")])

        if sys_text.startswith("You write the final case report"):
            if "Fix these problems" not in str(first_user):
                return self._r([_msg("**Verdict:** In copyright in the U.S. until the end of 2045\n**Confidence:** high\n"
                                     "### Evidence\n- Harper registered it [REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD]\n- An uncited line\n"
                                     "- Bogus [REG:FAKE@1900-01-01]\n### What these records can't tell us\n- n/a")])
            return self._r([_msg("**Verdict:** In copyright in the U.S. until the end of 2045\n**Confidence:** high\n"
                                 "### Evidence\n- Harper registered it on 15 Mar 1950 [REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD]\n"
                                 "- Highsmith renewed it on 6 Jun 1977 [REN:R663598]\n"
                                 "- Renewed works last 95 years [RULE:1950-us-True]\n"
                                 "### What these records can't tell us\n- Later editions' new matter.")])
        raise AssertionError("unknown agent: " + sys_text[:60])

    @staticmethod
    def _r(output):
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *a, **k):
        raise NotImplementedError


def test_pipeline():
    model = Scripted()
    for agent in (research.lead, research.researcher, research.writer):
        agent.model = model
    research.Agent  # noqa: B018

    from app import app  # import after patching models
    client = TestClient(app)

    # 1) vague question -> clarification, nothing else runs
    r = client.post("/chat", json={"message": "Is my grandmother's old novel free to use?"}).json()
    assert r["needs_clarification"] and r["tool_calls"] == [] and "title" in r["response"], r

    # 2) a full investigation
    r = client.post("/chat", json={"message": "Is Strangers on a Train by Patricia Highsmith public domain?"}).json()
    agents_seen = {c["agent"] for c in r["tool_calls"]}
    assert {"Lead", "Researcher 1", "Researcher 2", "Researcher 3", "Researcher 4", "CitationCheck"} <= agents_seen, agents_seen
    assert r["rounds"] == 2 and r["researchers"] == 4, (r["rounds"], r["researchers"])
    starts = sorted(model.researcher_starts[:3])
    assert starts[-1] - starts[0] < 0.25, f"round-1 researchers did not start in parallel: {starts}"
    checks = [c for c in r["tool_calls"] if c["agent"] == "CitationCheck"]
    assert checks[0]["output"] != "PASS" and checks[1]["output"] == "PASS", checks
    assert "[REG:FAKE" not in r["response"] and "### Sources" in r["response"]
    assert all({"agent", "name", "arguments", "output"} <= set(c) for c in r["tool_calls"])
    ids = {e["id"] for e in r["evidence"]}
    assert {"REG:404B12DE-79DE-1014-B198-F9D02DA5A3BD", "REN:R663598", "RULE:1950-us-True"} <= ids, ids
    print(r["response"])

    # 3) the SSE stream emits activity and a done event, and the context panel has every agent
    with client.stream("GET", "/stream", params={"message": "Is Strangers on a Train by Patricia Highsmith public domain?"}) as s:
        events = [json.loads(line[6:]) for line in s.iter_lines() if line.startswith("data: ")]
    kinds = {e["type"] for e in events}
    assert {"start", "activity", "round", "context", "done"} <= kinds, kinds
    run_id = events[0]["run_id"]
    panel = client.get("/context", params={"session_id": run_id}).json()["events"]
    assert {"Lead", "Writer"} <= {e["agent"] for e in panel}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
