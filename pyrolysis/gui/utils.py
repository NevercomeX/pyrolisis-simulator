"""
GUI Utilities and Internationalization Helper Functions.

Provides centralized language detection and dictionary translation lookups
across all Streamlit dashboard panels and tabs.
"""

from typing import Optional
import streamlit as st
from ..translations import TRANSLATIONS

GAL_PER_M3 = 264.172            # US gallons in one cubic metre
SYNGAS_DENSITY_KG_M3 = 1.15     # syngas density used to report gas volume
WATER_DENSITY_KG_M3 = 1000.0


def product_volumes(oil_kg, gas_kg, char_kg, water_kg):
    """Converts product masses to volumes: oil, char and water in gal, syngas in m³.
    Oil and char densities come from the sidebar (session_state)."""
    oil_density = float(st.session_state.get('bio_oil_density', 750.0))
    char_density = float(st.session_state.get('bio_char_density', 500.0))
    return (
        (oil_kg / oil_density) * GAL_PER_M3,
        gas_kg / SYNGAS_DENSITY_KG_M3,
        (char_kg / char_density) * GAL_PER_M3,
        (water_kg / WATER_DENSITY_KG_M3) * GAL_PER_M3,
    )


def sludge_gal(sludge_kg):
    """Sludge mass (kg) to volume (gal) with the sidebar sludge density."""
    return (sludge_kg / float(st.session_state.get('sludge_density', 944.7))) * GAL_PER_M3


def get_lang() -> str:
    """
    Returns current active language code ('en' or 'es') from session state.
    Defaults to Spanish ('es') if unset.
    """
    lang_option = st.session_state.get('lang_option', 'Spanish')
    return 'en' if lang_option == "English" else 'es'


def t(key: str, default: Optional[str] = None) -> str:
    """
    Translates a translation key string into the currently active language.
    Falls back to default if provided, or the key itself if not found.
    """
    lang = get_lang()
    val = TRANSLATIONS.get(lang, {}).get(key)
    if val is not None:
        return val
    return default if default is not None else key


def format_number(val: Optional[float], decimals: int = 2, default: str = "N/A") -> str:
    """
    Formats a floating point number with thousand separators and fixed decimals.
    """
    if val is None:
        return default
    try:
        return f"{float(val):,.{decimals}f}"
    except (ValueError, TypeError):
        return default
