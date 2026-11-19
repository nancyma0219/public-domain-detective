"""Offline regression tests for duplicate renewal ID / different original registration keys."""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'scripts/audit_cases.py'
tree = ast.parse(SRC.read_text())
fns = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in
       {'candidate_key','renewal_id_conflicts','candidate_relationship'}]
ns = {}
exec(compile(ast.Module(body=fns, type_ignores=[]), str(SRC), 'exec'), ns)

class VariantTests(unittest.TestCase):
    def setUp(self):
        self.a = {'renewal_id':'RE277631','orig_regnum':'A352575',
                  'orig_regdate':'1958-08-22','source_file':'1986-from-db.tsv'}
        self.b = {'renewal_id':'RE277631','orig_regnum':'AI5926',
                  'orig_regdate':'1958-04-01','source_file':'1986-from-db.tsv'}
    def test_same_renewal_id_different_keys_are_distinct(self):
        self.assertNotEqual(ns['candidate_key'](self.a),ns['candidate_key'](self.b))
    def test_duplicate_search_hit_is_deduplicated(self):
        self.assertEqual(len({ns['candidate_key'](self.a), ns['candidate_key'](dict(self.a))}),1)
    def test_conflicting_original_keys_reported(self):
        self.assertEqual(len(ns['renewal_id_conflicts']([self.a,self.b])['RE277631']),2)
    def test_matching_one_original_does_not_match_other(self):
        self.assertTrue(ns['candidate_relationship'](self.a,'A352575','1958-08-22').startswith('same_'))
        self.assertEqual(ns['candidate_relationship'](self.b,'A352575','1958-08-22'),
                         'different_original_registration_number')
    def test_readme_case_has_actual_registration_key(self):
        self.assertIn("'A352575'",SRC.read_text())
    def test_view_defaults_to_answer_before_research(self):
        html=(SRC.parents[1]/'index.html').read_text()
        self.assertIn('#report { order: 2; }',html)
        self.assertIn('#board { display: none; order: 3; }',html)
        self.assertIn('Show research steps',html)

if __name__ == '__main__': unittest.main()
