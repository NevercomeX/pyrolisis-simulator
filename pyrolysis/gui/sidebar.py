import streamlit as st
import numpy as np
from pyrolysis import (
    Feedstock,
    PETROLEUM_SLUDGE,
    HYDROCARBON_SLUDGE,
    blend_feedstocks,
    TRANSLATIONS
)
from .config_manager import DEFAULT_PARAMS

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def render_sidebar():
    """
    Renders the configuration and operation widgets in the Streamlit sidebar.
    
    Returns:
        dict: A dictionary containing all the active simulation and configuration parameters.
    """
    # Language selector at top of sidebar
    lang_option_list = ["English", "Español"]
    default_lang_idx = (
        lang_option_list.index(st.session_state['lang_option'])
        if st.session_state.get('lang_option') in lang_option_list
        else 1
    )
    lang_option = st.sidebar.selectbox("🌐 Language / Idioma", lang_option_list, index=default_lang_idx)
    st.session_state['lang_option'] = lang_option
    lang = 'en' if lang_option == "English" else 'es'

    # Operation Mode Selection
    st.sidebar.header(t("op_mode"))
    mode_continuous_str = t("mode_continuous")
    mode_batch_str = t("mode_batch")
    mode_options_list = [mode_continuous_str, mode_batch_str]
    default_mode_idx = 0 if st.session_state.get('mode_option') == "Continuous Operation" else 1
    mode_option_translated = st.sidebar.radio(
        t("select_op_mode"),
        mode_options_list,
        index=default_mode_idx
    )
    mode_option = "Continuous Operation" if mode_option_translated == mode_continuous_str else "Batch Operation"
    st.session_state['mode_option'] = mode_option

    st.sidebar.markdown("---")
    st.sidebar.header(t("feedstock_cond"))

    feed_blend_str = t("feed_blend")
    feed_petroleum_str = t("feed_petroleum")
    feed_hydrocarbon_str = t("feed_hydrocarbon")
    feed_custom_str = t("feed_custom")

    feed_options_list = [feed_blend_str, feed_petroleum_str, feed_hydrocarbon_str, feed_custom_str]
    
    # Map stored feed_option string to index
    stored_feed = st.session_state.get('feed_option', "Blend (Petroleum + Hydrocarbon)")
    if stored_feed == "Petroleum Sludge Only":
        default_feed_idx = 1
    elif stored_feed == "Hydrocarbon Sludge Only":
        default_feed_idx = 2
    elif stored_feed == "Blend (Petroleum + Hydrocarbon)":
        default_feed_idx = 0
    else:  # Custom Feedstock
        default_feed_idx = 3

    feed_option_translated = st.sidebar.selectbox(
        t("select_feed_type"),
        feed_options_list,
        index=default_feed_idx
    )

    # Initialize default feedstock values in case they aren't rendered
    c_moist = float(st.session_state.get('c_moist', 30.0))
    c_vol = float(st.session_state.get('c_vol', 50.0))
    c_fc = float(st.session_state.get('c_fc', 10.0))
    c_ash = float(st.session_state.get('c_ash', 10.0))
    c_ea = float(st.session_state.get('c_ea', 100.0)) * 1000.0
    c_a = float(st.session_state.get('c_a', 1e7))
    c_y_oil = float(st.session_state.get('c_y_oil', 60.0)) / 100.0
    c_y_gas = float(st.session_state.get('c_y_gas', 25.0)) / 100.0
    c_y_char = float(st.session_state.get('c_y_char', 15.0)) / 100.0
    blend_ratio = float(st.session_state.get('blend_ratio', 50.0)) / 100.0

    use_advanced = bool(st.session_state.get('use_advanced_kinetics', False))
    c_ea1 = float(st.session_state.get('c_ea1', 120.0)) * 1000.0
    c_a1 = float(st.session_state.get('c_a1', 6e6))
    c_ea2 = float(st.session_state.get('c_ea2', 125.0)) * 1000.0
    c_a2 = float(st.session_state.get('c_a2', 4e6))
    c_ea3 = float(st.session_state.get('c_ea3', 100.0)) * 1000.0
    c_a3 = float(st.session_state.get('c_a3', 5e5))

    # Define current feedstock based on selection
    if feed_option_translated == feed_petroleum_str:
        current_feed = PETROLEUM_SLUDGE
        feed_option = "Petroleum Sludge Only"
        c_ea1 = current_feed.Ea1
        c_a1 = current_feed.A1
        c_ea2 = current_feed.Ea2
        c_a2 = current_feed.A2
        c_ea3 = current_feed.Ea3
        c_a3 = current_feed.A3
    elif feed_option_translated == feed_hydrocarbon_str:
        current_feed = HYDROCARBON_SLUDGE
        feed_option = "Hydrocarbon Sludge Only"
        c_ea1 = current_feed.Ea1
        c_a1 = current_feed.A1
        c_ea2 = current_feed.Ea2
        c_a2 = current_feed.A2
        c_ea3 = current_feed.Ea3
        c_a3 = current_feed.A3
    elif feed_option_translated == feed_blend_str:
        feed_option = "Blend (Petroleum + Hydrocarbon)"
        blend_ratio = st.sidebar.slider(
            t("petroleum_frac"),
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state.get('blend_ratio', 50.0)),
            step=5.0
        ) / 100.0
        current_feed = blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, blend_ratio)
        c_ea1 = current_feed.Ea1
        c_a1 = current_feed.A1
        c_ea2 = current_feed.Ea2
        c_a2 = current_feed.A2
        c_ea3 = current_feed.Ea3
        c_a3 = current_feed.A3
    else:  # Custom
        feed_option = "Custom Feedstock"
        st.sidebar.markdown(t("custom_props"))
        c_moist = st.sidebar.slider(t("moisture_val"), 0.0, 90.0, float(st.session_state.get('c_moist', 30.0)), 1.0)
        c_vol = st.sidebar.slider(t("volatile_val"), 5.0, 95.0, float(st.session_state.get('c_vol', 50.0)), 1.0)
        c_fc = st.sidebar.slider(t("fixed_carbon_val"), 0.0, 50.0, float(st.session_state.get('c_fc', 10.0)), 1.0)
        c_ash = st.sidebar.slider(t("ash_val"), 0.0, 50.0, float(st.session_state.get('c_ash', 10.0)), 1.0)
        
        total = c_moist + c_vol + c_fc + c_ash
        if abs(total - 100.0) > 1e-2:
            st.sidebar.warning(t("normalize_warn").format(total))
            
        st.sidebar.markdown(t("pyro_kinetics"))
        use_advanced = st.sidebar.checkbox(
            t("use_advanced_kinetics"),
            value=bool(st.session_state.get('use_advanced_kinetics', False)),
            key="use_advanced_kinetics"
        )
        
        if use_advanced:
            st.sidebar.markdown(f"*{t('kinetics_multi_step_desc')}*")
            c_ea1_input = st.sidebar.number_input(t("ea1_label"), 40.0, 300.0, float(st.session_state.get('c_ea1', 120.0)), 5.0)
            c_a1 = st.sidebar.number_input(t("a1_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a1', 6e6)), format="%e")
            
            c_ea2_input = st.sidebar.number_input(t("ea2_label"), 40.0, 300.0, float(st.session_state.get('c_ea2', 125.0)), 5.0)
            c_a2 = st.sidebar.number_input(t("a2_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a2', 4e6)), format="%e")
            
            c_ea3_input = st.sidebar.number_input(t("ea3_label"), 40.0, 300.0, float(st.session_state.get('c_ea3', 100.0)), 5.0)
            c_a3 = st.sidebar.number_input(t("a3_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a3', 5e5)), format="%e")
            
            c_ea1 = c_ea1_input * 1000.0
            c_ea2 = c_ea2_input * 1000.0
            c_ea3 = c_ea3_input * 1000.0
            
            st.session_state['c_ea1'] = c_ea1_input
            st.session_state['c_a1'] = c_a1
            st.session_state['c_ea2'] = c_ea2_input
            st.session_state['c_a2'] = c_a2
            st.session_state['c_ea3'] = c_ea3_input
            st.session_state['c_a3'] = c_a3
            
            c_ea = c_ea1
            c_a = c_a1 + c_a2
            c_y_oil = c_a1 / c_a if c_a > 0 else 0.60
            c_y_gas = c_a2 / c_a if c_a > 0 else 0.25
            c_y_char = max(0.0, 1.0 - (c_y_oil + c_y_gas))
        else:
            c_ea_input = st.sidebar.number_input(t("activation_energy"), 40.0, 300.0, float(st.session_state.get('c_ea', 100.0)), 5.0)
            c_a = st.sidebar.number_input(t("pre_exponential"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a', 1e7)), format="%e")
            c_ea = c_ea_input * 1000.0
            st.session_state['c_ea'] = c_ea_input
            st.session_state['c_a'] = c_a
            
            st.sidebar.markdown(t("pyro_yields"))
            c_y_oil = st.sidebar.slider(t("bio_oil_yield"), 10.0, 90.0, float(st.session_state.get('c_y_oil', 60.0)), 5.0) / 100.0
            c_y_gas = st.sidebar.slider(t("syngas_yield"), 10.0, 90.0, float(st.session_state.get('c_y_gas', 25.0)), 5.0) / 100.0
            c_y_char = st.sidebar.slider(t("char_yield"), 0.0, 50.0, float(st.session_state.get('c_y_char', 15.0)), 5.0) / 100.0
            
            c_ea1 = c_ea
            c_a1 = c_a * c_y_oil
            c_ea2 = c_ea
            c_a2 = c_a * (c_y_gas + c_y_char)
            c_ea3 = 100.0 * 1000.0
            c_a3 = 5e5
            
            st.session_state['c_ea1'] = c_ea1 / 1000.0
            st.session_state['c_a1'] = c_a1
            st.session_state['c_ea2'] = c_ea2 / 1000.0
            st.session_state['c_a2'] = c_a2
            st.session_state['c_ea3'] = c_ea3 / 1000.0
            st.session_state['c_a3'] = c_a3
            
        current_feed = Feedstock(
            name="Custom Sludge" if lang == 'en' else "Lodo Personalizado",
            moisture=c_moist,
            volatile=c_vol,
            fixed_carbon=c_fc,
            ash=c_ash,
            E_a=c_ea,
            A=c_a,
            yield_oil=c_y_oil,
            yield_gas=c_y_gas,
            yield_char=c_y_char,
            Ea1=c_ea1, A1=c_a1,
            Ea2=c_ea2, A2=c_a2,
            Ea3=c_ea3, A3=c_a3
        )

    st.session_state['feed_option'] = feed_option
    if feed_option == "Blend (Petroleum + Hydrocarbon)":
        st.session_state['blend_ratio'] = blend_ratio * 100.0

    # Mode-specific feed config and initialization
    feed_rate_kgh = float(st.session_state.get('feed_rate', 100.0))
    temp_inlet_c = float(st.session_state.get('feed_inlet_temp', 25.0))
    
    # Dynamic conversion using configured sludge density
    sludge_dens_val = float(st.session_state.get('sludge_density', 900.0))
    KG_PER_GALLON = (sludge_dens_val / 1000.0) * 3.785411784
    batch_load_gal = float(st.session_state.get('batch_size', 440.0))

    if mode_option == "Continuous Operation":
        feed_rate_kgh = st.sidebar.slider(t("feed_rate"), 10.0, 1000.0, float(st.session_state.get('feed_rate', 100.0)), 10.0)
        temp_inlet_c = st.sidebar.slider(t("feed_inlet_temp"), 0.0, 100.0, float(st.session_state.get('feed_inlet_temp', 25.0)), 5.0)
        batch_load_kg = batch_load_gal * KG_PER_GALLON
    else:
        batch_load_gal = st.sidebar.slider(
            t("batch_size"), 
            0.0, 
            30000.0, 
            float(st.session_state.get('batch_size', 440.0)), 
            100.0
        )
        batch_load_kg = batch_load_gal * KG_PER_GALLON

    bio_oil_density = st.sidebar.slider(
        t("bio_oil_density"),
        700.0,
        1300.0,
        float(st.session_state.get('bio_oil_density', 750.0)),
        10.0,
        key="bio_oil_density"
    )

    # Reactor geometry
    st.sidebar.markdown("---")
    st.sidebar.header(t("reactor_geom"))
    length = st.sidebar.slider(t("reactor_len"), 1.0, 30.0, float(st.session_state.get('reactor_len', 8.0)), 0.5)
    diameter = st.sidebar.slider(t("reactor_dia"), 0.1, 10.0, float(st.session_state.get('reactor_dia', 3.0)), 0.05)
    rpm = st.sidebar.slider(t("rotation_speed"), 0.5, 15.0, float(st.session_state.get('rotation_speed', 3.0)), 0.5)

    slope_pct = float(st.session_state.get('reactor_slope', 2.0))
    slope = slope_pct / 100.0
    if mode_option == "Continuous Operation":
        slope_pct = st.sidebar.slider(t("reactor_slope"), 0.5, 10.0, float(st.session_state.get('reactor_slope', 2.0)), 0.1)
        slope = slope_pct / 100.0

    # Heating configuration
    st.sidebar.markdown("---")
    st.sidebar.header(t("heating_config"))
    h_eff = st.sidebar.slider(t("heat_transfer_coeff"), 10.0, 200.0, float(st.session_state.get('heat_transfer_coeff', 80.0)), 1.0)

    # Burner and Shell Calibration expander
    with st.sidebar.expander(t("burner_calib_header"), expanded=False):
        auto_heating_rate = st.checkbox(
            t("auto_heating_rate"),
            value=bool(st.session_state.get('auto_heating_rate', False))
        )
        
        # Steel material properties database
        materials = {
            t("steel_carbon"): {'density': 7850.0, 'Cp': 480.0, 'k': 50.0},
            t("steel_ss304"): {'density': 8000.0, 'Cp': 500.0, 'k': 16.2},
            t("steel_ss316"): {'density': 8000.0, 'Cp': 500.0, 'k': 16.3},
            t("steel_alloy"): {'density': 7800.0, 'Cp': 460.0, 'k': 26.0}
        }
        material_keys = list(materials.keys())
        
        # Load stored material or default to carbon steel
        stored_material = st.session_state.get('shell_material', 'Carbon Steel')
        default_mat_idx = 0
        if stored_material in ["Stainless Steel 304", "Acero Inoxidable 304"]:
            default_mat_idx = 1
        elif stored_material in ["Stainless Steel 316", "Acero Inoxidable 316"]:
            default_mat_idx = 2
        elif stored_material in ["Refractory Alloy Steel", "Acero Aleado / Refractario"]:
            default_mat_idx = 3
            
        selected_material_label = st.selectbox(
            t("shell_material"),
            material_keys,
            index=default_mat_idx
        )
        selected_material_dict = materials[selected_material_label]
        
        # Map back to English string for JSON config compatibility
        english_mat_names = ["Carbon Steel", "Stainless Steel 304", "Stainless Steel 316", "Refractory Alloy Steel"]
        shell_material_saved = english_mat_names[material_keys.index(selected_material_label)]
        
        shell_thickness_mm = st.slider(
            t("shell_thickness"),
            5.0, 50.0,
            float(st.session_state.get('shell_thickness_mm', 15.0)),
            1.0
        )
        
        burner_hp = st.slider(
            t("burner_hp"),
            10.0, 2000.0,
            float(st.session_state.get('burner_hp', 300.0)),
            10.0
        )
        
        burner_eff_pct = st.slider(
            t("burner_eff"),
            10.0, 100.0,
            float(st.session_state.get('burner_eff_pct', 70.0)),
            5.0
        )
        
        syngas_hp = st.slider(
            t("syngas_hp"),
            0.0, 1000.0,
            float(st.session_state.get('syngas_hp', 150.0)),
            10.0
        )
        
        h_loss = st.slider(
            t("h_loss"),
            0.0, 30.0,
            float(st.session_state.get('h_loss', 5.0)),
            0.5
        )
        
        sludge_density = st.slider(
            t("sludge_density"),
            500.0, 2000.0,
            float(st.session_state.get('sludge_density', 900.0)),
            50.0
        )
        
        custom_cp_oil = st.slider(
            t("custom_cp_oil"),
            1000.0, 3000.0,
            float(st.session_state.get('custom_cp_oil', 1800.0)),
            50.0
        )
        
        custom_cp_char = st.slider(
            t("custom_cp_char"),
            500.0, 2000.0,
            float(st.session_state.get('custom_cp_char', 1000.0)),
            50.0
        )
        
        custom_cp_ash = st.slider(
            t("custom_cp_ash"),
            500.0, 2000.0,
            float(st.session_state.get('custom_cp_ash', 800.0)),
            50.0
        )

    # New: Burner Fuel Configuration expander in the sidebar
    with st.sidebar.expander(t("fuel_config_title"), expanded=False):
        fuel_presets = {
            "Waste Oil / Aceite Residual": {'lhv': 41.0, 'density': 0.90, 'moisture': 1.0, 'ash': 0.5},
            "Diesel": {'lhv': 42.6, 'density': 0.84, 'moisture': 0.05, 'ash': 0.01},
            "Fuel Oil": {'lhv': 40.0, 'density': 0.95, 'moisture': 0.5, 'ash': 0.1}
        }
        preset_names = list(fuel_presets.keys())
        
        if 'fuel_type' not in st.session_state:
            st.session_state.fuel_type = "Waste Oil / Aceite Residual"
            
        default_idx = preset_names.index(st.session_state.fuel_type) if st.session_state.fuel_type in preset_names else 0
        
        selected_type = st.selectbox(
            t("fuel_type_label"),
            preset_names,
            index=default_idx,
            key='fuel_type_select_sidebar'
        )
        
        is_custom = (selected_type == "Waste Oil / Aceite Residual")
        
        if not is_custom:
            st.session_state.fuel_type = selected_type
            preset = fuel_presets[selected_type]
            st.session_state.fuel_lhv = preset['lhv']
            st.session_state.fuel_density = preset['density']
            st.session_state.fuel_moisture = preset['moisture']
            st.session_state.fuel_ash = preset['ash']
        else:
            previous_type = st.session_state.get('fuel_type', "Waste Oil / Aceite Residual")
            if previous_type != "Waste Oil / Aceite Residual":
                preset = fuel_presets["Waste Oil / Aceite Residual"]
                st.session_state.fuel_lhv = preset['lhv']
                st.session_state.fuel_density = preset['density']
                st.session_state.fuel_moisture = preset['moisture']
                st.session_state.fuel_ash = preset['ash']
            st.session_state.fuel_type = "Waste Oil / Aceite Residual"
            
        fuel_lhv = st.number_input(
            t("fuel_lhv_label"),
            min_value=1.0,
            max_value=100.0,
            value=float(st.session_state.get('fuel_lhv', 41.0)),
            step=0.5,
            disabled=not is_custom,
            key='fuel_lhv_val_sidebar'
        )
        if is_custom:
            st.session_state.fuel_lhv = fuel_lhv
            
        fuel_density = st.number_input(
            t("fuel_density_label"),
            min_value=0.1,
            max_value=3.0,
            value=float(st.session_state.get('fuel_density', 0.90)),
            step=0.01,
            disabled=not is_custom,
            key='fuel_density_val_sidebar'
        )
        if is_custom:
            st.session_state.fuel_density = fuel_density
            
        fuel_moisture = st.number_input(
            t("fuel_moisture_label"),
            min_value=0.0,
            max_value=90.0,
            value=float(st.session_state.get('fuel_moisture', 1.0)),
            step=0.1,
            disabled=not is_custom,
            key='fuel_moisture_val_sidebar'
        )
        if is_custom:
            st.session_state.fuel_moisture = fuel_moisture
            
        fuel_ash = st.number_input(
            t("fuel_ash_label"),
            min_value=0.0,
            max_value=50.0,
            value=float(st.session_state.get('fuel_ash', 0.5)),
            step=0.1,
            disabled=not is_custom,
            key='fuel_ash_val_sidebar'
        )
        if is_custom:
            st.session_state.fuel_ash = fuel_ash
            
        x_comb = 100.0 - st.session_state.fuel_moisture - st.session_state.fuel_ash
        LHV_eff = st.session_state.fuel_lhv * (x_comb/100.0) - 2.256 * (st.session_state.fuel_moisture/100.0)
        
        info_label = "Fracción Combustible Útil" if get_lang() == 'es' else "Useful Combustible Fraction"
        info_lhv = "Poder Calorífico Efectivo (base húmeda)" if get_lang() == 'es' else "Effective LHV (wet basis)"
        
        st.info(
            f"**{info_label}:** `{x_comb:.2f} %`  \n"
            f"**{info_lhv}:** `{LHV_eff:.2f} MJ/kg`"
        )

    # Pre-declare/initialize heating params to avoid unbound variables
    T_wall_type_str = "uniform"
    T_wall_params = {}
    t_uniform = float(st.session_state.get('wall_temp', 550.0))
    t_in = float(st.session_state.get('wall_temp_inlet', 300.0))
    t_out = float(st.session_state.get('wall_temp_outlet', 600.0))
    t_z1 = float(st.session_state.get('zone_1', 350.0))
    t_z2 = float(st.session_state.get('zone_2', 550.0))
    t_z3 = float(st.session_state.get('zone_3', 500.0))
    
    temp_start_c = float(st.session_state.get('starting_temp', 25.0))
    heating_rate_cmin = float(st.session_state.get('heating_rate', 10.0))
    temp_hold_c = float(st.session_state.get('holding_temp', 550.0))
    hold_time_min = float(st.session_state.get('holding_time', 60.0))

    if mode_option == "Continuous Operation":
        heating_uniform_str = t("heating_uniform")
        heating_linear_str = t("heating_linear")
        heating_zones_str = t("heating_zones")
        
        wall_heating_options = [heating_uniform_str, heating_linear_str, heating_zones_str]
        
        stored_heating = st.session_state.get('wall_heating_type', 'uniform')
        if stored_heating == 'linear':
            default_wall_idx = 1
        elif stored_heating == 'zones':
            default_wall_idx = 2
        else:
            default_wall_idx = 0
            
        wall_profile_type_translated = st.sidebar.selectbox(
            t("wall_heating_type"),
            wall_heating_options,
            index=default_wall_idx
        )
        
        if wall_profile_type_translated == heating_uniform_str:
            t_uniform = st.sidebar.slider(t("wall_temp"), 300.0, 800.0, float(st.session_state.get('wall_temp', 550.0)), 10.0)
            T_wall_params = {'T_wall': t_uniform}
            T_wall_type_str = 'uniform'
        elif wall_profile_type_translated == heating_linear_str:
            t_in = st.sidebar.slider(t("wall_temp_inlet"), 200.0, 600.0, float(st.session_state.get('wall_temp_inlet', 300.0)), 10.0)
            t_out = st.sidebar.slider(t("wall_temp_outlet"), 400.0, 900.0, float(st.session_state.get('wall_temp_outlet', 600.0)), 10.0)
            T_wall_params = {'T_wall_in': t_in, 'T_wall_out': t_out}
            T_wall_type_str = 'linear'
        else:  # 3-Zone
            st.sidebar.markdown(t("zone_temps"))
            t_z1 = st.sidebar.slider(t("zone_1"), 200.0, 500.0, float(st.session_state.get('zone_1', 350.0)), 10.0)
            t_z2 = st.sidebar.slider(t("zone_2"), 400.0, 800.0, float(st.session_state.get('zone_2', 550.0)), 10.0)
            t_z3 = st.sidebar.slider(t("zone_3"), 300.0, 700.0, float(st.session_state.get('zone_3', 500.0)), 10.0)
            T_wall_params = {'zones': [(0.3, t_z1), (0.7, t_z2), (1.0, t_z3)]}
            T_wall_type_str = 'zones'
    else:
        st.sidebar.markdown(t("batch_temp_prog"))
        temp_start_c = st.sidebar.slider(t("starting_temp"), 10.0, 300.0, float(st.session_state.get('starting_temp', 25.0)), 5.0)
        
        if auto_heating_rate:
            # Dynamically compute nominal heating rate based on physical mass
            t_steel = shell_thickness_mm / 1000.0
            rho_steel = selected_material_dict['density']
            M_steel = np.pi * diameter * length * t_steel * rho_steel
            C_steel = M_steel * selected_material_dict['Cp']
            
            fracs = current_feed.get_fractions()
            m_moist = batch_load_kg * fracs['moisture']
            m_volatile = batch_load_kg * fracs['volatile']
            m_char = batch_load_kg * fracs['fixed_carbon']
            m_ash = batch_load_kg * fracs['ash']
            m_solid_total = m_moist + m_volatile + m_char + m_ash
            
            Cp_s_init = (m_moist * 4184.0 + m_volatile * custom_cp_oil + m_char * custom_cp_char + m_ash * custom_cp_ash) / m_solid_total if m_solid_total > 0 else 1000.0
            C_solids_init = m_solid_total * Cp_s_init
            
            Q_main_nominal = burner_hp * 745.7 * (burner_eff_pct / 100.0)
            C_total_init = C_steel + C_solids_init
            nominal_rate_csec = Q_main_nominal / C_total_init if C_total_init > 0 else 0.1
            heating_rate_cmin = nominal_rate_csec * 60.0
            
            st.sidebar.info(t("nominal_heating_rate_info").format(heating_rate_cmin))
        else:
            heating_rate_cmin = st.sidebar.slider(t("heating_rate"), 1.0, 500.0, float(st.session_state.get('heating_rate', 10.0)), 1.0)
            
        temp_hold_c = st.sidebar.slider(t("holding_temp"), 300.0, 800.0, float(st.session_state.get('holding_temp', 550.0)), 10.0)
        hold_time_min = st.sidebar.slider(t("holding_time"), 10.0, 3000.0, float(st.session_state.get('holding_time', 60.0)), 10.0)

    # Compile the active configurations dictionary
    config_dict = {
        'lang_option': lang_option,
        'mode_option': mode_option,
        'feed_option': feed_option,
        'blend_ratio': blend_ratio * 100.0 if feed_option == "Blend (Petroleum + Hydrocarbon)" else 50.0,
        'c_moist': float(c_moist),
        'c_vol': float(c_vol),
        'c_fc': float(c_fc),
        'c_ash': float(c_ash),
        'c_ea': float(c_ea / 1000.0),
        'c_a': float(c_a),
        'c_y_oil': float(c_y_oil * 100.0),
        'c_y_gas': float(c_y_gas * 100.0),
        'c_y_char': float(c_y_char * 100.0),
        'use_advanced_kinetics': bool(use_advanced),
        'c_ea1': float(c_ea1 / 1000.0),
        'c_a1': float(c_a1),
        'c_ea2': float(c_ea2 / 1000.0),
        'c_a2': float(c_a2),
        'c_ea3': float(c_ea3 / 1000.0),
        'c_a3': float(c_a3),
        'feed_rate': float(feed_rate_kgh),
        'feed_inlet_temp': float(temp_inlet_c),
        'batch_size': float(batch_load_gal),
        'reactor_len': float(length),
        'reactor_dia': float(diameter),
        'rotation_speed': float(rpm),
        'reactor_slope': float(slope_pct),
        'heat_transfer_coeff': float(h_eff),
        'wall_heating_type': T_wall_type_str if mode_option == "Continuous Operation" else "Uniform Temperature",
        'wall_temp': float(t_uniform),
        'wall_temp_inlet': float(t_in),
        'wall_temp_outlet': float(t_out),
        'zone_1': float(t_z1),
        'zone_2': float(t_z2),
        'zone_3': float(t_z3),
        'starting_temp': float(temp_start_c),
        'heating_rate': float(heating_rate_cmin),
        'holding_temp': float(temp_hold_c),
        'holding_time': float(hold_time_min),
        'auto_heating_rate': auto_heating_rate,
        'burner_hp': float(burner_hp),
        'burner_eff_pct': float(burner_eff_pct),
        'syngas_hp': float(syngas_hp),
        'shell_material': shell_material_saved,
        'shell_thickness_mm': float(shell_thickness_mm),
        'h_loss': float(h_loss),
        'sludge_density': float(sludge_density),
        'custom_cp_oil': float(custom_cp_oil),
        'custom_cp_char': float(custom_cp_char),
        'custom_cp_ash': float(custom_cp_ash),
        'bio_oil_density': float(bio_oil_density),
        'capex_equip': float(st.session_state.get('capex_equip', DEFAULT_PARAMS['capex_equip'])),
        'capex_install': float(st.session_state.get('capex_install', DEFAULT_PARAMS['capex_install'])),
        'capex_permits': float(st.session_state.get('capex_permits', DEFAULT_PARAMS['capex_permits'])),
        'capex_cont': float(st.session_state.get('capex_cont', DEFAULT_PARAMS['capex_cont'])),
        'opex_handling': float(st.session_state.get('opex_handling', DEFAULT_PARAMS['opex_handling'])),
        'opex_tipping': float(st.session_state.get('opex_tipping', DEFAULT_PARAMS['opex_tipping'])),
        'opex_fuel': float(st.session_state.get('opex_fuel', DEFAULT_PARAMS['opex_fuel'])),
        'price_generator_fuel': float(st.session_state.get('price_generator_fuel', DEFAULT_PARAMS['price_generator_fuel'])),
        'gen_diesel_rate': float(st.session_state.get('gen_diesel_rate', DEFAULT_PARAMS['gen_diesel_rate'])),
        'gen_diesel_batch': float(st.session_state.get('gen_diesel_batch', DEFAULT_PARAMS['gen_diesel_batch'])),
        'opex_labor': float(st.session_state.get('opex_labor', DEFAULT_PARAMS['opex_labor'])),
        'opex_maint': float(st.session_state.get('opex_maint', DEFAULT_PARAMS['opex_maint'])),
        'price_oil': float(st.session_state.get('price_oil', DEFAULT_PARAMS['price_oil'])),
        'price_char': float(st.session_state.get('price_char', DEFAULT_PARAMS['price_char'])),
        'price_gas': float(st.session_state.get('price_gas', DEFAULT_PARAMS['price_gas'])),
        'discount_rate': float(st.session_state.get('discount_rate', DEFAULT_PARAMS['discount_rate'])),
        'project_lifetime': int(st.session_state.get('project_lifetime', DEFAULT_PARAMS['project_lifetime'])),
        'annual_days': int(st.session_state.get('annual_days', DEFAULT_PARAMS['annual_days'])),
        'motor_power': float(st.session_state.get('motor_power', DEFAULT_PARAMS['motor_power'])),
        'batch_turnaround_h': float(st.session_state.get('batch_turnaround_h', DEFAULT_PARAMS['batch_turnaround_h']))
    }

    # Also build inputs for solvers
    solver_inputs = {
        'current_feed': current_feed,
        'feed_option': feed_option,
        'blend_ratio': blend_ratio,
        'feed_rate_kgh': feed_rate_kgh,
        'temp_inlet_c': temp_inlet_c,
        'batch_load_kg': batch_load_kg,
        'length': length,
        'diameter': diameter,
        'rpm': rpm,
        'slope': slope,
        'h_eff': h_eff,
        'T_wall_type_str': T_wall_type_str,
        'T_wall_params': T_wall_params,
        'temp_start_c': temp_start_c,
        'heating_rate_cmin': heating_rate_cmin,
        'temp_hold_c': temp_hold_c,
        'hold_time_min': hold_time_min,
        'auto_heating_rate': auto_heating_rate,
        'burner_hp': burner_hp,
        'burner_eff_pct': burner_eff_pct,
        'syngas_hp': syngas_hp,
        'shell_material_dict': selected_material_dict,
        'shell_thickness_mm': shell_thickness_mm,
        'h_loss': h_loss,
        'sludge_density': sludge_density,
        'custom_cp_oil': custom_cp_oil,
        'custom_cp_char': custom_cp_char,
        'custom_cp_ash': custom_cp_ash,
        'bio_oil_density': bio_oil_density
    }

    return config_dict, solver_inputs
