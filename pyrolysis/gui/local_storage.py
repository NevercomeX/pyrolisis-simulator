import streamlit.components.v1 as components
import os

parent_dir = os.path.dirname(os.path.abspath(__file__))
component_dir = os.path.join(parent_dir, "local_storage")

_component_func = components.declare_component(
    "local_storage",
    path=component_dir
)

def local_storage_get(key, key_suffix=None):
    """Retrieves a value from browser localStorage."""
    component_key = f"ls_get_{key}"
    if key_suffix:
        component_key += f"_{key_suffix}"
    return _component_func(action="get", item_key=key, key=component_key, default=None, height=0)

def local_storage_set(key, value, key_suffix=None):
    """Saves a value to browser localStorage."""
    component_key = f"ls_set_{key}"
    if key_suffix:
        component_key += f"_{key_suffix}"
    return _component_func(action="set", item_key=key, value=value, key=component_key, default=None, height=0)
