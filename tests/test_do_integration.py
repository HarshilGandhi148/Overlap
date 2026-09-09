import os
import unittest
from unittest.mock import Mock, patch
from core.contracts import CategorySearchError, Person, SearchRequest, validate_response
from core.ranking import rank_candidates
from core.services import AppServices, Settings, ROOT
from nearby.adapter import outing_from_request, snapshot_places
from nearby.ingestion import normalize
from nearby.models import NYC, RecommendationResponse, RankedActivity
from categories import do
from streamlit.testing.v1 import AppTest


def request():
    return SearchRequest('do', (Person('a', 'Alex'), Person('b', 'Sam')), filters={
        'do_source': 'snapshot', 'radius_miles': 5,
        'do_people': {
            'a': dict(opinion='Art and a relaxed walk', max_minutes=120, max_cost=30),
            'b': dict(opinion='A free garden with somewhere to sit', max_minutes=60, max_cost=0),
        },
    })


class AdapterTests(unittest.TestCase):
    def test_saved_sources_and_legacy_limits_ignored(self):
        self.assertEqual(len(snapshot_places()), 50)
        outing = outing_from_request(request())
        self.assertEqual(outing.location, NYC)
        self.assertFalse(outing.enforce_metadata_limits)
        from nearby.search import hard_filter
        filters = hard_filter(outing, ['google:test'])
        self.assertNotIn('cost', filters)
        self.assertNotIn('duration', filters)
        self.assertNotIn('wheelchair', filters)

    def test_missing_written_preferences_and_fake_search_are_rejected(self):
        with self.assertRaises(CategorySearchError):
            outing_from_request(SearchRequest('do', (Person('a', 'Alex'),)))
        with self.assertRaises(CategorySearchError):
            do.search(request(), AppServices(Settings(), 'sample'))

    def test_adapter_preserves_semantic_order_and_does_not_index_on_search(self):
        doc = snapshot_places()[0].document()
        for key in ('cost_min', 'cost_max', 'duration_min', 'duration_max'):
            doc.pop(key, None)
        other = dict(doc, id='node:9999', name='Second choice')
        ranked = [RankedActivity(d, score, 1.2, {'a': .8, 'b': .7}, {})
                  for d, score in [(doc, 80), (other, 75)]]
        service = Mock()
        service.recommend.return_value = RecommendationResponse(ranked, ranked[::-1], 2, 50, 3, .15, 50)
        with patch('nearby.adapter.service_for', return_value=service):
            req = request()
            response = do.search(req, AppServices(Settings()))
        validate_response(response, req)
        self.assertEqual([r.id for r in rank_candidates(response.candidates, req.people)], [doc['id'], other['id']])
        self.assertEqual(response.engine, 'Typesense')
        self.assertFalse(any('missing cost' in w for w in response.warnings))
        service.index_places.assert_not_called()

    def test_malformed_osm_entries_are_skipped(self):
        self.assertEqual(normalize([None, {}, {'id': 1, 'type': 'node', 'lat': 'bad', 'lon': 0,
                                                'tags': {'name': 'Bad', 'leisure': 'park'}}]), [])

    def test_shared_group_size_is_supported(self):
        req = request()
        people = tuple(Person(str(i), f'Person {i}') for i in range(12))
        req = SearchRequest('do', people, filters={'do_people': {p.id: {'opinion': 'Art'} for p in people}})
        self.assertEqual(len(outing_from_request(req).people), 12)


class DoUITests(unittest.TestCase):
    def test_do_uses_shared_names_and_keeps_written_preferences_across_navigation(self):
        with patch.dict(os.environ, {'TYPESENSE_API_KEY': ''}):
            at = AppTest.from_file(str(ROOT / 'main.py'), default_timeout=15).run()
            def click(label):
                next(b for b in at.button if b.label == label).click().run()
                self.assertFalse(at.exception)
            click('Go →')
            at.session_state['ui_category'] = 'do'
            click('Continue →')
            self.assertTrue(next(b for b in at.button if b.label == 'Find our overlap').disabled)
            self.assertFalse(any(n.label in ('Maximum minutes','Maximum cost ($)') for n in at.number_input))
            self.assertFalse(any(c.label == 'Wheelchair access required' for c in at.checkbox))
            next(t for t in at.text_area if t.label == 'What would you like to do?').set_value('Art and a walk')
            click('Save preferences')
            click('Edit names · 2')
            click('Continue →')
            profile = at.session_state['group'].categories['do'].filters['do_people']['person-1']
            self.assertEqual(profile['opinion'], 'Art and a walk')
            self.assertEqual(next(t for t in at.text_area if t.label == 'What would you like to do?').value, 'Art and a walk')
            next(s for s in at.selectbox if s.label == 'Preferences for').set_value('person-2').run()
            next(t for t in at.text_area if t.label == 'What would you like to do?').set_value('Trees and a garden')
            click('Save preferences')
            self.assertFalse(next(b for b in at.button if b.label == 'Find our overlap').disabled)


if __name__ == '__main__':
    unittest.main()
