import streamlit as st
import json
import os

DEFAULT_PARAMS = {
    'lang_option': "Español",
    'mode_option': "Continuous Operation",
    'feed_option': "Blend (Petroleum + Hydrocarbon)",
    'blend_ratio': 50.0,
    'c_moist': 30.0,
    'c_vol': 50.0,
    'c_fc': 10.0,
    'c_ash': 10.0,
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
    'feed_rate': 100.0,
    'feed_inlet_temp': 25.0,
    'batch_size': 440.0,
    'reactor_len': 8.0,
    'reactor_dia': 3.0,
    'rotation_speed': 3.0,
    'reactor_slope': 2.0,
    'heat_transfer_coeff': 80.0,
    'wall_heating_type': "Uniform Temperature",
    'wall_temp': 550.0,
    'wall_temp_inlet': 300.0,
    'wall_temp_outlet': 600.0,
    'zone_1': 350.0,
    'zone_2': 550.0,
    'zone_3': 500.0,
    'starting_temp': 25.0,
    'heating_rate': 10.0,
    'holding_temp': 550.0,
    'holding_time': 60.0,
    'auto_heating_rate': False,
    'burner_hp': 300.0,
    'burner_eff_pct': 70.0,
    'syngas_hp': 150.0,
    'fuel_type': "Waste Oil / Aceite Residual",
    'fuel_lhv': 41.0,
    'fuel_density': 0.90,
    'fuel_moisture': 1.0,
    'fuel_ash': 0.5,
    'shell_material': "Carbon Steel",
    'shell_thickness_mm': 15.0,
    'h_loss': 5.0,
    'sludge_density': 900.0,
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
    'opex_tipping': 9.00,
    'opex_fuel': 180.00,
    'opex_electricity': 7.50,
    'opex_aux_utilities': 300000.0,
    'price_generator_fuel': 262.80,
    'gen_diesel_rate': 1.2,
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
    'motor_power': 15.0,
    'batch_turnaround_h': 1.0,
    'tax_rate': 25.0,
    'inflation_rate': 4.0,
    'manifold_main_dia_in': 8.0,
    'manifold_branch_dia_in': 4.0,
    'manifold_num_branches': 4,
    'cooling_tank_gal': 28000.0,
    'autogenous_purge': True
}

CONFIG_FILE = "pyrolysis_config.json"

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    from pyrolysis import TRANSLATIONS
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def init_session_state():
    """Loads configuration on startup from localStorage (with file fallback) and initializes session state."""
    # 1. First, make sure every default parameter is initialized in session state
    for k, v in DEFAULT_PARAMS.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # 2. Access localStorage using the custom component
    if not st.session_state.get('local_storage_loaded', False):
        from pyrolysis.gui.local_storage import local_storage_get
        ls_config = local_storage_get("pyrolysis_config", key_suffix="init")
        
        if ls_config is not None:
            if isinstance(ls_config, dict) and "__empty__" not in ls_config:
                # We found a configuration in localStorage! Apply it.
                for k in DEFAULT_PARAMS.keys():
                    if k in ls_config:
                        st.session_state[k] = ls_config[k]
                st.session_state['local_storage_loaded'] = True
                st.session_state['fallback_loaded'] = True
                st.session_state['_last_saved_config'] = {k: st.session_state[k] for k in DEFAULT_PARAMS.keys()}
                st.rerun()
            elif isinstance(ls_config, dict) and ls_config.get("__empty__", False):
                # The browser completed the check and found nothing. Try file fallback.
                if not st.session_state.get('fallback_loaded', False):
                    if os.path.exists(CONFIG_FILE):
                        try:
                            with open(CONFIG_FILE, 'r') as f:
                                loaded_config = json.load(f)
                                for k in DEFAULT_PARAMS.keys():
                                    if k in loaded_config:
                                        st.session_state[k] = loaded_config[k]
                        except Exception:
                            pass
                    st.session_state['fallback_loaded'] = True
                st.session_state['local_storage_loaded'] = True
                st.session_state['_last_saved_config'] = {k: st.session_state[k] for k in DEFAULT_PARAMS.keys()}
                st.rerun()
        else:
            # First frame fallback - load from JSON file while localStorage is fetching
            if not st.session_state.get('fallback_loaded', False):
                if os.path.exists(CONFIG_FILE):
                    try:
                        with open(CONFIG_FILE, 'r') as f:
                            loaded_config = json.load(f)
                            for k in DEFAULT_PARAMS.keys():
                                if k in loaded_config:
                                    st.session_state[k] = loaded_config[k]
                    except Exception:
                        pass
                st.session_state['fallback_loaded'] = True

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
        st.session_state[k] = full_config_data[k]

    # Auto-save configuration to browser localStorage whenever any parameter changes
    if st.session_state.get('local_storage_loaded', False):
        last_saved = st.session_state.get('_last_saved_config', None)
        if last_saved != full_config_data:
            from pyrolysis.gui.local_storage import local_storage_set
            local_storage_set("pyrolysis_config", full_config_data, key_suffix="auto_save")
            st.session_state['_last_saved_config'] = dict(full_config_data)
            try:
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(full_config_data, f, indent=4)
            except Exception:
                pass

    # Save to local storage (primary) and local file (fallback) manually
    if st.sidebar.button(t("save_config_default"), key="save_config_btn", use_container_width=True):
        st.session_state['trigger_save_ls'] = True
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(full_config_data, f, indent=4)
        except Exception:
            pass

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
            config_data = json.load(uploaded_file)
            # Update session state keys
            for k in DEFAULT_PARAMS.keys():
                if k in config_data:
                    st.session_state[k] = config_data[k]
            st.sidebar.success(t("config_loaded_success"))
            # Force rerun
            st.rerun()
        except Exception:
            st.sidebar.error(t("error_loading_config"))
