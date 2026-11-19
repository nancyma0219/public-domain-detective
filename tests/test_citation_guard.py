import unittest
from citation_guard import verify_citation_facts

REG = {"record_type":"REG", "record":{"regnum":"A41904", "regdate":"1950-03-15", "title":"Strangers on a train"}}
REN = {"record_type":"REN", "record":{"renewal_id":"R663598", "renewal_date":"1977-06-06", "original_regnum":"A41904", "original_regdate":"1950-03-15"}}
RULE_UNKNOWN = {"record_type":"RULE", "record":{"verdict":"undetermined"}}

class CitationGuardTests(unittest.TestCase):
    def test_supported_registration(self):
        self.assertEqual(verify_citation_facts('### Evidence\n- Registration A41904 on 1950-03-15 [REG:one]', {'REG:one':REG}), [])
    def test_wrong_registration_number(self):
        self.assertTrue(verify_citation_facts('### Evidence\n- Registration A99999 [REG:one]', {'REG:one':REG}))
    def test_wrong_date(self):
        self.assertTrue(verify_citation_facts('### Evidence\n- Registration on 1950-04-15 [REG:one]', {'REG:one':REG}))
    def test_linked_renewal(self):
        text='### Evidence\n- A41904 renewed as R663598 on 1977-06-06 [REG:one] [REN:two]'
        self.assertEqual(verify_citation_facts(text, {'REG:one':REG, 'REN:two':REN}), [])
    def test_conflicting_renewal_key(self):
        changed={**REN,'record':{**REN['record'], 'original_regnum':'A88888'}}
        text='### Evidence\n- Renewal R663598 [REG:one] [REN:two]'
        self.assertTrue(verify_citation_facts(text, {'REG:one':REG,'REN:two':changed}))
    def test_uncertain_rule_blocks_public_domain(self):
        text='**Verdict:** Probably public domain — no renewal found\n### Evidence\n- No hit [RULE:unknown]'
        self.assertTrue(verify_citation_facts(text, {'RULE:unknown': RULE_UNKNOWN}))
    def test_rule_allows_public_domain_verdict(self):
        text='**Verdict:** Public domain in the U.S.\n### Evidence\n- Rule [RULE:valid]'
        self.assertEqual(verify_citation_facts(text, {'RULE:valid': {'record_type':'RULE', 'record':{'verdict':'public_domain'}}}), [])

if __name__ == '__main__': unittest.main()
