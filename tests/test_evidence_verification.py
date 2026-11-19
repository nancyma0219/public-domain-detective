import unittest
from unittest.mock import patch
import evidence_verification as ev

class FakeDB:
    def __init__(self, registration=None, renewals=None):
        self.registration = registration or []
        self.renewals = renewals or []
        self.calls = []
    def execute(self, sql, params):
        self.calls.append((sql, params))
        self.last = self.registration if 'FROM reg_status' in sql else self.renewals
        return self
    def fetchall(self):
        return self.last

REG = ('test-entry', 'A41904', '1950-03-15', 'Strangers on a train.',
       'Highsmith, Patricia', '1950.xml', 'https://example.org/original', 'exact_key_candidate')
REN = ('renewal-row-1', 'R663598', '1977-06-06', 'A41904', '1950-03-15',
       'Strangers on a train.', 'Highsmith', 'Highsmith', '1977.tsv', None)

class EvidenceLinkTests(unittest.TestCase):
    def test_one_candidate_has_record_provenance(self):
        db = FakeDB([REG], [REN])
        with patch.object(ev.records, 'db', return_value=db):
            out = ev.verify_record_link('test-entry')
        self.assertEqual(out['status'], 'exact_key_candidate')
        self.assertEqual(out['registration']['eid'], 'REG:test-entry')
        self.assertEqual(out['candidates'][0]['eid'], 'REN:R663598')
        self.assertEqual(out['candidates'][0]['entry_id'], 'renewal-row-1')
        self.assertEqual(db.calls[1][1][:2], ['A41904','1950-03-15'])
    def test_missing_match_is_not_public_domain(self):
        with patch.object(ev.records, 'db', return_value=FakeDB([REG], [])):
            out = ev.verify_record_link('test-entry')
        self.assertEqual(out['status'], 'no_exact_key_match')
        self.assertNotIn('public_domain', out)
    def test_collision_is_never_silently_accepted(self):
        bad = REG[:-1] + ('registration_key_collision',)
        with patch.object(ev.records, 'db', return_value=FakeDB([bad], [REN])):
            out = ev.verify_record_link('test-entry')
        self.assertEqual(out['status'], 'registration_key_collision')
    def test_entry_id_reuse_is_ambiguous(self):
        with patch.object(ev.records, 'db', return_value=FakeDB([REG,REG])):
            out = ev.verify_record_link('test-entry')
        self.assertEqual(out['status'], 'ambiguous_registration_id')
    def test_multiple_renewals_stay_separate(self):
        other = ('renewal-row-2', 'R888', '1977-06-07','A41904','1950-03-15',
                 'Strangers', 'Highsmith', 'Highsmith', '1977.tsv',None)
        with patch.object(ev.records, 'db', return_value=FakeDB([REG], [REN,other])):
            out = ev.verify_record_link('test-entry')
        self.assertEqual(out['status'], 'multiple_renewal_candidates')
        self.assertEqual(len(out['candidates']),2)
        self.assertEqual([r['eid'] for r in out['candidates']], ['REN:R663598', 'REN:R888'])

if __name__ == '__main__': unittest.main()
