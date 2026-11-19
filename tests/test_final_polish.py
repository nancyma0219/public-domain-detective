import pathlib
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
HTML=(ROOT/'index.html').read_text()
RESEARCH=(ROOT/'research.py').read_text()

class FinalPolishTests(unittest.TestCase):
    def test_intent_uses_user_question(self):
        self.assertIn('intentFor(activeQuestion, r.response',HTML)
        self.assertIn('activeQuestion = message;',HTML)
        self.assertNotIn('stampFor(r.response, r.needs_clarification);',HTML)
    def test_comparison_distinguishes_two_outcomes(self):
        self.assertIn('Record reconciliation',HTML)
        self.assertIn('U.S. copyright status (separate finding)',HTML)
        self.assertIn('Record assessment:',RESEARCH)
        self.assertIn('discrepancies remain unresolved',RESEARCH)
    def test_chart_before_annual_table(self):
        self.assertIn('annual.parentNode.insertBefore(figure,annual)',HTML)
        self.assertIn('collapseAnnualTable()',HTML)
        self.assertIn('View all annual data',HTML)
    def test_traces_still_available(self):
        self.assertIn('Technical evidence log (tool calls)',HTML)
        self.assertIn('r.tool_calls',HTML)
        self.assertIn('Show research steps',HTML)
    def test_javascript_parses(self):
        js=HTML.split('<script>')[1].split('</script>')[0]
        program='new Function('+repr(js)+');'
        result=subprocess.run(['node','-e',program],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_question_aware_stamps(self):
        js=HTML.split('<script>')[1].split('</script>')[0]
        code=js[js.index('function intentFor('):js.index('function drawVerifiedTrend(')]
        tests='''
if(intentFor("Why does The World of Carbon have different original registration numbers?","**Verdict:** In copyright",false)!=="records") throw Error('compare failed');
if(intentFor("For books 1931 to 1963, how did the trend change?","### Research findings",false)!=="trends") throw Error('trend failed');
if(intentFor("Is Strangers on a Train public domain?","**Verdict:** In copyright",false)!=="book") throw Error('book failed');
if(stampFor("**Verdict:** In copyright",false,"records")[1]==="In copyright") throw Error('wrong compare stamp');
if(stampFor("### Research findings",false,"trends")[1]!=="Research findings") throw Error('wrong trend stamp');
if(stampFor("**Verdict:** In copyright",false,"book")[1]!=="In copyright") throw Error('wrong book stamp');
'''
        result=subprocess.run(['node','-e',code+tests],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
