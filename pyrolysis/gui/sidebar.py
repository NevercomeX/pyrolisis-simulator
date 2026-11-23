import streamlit as st
import numpy as np
from pyrolysis import (
    Feedstock,
    PETROLEUM_SLUDGE,
    HYDROCARBON_SLUDGE,
    blend_feedstocks
)
from pyrolysis.reactor.base import BHP_TO_W
from .config_manager import DEFAULT_PARAMS
from .utils import t

LITERS_PER_GALLON = 3.785411784

# Stored feed_option (English, config JSON) -> position in the feedstock selectbox; anything else is Custom (3)
_FEED_OPTION_INDEX = {
    "Blend (Petroleum + Hydrocarbon)": 0,
    "Petroleum Sludge Only": 1,
    "Hydrocarbon Sludge Only": 2,
}

# Stored shell_material (English or older Spanish JSON) -> position in the material selectbox; else Carbon Steel (0)
_SHELL_MATERIAL_INDEX = {
    "Stainless Steel 304": 1, "Acero Inoxidable 304": 1,
    "Stainless Steel 316": 2, "Acero Inoxidable 316": 2,
    "Refractory Alloy Steel": 3, "Acero Aleado / Refractario": 3,
}
SHELL_MATERIAL_NAMES = ["Carbon Steel", "Stainless Steel 304", "Stainless Steel 316", "Refractory Alloy Steel"]

# Burner fuels: LHV (MJ/kg), density (kg/L), moisture and ash (wt%). Waste oil is the only editable one.
WASTE_OIL = "Waste Oil / Aceite Residual"
FUEL_PRESETS = {
    WASTE_OIL: {'lhv': 41.0, 'density': 0.90, 'moisture': 1.0, 'ash': 0.5},
    "Diesel": {'lhv': 42.6, 'density': 0.84, 'moisture': 0.05, 'ash': 0.01},
    "Fuel Oil": {'lhv': 40.0, 'density': 0.95, 'moisture': 0.5, 'ash': 0.1}
}
WATER_LATENT_HEAT_MJ_KG = 2.256
WATER_CP_J_KGK = 4184.0

# Parameters edited elsewhere (economics panel) that the sidebar passes through from session_state, with their type
_PASSTHROUGH_PARAMS = [
    ('capex_equip', float), ('capex_install', float), ('capex_civil', float), ('capex_piping_elec', float),
    ('capex_eng', float), ('capex_permits', float), ('capex_cont', float),
    ('opex_handling', float), ('opex_tipping', float), ('opex_fuel', float), ('opex_electricity', float),
    ('opex_aux_utilities', float), ('price_generator_fuel', float),
    ('gen_diesel_batch', float), ('opex_labor', float), ('opex_maint', float), ('opex_insurance_tax', float),
    ('price_oil', float), ('price_char', float), ('price_gas', float), ('price_carbon', float),
    ('rate_carbon_offset', float), ('discount_rate', float),
    ('project_lifetime', int), ('annual_days', int), ('shutdown_days', int), ('holidays_days', int),
    ('motor_power', float), ('batch_turnaround_h', float), ('batch_cooldown_h', float), ('batch_loading_h', float),
    ('batches_before_cleaning', int), ('maint_cooldown_h', float), ('cleaning_time_h', float),
    ('tax_rate', float), ('inflation_rate', float),
]


def _arrhenius_params(feed):
    """(Ea1, A1, Ea2, A2, Ea3, A3) of a feedstock, Ea in J/mol."""
    return feed.Ea1, feed.A1, feed.Ea2, feed.A2, feed.Ea3, feed.A3


def _nominal_heating_rate_cmin(feed, batch_load_kg, length, diameter, shell_thickness_mm, material,
                               burner_hp, cp_oil, cp_char, cp_ash):
    """Heating rate (°C/min) the burner nameplate gives when it heats the steel shell and the cold load."""
    t_steel = shell_thickness_mm / 1000.0
    M_steel = np.pi * diameter * length * t_steel * material['density']
    C_steel = M_steel * material['Cp']

    fracs = feed.get_fractions()
    m_moist = batch_load_kg * fracs['moisture']
    m_volatile = batch_load_kg * fracs['volatile']
    m_char = batch_load_kg * fracs['fixed_carbon']
    m_ash = batch_load_kg * fracs['ash']
    m_solid_total = m_moist + m_volatile + m_char + m_ash

    Cp_s_init = (m_moist * WATER_CP_J_KGK + m_volatile * cp_oil + m_char * cp_char + m_ash * cp_ash) / m_solid_total if m_solid_total > 0 else 1000.0
    C_solids_init = m_solid_total * Cp_s_init

    Q_main_nominal = burner_hp * BHP_TO_W   # nameplate in boiler hp = useful heat output
    C_total_init = C_steel + C_solids_init
    nominal_rate_csec = Q_main_nominal / C_total_init if C_total_init > 0 else 0.1
    return nominal_rate_csec * 60.0


