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
    render_guide_tab,
    render_export_tab,
    render_reactor_geometry_section
)

# Initialize session state configuration parameters
init_session_state()

# Set page config for a premium, wide-layout application
st.set_page_config(
    page_title="Rotary Pyrolysis Reactor Simulator",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# Execute simulation based on operation mode
mode_option = config_dict['mode_option']

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
        bulk_density=solver_inputs.get('sludge_density', 900.0),
        Cp_volatile=solver_inputs.get('custom_cp_oil', 1800.0),
        Cp_char=solver_inputs.get('custom_cp_char', 1000.0),
        Cp_ash=solver_inputs.get('custom_cp_ash', 800.0),
        burner_hp=solver_inputs.get('burner_hp', 300.0),
        burner_eff_pct=solver_inputs.get('burner_eff_pct', 70.0),
        syngas_hp=solver_inputs.get('syngas_hp', 150.0),
        fuel_lhv_mj_kg=st.session_state.get('fuel_lhv', 41.0),
        fuel_density_kg_l=st.session_state.get('fuel_density', 0.90),
        fuel_moisture_pct=st.session_state.get('fuel_moisture', 1.0),
        fuel_ash_pct=st.session_state.get('fuel_ash', 0.5)
    )
    results = sim.simulate(steps=250)
    summary = results['summary']
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
        burner_eff_pct=solver_inputs.get('burner_eff_pct', 70.0),
        syngas_hp=solver_inputs.get('syngas_hp', 150.0),
        shell_material_dict=solver_inputs.get('shell_material_dict', None),
        shell_thickness_mm=solver_inputs.get('shell_thickness_mm', 15.0),
        h_loss=solver_inputs.get('h_loss', 5.0),
        bulk_density=solver_inputs.get('sludge_density', 900.0),
        Cp_volatile=solver_inputs.get('custom_cp_oil', 1800.0),
        Cp_char=solver_inputs.get('custom_cp_char', 1000.0),
        Cp_ash=solver_inputs.get('custom_cp_ash', 800.0),
        fuel_lhv_mj_kg=st.session_state.get('fuel_lhv', 41.0),
        fuel_density_kg_l=st.session_state.get('fuel_density', 0.90),
        fuel_moisture_pct=st.session_state.get('fuel_moisture', 1.0),
        fuel_ash_pct=st.session_state.get('fuel_ash', 0.5)
    )
    results = sim.simulate(dt_sec=2.0)
    summary = results['summary']

# Render physical reactor cylinder filling degree visualization directly on the page (outside the tabs)
render_reactor_geometry_section(mode_option, summary, solver_inputs)

st.markdown("---")

# Render detailed profiles, total results, and balance tables using tabs
tab_metrics, tab_charts, tab_properties, tab_balances, tab_economics, tab_guide, tab_export = st.tabs([
    t("tab_metrics"),
    t("tab_charts"), 
    t("tab_properties"), 
    t("tab_balances"),
    t("tab_economics"),
    t("tab_guide"), 
    t("tab_export")
])

with tab_metrics:
    # Render mass yields, volume yields, and diagnostics cards inside its own tab
    render_metrics_panel(mode_option, summary, results)

with tab_charts:
    # Render dynamic charts inside its own tab
    render_charts_panel(mode_option, results)

with tab_properties:
    render_properties_tab(
        current_feed=solver_inputs['current_feed'],
        mode_option=mode_option,
        feed_rate_kgh=solver_inputs['feed_rate_kgh'],
        batch_load_kg=solver_inputs['batch_load_kg'],
        feed_option=config_dict['feed_option']
    )

with tab_balances:
    render_balances_tab(
        mode_option=mode_option,
        current_feed=solver_inputs['current_feed'],
        results=results,
        summary=summary,
        feed_rate_kgh=solver_inputs['feed_rate_kgh'],
        batch_load_kg=solver_inputs['batch_load_kg'],
        feed_option=config_dict['feed_option']
    )

with tab_economics:
    render_economics_tab(
        mode_option=mode_option,
        results=results,
        summary=summary,
        solver_inputs=solver_inputs
    )

with tab_guide:
    render_guide_tab()

with tab_export:
    render_export_tab(mode_option, results, summary)
