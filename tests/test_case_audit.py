"""Small offline unit tests for audit classification, no credentials or DuckDB needed."""
import ast
import unittest
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'scripts' / 'audit_cases.py'
fn = next(n for n in ast.parse(p.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'candidate_relationship')
namespace = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), str(p), 'exec'), namespace)
classify = namespace['candidate_relationship']

class AuditTests(unittest.TestCase):
    def test_exact_key_is_only_candidate(self):
        self.assertEqual(classify({'orig_regnum':'A68131','orig_regdate':'1952-04-15'},'A68131','1952-04-15'),
                         'same_registration_number_and_date_candidate_needs_edition_review')
    def test_date_mismatch(self):
        self.assertEqual(classify({'orig_regnum':'AI5926','orig_regdate':'1958-04-01'},'AI5926','1953-04-01'),
                         'same_registration_number_date_missing_or_different')
    def test_different_number(self):
        self.assertEqual(classify({'orig_regnum':'A111'},'A68131','1952-04-15'),
                         'different_original_registration_number')
    def test_no_number(self):
        self.assertEqual(classify({'orig_regnum':None},'A68131','1952-04-15'),
                         'original_registration_number_not_transcribed')

if __name__ == '__main__': unittest.main()
