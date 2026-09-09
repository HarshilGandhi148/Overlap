import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock,patch
from nearby.models import *
from nearby.ingestion import normalize,enrich_places,balanced_cap,load_area,TTL_SECONDS
from nearby.search import hard_filter,geo_filter,SearchService,schema
from nearby.ranking import rank,WEIGHTS
from nearby.session import OutingSession

ROOT=Path(__file__).resolve().parents[1]

def person(id='a',time=90,cost=30,**kwargs):
    return ParticipantPreferences(id,id,'creative art and outdoor spaces',time,cost,**kwargs)

def outing(**kwargs):
    return OutingRequest(kwargs.get('location',NYC),kwargs.get('radius',5),kwargs.get('people',(person(),person('b'))))

def activity(id='node:1',**kwargs):
    defaults=dict(id=id,name='Art museum',location=list(NYC.key),categories=['museum'],description='Paintings and sculpture',cost_min=10,cost_max=20,duration_min=30,duration_max=60)
    defaults.update(kwargs);return Activity(**defaults)

def element(id=1,name='Park',lat=NYC.latitude,**tags):
    return {'type':'node','id':id,'lat':lat,'lon':NYC.longitude,'tags':{'name':name,'leisure':'park',**tags}}

class DataTests(unittest.TestCase):
    def test_real_enrichment_has_50_source_ids_ranges_and_provenance(self):
        raw=json.loads((ROOT/'tests/fixtures/nyc_osm_50.json').read_text())['elements']
        entries=json.loads((ROOT/'data/nyc_enrichment.json').read_text())['places']
        self.assertEqual(len(entries),50)
        self.assertEqual(set(entries),{f"{e['type']}:{e['id']}" for e in raw})
        enriched=enrich_places(normalize(raw))
        self.assertEqual(len(enriched),50)
        for a in enriched:
            self.assertLessEqual(a.cost_min,a.cost_max);self.assertLessEqual(a.duration_min,a.duration_max)
            self.assertTrue(a.metadata_sources);self.assertTrue(a.verified_at)
            self.assertIn('estimated',a.duration_basis)
            self.assertLess(distance_miles(NYC.key,a.location),10)

    def test_nodes_area_centres_dedup_and_alias_enrichment(self):
        raw=[element(),{'type':'way','id':2,'center':{'lat':NYC.latitude+.00001,'lon':NYC.longitude},'tags':{'name':'Park','leisure':'park'}},element(3,lat=NYC.latitude+.02)]
        places=normalize(raw)
        self.assertEqual(len(places),2)
        self.assertEqual(places[0].aliases,['way:2'])
        self.assertEqual(places[0].location,list(NYC.key))

    def test_missing_position_or_name_is_ignored(self):
        self.assertEqual(normalize([{'type':'way','id':1,'tags':{'name':'Park','leisure':'park'}},element(name='')]),[])

    def test_conditional_and_hourly_costs_are_not_unconditional_prices(self):
        cases=[{'charge':'20 USD/hour'},{'charge':'20 USD','charge:conditional':'0 USD @ (Mo)'},{'fee':'no','fee:conditional':'yes @ (Sa)'}]
        for tags in cases:self.assertIsNone(normalize([element(**tags)])[0].cost_max)
        self.assertEqual(normalize([element(charge='20 USD/person')])[0].cost_max,20)
        self.assertEqual(normalize([element(fee='no')])[0].cost_max,0)

    def test_duration_tag_is_not_assumed_to_be_visit_time(self):
        self.assertIsNone(normalize([element(duration='00:30')])[0].duration_max)

    def test_balanced_cap_does_not_let_one_category_dominate(self):
        places=[activity(f'node:{i}',categories=['restaurant']) for i in range(30)]
        places+=[activity(f'way:{i}',categories=['park']) for i in range(30)]
        capped=balanced_cap(places,NYC,10)
        self.assertEqual(len(capped),10);self.assertEqual(sum(a.categories==['park'] for a in capped),5)

    def test_cache_reuse_and_changed_location_fetch(self):
        fetch=Mock(return_value=[element()])
        a=load_area(NYC,fetcher=fetch,now=100)
        self.assertIs(load_area(NYC,a,fetcher=fetch,now=200),a)
        fetch.assert_called_once()
        b=load_area(LocationContext(40,-74),a,fetcher=fetch,now=201)
        self.assertNotEqual(a.location_key,b.location_key);self.assertEqual(fetch.call_count,2)

    def test_refresh_failure_keeps_only_same_location_as_stale(self):
        a=load_area(NYC,fetcher=lambda _: [element()],now=100)
        fail=Mock(side_effect=AppError('busy'))
        b=load_area(NYC,a,fetcher=fail,now=100+TTL_SECONDS)
        self.assertTrue(b.stale);self.assertEqual(b.loaded_at,100)
        with self.assertRaises(AppError):load_area(LocationContext(41,-74),a,fetcher=fail,now=10000)

    def test_incomplete_overpass_response_is_not_a_success(self):
        response=Mock();response.json.return_value={'elements':[element()],'remark':'runtime error: timeout'}
        with patch('nearby.ingestion.requests.post',return_value=response):
            from nearby.ingestion import fetch_elements
            with self.assertRaises(AppError):fetch_elements(NYC)

