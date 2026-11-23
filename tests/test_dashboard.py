"""Dashboard behaviour with Streamlit's AppTest: navigation, the economics form and the thesis profile.

These tests run the whole app, so they take a few seconds each.
"""
import logging
import unittest

from streamlit.testing.v1 import AppTest

from pyrolysis.profiles import THESIS_PROFILE_VERSION

logging.getLogger("streamlit").setLevel(logging.ERROR)
APP = "../app.py"   # AppTest resolves the path from this file's folder


def _thesis_app():
    """The app already run once with the thesis profile loaded."""
    from pyrolysis.gui.config_manager import DEFAULT_PARAMS
    from pyrolysis.profiles import THESIS_GUI_OVERRIDES
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in {**DEFAULT_PARAMS, **THESIS_GUI_OVERRIDES,
                 'profile': 'tesis', 'profile_version': THESIS_PROFILE_VERSION}.items():
        at.session_state[k] = v
    return at.run()


def _open_section(at, section):
    at.button_group(key='nav_section').set_value(section).run()


def _text(at):
    """All markdown, info and caption text on the page."""
    return "\n".join(str(e.value) for e in list(at.markdown) + list(at.info) + list(at.caption))


class TestDashboard(unittest.TestCase):

    def test_section_stays_after_changing_a_sidebar_parameter(self):
        at = AppTest.from_file(APP, default_timeout=180).run()
        _open_section(at, 'economy')
        batch = next(n for n in at.sidebar.number_input if n.label.startswith(("Tamaño del Lote", "Batch Size")))
        batch.set_value(batch.value + 100.0).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.button_group(key='nav_section').value, 'economy')
        self.assertEqual(at.session_state['nav_section'], 'economy')

    def test_economic_form_recalculate_keeps_the_section(self):
        # AppTest sends widget values on every run, so the form's "apply only on submit" behaviour is a
        # browser feature it cannot reproduce; here we check that submitting applies the value and stays put.
        at = _thesis_app()
        _open_section(at, 'economy')
        at.number_input(key='price_oil').set_value(130.0)
        next(b for b in at.button if b.label.endswith(("Recalcular", "Recalculate"))).click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['price_oil'], 130.0)          # applied on submit
        self.assertEqual(at.session_state['nav_section'], 'economy')    # still in Economy

    def test_thesis_summary_shows_table_9(self):
        at = _thesis_app()
        self.assertFalse(at.exception)
        text = _text(at)
        for expected in ("RD$ 103,915,543", "107.06 %", "1.11 años", "6.18", "RD$ -28.86/gal",
                         "mientras el lodo cueste menos de RD$ 28.86/gal",
                         "60.56 %", "Medido al apagar: 60.56 %"):
            self.assertIn(expected, text)

    def test_section_stays_after_resetting_the_thesis_profile(self):
        # The reset button calls st.rerun() from the sidebar, before the navigation is drawn
        at = _thesis_app()
        _open_section(at, 'economy')
        at.session_state['price_oil'] = 130.0
        next(b for b in at.sidebar.button if b.label.startswith("↺")).click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['price_oil'], 121.0)          # profile values back
        self.assertEqual(at.session_state['nav_section'], 'economy')    # still in Economy

    def test_economic_values_survive_switching_sections(self):
        at = _thesis_app()
        nav = at.button_group(key='nav_section')
        for section in ('economy', 'process', 'balances', 'summary'):
            nav.set_value(section).run()
            self.assertFalse(at.exception, section)
        self.assertEqual(at.session_state['econ_batches_per_year'], 216)
        self.assertIn("RD$ 103,915,543", _text(at))


def _load_script():
    import streamlit as st
    from pyrolysis.gui.config_manager import load_saved_config
    st.session_state['reapplied'] = load_saved_config(st.session_state['saved'])


class TestSavedConfiguration(unittest.TestCase):

    def _load(self, saved):
        at = AppTest.from_function(_load_script)
        at.session_state['saved'] = saved
        return at.run()

    def test_thesis_config_from_an_older_version_gets_the_profile_again(self):
        # Saved before the economics were added to the profile: no version, no fixed batches
        at = self._load({'profile': 'tesis', 'econ_batches_per_year': 0, 'price_oil': 120.0})
        self.assertTrue(at.session_state['reapplied'])
        self.assertEqual(at.session_state['econ_batches_per_year'], 216)
        self.assertEqual(at.session_state['price_oil'], 121.0)
        self.assertEqual(at.session_state['profile_version'], THESIS_PROFILE_VERSION)

    def test_current_thesis_config_keeps_the_user_edits(self):
        at = self._load({'profile': 'tesis', 'profile_version': THESIS_PROFILE_VERSION, 'price_oil': 130.0})
        self.assertFalse(at.session_state['reapplied'])
        self.assertEqual(at.session_state['price_oil'], 130.0)

    def test_general_config_is_loaded_as_is(self):
        at = self._load({'profile': 'general', 'price_oil': 130.0})
        self.assertFalse(at.session_state['reapplied'])
        self.assertEqual(at.session_state['price_oil'], 130.0)


if __name__ == "__main__":
    unittest.main()
