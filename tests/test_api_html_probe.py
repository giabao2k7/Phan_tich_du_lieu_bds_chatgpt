import json
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts.probe_api_html import select_samples
from src.api_html_probe import identify_html, inspect_sample
from src.config import ROOT
from src.crawler import CrawlStopped


class ApiHtmlProbeTest(unittest.TestCase):
    def test_real_saved_html_identity_type_and_known_id(self):
        manifest = [json.loads(line) for line in (ROOT / 'data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
        meta = next(item for item in manifest if item.get('tin_id') == '6aed8a950baa4e9abf9409ef')
        body = (ROOT / meta['html_path']).read_bytes()
        result = inspect_sample(body, meta, {meta['tin_id']})
        self.assertEqual(result['tin_id'], meta['tin_id'])
        self.assertFalse(result['new_id'])
        self.assertEqual(result['html_type'], 'can_ho')
        self.assertEqual(result['district'], 'Nhà Bè')
        self.assertEqual(result['parsed_column_count'], 23)
        self.assertTrue(result['eligible_under_existing_rules'])
        self.assertNotIn('owner', result)
        self.assertNotIn('phone', result)

    def test_identity_rejects_ambiguity_wrong_model_and_missing_match(self):
        url = 'https://moso.vn/listing-test'
        soup = BeautifulSoup('<link rel="canonical" href="https://moso.vn/listing-test"><h1>Fixture</h1>', 'lxml')
        def obj(identifier, model=None, slug='listing-test'):
            return dict(_id=identifier, type='sale', **{'@page': dict(slug=slug, modelId=model or identifier)})
        cases = [[obj('a'*24), obj('b'*24)], [obj('a'*24, 'b'*24)], [obj('a'*24, slug='other')], []]
        for objects in cases:
            with self.subTest(objects=len(objects)), patch('src.api_html_probe.soup_from_html', return_value=soup), \
                    patch('src.api_html_probe.flight_objects', return_value=iter(objects)), self.assertRaises(CrawlStopped):
                identify_html(b'fixture', url)
        with patch('src.api_html_probe.soup_from_html', return_value=soup), self.assertRaises(CrawlStopped):
            identify_html(b'fixture', 'https://moso.vn/other')

    def test_selection_preserves_filters_and_excludes_known_urls(self):
        requests = []
        for group in ('apartment', 'frontage', 'detached_house'):
            requests.append(dict(group=group, offset=0, candidates=[dict(url=f'https://moso.vn/{group}-{n}', order=n+1) for n in range(3)]))
        result = select_samples(dict(requests=requests), {'https://moso.vn/apartment-0'})
        self.assertEqual([item['api_filter'] for item in result], ['apartment', 'apartment', 'frontage', 'frontage', 'detached_house'])
        self.assertEqual(result[0]['url'], 'https://moso.vn/apartment-1')
        self.assertEqual(len({item['url'] for item in result}), 5)
        self.assertNotIn('html_type', result[-1])


if __name__ == '__main__':
    unittest.main()
