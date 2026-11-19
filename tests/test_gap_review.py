import json
import unittest

from gap_review import review_round


def call(name, body, agent='Researcher 1'):
    return {'name': name, 'agent': agent, 'arguments': {}, 'output': json.dumps(body)}


class GapReviewTests(unittest.TestCase):
    def test_confirmed_renewal_does_not_trigger_unresolved_gap(self):
        calls = [call('search_registrations', {'results': [{'match_status': 'exact_key_candidate', 'renewal_id': 'R663598'}]}),
                 call('search_renewals', {'results': [{'renewal_id': 'R663598'}]})]
        r = review_round(calls, round_no=1, max_rounds=2)
        self.assertEqual(r['actionable_issue_count'], 0)

    def test_missing_renewal_yields_followup(self):
        calls = [call('search_registrations', {'results': [{'match_status': 'no_exact_key_match', 'renewal_id': None}]}),
                 call('search_renewals', {'results': [], 'status': 'no_results'})]
        r = review_round(calls, round_no=1, max_rounds=2)
        codes = {p['code'] for p in r['issues']}
        self.assertIn('renewal_unresolved', codes)
        self.assertNotIn('renewal_search_not_attempted', codes)
        self.assertTrue(r['additional_round_permitted'])

    def test_api_failure_is_not_no_results(self):
        calls = [call('search_registrations', {'results': [{'match_status': 'exact_key_candidate', 'renewal_id': 'R1'}]}),
                 call('wikidata_author', {'status': 'source_unavailable', 'error': {'http_status': 403}})]
        r = review_round(calls, round_no=1, max_rounds=2)
        self.assertIn('external_source_failed', {x['code'] for x in r['issues']})
        self.assertNotIn('renewal_unresolved', {x['code'] for x in r['issues']})

    def test_conflicting_key_and_truncation(self):
        calls = [call('search_registrations', {'scan_truncated': True, 'results': [{'match_status': 'registration_key_collision'}]})]
        r = review_round(calls, round_no=2, max_rounds=2)
        self.assertIn('registration_conflict', {x['code'] for x in r['issues']})
        self.assertIn('truncated_search', {x['code'] for x in r['issues']})
        self.assertFalse(r['additional_round_permitted'])

    def test_invalid_json_cannot_be_treated_as_absence(self):
        r = review_round([{'name': 'search_registrations', 'output': '{truncated'}], round_no=1, max_rounds=2)
        self.assertIn('uninspectable_tool_output', {x['code'] for x in r['issues']})


if __name__ == '__main__':
    unittest.main()
