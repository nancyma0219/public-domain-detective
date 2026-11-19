"""Offline author lookup tests; no network, DuckDB, Gemini or Google credentials required."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'records.py').read_text()
TREE = ast.parse(SOURCE)
FUNCTION = next(x for x in TREE.body if isinstance(x, ast.FunctionDef) and x.name == 'openlibrary_author')
MOCK_SOURCE = ast.Module(body=[FUNCTION], type_ignores=[])

# Pure-function isolation, instead of requiring full production DB dependencies in this test.
import re
import unicodedata

def norm(v):
    s = unicodedata.normalize('NFKD', v or '').casefold()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

namespace = {'norm': norm, 're': re}
exec(compile(MOCK_SOURCE, str(ROOT / 'records.py'), 'exec'), namespace)
lookup = namespace['openlibrary_author']

class AuthorLookupTests(unittest.TestCase):
    def test_two_namesake_records_remain_distinct_and_rank_completeness(self):
        payload = {'docs': [
            {'key':'OL16705475A','name':'Patricia Highsmith'},
            {'key':'OL28577A','name':'Patricia Highsmith','birth_date':'19 Jan 1921',
             'death_date':'4 Feb 1995','alternate_names':['Claire Morgan']},
        ]}
        with patch.dict(namespace, {'_get_json': lambda url, params: payload}):
            result=lookup('Patricia Highsmith')
        self.assertEqual(len(result['results']),2)
        self.assertEqual(result['results'][0]['eid'],'OL:AUTHOR:OL28577A')
        self.assertEqual(result['results'][0]['died'],'4 Feb 1995')
        self.assertEqual(result['results'][1]['died'],None)
        self.assertIn('Do not merge',result['note'])

    def test_empty_lookup_is_not_an_error(self):
        with patch.dict(namespace, {'_get_json':lambda url, params: {'docs':[]}}):
            self.assertEqual(lookup('Nonsuch')['results'],[])

    def test_author_ids_are_safe_and_citable(self):
        payload={'docs':[{'key':'OL28577A','name':'Patricia Highsmith'},
                         {'key':'/authors/OL123A','name':'Someone'},
                         {'key':'../../bad','name':'bad'}]}
        with patch.dict(namespace, {'_get_json':lambda url, params: payload}):
            output=lookup('Patricia Highsmith')['results']
        self.assertEqual(len(output),2)
        self.assertTrue(all(item['eid'].startswith('OL:AUTHOR:OL') for item in output))
        self.assertTrue(all(item['url'].startswith('https://openlibrary.org/authors/OL') for item in output))

    def test_api_arguments_are_bounded(self):
        calls=[]
        def get(url, params):
            calls.append((url,params))
            return {'docs':[]}
        with patch.dict(namespace, {'_get_json':get}):
            lookup('Claire Morgan',limit=100)
        self.assertEqual(calls[0][1]['limit'],10)
        self.assertTrue(calls[0][0].endswith('/search/authors.json'))

if __name__ == '__main__': unittest.main()
