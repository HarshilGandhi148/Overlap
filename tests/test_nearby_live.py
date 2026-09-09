"""Opt-in tests against real Typesense. Uses an isolated temporary collection."""
import json
import os
import unittest
from dataclasses import replace
from uuid import uuid4
from nearby.models import *
from nearby.search import SearchService
from nearby.ingestion import normalize,enrich_places
from tests.test_nearby import ROOT,person,outing,activity

@unittest.skipUnless(os.getenv('RUN_LIVE_TYPESENSE')=='1','Set RUN_LIVE_TYPESENSE=1 with a running local Typesense server')
class LiveTypesenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service=SearchService(collection='overlap_test_'+uuid4().hex)
        cls.docs=[
            activity('node:1',wheelchair='yes'),
            activity('node:2',location=[NYC.latitude+.03,NYC.longitude],wheelchair='yes'),
            activity('node:3',cost_max=40,wheelchair='yes'),
            activity('node:4',duration_max=180,wheelchair='yes'),
            activity('node:5',duration_min=None,duration_max=None,wheelchair='yes'),
            activity('node:6',cost_min=None,cost_max=None,wheelchair='yes'),
            activity('node:7',categories=['park'],cost_min=0,cost_max=0,wheelchair='yes'),
            activity('node:8',wheelchair='unknown'),
            activity('node:9',cost_min=0,cost_max=0),
            activity('node:10',location=[NYC.latitude+.0143,NYC.longitude]),
            activity('node:11',location=[NYC.latitude+.0147,NYC.longitude]),
        ]
        cls.ids,failed=cls.service.index_places(cls.docs)
        assert failed==0

    @classmethod
    def tearDownClass(cls):
        cls.service.client.collections[cls.service.collection].delete()

    def test_real_typesense_applies_all_constraints_and_keeps_boundaries(self):
        o=outing(radius=1,people=(person(time=90,cost=35,exclusions=('park',),wheelchair=True),person('b',time=60,cost=20)))
        r=self.service.recommend(o,self.ids)
        self.assertEqual([a.document['id'] for a in r.ranked],['node:1'])
        self.assertEqual(r.missing_metadata_count,2)
        self.assertTrue(all(set(a.individual_scores)=={'a','b'} for a in r.ranked))

    def test_zero_budget(self):
        r=self.service.recommend(outing(people=(person(cost=0),person('b',cost=10))),self.ids)
        self.assertEqual({a.document['id'] for a in r.ranked},{'node:7','node:9'})

    def test_geo_boundary_inside_outside_and_nearest(self):
        r=self.service.recommend(outing(radius=1),['node:1','node:10','node:11'])
        self.assertEqual([a.document['id'] for a in r.nearest],['node:1','node:10'])

    def test_candidate_ids_isolate_search_and_empty_results(self):
        r=self.service.recommend(outing(),['node:3'])
        self.assertEqual(r.eligible_count,0)
        self.assertEqual(self.service.recommend(outing(),[]).ranked,[])

    def test_unrelated_metadata_does_not_change_embedding(self):
        before=self.service.client.collections[self.service.collection].documents['node:1'].retrieve()['embedding']
        self.service.client.collections[self.service.collection].documents['node:1'].update({'fetched_at':123456})
        after=self.service.client.collections[self.service.collection].documents['node:1'].retrieve()['embedding']
        self.assertEqual(before,after)

    def test_actual_semantic_paraphrase(self):
        art=activity('node:8001',name='Studio Gallery',description='An exhibition of paintings, sculpture and visual art.')
        sport=activity('node:8002',name='Sports Hall',description='A sports centre for competitive basketball, football and exercise.',categories=['sports'])
        ids,failed=self.service.index_places([art,sport]);self.assertEqual(failed,0)
        o=outing(people=(replace(person(),opinion='I want to admire creative works made by artists.'),replace(person('b'),opinion='I want to admire creative works made by artists.')))
        r=self.service.recommend(o,ids)
        self.assertEqual(r.ranked[0].document['id'],'node:8001')

    def test_complete_pagination_for_eight_people(self):
        docs=[activity(f'page:{i}',description='A place for visual art and creative exhibitions.') for i in range(501)]
        ids,failed=self.service.index_places(docs);self.assertEqual(failed,0)
        r=self.service.recommend(outing(people=tuple(person(str(i)) for i in range(8))),ids)
        self.assertEqual(len(r.ranked),501)
        self.assertTrue(all(len(a.individual_scores)==8 for a in r.ranked))

    def test_real_nyc_fixture_enrichment(self):
        raw=json.loads((ROOT/'tests/fixtures/nyc_osm_50.json').read_text())['elements']
        places=enrich_places(normalize(raw));ids,failed=self.service.index_places(places)
        self.assertEqual(failed,0)
        r=self.service.recommend(outing(people=(person(time=180),person('b',time=180))),ids)
        self.assertEqual(len(r.ranked),50)

if __name__=='__main__':unittest.main()
