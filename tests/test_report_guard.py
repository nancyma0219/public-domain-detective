import unittest
from report_guard import verify_report_claims

class ReportGuardTests(unittest.TestCase):
    def test_none_found_is_too_broad(self):
        self.assertTrue(verify_report_claims('### Where to read it\n- None found.'))

    def test_universal_claim_rejected(self):
        self.assertTrue(verify_report_claims('- No free public domain copies are available online.'))

    def test_source_scoped_no_hit_passes(self):
        self.assertEqual([], verify_report_claims('- No matching copy found in Project Gutenberg in this search.'))

    def test_unverified_nonrenewal_rejected(self):
        self.assertTrue(verify_report_claims('- Copyright was never renewed.'))

    def test_search_no_hit_statement_is_allowed(self):
        self.assertEqual([], verify_report_claims('- No matching renewal found in the searched records.'))

    def test_public_domain_requires_rule(self):
        self.assertTrue(verify_report_claims('**Verdict:** Public domain in the U.S.', {}))

    def test_public_domain_with_rule_is_not_flagged_here(self):
        ledger={'RULE:test':{'record_type':'RULE','record':{'verdict':'public_domain'}}}
        self.assertEqual([], verify_report_claims('**Verdict:** Public domain in the U.S.', ledger))

if __name__ == '__main__':
    unittest.main()
