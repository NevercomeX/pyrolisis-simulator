"""
GUI Utilities and Internationalization Helper Functions.

Provides centralized language detection and dictionary translation lookups
across all Streamlit dashboard panels and tabs.
"""

from typing import Any, Optional
import streamlit as st
from ..translations import TRANSLATIONS


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
