import pathlib, unittest, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import cohort_research as c

class TestCohort(unittest.TestCase):
    def test_regex(self):
        self.assertIn("'^A[0-9]+$'",c.ANNUAL_SQL)
        self.assertNotIn('LIKE',c.ANNUAL_SQL)
    def test_detect(self):
        self.assertTrue(c.is_annual_book_query('How did renewal linkage change by year from 1931 to 1963?'))
        self.assertFalse(c.is_annual_book_query('Is Strangers on a Train public domain?'))
    def test_validate_complete(self):
        queries=[c.ANNUAL_SQL,c.PERIOD_SQL,c.COVERAGE_SQL]
        def fake(sql):
            i=queries.index(sql)
            rows=[ [y,10,10,2,20.] for y in range(1931,1964)] if i==0 else ([['1931–1952',220,220,44,20.],['1953–1963',110,110,22,20.]] if i==1 else [[y,10,1,10,2] for y in range(1951,1955)])
            return dict(eid='SQL:test'+str(i),sql=sql,columns=['year','registration_rows','distinct_keys','linked_rows','link_pct'],rows=rows,truncated=False)
        result=c.compute(fake)
        self.assertTrue(result['ok'])
        self.assertIn('### Annual results', c.markdown(result))
        self.assertIn('not evidence of a change', c.markdown(result))
    def test_reject_truncated(self):
        self.assertFalse(c.compute(lambda sql: {'truncated':True})['ok'])
    def test_ui(self):
        html=(pathlib.Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertIn('Start research',html)
        self.assertIn('drawVerifiedTrend',html)
        self.assertNotIn('Investigate book →',html)
        self.assertIn('rows="4"',html)

if __name__=='__main__': unittest.main()
