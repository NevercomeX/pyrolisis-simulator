import streamlit.components.v1 as components
import os

# The component's front-end (index.html) lives in the local_storage/ folder next to this file
_component_func = components.declare_component(
    "local_storage",
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_storage")
)

def _widget_key(action, key, key_suffix):
    """Streamlit widget key: unique per action, storage key and call site (key_suffix)."""
    return f"ls_{action}_{key}" + (f"_{key_suffix}" if key_suffix else "")

def local_storage_get(key, key_suffix=None):
    """Retrieves a value from browser localStorage."""
    return _component_func(action="get", item_key=key, key=_widget_key("get", key, key_suffix),
                           default=None, height=0)

def local_storage_set(key, value, key_suffix=None):
    """Saves a value to browser localStorage."""
    return _component_func(action="set", item_key=key, value=value, key=_widget_key("set", key, key_suffix),
                           default=None, height=0)
