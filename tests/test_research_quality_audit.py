import unittest
from audit_research_quality import audit

class ResearchQualityAuditTests(unittest.TestCase):
    def test_clarification_good(self):
        self.assertFalse(audit({'case_id':'clarification','result':{'needs_clarification':True,'rounds':0,'tool_calls':[]}}))
    def test_unqueried_source(self):
        r={'case_id':'renewed','result':{'response':'**HathiTrust:** No matching copy found in HathiTrust in this search.','tool_calls':[]}}
        self.assertIn('unqueried_source',[x['code'] for x in audit(r)])
    def test_wrong_class_scope(self):
        r={'case_id':'patterns','result':{'response':'Class A renewal rate','tool_calls':[{'name':'query_records','arguments':{'sql':"SELECT COUNT(*) FROM reg_status WHERE regnum LIKE 'A%'"}}]}}
        self.assertIn('class_prefix_scope',[x['code'] for x in audit(r)])
    def test_invalid_year_claim(self):
        r={'case_id':'patterns','result':{'response':'824,646 out-of-range registration years are corrupted','tool_calls':[]}}
        self.assertIn('year_scope',[x['code'] for x in audit(r)])
    def test_variants_overclaim(self):
        r={'case_id':'variants','result':{'response':'All dates fully reconciled.','tool_calls':[]}}
        self.assertIn('overclaimed_conflict_resolution',[x['code'] for x in audit(r)])

if __name__=='__main__': unittest.main()
