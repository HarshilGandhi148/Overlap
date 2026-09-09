import os
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from core.services import ROOT


class UITests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'TYPESENSE_API_KEY': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def click(self, at, label):
        next(b for b in at.button if b.label == label).click().run()
        self.assertFalse(at.exception)
        return at

    def app(self, enter=True):
        at = AppTest.from_file(str(ROOT / 'main.py'), default_timeout=15).run()
        self.assertFalse(at.exception)
        if enter:
            self.click(at, 'Go →')
            self.click(at, 'Continue →')
        return at

    def test_landing_then_names_then_app(self):
        at = self.app(enter=False)
        self.assertFalse(at.text_input)
        self.click(at, 'Go →')
        self.assertTrue(any(i.label == 'Person 1' for i in at.text_input))
        self.click(at, 'Continue →')
        self.assertTrue(any(b.label == 'Find our overlap' for b in at.button))

    def test_initial_page_and_search(self):
        at = self.app()
        self.click(at, 'Find our overlap')
        self.assertTrue(at.session_state['group'].categories['eat'].results)

    def test_add_member_and_save_preferences(self):
        at = self.app(enter=False)
        self.click(at, 'Go →')
        next(i for i in at.text_input if i.label == 'Add a person').set_value('Taylor')
        self.click(at, 'Add')
        self.assertEqual(len(at.session_state['group'].members), 3)
        self.click(at, 'Continue →')
        next(i for i in at.multiselect if i.label == 'Would like').set_value(['Italian'])
        self.click(at, 'Save preferences')
        active = at.session_state['ui_person']
        self.assertEqual(at.session_state['group'].categories['eat'].preferences[active]['likes'], ('Italian',))

    def test_edit_names_preserves_results_and_selected_options(self):
        at = self.app()
        self.click(at, 'Find our overlap')
        self.click(at, 'Add to vote')
        chosen = at.session_state['group'].categories['eat'].shortlist[0].id
        self.click(at, 'Edit names · 2')
        next(i for i in at.text_input if i.label == 'Person 1').set_value('Nathan').run()
        self.assertEqual(at.session_state['group'].members[0]['name'], 'Nathan')
        self.click(at, 'Continue →')
        state = at.session_state['group'].categories['eat']
        self.assertTrue(state.results)
        self.assertEqual(state.shortlist[0].id, chosen)

    def test_vote_flow_still_requires_every_person(self):
        at = self.app()
        self.click(at, 'Find our overlap')
        self.click(at, 'Add to vote')
        self.click(at, '2 · Vote (1)')
        candidate = at.session_state['group'].categories['eat'].shortlist[0]
        next(r for r in at.radio if r.label == candidate.title).set_value(2)
        self.click(at, 'Save my votes')
        self.assertTrue(next(b for b in at.button if b.label == 'Confirm this pick').disabled)
        next(s for s in at.selectbox if s.label == 'Whose turn?').set_value('person-2').run()
        next(r for r in at.radio if r.label == candidate.title).set_value(1)
        self.click(at, 'Save my votes')
        self.click(at, 'Confirm this pick')
        self.assertEqual(at.session_state['group'].categories['eat'].chosen_id, candidate.id)


    def test_pass_reduces_points_without_blocking_confirmation(self):
        at = self.app()
        self.click(at, 'Find our overlap')
        self.click(at, 'Add to vote')
        self.click(at, '2 · Vote (1)')
        candidate = at.session_state['group'].categories['eat'].shortlist[0]
        next(r for r in at.radio if r.label == candidate.title).set_value(2)
        self.click(at, 'Save my votes')
        self.assertTrue(next(b for b in at.button if b.label == 'Confirm this pick').disabled)
        next(s for s in at.selectbox if s.label == 'Whose turn?').set_value('person-2').run()
        next(r for r in at.radio if r.label == candidate.title).set_value(0)
        self.click(at, 'Save my votes')
        self.assertFalse(next(b for b in at.button if b.label == 'Confirm this pick').disabled)
        self.assertTrue(any('2 points' in c.value for c in at.caption))
        self.click(at, 'Confirm this pick')
        self.assertEqual(at.session_state['group'].categories['eat'].chosen_id, candidate.id)


if __name__ == '__main__':
    unittest.main()
