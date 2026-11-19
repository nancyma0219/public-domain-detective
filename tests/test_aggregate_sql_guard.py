import json
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gap_review import review_round
from quality_guard import check_research_claims

BAD = "SELECT reg_year, COUNT(*) FROM reg_status WHERE reg_year BETWEEN 1931 AND 1963 GROUP BY reg_year"
GOOD = "SELECT reg_year, COUNT(*), SUM(CASE WHEN renewal_id IS NOT NULL THEN 1 ELSE 0 END) FROM reg_status WHERE reg_year BETWEEN 1931 AND 1963 AND regexp_matches(regnum, '^A[0-9]') GROUP BY reg_year"
DIAG = "SELECT source_file, COUNT(DISTINCT regnum), COUNT(*) FROM reg_status GROUP BY source_file"
Q = 'For U.S. books registered 1931–1963, what share had matched renewals by year?'
def call(sql):
    return {'name':'query_records','arguments':{'sql':sql},'output':json.dumps({'eid':'SQL:test','sql':sql,'columns':['x'],'rows':[[1]],'truncated':False})}
class AggregateGuardTests(unittest.TestCase):
    def test_reject_unfiltered_annual_sql_even_if_report_has_no_class_a_words(self):
        issues=check_research_claims('### Research findings\nThe rate was 16.11%.', [call(BAD)], Q)
        self.assertTrue(any('exact Class A' in x for x in issues))
    def test_gap_review_detects_missing_scope(self):
        result=review_round([call(BAD)],round_no=1,max_rounds=2,mode='aggregate')
        self.assertIn('class_a_scope_missing',[x['code'] for x in result['issues']])
        self.assertNotIn('records_not_checked',[x['code'] for x in result['issues']])
    def test_good_cohort_and_diagnostic_no_method_gap(self):
        result=review_round([call(GOOD),call(DIAG),call('SELECT COUNT(*) FROM renewals')],round_no=1,max_rounds=2,mode='aggregate')
        codes=[x['code'] for x in result['issues']]
        self.assertNotIn('class_a_scope_missing',codes)
        self.assertNotIn('method_validation_missing',codes)
        self.assertNotIn('thin_aggregate_research',codes)
    def test_report_mislabels_renewal_rate(self):
        issues=check_research_claims('### Research findings\nThe renewal rate was 16%.', [call(GOOD)], Q)
        self.assertTrue(any('candidate linkage rate' in x for x in issues))
    def test_actual_uploaded_live_case_detected(self):
        path=Path('/mnt/data/patterns(1).json')
        if not path.exists(): self.skipTest('Live response not mounted')
        data=json.loads(path.read_text())
        issues=check_research_claims(data['result']['response'],data['result']['tool_calls'],data['question'])
        self.assertTrue(any('exact Class A' in x for x in issues))
        self.assertTrue(any('candidate linkage rate' in x for x in issues))
if __name__=='__main__': unittest.main()
