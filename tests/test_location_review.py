import json
import unittest
from pathlib import Path
from src.config import ROOT
from src.location_review import polygon_centroid, inside_polygon, embed_reference, evaluate_case

BASE=ROOT/'revisions/2026-11-02_location_review_v1'


class LocationReviewTest(unittest.TestCase):
    def test_polygon_reference_is_in_area(self):
        square=[[106,10],[106.01,10],[106.01,10.01],[106,10.01],[106,10]]
        point=polygon_centroid(square)
        self.assertAlmostEqual(point[0],106.005,places=10)
        self.assertAlmostEqual(point[1],10.005,places=10)
        self.assertTrue(inside_polygon(point,square))

    def test_open_polygon_is_not_accepted(self):
        with self.assertRaises(ValueError):polygon_centroid([[106,10],[106.01,10],[106.01,10.01]])

    def test_point_is_marker_not_viewport(self):
        evidence=json.loads((BASE/'evidence/cbre_park_google_embed.json').read_text(encoding='utf-8'))
        ref=embed_reference(evidence,'The Park Residence','project')
        self.assertEqual(ref['coordinates'],[106.7080306,10.7118696])
        self.assertNotAlmostEqual(ref['coordinates'][0],106.70584191480016,places=5)
        self.assertIsNone(ref['accuracy_m'])

    def test_multiple_points_cannot_be_selected_by_first_occurrence(self):
        evidence=dict(http_status=200,candidate_pairs=[dict(longitude=106,latitude=10),dict(longitude=107,latitude=11)])
        with self.assertRaises(ValueError):embed_reference(evidence,'unknown','project')

    def test_reference_does_not_become_verified_property_pin(self):
        source=dict(snapshot=dict(tin_id='example',capture_at='2026-11-02',html_sha256='hash'),
                    compatibility_row=dict(url='https://example.org',kinh_do=106.7,vi_do=10.7),coordinate_verification='unverified')
        review=dict(status='project_reference_supported',reason='same project',source_ids=['source'],identity_match_level='project_only',unresolved='unit unknown')
        ref=dict(coordinates=[106.71,10.71],level='project',status='reference_only_not_surveyed')
        result=evaluate_case(source,review,ref)
        self.assertEqual(result['source_coordinates'],[106.7,10.7])
        self.assertIsNone(result['verified_property_coordinates'])
        self.assertFalse(result['exact_spatial_analysis_eligible'])
        self.assertGreater(result['distance_to_reference_m'],1000)

    def test_unresolved_address_has_no_imputed_coordinate(self):
        source=dict(snapshot={},compatibility_row=dict(url='https://example.org',kinh_do=106.7,vi_do=10.7),coordinate_verification='unverified')
        review=dict(status='unresolved',reason='hidden house number',source_ids=[],identity_match_level='street_only',unresolved='need number')
        result=evaluate_case(source,review)
        self.assertIsNone(result['reference'])
        self.assertIsNone(result['distance_to_reference_m'])

    def test_result_coverage_and_independent_distances(self):
        path=BASE/'data/location_decisions.jsonl'
        cases={r['tin_id']:r for line in path.read_text(encoding='utf-8').splitlines()if(r:=json.loads(line))}
        self.assertEqual(len(cases),12)
        self.assertEqual(sum(c['reference']is not None for c in cases.values()),7)
        self.assertTrue(all(c['verified_property_coordinates']is None for c in cases.values()))
        expected={'6ae798b72cdb82e3b72068cc':76.818,'6ae45114bfaa4b4f2be2e31d':881.991,
                  '6ae2b887575dffe7bf6cef1e':758.537,'6ae7ee832cdb82e3b729d302':840.615}
        for tid,distance in expected.items():
            self.assertAlmostEqual(cases[tid]['distance_to_reference_m'],distance,delta=.01)

    def test_wrong_house_number_geocoder_result_is_rejected(self):
        generic=json.loads((BASE/'evidence/google_2g.json').read_text(encoding='utf-8'))
        self.assertIn('2G 35',generic['candidate_pairs'][0]['context'])
        reviews=json.loads((BASE/'review_inputs.json').read_text(encoding='utf-8'))
        key=reviews['cases']['6ae7ee832cdb82e3b729d302']['reference_key']
        self.assertEqual(reviews['references'][key]['evidence_id'],'google_res2g')


if __name__=='__main__':unittest.main()
