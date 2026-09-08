import os
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from core.services import ROOT


class UITests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'TYPESENSE_API_KEY':''})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def app(self):
        at=AppTest.from_file(str(ROOT/'main.py'),default_timeout=15).run()
        self.assertFalse(at.exception)
        return at

    def test_initial_page_and_search(self):
        at=self.app()
        next(b for b in at.button if b.label=='Find our overlap').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.session_state['group'].categories['eat'].results)

    def test_add_member_and_save_preferences(self):
        at=self.app()
        next(i for i in at.text_input if i.label=='Add a person').set_value('Taylor')
        next(b for b in at.button if b.label=='Add person').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['group'].members),3)
        next(i for i in at.multiselect if i.label=='Would like').set_value(['Italian'])
        next(b for b in at.button if b.label=='Save preferences').click().run()
        self.assertFalse(at.exception)
        active=at.session_state['active_person']
        self.assertEqual(at.session_state['group'].categories['eat'].preferences[active]['likes'],('Italian',))


if __name__=='__main__':
    unittest.main()