def _set_fuel_properties(preset):
    st.session_state.fuel_lhv = preset['lhv']
    st.session_state.fuel_density = preset['density']
    st.session_state.fuel_moisture = preset['moisture']
    st.session_state.fuel_ash = preset['ash']


def _render_fuel_config(lang):
    """Burner fuel expander. Presets fill the fuel properties (read-only); waste oil can be edited.
    The values are kept in session_state (fuel_type, fuel_lhv, fuel_density, fuel_moisture, fuel_ash)."""
    with st.sidebar.expander(t("fuel_config_title"), expanded=False):
        preset_names = list(FUEL_PRESETS.keys())
        default_idx = preset_names.index(st.session_state.fuel_type) if st.session_state.fuel_type in preset_names else 0

        selected_type = st.selectbox(
            t("fuel_type_label"),
            preset_names,
            index=default_idx,
            key='fuel_type_select_sidebar'
        )

        editable = (selected_type == WASTE_OIL)
        if not editable:
            _set_fuel_properties(FUEL_PRESETS[selected_type])
        elif st.session_state.get('fuel_type', WASTE_OIL) != WASTE_OIL:
            # Coming back from a preset: start from the waste-oil values
            _set_fuel_properties(FUEL_PRESETS[WASTE_OIL])
        st.session_state.fuel_type = selected_type

        fuel_lhv = st.number_input(
            t("fuel_lhv_label"),
            min_value=1.0,
            max_value=100.0,
            value=float(st.session_state.get('fuel_lhv', 41.0)),
            step=0.5,
            disabled=not editable,
            key='fuel_lhv_val_sidebar'
        )
        if editable:
            st.session_state.fuel_lhv = fuel_lhv

        fuel_density = st.number_input(
            t("fuel_density_label"),
            min_value=0.1,
            max_value=3.0,
            value=float(st.session_state.get('fuel_density', 0.90)),
            step=0.01,
            disabled=not editable,
            key='fuel_density_val_sidebar'
        )
        if editable:
            st.session_state.fuel_density = fuel_density

        fuel_moisture = st.number_input(
            t("fuel_moisture_label"),
            min_value=0.0,
            max_value=90.0,
            value=float(st.session_state.get('fuel_moisture', 1.0)),
            step=0.1,
            disabled=not editable,
            key='fuel_moisture_val_sidebar'
        )
        if editable:
            st.session_state.fuel_moisture = fuel_moisture

        fuel_ash = st.number_input(
            t("fuel_ash_label"),
            min_value=0.0,
            max_value=50.0,
            value=float(st.session_state.get('fuel_ash', 0.5)),
            step=0.1,
            disabled=not editable,
            key='fuel_ash_val_sidebar'
        )
        if editable:
            st.session_state.fuel_ash = fuel_ash

        combustible_pct = 100.0 - st.session_state.fuel_moisture - st.session_state.fuel_ash
        lhv_wet_mj_kg = st.session_state.fuel_lhv * (combustible_pct/100.0) - WATER_LATENT_HEAT_MJ_KG * (st.session_state.fuel_moisture/100.0)

        info_label = "Fracción Combustible Útil" if lang == 'es' else "Useful Combustible Fraction"
        info_lhv = "Poder Calorífico Efectivo (base húmeda)" if lang == 'es' else "Effective LHV (wet basis)"

        st.info(
            f"**{info_label}:** `{combustible_pct:.2f} %`  \n"
            f"**{info_lhv}:** `{lhv_wet_mj_kg:.2f} MJ/kg`"
        )


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

    # Perfil de simulación: general (público) o caso de estudio de la tesis
    from pyrolysis.profiles import PROFILE_GENERAL, PROFILE_THESIS, PROFILE_LABELS, THESIS_NOTE
    from .config_manager import apply_profile
    profile_keys = [PROFILE_GENERAL, PROFILE_THESIS]
    current_profile = st.session_state.get('profile', PROFILE_GENERAL)
    if current_profile not in profile_keys:
        current_profile = PROFILE_GENERAL
    chosen_profile = st.sidebar.selectbox(
        "📁 Perfil" if lang == 'es' else "📁 Profile",
        profile_keys,
        index=profile_keys.index(current_profile),
        format_func=lambda k: PROFILE_LABELS[k][lang],
    )
    if chosen_profile != current_profile:
        apply_profile(chosen_profile)
        st.rerun()
    if chosen_profile == PROFILE_THESIS:
        st.sidebar.info(THESIS_NOTE[lang])
        if st.sidebar.button("↺ Restablecer datos de la corrida" if lang == 'es' else "↺ Reset run data",
                             use_container_width=True):
            apply_profile(PROFILE_THESIS)
            st.rerun()

    _box = st.sidebar.expander(t("feedstock_cond"), expanded=False)

    feed_blend_str = t("feed_blend")
    feed_petroleum_str = t("feed_petroleum")
    feed_hydrocarbon_str = t("feed_hydrocarbon")
    feed_custom_str = t("feed_custom")

    feed_options_list = [feed_blend_str, feed_petroleum_str, feed_hydrocarbon_str, feed_custom_str]
    stored_feed = st.session_state.get('feed_option', "Blend (Petroleum + Hydrocarbon)")
    feed_option_translated = _box.selectbox(
        t("select_feed_type"),
        feed_options_list,
        index=_FEED_OPTION_INDEX.get(stored_feed, 3)
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
        c_ea1, c_a1, c_ea2, c_a2, c_ea3, c_a3 = _arrhenius_params(current_feed)
    elif feed_option_translated == feed_hydrocarbon_str:
        current_feed = HYDROCARBON_SLUDGE
        feed_option = "Hydrocarbon Sludge Only"
        c_ea1, c_a1, c_ea2, c_a2, c_ea3, c_a3 = _arrhenius_params(current_feed)
    elif feed_option_translated == feed_blend_str:
        feed_option = "Blend (Petroleum + Hydrocarbon)"
        blend_ratio = _box.number_input(
            t("petroleum_frac"),
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state.get('blend_ratio', 50.0)),
            step=1.0,
            format="%.1f"
        ) / 100.0
        current_feed = blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, blend_ratio)
        c_ea1, c_a1, c_ea2, c_a2, c_ea3, c_a3 = _arrhenius_params(current_feed)
    else:  # Custom
        feed_option = "Custom Feedstock"
        _box.markdown(t("custom_props"))
        c_moist = _box.number_input(t("moisture_val"), min_value=0.0, max_value=90.0, value=float(st.session_state.get('c_moist', 30.0)), step=0.5, format="%.2f")
        c_vol = _box.number_input(t("volatile_val"), min_value=0.0, max_value=95.0, value=float(st.session_state.get('c_vol', 50.0)), step=0.5, format="%.2f")
        c_fc = _box.number_input(t("fixed_carbon_val"), min_value=0.0, max_value=50.0, value=float(st.session_state.get('c_fc', 10.0)), step=0.5, format="%.2f")
        c_ash = _box.number_input(t("ash_val"), min_value=0.0, max_value=50.0, value=float(st.session_state.get('c_ash', 10.0)), step=0.5, format="%.2f")
        
        c_t_onset = _box.number_input(
            "Temperatura de inicio de pirólisis (°C)" if lang == 'es' else "Pyrolysis onset temperature (°C)",
            min_value=100.0, max_value=600.0, value=float(st.session_state.get('c_t_onset', 250.0)),
            step=5.0, format="%.1f")
        st.session_state['c_t_onset'] = c_t_onset

        total = c_moist + c_vol + c_fc + c_ash
        if abs(total - 100.0) > 1e-2:
            _box.warning(t("normalize_warn").format(total))
            
        _box.markdown(t("pyro_kinetics"))
        use_advanced = _box.checkbox(
            t("use_advanced_kinetics"),
            value=bool(st.session_state.get('use_advanced_kinetics', False)),
            key="use_advanced_kinetics"
        )
        
        if use_advanced:
            _box.markdown(f"*{t('kinetics_multi_step_desc')}*")
            c_ea1_input = _box.number_input(t("ea1_label"), 40.0, 300.0, float(st.session_state.get('c_ea1', 120.0)), 5.0)
            c_a1 = _box.number_input(t("a1_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a1', 6e6)), format="%e")
            
            c_ea2_input = _box.number_input(t("ea2_label"), 40.0, 300.0, float(st.session_state.get('c_ea2', 125.0)), 5.0)
            c_a2 = _box.number_input(t("a2_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a2', 4e6)), format="%e")
            
            c_ea3_input = _box.number_input(t("ea3_label"), 40.0, 300.0, float(st.session_state.get('c_ea3', 100.0)), 5.0)
            c_a3 = _box.number_input(t("a3_label"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a3', 5e5)), format="%e")
            
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
            c_ea_input = _box.number_input(t("activation_energy"), 40.0, 300.0, float(st.session_state.get('c_ea', 100.0)), 5.0)
            c_a = _box.number_input(t("pre_exponential"), min_value=0.0, max_value=1e16, value=float(st.session_state.get('c_a', 1e7)), format="%e")
            c_ea = c_ea_input * 1000.0
            st.session_state['c_ea'] = c_ea_input
            st.session_state['c_a'] = c_a
            
            _box.markdown(t("pyro_yields"))
            c_y_oil = _box.number_input(t("bio_oil_yield"), min_value=0.0, max_value=100.0, value=float(st.session_state.get('c_y_oil', 60.0)), step=1.0, format="%.1f") / 100.0
            c_y_gas = _box.number_input(t("syngas_yield"), min_value=0.0, max_value=100.0, value=float(st.session_state.get('c_y_gas', 25.0)), step=1.0, format="%.1f") / 100.0
            c_y_char = _box.number_input(t("char_yield"), min_value=0.0, max_value=100.0, value=float(st.session_state.get('c_y_char', 15.0)), step=1.0, format="%.1f") / 100.0
            
            y_sum = c_y_oil + c_y_gas + c_y_char
            if y_sum > 0:
                c_y_oil_norm = c_y_oil / y_sum
                c_y_gas_norm = c_y_gas / y_sum
                c_y_char_norm = c_y_char / y_sum
            else:
                c_y_oil_norm, c_y_gas_norm, c_y_char_norm = 0.60, 0.25, 0.15
            
            c_ea1 = c_ea
            c_a1 = c_a * c_y_oil_norm
            c_ea2 = c_ea
            c_a2 = c_a * (c_y_gas_norm + c_y_char_norm)
            c_ea3 = 100.0 * 1000.0
            c_a3 = 5e5
            
            st.session_state['c_ea1'] = c_ea1 / 1000.0
            st.session_state['c_a1'] = c_a1
            st.session_state['c_ea2'] = c_ea2 / 1000.0
            st.session_state['c_a2'] = c_a2
            st.session_state['c_ea3'] = c_ea3 / 1000.0
            st.session_state['c_a3'] = c_a3
            
        current_feed = Feedstock(
            name="Custom Sludge" if lang == 'en' else "Lodo Petróleo/Hidrocarburos",
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
        current_feed.T_onset_K = float(c_t_onset) + 273.15

    st.session_state['feed_option'] = feed_option
    if feed_option == "Blend (Petroleum + Hydrocarbon)":
        st.session_state['blend_ratio'] = blend_ratio * 100.0

    # Batch size is entered in gallons; the density is the one from the burner/shell expander (previous run)
    sludge_density_prev = float(st.session_state.get('sludge_density', 944.7))
    kg_per_gal = (sludge_density_prev / 1000.0) * LITERS_PER_GALLON
    batch_load_gal = _box.number_input(
        t("batch_size"), 
        min_value=0.0, 
        max_value=100000.0, 
        value=float(st.session_state.get('batch_size', 440.0)), 
        step=50.0,
        format="%.1f"
    )
    batch_load_kg = batch_load_gal * kg_per_gal

    bio_oil_density = _box.number_input(
        t("bio_oil_density"),
        min_value=500.0,
        max_value=2000.0,
        value=float(st.session_state.get('bio_oil_density', 750.0)),
        step=10.0,
        format="%.1f",
        key="bio_oil_density"
    )

    bio_char_density = _box.number_input(
        t("bio_char_density"),
        min_value=100.0,
        max_value=2500.0,
        value=float(st.session_state.get('bio_char_density', 500.0)),
        step=10.0,
        format="%.1f",
        key="bio_char_density"
    )

    # Reactor geometry
    _box = st.sidebar.expander(t("reactor_geom"), expanded=False)
    length = _box.number_input(t("reactor_len"), min_value=0.5, max_value=50.0, value=float(st.session_state.get('reactor_len', 8.0)), step=0.5, format="%.2f")
    diameter = _box.number_input(t("reactor_dia"), min_value=0.1, max_value=15.0, value=float(st.session_state.get('reactor_dia', 3.0)), step=0.1, format="%.2f")
    rpm = _box.number_input(t("rotation_speed"), min_value=0.1, max_value=30.0, value=float(st.session_state.get('rotation_speed', 3.0)), step=0.5, format="%.2f")

    # Burner and Shell Calibration expander
    with st.sidebar.expander(t("burner_calib_header"), expanded=False):
        auto_heating_rate = st.checkbox(
            t("auto_heating_rate"),
            value=bool(st.session_state.get('auto_heating_rate', False))
        )

        # Shell steels: density (kg/m³), Cp (J/kg·K), k (W/m·K); same order as SHELL_MATERIAL_NAMES
        materials = {
            t("steel_carbon"): {'density': 7850.0, 'Cp': 480.0, 'k': 50.0},
            t("steel_ss304"): {'density': 8000.0, 'Cp': 500.0, 'k': 16.2},
            t("steel_ss316"): {'density': 8000.0, 'Cp': 500.0, 'k': 16.3},
            t("steel_alloy"): {'density': 7800.0, 'Cp': 460.0, 'k': 26.0}
        }
        material_keys = list(materials.keys())
        stored_material = st.session_state.get('shell_material', 'Carbon Steel')
        selected_material_label = st.selectbox(
            t("shell_material"),
            material_keys,
            index=_SHELL_MATERIAL_INDEX.get(stored_material, 0)
        )
        selected_material_dict = materials[selected_material_label]
        # Saved in English so the config JSON does not depend on the UI language
        shell_material_saved = SHELL_MATERIAL_NAMES[material_keys.index(selected_material_label)]
        
        shell_thickness_mm = st.number_input(
            t("shell_thickness"),
            min_value=1.0,
            max_value=100.0,
            value=float(st.session_state.get('shell_thickness_mm', 15.0)),
            step=1.0,
            format="%.1f"
        )
        
        burner_hp = st.number_input(
            t("burner_hp"),
            min_value=1.0,
            max_value=10000.0,
            value=float(st.session_state.get('burner_hp', 300.0)),
            step=10.0,
            format="%.1f"
        )

        burner_eff_pct = st.number_input(
            t("burner_eff"),
            min_value=5.0,
            max_value=100.0,
            value=float(st.session_state.get('burner_eff_pct', 85.0)),
            step=1.0,
            format="%.1f"
        )
        
        syngas_hp = st.number_input(
            t("syngas_hp"),
            min_value=0.0,
            max_value=5000.0,
            value=float(st.session_state.get('syngas_hp', 150.0)),
            step=10.0,
            format="%.1f"
        )
        
        h_loss = st.number_input(
            t("h_loss"),
            min_value=0.0,
            max_value=50.0,
            value=float(st.session_state.get('h_loss', 5.0)),
            step=0.5,
            format="%.1f"
        )
        
        sludge_density = st.number_input(
            t("sludge_density"),
            min_value=200.0,
            max_value=3000.0,
            value=float(st.session_state.get('sludge_density', 944.7)),
            step=1.0,
            format="%.1f"
        )
        
        custom_cp_oil = st.number_input(
            t("custom_cp_oil"),
            min_value=500.0,
            max_value=5000.0,
            value=float(st.session_state.get('custom_cp_oil', 1800.0)),
            step=25.0,
            format="%.1f"
        )
        
        custom_cp_char = st.number_input(
            t("custom_cp_char"),
            min_value=200.0,
            max_value=4000.0,
            value=float(st.session_state.get('custom_cp_char', 1000.0)),
            step=25.0,
            format="%.1f"
        )
        
        custom_cp_ash = st.number_input(
            t("custom_cp_ash"),
            min_value=200.0,
            max_value=4000.0,
            value=float(st.session_state.get('custom_cp_ash', 800.0)),
            step=25.0,
            format="%.1f"
        )

    _render_fuel_config(lang)

    # PROENERGETICOS Industrial Plant Specs expander in the sidebar
    with st.sidebar.expander(t("proenergeticos_title"), expanded=False):
        manifold_main_dia_in = st.number_input(
            t("manifold_main_dia"), 2.0, 24.0, float(st.session_state.get('manifold_main_dia_in', 8.0)), 1.0, key='manifold_main_dia_in'
        )
        manifold_branch_dia_in = st.number_input(
            t("manifold_branch_dia"), 1.0, 12.0, float(st.session_state.get('manifold_branch_dia_in', 4.0)), 0.5, key='manifold_branch_dia_in'
        )
        manifold_num_branches = st.number_input(
            t("manifold_num_branches"), 1, 16, int(st.session_state.get('manifold_num_branches', 4)), 1, key='manifold_num_branches'
        )
        cooling_tank_gal = st.number_input(
            t("cooling_tank_cap"), 1000.0, 100000.0, float(st.session_state.get('cooling_tank_gal', 28000.0)), 1000.0, key='cooling_tank_gal'
        )
        autogenous_purge = st.checkbox(
            t("autogenous_purge_opt"), value=bool(st.session_state.get('autogenous_purge', True)), key='autogenous_purge'
        )

    # Heating program (after the burner/fuel expanders: it uses auto_heating_rate and the shell data)
    _box = st.sidebar.expander(t("heating_config"), expanded=False)
    h_eff = _box.number_input(t("heat_transfer_coeff"), min_value=1.0, max_value=1000.0, value=float(st.session_state.get('heat_transfer_coeff', 80.0)), step=5.0, format="%.1f")

    _box.markdown(t("batch_temp_prog"))
    temp_start_c = _box.number_input(t("starting_temp"), min_value=0.0, max_value=500.0, value=float(st.session_state.get('starting_temp', 25.0)), step=5.0, format="%.1f")
    
    if auto_heating_rate:
        heating_rate_cmin = _nominal_heating_rate_cmin(
            current_feed, batch_load_kg, length, diameter, shell_thickness_mm, selected_material_dict,
            burner_hp, custom_cp_oil, custom_cp_char, custom_cp_ash)
        _box.info(t("nominal_heating_rate_info").format(heating_rate_cmin))
    else:
        heating_rate_cmin = _box.number_input(t("heating_rate"), min_value=0.1, max_value=100.0, value=float(st.session_state.get('heating_rate', 10.0)), step=0.5, format="%.2f")
        
    temp_hold_c = _box.number_input(t("holding_temp"), min_value=100.0, max_value=1200.0, value=float(st.session_state.get('holding_temp', 550.0)), step=10.0, format="%.1f")
    hold_time_min = _box.number_input(t("holding_time"), min_value=1.0, max_value=10000.0, value=float(st.session_state.get('holding_time', 60.0)), step=10.0, format="%.1f")

    # Compile the active configurations dictionary
    config_dict = {
        'lang_option': lang_option,
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
        'batch_size': float(batch_load_gal),
        'reactor_len': float(length),
        'reactor_dia': float(diameter),
        'rotation_speed': float(rpm),
        'heat_transfer_coeff': float(h_eff),
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
        'bio_char_density': float(bio_char_density),
        'fuel_type': st.session_state.get('fuel_type', DEFAULT_PARAMS['fuel_type']),
        'fuel_lhv': float(st.session_state.get('fuel_lhv', DEFAULT_PARAMS['fuel_lhv'])),
        'fuel_density': float(st.session_state.get('fuel_density', DEFAULT_PARAMS['fuel_density'])),
        'fuel_moisture': float(st.session_state.get('fuel_moisture', DEFAULT_PARAMS['fuel_moisture'])),
        'fuel_ash': float(st.session_state.get('fuel_ash', DEFAULT_PARAMS['fuel_ash'])),
        'manifold_main_dia_in': float(manifold_main_dia_in),
        'manifold_branch_dia_in': float(manifold_branch_dia_in),
        'manifold_num_branches': int(manifold_num_branches),
        'cooling_tank_gal': float(cooling_tank_gal),
        'autogenous_purge': bool(autogenous_purge)
    }
    config_dict.update({k: cast(st.session_state.get(k, DEFAULT_PARAMS[k])) for k, cast in _PASSTHROUGH_PARAMS})

    # Populate any missing default parameters
    for k, v in DEFAULT_PARAMS.items():
        if k not in config_dict:
            config_dict[k] = st.session_state.get(k, v)

    # Sync all config_dict parameters into st.session_state safely
    for k, v in config_dict.items():
        try:
            st.session_state[k] = v
        except Exception:
            pass

    # Also build inputs for solvers
    solver_inputs = {
        'current_feed': current_feed,
        'feed_option': feed_option,
        'blend_ratio': blend_ratio,
        'batch_load_kg': batch_load_kg,
        'length': length,
        'diameter': diameter,
        'rpm': rpm,
        'h_eff': h_eff,
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
