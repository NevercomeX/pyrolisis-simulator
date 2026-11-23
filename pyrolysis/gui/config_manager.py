import streamlit as st
import json
from .utils import t

DEFAULT_PARAMS = {
    'profile': "general",
    'profile_version': 0,   # version of the profile values stored in this configuration (see profiles.py)
    'lang_option': "Español",
    'feed_option': "Blend (Petroleum + Hydrocarbon)",
    'blend_ratio': 50.0,
    'c_moist': 2.0,
    'c_vol': 82.0,
    'c_fc': 14.39,
    'c_ash': 1.61,
    'c_ea': 100.0,
    'c_a': 1e7,
    'c_y_oil': 60.0,
    'c_y_gas': 25.0,
    'c_y_char': 15.0,
    'use_advanced_kinetics': False,
    'c_ea1': 120.0,
    'c_a1': 1e8,
    'c_ea2': 140.0,
    'c_a2': 2e6,
    'c_ea3': 100.0,
    'c_a3': 5e5,
    'c_t_onset': 250.0,
    'batch_size': 440.0,
    'reactor_len': 8.0,
    'reactor_dia': 3.0,
    'rotation_speed': 3.0,
    'heat_transfer_coeff': 80.0,
    'starting_temp': 25.0,
    'heating_rate': 10.0,
    'holding_temp': 550.0,
    'holding_time': 60.0,
    'auto_heating_rate': False,
    'burner_hp': 300.0,
    'burner_eff_pct': 85.0,
    'syngas_hp': 150.0,
    'fuel_type': "Waste Oil / Aceite Residual",
    'fuel_lhv': 41.0,
    'fuel_density': 0.90,
    'fuel_moisture': 1.0,
    'fuel_ash': 0.5,
    'shell_material': "Carbon Steel",
    'shell_thickness_mm': 15.0,
    'h_loss': 5.0,
    'sludge_density': 944.7,
    'custom_cp_oil': 1800.0,
    'custom_cp_char': 1000.0,
    'custom_cp_ash': 800.0,
    'bio_oil_density': 750.0,
    'bio_char_density': 500.0,
    'capex_equip': 9000000.0,
    'capex_install': 3150000.0,
    'capex_civil': 2250000.0,
    'capex_piping_elec': 2250000.0,
    'capex_eng': 1350000.0,
    'capex_permits': 450000.0,
    'capex_cont': 900000.0,
    'opex_handling': 3.00,
    'opex_tipping': 9.00,                 # Y: disposal fee charged (RD$/gal)
    'econ_sludge_cost': 0.0,              # X: sludge purchase cost (RD$/gal)
    'econ_sludge_scenario': 'tipping',    # 'purchase' (−X), 'free' (0) or 'tipping' (+Y)
    'opex_fuel': 180.00,
    'opex_electricity': 7.50,
    'opex_aux_utilities': 300000.0,
    'price_generator_fuel': 262.80,
    'gen_diesel_batch': 1.0,
    'opex_labor': 3000000.0,
    'opex_maint': 3.0,
    'opex_insurance_tax': 1.0,
    'price_oil': 120.00,
    'price_char': 21.00,
    'price_gas': 3.60,
    'price_carbon': 1200.0,
    'rate_carbon_offset': 2.2,
    'discount_rate': 14.0,
    'project_lifetime': 10,
    'annual_days': 246,
    'shutdown_days': 15,
    'holidays_days': 15,
    'motor_power': 15.0,
    'batch_turnaround_h': 1.0,
    'batch_cooldown_h': 0.5,
    'batch_loading_h': 0.5,
    'batches_before_cleaning': 20,
    'maint_cooldown_h': 6.0,
    'cleaning_time_h': 4.0,
    # Plant data for the economics; 0 = use the simulated value
    'econ_batches_per_year': 0,
    'econ_oil_gal_per_batch': 0.0,
    'econ_fuel_gal_per_batch': 0.0,
    'tax_rate': 25.0,
    'inflation_rate': 4.0,
    'manifold_main_dia_in': 8.0,
    'manifold_branch_dia_in': 4.0,
    'manifold_num_branches': 4,
    'cooling_tank_gal': 28000.0,
    'autogenous_purge': True
}

