"""Run: python -m unittest discover -s tests -p 'test_search_ranking.py' -v"""
import unittest
from unittest.mock import patch
import records


class MockRows:
    def execute(self, sql, params):
        self.params = params
        return self

    def fetchall(self):
        # Same columns as search_registrations SELECT.
        return [
            ("AFO6913", "1951-11-30", "Patricia Highsmith", "L'inconnu du nord-express (Strangers on a train) roman; traduit de l'américain par Jean Rosenthal.", None, None, "foreign.xml", "foreign-id", "RE30907", "1979-01-01", None, "exact_key_candidate"),
            ("A41904", "1950-03-15", "Patricia Highsmith", "Strangers on a train.", None, None, "original.xml", "original-id", "R663598", "1977-06-06", None, "exact_key_candidate"),
        ]


class SearchRankingTests(unittest.TestCase):
    def test_exact_title_outranks_translation(self):
        with patch.object(records, 'db', return_value=MockRows()):
            hits = records.search_registrations("Strangers on a Train", "Patricia Highsmith")["results"]
        self.assertEqual(hits[0]["regnum"], "A41904")
        self.assertEqual(hits[1]["regnum"], "AFO6913")
        self.assertEqual(hits[0]["eid"], "REG:original-id")

    def test_no_renewal_does_not_mean_public_domain(self):
        self.assertEqual(records.us_status(1952, renewed=False)["verdict"], "undetermined")

    def test_exact_title_scores_above_embedded_title(self):
        exact = records._score("Strangers on a Train", "Patricia Highsmith", "Strangers on a train.", "Patricia Highsmith")
        translated = records._score("Strangers on a Train", "Patricia Highsmith", "L'inconnu (Strangers on a Train)", "Patricia Highsmith")
        self.assertGreater(exact, translated)


if __name__ == '__main__':
    unittest.main()
