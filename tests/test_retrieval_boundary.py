"""Run: python -m unittest discover -s tests -p 'test_retrieval_boundary.py' -v"""
import unittest
from unittest.mock import patch
import records


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.rows


def regrow(index, title):
    return (f"A{index}", "1950-01-01", "Patricia Highsmith", title, None, None,
            f"source{index}.xml", f"id-{index}", None, None, None, "no_exact_key_match")


def renrow(index, title):
    return (f"R{index}", "1977-01-01", f"A{index}", "1950-01-01", "Patricia Highsmith", title,
            None, None, None, f"source{index}.tsv")


class RetrievalBoundaryTests(unittest.TestCase):
    def test_registration_sql_prioritizes_exact_title_before_limit(self):
        db = FakeDB([regrow(1, "Strangers on a train.")])
        with patch.object(records, "db", return_value=db):
            result = records.search_registrations("Strangers on a Train", "Patricia Highsmith")
        self.assertIn("ORDER BY CASE WHEN title_norm = ?", db.sql)
        self.assertEqual(db.params[-2:], ["strangers on a train", 5001])
        self.assertFalse(result["scan_truncated"])
        self.assertEqual(result["results"][0]["regnum"], "A1")

    def test_registration_truncation_is_explicit(self):
        db = FakeDB([regrow(i, "A long book title") for i in range(5001)])
        with patch.object(records, "db", return_value=db):
            result = records.search_registrations("A long book title")
        self.assertTrue(result["scan_truncated"])
        self.assertEqual(result["candidates_scanned"], 5000)
        self.assertIn("more may exist", result["retrieval_note"])

    def test_renewal_sql_prioritizes_title_and_warns_about_truncation(self):
        db = FakeDB([renrow(i, "A long book title") for i in range(5001)])
        with patch.object(records, "db", return_value=db):
            result = records.search_renewals("A long book title")
        self.assertIn("ORDER BY CASE WHEN title_norm = ?", db.sql)
        self.assertEqual(db.params[-2:], ["a long book title", 5001])
        self.assertTrue(result["scan_truncated"])
        self.assertEqual(result["candidates_scanned"], 5000)

    def test_rule_remains_conservative(self):
        self.assertEqual(records.us_status(1952, renewed=False)["verdict"], "undetermined")


if __name__ == "__main__":
    unittest.main()
