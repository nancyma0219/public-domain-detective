"""Synthetic integration test; runs without external APIs or real NYPL data."""
import sys
import tempfile
import unittest
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_agent_data import export


class TestBridge(unittest.TestCase):
    def test_export_no_row_multiplication_and_no_false_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / 'nypl.duckdb'
            out = root / 'out'
            con = duckdb.connect(str(db))
            con.execute('''CREATE TABLE registrations (
              entry_id VARCHAR, source_file VARCHAR, source_url VARCHAR,
              regnum VARCHAR, reg_date VARCHAR, catalog_year VARCHAR,
              author VARCHAR, title VARCHAR, publisher VARCHAR)''')
            con.execute("""INSERT INTO registrations VALUES
              ('r1','a.xml','https://example.org/a','A 10','1950-01-01','1950','One','Book One','Pub'),
              ('r2','b.xml','https://example.org/b','A 10','1950-01-01','1960','One','Book One','Pub'),
              ('r3','c.xml','https://example.org/c','A 20','1950-01-01','1950','Two','Title A','Pub'),
              ('r4','d.xml','https://example.org/d','A 20','1950-01-01','1950','Two','Title B','Pub'),
              ('r5','e.xml','https://example.org/e','A 30','1950-01-01','1950','Three','Book Three','Pub'),
              ('r6','f.xml','https://example.org/f','A 40','1950-01-01','1950','Four','No Renewal','Pub')""")
            con.execute('''CREATE TABLE renewals (
              entry_id VARCHAR, renewal_regnum VARCHAR, renewal_date VARCHAR,
              original_regnum VARCHAR, original_reg_date VARCHAR,
              author VARCHAR, title VARCHAR, claimants VARCHAR,
              new_matter VARCHAR, notes VARCHAR, source_file VARCHAR)''')
            con.execute("""INSERT INTO renewals VALUES
              ('n1','R10','1977-01-01','A10','1950-01-01','One','Book One','C',NULL,NULL,'r.tsv'),
              ('n2','R20','1977-01-01','A20','1950-01-01','Two','Title A','C',NULL,NULL,'r.tsv'),
              ('n3','R30','1977-01-01','A30','1950-01-01','Three','Book Three','C',NULL,NULL,'r.tsv'),
              ('n4','R31','1977-01-02','A30','1950-01-01','Three','Book Three','D',NULL,NULL,'r.tsv')""")
            con.close()
            export(db, out)
            check = duckdb.connect()
            rows = check.execute(f"SELECT entry_id, renewal_id, match_status FROM read_parquet('{out}/reg_status_*.parquet') ORDER BY entry_id").fetchall()
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0], ('r1', 'R10', 'exact_key_candidate'))
            self.assertEqual(rows[1], ('r2', 'R10', 'exact_key_candidate'))
            self.assertEqual(rows[2][2], 'registration_key_collision')
            self.assertIsNone(rows[2][1])
            self.assertEqual(rows[4][2], 'multiple_renewal_candidates')
            self.assertIsNone(rows[4][1])
            self.assertEqual(rows[5][2], 'no_exact_key_match')
            check.close()


if __name__ == '__main__':
    unittest.main()
