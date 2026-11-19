import json
import unittest
from quality_guard import question_mode, check_research_claims
from gap_review import review_round

class QualityGuardTests(unittest.TestCase):
    def test_aggregate_mode(self):
        self.assertEqual(question_mode('How did matched renewals vary by year 1931–1963?'), 'aggregate')
        self.assertEqual(question_mode('Is Strangers on a Train public domain?'), 'book')
    def test_sql_gap_not_falsely_flagged(self):
        calls=[{'name':'query_records','output':json.dumps({'eid':'SQL:x','columns':['n'],'rows':[[3]]})}]
        review=review_round(calls,round_no=1,max_rounds=2,mode='aggregate')
        self.assertFalse(any(x['code']=='records_not_checked' for x in review['issues']))
        review2=review_round(calls,round_no=1,max_rounds=2)
        self.assertTrue(any(x['code']=='records_not_checked' for x in review2['issues']))
    def test_unqueried_source(self):
        report='### Digitized copies and access\n- **HathiTrust:** No matching copy found in HathiTrust in this search.'
        self.assertTrue(any('never called' in x for x in check_research_claims(report,[], 'Is this book public domain?')))
        calls=[{'name':'hathitrust_lookup','output':json.dumps({'status':'no_results','items':[]})}]
        self.assertFalse(check_research_claims(report,calls,'Is this book public domain?'))
    def test_aggregate_invalid_metrics(self):
        report='**Verdict:** Undetermined\n811,084 registrations with duplicate numbers. The renewal rate was 18%.\n### Digitized copies and access'
        calls=[{'name':'query_records','arguments':{'sql':"SELECT count(*) FROM reg_status WHERE regnum LIKE 'A%'"},'output':'{}'}]
        flags=' '.join(check_research_claims(report,calls,'Share by year 1931–1963'))
        self.assertIn('GROUPS', flags)
        self.assertIn('renewal rate', flags)
        self.assertIn('aggregate', flags.lower())
    def test_key_conflict_overclaim(self):
        report='The AI5926 date is a clerical transcription error, and all conflicts have been fully reconciled.'
        flags=check_research_claims(report,[], 'Investigate The World of Carbon')
        self.assertGreaterEqual(len(flags),2)
    def test_negative_renewal_requires_search_evidence(self):
        report='- No matching renewal was found [RULE:1952-us-False].'
        self.assertTrue(any('RULE citation' in x for x in check_research_claims(report,[],'Is The Price of Salt public domain?')))

if __name__=='__main__': unittest.main()
