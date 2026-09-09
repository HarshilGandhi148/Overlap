import unittest
from unittest.mock import patch, MagicMock
from categories import eat
from core.contracts import SearchRequest, Person, CategorySearchError, validate_response
from core.services import AppServices, Settings
from scripts.import_eat import extract_dietary_options, enrich_with_google

class EatTests(unittest.TestCase):
    def test_normal_search_not_custom_choices(self):
        self.assertFalse(eat.SPEC.custom)
        with self.assertRaises(CategorySearchError):
            eat.search(SearchRequest('eat', (), custom_options=('Unverified',)), AppServices(Settings()))

    def test_unknown_price_only_allowed_without_budget(self):
        self.assertFalse(eat.eligible({}, SearchRequest('eat', (), filters={'budget':40}))[0])
        self.assertTrue(eat.eligible({}, SearchRequest('eat', (), filters={'budget':40,'use_budget':False}))[0])

    def test_filter_quotes_and_exclusions(self):
        req=SearchRequest('eat',(Person('p','P',avoids=('Italian',)),),filters={'dietary_options':['Gluten-free']})
        self.assertIn('dietary_options:=`Gluten-free`',eat.filter_expression(req))
        self.assertFalse(eat.eligible({'cuisine':['Italian'],'dietary_options':['Gluten-free']},req)[0])
        with self.assertRaises(CategorySearchError):
            eat.filter_expression(SearchRequest('eat',(),filters={'dietary_options':['bad`value']}))

    def test_geo_filter_without_other_constraints(self):
        client=MagicMock(); client.collections.__getitem__.return_value.documents.search.return_value={'hits':[],'found':0}
        eat.search_typesense(SearchRequest('eat',(),filters={'max_distance':3}),AppServices(Settings(api_key='test'),_client=client),(40.75,-73.99))
        params=client.collections.__getitem__.return_value.documents.search.call_args.args[0]
        self.assertTrue(params['filter_by'].startswith('location:('))
        self.assertNotIn('&&',params['filter_by'])
        self.assertEqual(params['drop_tokens_threshold'],0)

    def test_unresolved_location_never_drops_radius(self):
        with patch.dict('os.environ',{'GOOGLE_MAPS_API_KEY':''}):
            with self.assertRaises(CategorySearchError): eat.meeting_coordinates('Unknown address')
        self.assertEqual(eat.meeting_coordinates('40.75, -73.99'),(40.75,-73.99))
        with self.assertRaises(CategorySearchError): eat.meeting_coordinates('100, 200')

    def test_no_real_catalog_no_fictional_fallback(self):
        with patch.object(eat,'DATA_FILE',eat.ROOT/'data'/'missing-eat.json'):
            with self.assertRaises(CategorySearchError): eat.load_restaurants()

    def test_osm_diet_tags(self):
        self.assertEqual(extract_dietary_options({'diet:vegan':'only','diet:halal':'yes','diet:vegetarian':'no'}),['Vegan','Halal'])

    def test_google_enum_and_wrong_branch_rejected(self):
        record={'id':'a','title':'Pizza Place','address':'NYC','location':{'lat':40.75,'lng':-73.99},'cuisine':['Pizza'],'source_url':'https://www.openstreetmap.org/node/1','provenance':{}}
        place={'id':'google','displayName':{'text':'Pizza Place'},'location':{'latitude':40.75,'longitude':-73.99},'priceLevel':'PRICE_LEVEL_MODERATE'}
        with patch('scripts.import_eat.google_search_text',return_value=place):
            result=enrich_with_google(dict(record),'test')
            self.assertEqual(result['price_level'],2)
            self.assertEqual(result['budget_estimate'],30)
        place['location']['latitude']=41.75
        with patch('scripts.import_eat.google_search_text',return_value=place):
            self.assertNotIn('budget_estimate',enrich_with_google(dict(record),'test'))

    def test_sample_query_remains_relevant(self):
        response=eat.search(SearchRequest('eat',(),query='nonsensezzzz'),AppServices(Settings(),mode='sample'))
        self.assertFalse(response.candidates)

if __name__=='__main__': unittest.main()
