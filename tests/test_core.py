import unittest
from dataclasses import replace
from core.contracts import Candidate, CategorySearchError, Person, SearchRequest, SearchResponse, validate_response
from core.catalog import eligible, filter_expression
from core.ranking import rank_candidates, vote_status
from core.services import AppServices, Settings
from core.state import GroupState
from categories import eat, watch, play, anything


class RankingTests(unittest.TestCase):
    def test_fairness_beats_one_person_only(self):
        people = (Person('a','A',('x','y')), Person('b','B',('x','y')))
        polarizing = Candidate('eat','1','One-sided',matched_likes={'a':('x','y'),'b':()})
        balanced = Candidate('eat','2','Balanced',matched_likes={'a':('x',),'b':('y',)})
        self.assertEqual(rank_candidates((polarizing,balanced),people)[0].id,'2')

    def test_neutral_people_and_ties_keep_provider_order(self):
        a,b = Candidate('eat','a','A'), Candidate('eat','b','B')
        self.assertEqual(rank_candidates((b,a),(Person('p','P'),)),[b,a])

    def test_unsupported_preference_is_rejected(self):
        req = SearchRequest('eat',(Person('p','P',('Italian',)),))
        c = Candidate('eat','a','A',matched_likes={'p':('Mexican',)})
        with self.assertRaises(CategorySearchError):
            validate_response(SearchResponse((c,)),req)

    def test_duplicate_results_rejected(self):
        c = Candidate('eat','a','A')
        with self.assertRaises(CategorySearchError):
            validate_response(SearchResponse((c,c)), SearchRequest('eat',()))


class WorkflowTests(unittest.TestCase):
    def test_changed_preferences_clear_stale_decisions(self):
        group=GroupState(); state=group.category(eat.get_spec())
        c=Candidate('eat','a','A'); state.results=[c]; state.shortlist=[c]
        state.votes={'a':{'person-1':2}};state.chosen_id='a'
        state.set_preferences('person-1',['Italian'],[])
        self.assertFalse(state.results);self.assertFalse(state.votes);self.assertIsNone(state.chosen_id)

    def test_switching_categories_preserves_inputs(self):
        group=GroupState(); eat_state=group.category(eat.get_spec())
        eat_state.set_preferences('person-1',['Italian'],[])
        group.category(watch.get_spec()).query='mystery'
        self.assertEqual(group.category(eat.get_spec()).preferences['person-1']['likes'],('Italian',))

    def test_member_ids_are_stable_with_duplicate_names(self):
        group=GroupState(); a=group.add('Alex'); b=group.add('Alex')
        self.assertNotEqual(a,b);group.remove(a)
        self.assertIn(b,[m['id'] for m in group.members])

    def test_membership_change_invalidates_all_categories(self):
        group=GroupState()
        for spec in [eat.get_spec(),watch.get_spec()]:
            group.category(spec).searched=True
        group.add('Third')
        self.assertTrue(all(not s.searched for s in group.categories.values()))

    def test_incomplete_and_pass_votes_never_confirm(self):
        self.assertEqual(vote_status({'a':2},['a','b'])[:2],(False,False))
        self.assertEqual(vote_status({'a':2,'b':0},['a','b'])[:2],(True,False))
        self.assertEqual(vote_status({'a':2,'b':1},['a','b']),(True,True,3))


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.services=AppServices(Settings(),mode='sample')

    def test_hard_exclusion_and_budget(self):
        req=SearchRequest('eat',(Person('p','P',avoids=('Italian',)),),filters={'budget':20})
        result=eat.search(req,self.services)
        self.assertTrue(result.candidates)
        self.assertTrue(all('Italian' not in c.tags for c in result.candidates))
        self.assertNotIn('market',[c.id for c in result.candidates])

    def test_unknown_cost_does_not_pass_budget(self):
        self.assertFalse(eligible({'tags':[]},SearchRequest('eat',(),filters={'budget':20})))

    def test_all_required_dietary_options(self):
        req=SearchRequest('eat',(),filters={'budget':30,'dietary_options':['Vegetarian','Vegan']})
        self.assertEqual({c.id for c in eat.search(req,self.services).candidates},{'mesa','saffron','market'})

    def test_game_player_count(self):
        req=SearchRequest('play',(),filters={'players':8,'max_duration':30})
        self.assertEqual({c.id for c in play.search(req,self.services).candidates},{'draw','word','tower'})

    def test_anything_deduplicates_and_keeps_stable_ids(self):
        req=SearchRequest('anything',(),custom_options=(' Pizza ','pizza','Movie'))
        result=anything.search(req,self.services)
        self.assertEqual(len(result.candidates),2)
        again=anything.search(replace(req,custom_options=('Movie','Pizza')),self.services)
        self.assertEqual(result.candidates[0].id,again.candidates[1].id)

    def test_filter_values_cannot_inject_an_expression(self):
        with self.assertRaises(CategorySearchError):
            filter_expression(SearchRequest('eat',(),filters={'city':'x` || cost:>0'}))

    def test_catalogs_meet_contract(self):
        from core.registry import load_categories
        ready, unavailable=load_categories()
        self.assertFalse(unavailable)
        for key,(spec,module) in ready.items():
            req=SearchRequest(key,(Person('p','P'),),filters={f.key:f.default for f in spec.filter_fields},custom_options=('Choice',) if spec.custom else ())
            if key == 'do':
                # Semantic search deliberately cannot masquerade as an offline preview.
                with self.assertRaises(CategorySearchError):
                    module.search(req,self.services)
                continue
            result=module.search(req,self.services)
            validate_response(result,req)
            self.assertTrue(result.candidates)


if __name__=='__main__':
    unittest.main()
