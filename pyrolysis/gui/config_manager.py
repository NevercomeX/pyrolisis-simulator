import streamlit as st
import json
import os

DEFAULT_PARAMS = {
    'lang_option': "English",
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
    'c_a1': 6e6,
    'c_ea2': 125.0,
    'c_a2': 4e6,
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
    'capex_equip': 150000.0,
    'capex_install': 40000.0,
    'capex_permits': 15000.0,
    'capex_cont': 10000.0,
    'opex_handling': 10.0,
    'opex_tipping': 40.0,
    'opex_fuel': 3.0,
    'price_generator_fuel': 3.0,
    'gen_diesel_rate': 1.2,
    'gen_diesel_batch': 1.0,
    'opex_labor': 50000.0,
    'opex_maint': 3.0,
    'price_oil': 0.40,
    'price_char': 0.15,
    'price_gas': 0.05,
    'discount_rate': 8.0,
    'project_lifetime': 10,
    'annual_days': 246,
    'motor_power': 15.0,
    'batch_turnaround_h': 1.0
}

CONFIG_FILE = "pyrolysis_config.json"

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'English')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    from pyrolysis import TRANSLATIONS
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def init_session_state():
    """Loads configuration on startup and initializes session state."""
    loaded_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
        except Exception:
            pass

    for k, v in DEFAULT_PARAMS.items():
        if k not in st.session_state:
            st.session_state[k] = loaded_config.get(k, v)

def render_config_manager(current_config_data):
    """Renders the config manager section at the bottom of the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader(t("config_manager_title"))

    # Compile the full configuration including session state values for all parameters
    full_config_data = {}
    for k in DEFAULT_PARAMS.keys():
        if k in st.session_state:
            full_config_data[k] = st.session_state[k]
        elif k in current_config_data:
            full_config_data[k] = current_config_data[k]
        else:
            full_config_data[k] = DEFAULT_PARAMS[k]

    # Save to local file config
    if st.sidebar.button(t("save_config_default"), width='stretch'):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(full_config_data, f, indent=4)
            st.sidebar.success(t("config_saved_success"))
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

    # Download current configuration
    config_json_bytes = json.dumps(full_config_data, indent=4).encode('utf-8')
    st.sidebar.download_button(
        label=t("download_config_btn"),
        data=config_json_bytes,
        file_name="pyrolysis_config.json",
        mime="application/json",
        width='stretch'
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
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        except Exception:
            st.sidebar.error(t("error_loading_config"))
