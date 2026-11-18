import streamlit as st
from pyrolysis import (
    ContinuousReactorSimulation,
    BatchReactorSimulation,
    TRANSLATIONS
)
from pyrolysis.gui import (
    apply_custom_styles,
    init_session_state,
    render_config_manager,
    render_sidebar,
    render_metrics_panel,
    render_charts_panel,
    render_properties_tab,
    render_balances_tab,
    render_economics_tab,
    compute_economics,
    render_summary_section,
    render_sustainability_tab,
    render_guide_tab,
    render_export_tab,
    render_reactor_geometry_section,
    ENABLE_REPORTS
)

# Set page config for a premium, wide-layout application
st.set_page_config(
    page_title="Rotary Pyrolysis Reactor Simulator",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state configuration parameters
init_session_state()

# Render the sidebar parameters and get active configurations
config_dict, solver_inputs = render_sidebar()

# Determine selected language and set translation helper
lang_option = config_dict['lang_option']
lang = 'en' if lang_option == "English" else 'es'

def t(key):
    return TRANSLATIONS[lang].get(key, key)

# Apply premium styles
apply_custom_styles()

# Render Header
st.title(t("title"))
st.markdown(t("subtitle"))
st.markdown("---")

# Render Config Save/Upload at the bottom of the sidebar
render_config_manager(config_dict)

# Execute simulation based on operation mode (cached in session state, so switching sections does not re-simulate)
mode_option = config_dict['mode_option']
feed_obj = solver_inputs['current_feed']

sim_cache_key = (
    mode_option,
    # Every feedstock attribute (yields, Ea1-3, A1-3, onset/end), so any change reruns the simulation
    tuple(sorted(vars(feed_obj).items())),
    float(solver_inputs.get('feed_rate_kgh', 0.0)),
    float(solver_inputs.get('batch_load_kg', 0.0)),
    float(solver_inputs.get('length', 0.0)),
    float(solver_inputs.get('diameter', 0.0)),
    float(solver_inputs.get('slope', 0.0)),
    float(solver_inputs.get('rpm', 0.0)),
    float(solver_inputs.get('temp_inlet_c', 0.0)),
    float(solver_inputs.get('temp_start_c', 0.0)),
    float(solver_inputs.get('heating_rate_cmin', 0.0)),
    float(solver_inputs.get('temp_hold_c', 0.0)),
    float(solver_inputs.get('hold_time_min', 0.0)),
    float(solver_inputs.get('h_eff', 0.0)),
    str(solver_inputs.get('T_wall_type_str', '')),
    str(solver_inputs.get('T_wall_params', '')),
    bool(solver_inputs.get('auto_heating_rate', False)),
    float(solver_inputs.get('burner_hp', 300.0)),
    float(solver_inputs.get('burner_eff_pct', 85.0)),
    float(solver_inputs.get('syngas_hp', 150.0)),
    float(solver_inputs.get('sludge_density', 944.7)),
    float(solver_inputs.get('custom_cp_oil', 1800.0)),
    float(solver_inputs.get('custom_cp_char', 1000.0)),
    float(solver_inputs.get('custom_cp_ash', 800.0)),
    float(solver_inputs.get('bio_oil_density', 750.0)),
    float(solver_inputs.get('shell_thickness_mm', 15.0)),
    float(solver_inputs.get('h_loss', 5.0)),
    str(solver_inputs.get('shell_material_dict', '')),
    float(st.session_state.get('fuel_lhv', 41.0)),
    float(st.session_state.get('fuel_density', 0.90)),
    float(st.session_state.get('fuel_moisture', 1.0)),
    float(st.session_state.get('fuel_ash', 0.5))
)

if st.session_state.get('last_sim_key') == sim_cache_key and 'last_sim_results' in st.session_state:
    results = st.session_state['last_sim_results']
    summary = results['summary']
else:
    if mode_option == "Continuous Operation":
        sim = ContinuousReactorSimulation(
            feedstock=solver_inputs['current_feed'],
            feed_rate_kgh=solver_inputs['feed_rate_kgh'],
            length=solver_inputs['length'],
            diameter=solver_inputs['diameter'],
            slope=solver_inputs['slope'],
            rpm=solver_inputs['rpm'],
            T_inlet_C=solver_inputs['temp_inlet_c'],
            h_eff=solver_inputs['h_eff'],
            T_wall_type=solver_inputs['T_wall_type_str'],
            T_wall_params=solver_inputs['T_wall_params'],
            bulk_density=solver_inputs.get('sludge_density', 944.7),
            Cp_volatile=solver_inputs.get('custom_cp_oil', 1800.0),
            Cp_char=solver_inputs.get('custom_cp_char', 1000.0),
            Cp_ash=solver_inputs.get('custom_cp_ash', 800.0),
            burner_hp=solver_inputs.get('burner_hp', 300.0),
            burner_eff_pct=solver_inputs.get('burner_eff_pct', 85.0),
            syngas_hp=solver_inputs.get('syngas_hp', 150.0),
            fuel_lhv_mj_kg=st.session_state.get('fuel_lhv', 41.0),
            fuel_density_kg_l=st.session_state.get('fuel_density', 0.90),
            fuel_moisture_pct=st.session_state.get('fuel_moisture', 1.0),
            fuel_ash_pct=st.session_state.get('fuel_ash', 0.5)
        )
        results = sim.simulate(steps=250)
    else:
        sim = BatchReactorSimulation(
            feedstock=solver_inputs['current_feed'],
            batch_load_kg=solver_inputs['batch_load_kg'],
            length=solver_inputs['length'],
            diameter=solver_inputs['diameter'],
            rpm=solver_inputs['rpm'],
            T_start_C=solver_inputs['temp_start_c'],
            heating_rate_cmin=solver_inputs['heating_rate_cmin'],
            T_hold_C=solver_inputs['temp_hold_c'],
            hold_time_min=solver_inputs['hold_time_min'],
            h_eff=solver_inputs['h_eff'],
            auto_heating_rate=solver_inputs.get('auto_heating_rate', False),
            burner_hp=solver_inputs.get('burner_hp', 300.0),
            burner_eff_pct=solver_inputs.get('burner_eff_pct', 85.0),
            syngas_hp=solver_inputs.get('syngas_hp', 150.0),
            shell_material_dict=solver_inputs.get('shell_material_dict', None),
            shell_thickness_mm=solver_inputs.get('shell_thickness_mm', 15.0),
            h_loss=solver_inputs.get('h_loss', 5.0),
            bulk_density=solver_inputs.get('sludge_density', 944.7),
            Cp_volatile=solver_inputs.get('custom_cp_oil', 1800.0),
            Cp_char=solver_inputs.get('custom_cp_char', 1000.0),
            Cp_ash=solver_inputs.get('custom_cp_ash', 800.0),
            fuel_lhv_mj_kg=st.session_state.get('fuel_lhv', 41.0),
            fuel_density_kg_l=st.session_state.get('fuel_density', 0.90),
            fuel_moisture_pct=st.session_state.get('fuel_moisture', 1.0),
            fuel_ash_pct=st.session_state.get('fuel_ash', 0.5),
            bio_oil_density=solver_inputs.get('bio_oil_density', 750.0)
        )
        results = sim.simulate(dt_sec=2.0)
    summary = results['summary']
    st.session_state['last_sim_key'] = sim_cache_key
    st.session_state['last_sim_results'] = results

# Economic results computed once from session_state; the Summary and Economy sections share them
econ = compute_economics(mode_option, summary, solver_inputs)

# ------------------------------------------------------------------------------------------------
# Dashboard navigation. Its value lives in session_state under 'nav_section', so any rerun caused by
# changing a parameter keeps the user in the section they were looking at.
# ------------------------------------------------------------------------------------------------
SECTIONS = {
    'summary': ("📊 Resumen", "📊 Summary"),
    'process': ("🌡️ Proceso", "🌡️ Process"),
    'balances': ("⚖️ Balances", "⚖️ Balances"),
    'economy': ("💸 Economía", "💸 Economy"),
    'sustainability': ("🌿 Sostenibilidad", "🌿 Sustainability"),
    'theory': ("📘 Teoría y ecuaciones", "📘 Theory & equations"),
    'export': ("📥 Exportar", "📥 Export"),
}
if st.session_state.get('nav_section') not in SECTIONS:
    st.session_state['nav_section'] = 'summary'
section = st.segmented_control(
    "Sección" if lang == 'es' else "Section", list(SECTIONS),
    format_func=lambda k: SECTIONS[k][0 if lang == 'es' else 1],
    key='nav_section', required=True, label_visibility='collapsed', width='stretch')

if section == 'summary':
    render_summary_section(mode_option, summary, econ)

elif section == 'process':
    render_reactor_geometry_section(mode_option, summary, solver_inputs)
    st.markdown("---")
    render_charts_panel(mode_option, results)

elif section == 'balances':
    render_metrics_panel(mode_option, summary, results)
    st.markdown("---")
    render_balances_tab(
        mode_option=mode_option,
        current_feed=solver_inputs['current_feed'],
        results=results,
        summary=summary,
        feed_rate_kgh=solver_inputs['feed_rate_kgh'],
        batch_load_kg=solver_inputs['batch_load_kg'],
        feed_option=config_dict['feed_option']
    )
    st.markdown("---")
    render_properties_tab(
        current_feed=solver_inputs['current_feed'],
        mode_option=mode_option,
        feed_rate_kgh=solver_inputs['feed_rate_kgh'],
        batch_load_kg=solver_inputs['batch_load_kg'],
        feed_option=config_dict['feed_option']
    )

elif section == 'economy':
    render_economics_tab(mode_option=mode_option, results=results, summary=summary,
                         solver_inputs=solver_inputs, econ=econ)

elif section == 'sustainability':
    render_sustainability_tab(summary=summary, solver_inputs=solver_inputs)

elif section == 'theory':
    render_guide_tab()

elif section == 'export':
    render_export_tab(mode_option, results, summary, solver_inputs, config_dict, enable_reports=ENABLE_REPORTS)
