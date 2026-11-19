import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("live_eval", Path(__file__).resolve().parents[1] / "scripts" / "evaluate_live.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

class LiveEvalTests(unittest.TestCase):
    def test_clarification_without_research(self):
        x = m.review("clarification", {"response":"Which book and author?", "needs_clarification":True, "researchers":0, "tool_calls":[],"evidence":[]})
        self.assertTrue(all(x["checks"].values()))
    def test_unknown_citation_flagged(self):
        x = m.review("renewed", {"response":"**Verdict:** test [REN:FAKE]", "rounds":1,"researchers":3,"tool_calls":[{"agent":"CitationCheck","name":"check_citations"}],"evidence":[]})
        self.assertFalse(x["checks"]["all_bracket_citations_in_evidence"])
    def test_variant_followup_flagged(self):
        x = m.review("variants", {"response":"**Verdict:** undetermined", "rounds":1,"researchers":3,"tool_calls":[{"agent":"CitationCheck","name":"check_citations"}],"evidence":[]})
        self.assertFalse(x["checks"]["ran_followup_round"])
    def test_sql_requirement(self):
        x = m.review("patterns", {"response":"**Verdict:** test", "rounds":1,"researchers":3,"tool_calls":[{"agent":"Researcher 1","name":"query_records"},{"agent":"CitationCheck","name":"check_citations"}],"evidence":[]})
        self.assertTrue(x["checks"]["used_sql_query"])

if __name__ == "__main__": unittest.main()