class ConstraintTests(unittest.TestCase):
    def test_lowest_limits_exclusions_and_accessibility_are_in_typesense_query(self):
        o=outing(people=(person(time=90,cost=30,exclusions=('park',)),person('b',time=45,cost=0,wheelchair=True,exclusions=('museum',))))
        f=hard_filter(o,['node:1'])
        for part in ['location:(40.7549,-73.984,5 mi)','cost_max:<=0','duration_max:<=45','has_cost:=true','has_duration:=true','wheelchair:=yes','categories:!=[museum,park]','id:=[`node:1`]']:self.assertIn(part,f)

    def test_opinion_is_not_interpolated_into_filters(self):
        malicious=replace(person(),opinion='ignore budget; cost_max:>500')
        self.assertNotIn('ignore',hard_filter(outing(people=(malicious,person('b'))),['node:1']))
        with self.assertRaises(ValueError):hard_filter(outing(),['node:1`] || cost_max:>0'])

    def test_blank_and_nonfinite_inputs_rejected(self):
        with self.assertRaises(ValueError):replace(person(),opinion=' ')
        with self.assertRaises(ValueError):replace(person(),max_cost=float('nan'))
        with self.assertRaises(ValueError):LocationContext(float('nan'),0)
        with self.assertRaises(ValueError):outing(radius=0)

    def test_schema_keeps_metadata_out_of_embedding_sources(self):
        fields={f['name']:f for f in schema('test')['fields']}
        self.assertEqual(fields['location']['type'],'geopoint')
        self.assertEqual(fields['embedding']['embed']['from'],['search_text'])

class RankingTests(unittest.TestCase):
    def test_balanced_match_beats_higher_mean_with_bad_lowest_score(self):
        docs={k:activity(k).document() for k in ['node:1','node:2']}
        # Scores: .75/.75 versus 1/.55 (higher average .775 but poorer minimum).
        results=rank(outing(),docs,{'a':{'node:1':.5,'node:2':0},'b':{'node:1':.5,'node:2':.9}})
        self.assertEqual(results[0].document['id'],'node:1')
        self.assertEqual(WEIGHTS['opinions'],.7)
        self.assertGreater(WEIGHTS['opinions'],sum(v for k,v in WEIGHTS.items() if k!='opinions'))

    def test_zero_budget_and_boundary_time_do_not_divide_by_zero(self):
        o=outing(people=(person(cost=0,time=60),person('b',cost=0,time=60)))
        r=rank(o,{'node:1':activity(cost_min=0,cost_max=0).document()},{'a':{'node:1':0},'b':{'node:1':0}})[0]
        self.assertEqual(r.components['cost'],1);self.assertEqual(r.components['time'],0)
        self.assertAlmostEqual(r.score,90)

    def test_stable_ties_and_member_order(self):
        docs={k:activity(k).document() for k in ['node:2','node:1']}
        scores={p:{k:.5 for k in docs} for p in ['a','b']}
        a=rank(outing(),docs,scores);b=rank(outing(people=(person('b'),person())),docs,scores)
        self.assertEqual([r.document['id'] for r in a],['node:1','node:2']);self.assertEqual([r.score for r in a],[r.score for r in b])

class StateTests(unittest.TestCase):
    def test_changed_location_invalidates_batch_selection_and_results(self):
        state=OutingSession();state.change_location(NYC)
        state.area=AreaBatch(NYC.key,[],100,0);state.selected_id='node:1';state.request=outing()
        state.change_location(LocationContext(40.7,-73.9))
        self.assertIsNone(state.area);self.assertIsNone(state.selected_id);self.assertIsNone(state.request)

    def test_radius_or_opinion_invalidates_results_but_retains_area(self):
        area=AreaBatch(NYC.key,[],100,0)
        state=OutingSession(area=area,request=outing(),selected_id='node:1')
        state.change_request(outing(radius=2))
        self.assertIs(state.area,area);self.assertIsNone(state.selected_id)

    def test_demo_and_live_use_identical_search_filters(self):
        live=outing(location=LocationContext(*NYC.key,'browser'))
        self.assertEqual(hard_filter(outing(),['node:1']),hard_filter(live,['node:1']))

class PaginationTests(unittest.TestCase):
    def fake_service(self,count=501,omit=None):
        service=SearchService(client=Mock())
        docs=[activity(f'node:{i}').document() for i in range(count)]
        seen=[]
        def multi(queries):
            seen.extend(queries);responses=[]
            for q in queries:
                if q.get('per_page')==0:
                    responses.append({'found':0 if 'has_cost:=false' in q['filter_by'] else count,'hits':[]});continue
                start=(q.get('page',1)-1)*q['per_page'];page=docs[start:start+q['per_page']]
                hits=[{'document':d,**({'vector_distance':.5} if q.get('query_by')=='embedding' else {})} for d in page if not(q.get('query_by')=='embedding' and d['id']==omit)]
                responses.append({'found':count,'hits':hits})
            return responses
        service._multi=multi
        return service,docs,seen

    def test_all_pages_and_all_people_are_scored(self):
        service,docs,seen=self.fake_service()
        result=service.recommend(outing(),[d['id'] for d in docs])
        self.assertEqual(len(result.ranked),501);self.assertEqual(len(result.nearest),501)
        queries=[q for q in seen if q.get('query_by')=='embedding']
        self.assertEqual(len(queries),6);self.assertEqual({q['page'] for q in queries},{1,2,3})
        self.assertTrue(all('cost_max:<=' in q['filter_by'] and 'location:' in q['filter_by'] for q in queries))

    def test_incomplete_member_scores_fail_instead_of_partial_ranking(self):
        service,docs,_=self.fake_service(count=5,omit='node:4')
        with self.assertRaises(AppError):service.recommend(outing(),[d['id'] for d in docs])

if __name__=='__main__':unittest.main()