def apply_profile(profile_key):
    """Carga un perfil completo en session_state: 'general' restablece los valores por defecto
    y 'tesis' aplica además los datos de la corrida documentada."""
    from pyrolysis.profiles import PROFILE_THESIS, THESIS_GUI_OVERRIDES, THESIS_PROFILE_VERSION
    params = dict(DEFAULT_PARAMS)
    if profile_key == PROFILE_THESIS:
        params.update(THESIS_GUI_OVERRIDES)
        params['profile_version'] = THESIS_PROFILE_VERSION
    params['profile'] = profile_key
    params['lang_option'] = st.session_state.get('lang_option', DEFAULT_PARAMS['lang_option'])
    for k, v in params.items():
        st.session_state[k] = v


def load_saved_config(config):
    """Copies a saved configuration (localStorage or uploaded JSON) into session_state.
    Keys not in DEFAULT_PARAMS (e.g. the removed continuous-mode settings in old configurations) are ignored.
    A thesis-profile configuration saved with an older profile version gets the current profile values
    again; returns True when that happened."""
    from pyrolysis.profiles import PROFILE_THESIS, THESIS_PROFILE_VERSION
    for k in DEFAULT_PARAMS.keys():
        if k in config:
            st.session_state[k] = config[k]
    if config.get('profile') == PROFILE_THESIS and config.get('profile_version') != THESIS_PROFILE_VERSION:
        apply_profile(PROFILE_THESIS)
        return True
    return False


def init_session_state():
    """Initializes session state with defaults, then loads this browser's saved configuration from localStorage.
    Nothing is read from a server-side file: each visitor only sees their own settings."""
    for k, v in DEFAULT_PARAMS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Streamlit drops the state of widgets that a run does not draw (a hidden section, or a st.rerun()
    # issued before the navigation is drawn). Re-assigning the values at the start of every run keeps
    # them: the economic inputs, and the active section.
    for k in list(DEFAULT_PARAMS) + ['nav_section']:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]

    if not st.session_state.get('local_storage_loaded', False):
        from pyrolysis.gui.local_storage import local_storage_get
        ls_config = local_storage_get("pyrolysis_config", key_suffix="init")
        # None = the browser has not answered yet; a dict means the check finished
        if isinstance(ls_config, dict):
            if "__empty__" not in ls_config:
                load_saved_config(ls_config)
            st.session_state['local_storage_loaded'] = True
            st.session_state['_last_saved_config'] = {k: st.session_state[k] for k in DEFAULT_PARAMS.keys()}
            st.rerun()

def render_config_manager(current_config_data):
    """Renders the config manager section at the bottom of the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader(t("config_manager_title"))

    # Compile the full configuration including session state values for all parameters
    full_config_data = {}
    for k in DEFAULT_PARAMS.keys():
        if k in current_config_data:
            full_config_data[k] = current_config_data[k]
        elif k in st.session_state:
            full_config_data[k] = st.session_state[k]
        else:
            full_config_data[k] = DEFAULT_PARAMS[k]
        try:  # Streamlit refuses to set a widget key whose widget was already drawn this run
            st.session_state[k] = full_config_data[k]
        except Exception:
            pass

    # Auto-save configuration to browser localStorage whenever any parameter changes
    if st.session_state.get('local_storage_loaded', False):
        last_saved = st.session_state.get('_last_saved_config', None)
        if last_saved != full_config_data:
            from pyrolysis.gui.local_storage import local_storage_set
            local_storage_set("pyrolysis_config", full_config_data, key_suffix="auto_save")
            st.session_state['_last_saved_config'] = dict(full_config_data)

    # Save to browser localStorage manually
    if st.sidebar.button(t("save_config_default"), key="save_config_btn", use_container_width=True):
        st.session_state['trigger_save_ls'] = True

    if st.session_state.get('trigger_save_ls', False):
        from pyrolysis.gui.local_storage import local_storage_set
        res = local_storage_set("pyrolysis_config", full_config_data, key_suffix="save_action")
        if res is True:
            st.session_state['trigger_save_ls'] = False
            st.sidebar.success(t("config_saved_success"))
            st.rerun()

    # Download current configuration
    config_json_bytes = json.dumps(full_config_data, indent=4).encode('utf-8')
    st.sidebar.download_button(
        label=t("download_config_btn"),
        data=config_json_bytes,
        file_name="pyrolysis_config.json",
        mime="application/json",
        use_container_width=True
    )

    # Upload configuration file
    uploaded_file = st.sidebar.file_uploader(t("upload_config_label"), type=["json"])
    if uploaded_file is not None:
        try:
            load_saved_config(json.load(uploaded_file))
            st.sidebar.success(t("config_loaded_success"))
            st.rerun()
        except Exception:
            st.sidebar.error(t("error_loading_config"))
