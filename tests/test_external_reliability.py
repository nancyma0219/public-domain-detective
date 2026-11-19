"""Offline regression checks for external API response semantics.
Run: uv run python -m unittest discover -s tests -p test_external_reliability.py -v
"""
import unittest
from unittest.mock import Mock
import httpx
import records


class ExternalReliabilityTests(unittest.TestCase):
    @staticmethod
    def fn(name, response=None, exception=None):
        def lookup(**kwargs):
            if exception is not None:
                raise exception
            return response
        lookup.__name__ = name
        return lookup

    def test_wikidata_403_is_unavailable_not_empty(self):
        request = httpx.Request('GET', 'https://www.wikidata.org/w/api.php')
        response = httpx.Response(403, request=request)
        fn = self.fn('wikidata_author', exception=httpx.HTTPStatusError('Forbidden', request=request, response=response))
        result = records.safe(fn, name='Patricia Highsmith')
        self.assertEqual(result['status'], 'source_unavailable')
        self.assertEqual(result['error']['http_status'], 403)
        self.assertEqual(result['source'], 'Wikidata')
        self.assertIn('not', result['coverage_note'].lower())

    def test_empty_result_is_not_api_failure(self):
        fn = self.fn('gutenberg_search', response={'source': 'Project Gutenberg catalog', 'results': []})
        result = records.safe(fn, title='Example')
        self.assertEqual(result['status'], 'no_results')
        self.assertIsNone(result['error'])

    def test_positive_openlibrary_keeps_evidence(self):
        hit = {'eid': 'OL:TEST1', 'title': 'Example'}
        fn = self.fn('openlibrary_search', response={'source': 'Open Library search API', 'results': [hit]})
        result = records.safe(fn, title='Example')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['results'][0]['eid'], 'OL:TEST1')

    def test_hathi_no_identifier_is_error_not_no_results(self):
        fn = self.fn('hathitrust_lookup', response={'error': 'Give an OCLC or LCCN number.'})
        result = records.safe(fn)
        self.assertEqual(result['status'], 'error')

    def test_local_database_response_remains_unchanged(self):
        original = {'results': [{'eid': 'REG:TEST'}], 'query': {'title': 'Example'}}
        fn = self.fn('search_registrations', response=original)
        self.assertEqual(records.safe(fn, title='Example'), original)

    def test_timeout_is_source_unavailable(self):
        fn = self.fn('openlibrary_search', exception=httpx.ReadTimeout('timed out'))
        self.assertEqual(records.safe(fn, title='Example')['status'], 'source_unavailable')


if __name__ == '__main__':
    unittest.main()
