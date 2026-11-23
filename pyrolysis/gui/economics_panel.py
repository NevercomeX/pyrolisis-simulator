"""Economy and Sustainability sections of the dashboard (all amounts in DOP, RD$).

Layout of this file:
  1. Economic inputs form          render_economics_inputs (values live in session_state)
  2. Economic results             compute_economics (no widgets; shared with the Summary section)
  3. Economy section              render_economics_tab and one _render_* helper per block on screen
  4. Sustainability section       render_sustainability_tab

The financial maths (cash flows, NPV, IRR, paybacks, break-even fee, sludge scenarios) is in
economics_model.py and the pre-dryer evaluator in pre_drying_panel.py; the public names of both are
re-exported here, so `from pyrolysis.gui.economics_panel import run_financial_model` keeps working.
"""
import io
from itertools import accumulate

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .economics_model import (  # noqa: F401  (re-exported for app, reports and tests)
    GAL_PER_M3,
    IRR_SEARCH_MAX,
    SLUDGE_SCENARIOS,
    SLUDGE_SCENARIO_LABELS,
    batch_thermal_cycle_min,
    breakeven_note,
    format_irr,
    run_financial_model,
    scenario_tipping_fee,
    solve_irr,
)
from .pre_drying_panel import render_pre_drying_evaluator
from .utils import get_lang, t

CURR_SYM = "RD$"

# Assumed CO2 emission factors for the process-emissions balance (sustainability tab)
EF_CO2_FUEL_OIL_KG_PER_KG = 3.15   # waste / fuel oil combustion
EF_CO2_DIESEL_KG_PER_GAL = 10.21   # diesel generator
EF_CO2_SYNGAS_KG_PER_KG = 0.84     # pyrolysis gas at ~12 MJ/kg and ~0.07 kg CO2/MJ

# Equivalences shown on the sustainability cards
CO2_T_PER_TREE_YEAR = 0.022        # CO2 absorbed by one tree in a year (t)
CO2_T_PER_CAR_YEAR = 4.6           # CO2 emitted by one passenger car in a year (t)
LITRES_PER_GAL = 3.785

_CHART_LAYOUT = dict(margin=dict(l=40, r=20, t=50, b=40))   # colours come from the Streamlit theme


def _fmt_money(x):
    """'RD$1,234.56' or '-RD$1,234.56'."""
    return f"{CURR_SYM}{x:,.2f}" if x >= 0 else f"-{CURR_SYM}{abs(x):,.2f}"


def _bottom_legend(y, font_size):
    """Horizontal legend centred under the plot."""
    return dict(orientation="h", yanchor="bottom", y=y, xanchor="center", x=0.5, font=dict(size=font_size))


def render_kpi_card(title, value_str, subtitle=None, is_positive=True):
    """Renders a premium visual card for financial KPIs."""
    color = "#10b981" if is_positive else "#ef4444"

    html = f"""
    <div style="
        background: rgba(128,128,128,0.08);
        padding: 18px;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,0.25);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        text-align: center;
        margin-bottom: 15px;
        height: 100%;
    ">
        <h4 style="opacity: 0.7; margin: 0; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;">{title}</h4>
        <h2 style="color: {color}; margin: 8px 0; font-size: 24px; font-weight: 700;">{value_str}</h2>
        {f'<p style="opacity: 0.6; margin: 0; font-size: 11px;">{subtitle}</p>' if subtitle else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================================
# 1. Economic inputs form
# =============================================================================================
def _econ_defaults():
    """Fallback values of the economic inputs (session_state normally already holds them via DEFAULT_PARAMS)."""
    return {
        'capex_equip': 4800000.0,
        'capex_install': 1680000.0,
        'capex_civil': 1200000.0,
        'capex_piping_elec': 1200000.0,
        'capex_eng': 720000.0,
        'capex_permits': 450000.0,
        'capex_cont': 900000.0,
        'opex_handling': 3.00,
        'opex_tipping': 9.00,
        'opex_fuel': 180.00,
        'opex_electricity': 7.50,
        'opex_aux_utilities': 300000.0,
        'price_generator_fuel': 262.80,
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
        'tax_rate': 25.0,
        'inflation_rate': 4.0,
        'shutdown_days': 15,
        'holidays_days': 15,
        'gen_diesel_batch': 1.0,   # gal/batch
        'batch_cooldown_h': 0.50,
        'batch_loading_h': 0.50,
        'batches_before_cleaning': 20,
        'cleaning_time_h': 4.0,
        'maint_cooldown_h': 6.0,
        'econ_sludge_scenario': 'tipping',
        'econ_sludge_cost': 0.0,
        'econ_batches_per_year': 0,
        'econ_oil_gal_per_batch': 0.0,
        'econ_fuel_gal_per_batch': 0.0,
    }


# CAPEX items as a fraction of the main equipment cost (button "apply ratios")
_CAPEX_RATIOS = {
    'capex_install': 0.35,
    'capex_civil': 0.25,
    'capex_piping_elec': 0.25,
    'capex_eng': 0.15,
    'capex_permits': 0.05,
    'capex_cont': 0.10,
}


def render_economics_inputs():
    """Economic parameters inside a form: new values reach session_state (and every section) only when the
    user presses "Recalcular", so typing a number does not reload the page."""
    lang = get_lang()
    d = _econ_defaults()
    ss = st.session_state

    def num(label, key, **kw):
        cast = int if isinstance(d[key], int) else float
        return st.number_input(label, value=cast(ss.get(key, d[key])), key=key, **kw)

    def _apply_capex_ratios_cb():
        eq_val = ss.get('capex_equip', d['capex_equip'])
        for key, ratio in _CAPEX_RATIOS.items():
            ss[key] = float(round(eq_val * ratio, 2))

    if ss.get('econ_sludge_scenario') not in SLUDGE_SCENARIOS:
        ss['econ_sludge_scenario'] = 'tipping'

    with st.form("econ_params_form"):
        st.markdown("##### ⚙️ " + ("Parámetros económicos" if lang == 'es' else "Economic parameters"))
        st.caption("Los cambios se aplican al pulsar «Recalcular»." if lang == 'es'
                   else "Changes are applied when you press “Recalculate”.")
        col_param_l, col_param_r = st.columns(2)
        with col_param_l:
            with st.expander(f"🏗️ {t('econ_section_capex')}", expanded=True):
                col_cx1, col_cx2 = st.columns(2)
                with col_cx1:
                    num(t('econ_input_reactor_cost'), 'capex_equip', min_value=0.0, step=250000.0)
                    num(t('econ_input_civil_works'), 'capex_civil', min_value=0.0, step=100000.0)
                    num(t('econ_input_engineering'), 'capex_eng', min_value=0.0, step=100000.0)
                with col_cx2:
                    num(t('econ_input_installation'), 'capex_install', min_value=0.0, step=100000.0)
                    num(t('econ_input_piping_elec'), 'capex_piping_elec', min_value=0.0, step=100000.0)
                    num(t('econ_input_permits'), 'capex_permits', min_value=0.0, step=50000.0)
                num(t('econ_input_contingency'), 'capex_cont', min_value=0.0, step=50000.0)

            with st.expander(f"⚙️ {t('econ_section_opex')}", expanded=True):
                col_ox1, col_ox2 = st.columns(2)
                with col_ox1:
                    num(t('econ_input_handling'), 'opex_handling', min_value=0.0, step=0.5)
                    num(t('econ_input_electricity'), 'opex_electricity', min_value=0.0, step=0.5)
                    num(t('econ_input_gen_fuel'), 'price_generator_fuel', min_value=0.0, step=5.0)
                    num(t('econ_input_labor'), 'opex_labor', min_value=0.0, step=250000.0)
                with col_ox2:
                    num(t('econ_input_fuel'), 'opex_fuel', min_value=0.0, step=5.0, format="%.4f")
                    num(t('econ_input_aux_utilities'), 'opex_aux_utilities', min_value=0.0, step=25000.0)
                    num(t('econ_input_gen_fuel_batch'), 'gen_diesel_batch', min_value=0.0, step=0.5)
                    num(t('econ_input_maintenance'), 'opex_maint', min_value=0.0, max_value=25.0, step=0.5)
                num(t('econ_input_insurance_tax'), 'opex_insurance_tax', min_value=0.0, max_value=10.0, step=0.1)

        with col_param_r:
            with st.expander(f"🏷️ {t('econ_section_revenue')}", expanded=True):
                st.radio("Escenario económico del lodo" if lang == 'es' else "Sludge economic scenario",
                         SLUDGE_SCENARIOS, format_func=lambda k: SLUDGE_SCENARIO_LABELS[k][lang],
                         key='econ_sludge_scenario')
                col_sc1, col_sc2 = st.columns(2)
                with col_sc1:
                    num("Costo de compra del lodo, X (RD$/gal)" if lang == 'es' else "Sludge purchase cost, X (RD$/gal)",
                        'econ_sludge_cost', min_value=0.0, step=1.0)
                with col_sc2:
                    num(t('econ_input_tipping') + ", Y", 'opex_tipping', min_value=0.0, step=1.0)
                col_rv1, col_rv2 = st.columns(2)
                with col_rv1:
                    num(t('econ_input_price_oil'), 'price_oil', min_value=0.0, step=5.0)
                    num(t('econ_input_price_char'), 'price_char', min_value=0.0, step=1.0)
                with col_rv2:
                    num(t('econ_input_price_gas'), 'price_gas', min_value=0.0, step=0.5)
                    num(t('econ_input_carbon_price'), 'price_carbon', min_value=0.0, step=50.0)
                num(t('econ_input_carbon_rate'), 'rate_carbon_offset', min_value=0.0, step=0.1)

            with st.expander(f"📈 {t('econ_section_params')}", expanded=True):
                col_pr1, col_pr2 = st.columns(2)
                with col_pr1:
                    num(t('econ_input_discount'), 'discount_rate', min_value=0.0, max_value=50.0, step=0.5)
                    num(t('econ_input_income_tax'), 'tax_rate', min_value=0.0, max_value=80.0, step=1.0)
                    num(t('econ_input_lifetime'), 'project_lifetime', min_value=1, max_value=30, step=1)
                with col_pr2:
                    num(t('econ_input_inflation'), 'inflation_rate', min_value=0.0, max_value=50.0, step=0.5)
                    num(t('econ_input_shutdown_days'), 'shutdown_days', min_value=0, max_value=200, step=1,
                        help="Días al año para paradas técnicas mayores, averías o mantenimiento anual general.")
                    num(t('econ_input_holidays_days'), 'holidays_days', min_value=0, max_value=200, step=1,
                        help="Días feriados o no laborables al año según calendario legal/laboral.")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    num("Tiempo de Enfriamiento por Lote (h)", 'batch_cooldown_h',
                        min_value=0.0, max_value=200.0, step=0.25, format="%.2f")
                with col_b2:
                    num("Tiempo de Carga y Descarga por Lote (h)", 'batch_loading_h',
                        min_value=0.0, max_value=200.0, step=0.25, format="%.2f")

                st.markdown("##### 🧹 Mantenimiento Periódico y Limpieza")
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    num("Cantidad de Lotes antes de Limpieza", 'batches_before_cleaning',
                        min_value=1, max_value=1000, step=1,
                        help="Cantidad de lotes operados antes de detener el reactor para limpieza y mantenimiento.")
                with col_m2:
                    num("Tiempo de Limpieza (h)", 'cleaning_time_h', min_value=0.0, max_value=200.0, step=0.5,
                        format="%.2f", help="Duración del trabajo de limpieza física, decoking e inspección interna.")
                with col_m3:
                    num("Tiempo de Enfriamiento para Mantenimiento (h)", 'maint_cooldown_h',
                        min_value=0.0, max_value=200.0, step=0.5, format="%.2f",
                        help="Tiempo de enfriamiento profundo necesario para poder abrir e intervenir el reactor de forma segura.")

                # Plant data that override the simulation in the economics (0 = use the simulated value)
                st.markdown("##### 📌 " + ("Datos de planta para la economía (0 = usar la simulación)" if lang == 'es'
                                           else "Plant data for the economics (0 = use the simulation)"))
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    num("Lotes por año (fijo)" if lang == 'es' else "Batches per year (fixed)",
                        'econ_batches_per_year', min_value=0, max_value=10000, step=1,
                        help="Si es mayor que 0, no se calculan a partir del tiempo de ciclo simulado." if lang == 'es'
                        else "If above 0, batches are not derived from the simulated cycle time.")
                with col_f2:
                    num("Aceite por lote (gal)" if lang == 'es' else "Oil per batch (gal)",
                        'econ_oil_gal_per_batch', min_value=0.0, step=10.0, format="%.4f")
                with col_f3:
                    num("Combustible auxiliar por lote (gal)" if lang == 'es' else "Auxiliary fuel per batch (gal)",
                        'econ_fuel_gal_per_batch', min_value=0.0, step=10.0, format="%.2f")

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            st.form_submit_button("🔄 " + ("Recalcular" if lang == 'es' else "Recalculate"), type="primary",
                                  use_container_width=True)
        with col_btn2:
            st.form_submit_button(t('econ_btn_apply_ratios'), on_click=_apply_capex_ratios_cb,
                                  use_container_width=True)


# =============================================================================================
# 2. Economic results
# =============================================================================================
def compute_economics(summary, solver_inputs):
    """Every economic result, computed from the parameters stored in session_state (no widgets).
    The Summary and Economy sections both use it, so they always show the same numbers.

    Returns every local variable of this function as a dict (the `econ` dict): the local names below
    ARE its keys, read by render_economics_tab and summary_panel, so rename them only together.
    `m` is the run_financial_model() result and `_model(fee)` re-runs it for another tipping fee."""
    ss = st.session_state
    d = _econ_defaults()

    def g(key):
        return ss.get(key, d[key])

    # --- parameters --------------------------------------------------------------------------
    capex_equip = float(g('capex_equip'))
    capex_install = float(g('capex_install'))
    capex_civil = float(g('capex_civil'))
    capex_piping_elec = float(g('capex_piping_elec'))
    capex_eng = float(g('capex_eng'))
    capex_permits = float(g('capex_permits'))
    capex_cont = float(g('capex_cont'))

    opex_handling = float(g('opex_handling'))
    opex_electricity = float(g('opex_electricity'))
    price_generator_fuel = float(g('price_generator_fuel'))
    opex_labor = float(g('opex_labor'))
    opex_fuel = float(g('opex_fuel'))
    opex_aux_utilities = float(g('opex_aux_utilities'))
    opex_maint = float(g('opex_maint'))
    opex_insurance_tax = float(g('opex_insurance_tax'))

    sludge_scenario = g('econ_sludge_scenario')
    if sludge_scenario not in SLUDGE_SCENARIOS:
        sludge_scenario = 'tipping'
    sludge_cost = float(g('econ_sludge_cost'))
    tipping_y = float(g('opex_tipping'))
    # Fee used by the whole economics (negative = the plant pays for the sludge)
    opex_tipping = scenario_tipping_fee(sludge_scenario, sludge_cost, tipping_y)
    price_oil = float(g('price_oil'))
    price_char = float(g('price_char'))
    price_gas = float(g('price_gas'))
    price_carbon = float(g('price_carbon'))
    rate_carbon_offset = float(g('rate_carbon_offset'))

    discount_rate = float(g('discount_rate'))
    tax_rate = float(g('tax_rate'))
    project_lifetime = int(g('project_lifetime'))
    inflation_rate = float(g('inflation_rate'))
    shutdown_days = int(g('shutdown_days'))
    holidays_days = int(g('holidays_days'))

    available_calendar_days = max(1, 365 - shutdown_days - holidays_days)
    annual_days = available_calendar_days
    ss['annual_days'] = annual_days

    gen_diesel_batch = float(g('gen_diesel_batch'))
    batch_cooldown_h = float(g('batch_cooldown_h'))
    batch_loading_h = float(g('batch_loading_h'))
    batch_turnaround_h = batch_cooldown_h + batch_loading_h
    ss['batch_turnaround_h'] = batch_turnaround_h
    batches_before_cleaning = int(g('batches_before_cleaning'))
    cleaning_time_h = float(g('cleaning_time_h'))
    maint_cooldown_h = float(g('maint_cooldown_h'))
    maint_stop_total_h = maint_cooldown_h + cleaning_time_h
    maint_penalty_per_batch_h = maint_stop_total_h / max(batches_before_cleaning, 1)
    econ_batches_fixed = int(g('econ_batches_per_year'))
    econ_oil_gal_batch = float(g('econ_oil_gal_per_batch'))
    econ_fuel_gal_batch = float(g('econ_fuel_gal_per_batch'))

    total_capex = capex_equip + capex_install + capex_civil + capex_piping_elec + capex_eng + capex_permits + capex_cont

    # --- annual production and consumption ---------------------------------------------------
    sludge_density = float(ss.get('sludge_density', 944.7))
    oil_density = float(ss.get('bio_oil_density', 750.0))
    gas_density = 1.15   # kg/m³, non-condensable gas
    annual_hours = annual_days * 24.0

    t_cycle_min, t_heat_min, t_hold_min = batch_thermal_cycle_min(summary, solver_inputs)
    t_op_batch_hours = (t_cycle_min / 60.0) + batch_turnaround_h
    t_cycle_hours = t_op_batch_hours + maint_penalty_per_batch_h

    if econ_batches_fixed > 0:
        batches_per_year = float(econ_batches_fixed)
    else:
        batches_per_year = np.floor(annual_hours / t_cycle_hours) if t_cycle_hours > 0 else 0.0

    operating_days_batches = (batches_per_year * t_op_batch_hours) / 24.0
    cleaning_days_annual = (batches_per_year * maint_penalty_per_batch_h) / 24.0
    campaign_active_days = operating_days_batches + cleaning_days_annual

    sludge_treated_kg = summary['batch_load_kg'] * batches_per_year
    oil_produced_kg = summary['oil_yield_kg'] * batches_per_year
    char_produced_kg = summary['char_yield_kg'] * batches_per_year
    char_carbon_kg = summary.get('char_organic_kg', summary['char_yield_kg']) * batches_per_year
    # Only the syngas not burned in the process is sellable (burned syngas already offsets fuel)
    gas_produced_kg = summary.get('syngas_flare_kg', summary['gas_yield_kg']) * batches_per_year

    fuel_per_batch_gal = econ_fuel_gal_batch if econ_fuel_gal_batch > 0 else summary['waste_oil_consumed_gal']
    fuel_consumed_gal = fuel_per_batch_gal * batches_per_year
    elec_consumed_kwh = 0.0
    generator_fuel_consumed_gal = gen_diesel_batch * batches_per_year

    # Liquids in gallons, gas in m³, char stays in kg
    sludge_treated_gal = (sludge_treated_kg / sludge_density) * GAL_PER_M3
    if econ_oil_gal_batch > 0:
        oil_produced_gal = econ_oil_gal_batch * batches_per_year
    else:
        oil_produced_gal = (oil_produced_kg / oil_density) * GAL_PER_M3
    gas_produced_m3 = gas_produced_kg / gas_density

    # --- financial model ---------------------------------------------------------------------
    def _model(tipping_fee):
        return run_financial_model(
            total_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
            fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
            opex_handling, opex_fuel, opex_electricity, opex_aux_utilities, price_generator_fuel,
            opex_labor, opex_maint, opex_insurance_tax,
            tipping_fee, price_oil, price_char, price_gas, price_carbon, rate_carbon_offset,
            discount_rate, project_lifetime, tax_rate, inflation_rate,
            char_carbon_kg=char_carbon_kg
        )

    m = _model(opex_tipping)
    return {k: v for k, v in locals().items() if k not in ('ss', 'd', 'g')}


# =============================================================================================
# 3. Economy section
# =============================================================================================
def render_economics_tab(results, summary, solver_inputs, econ=None):
    """Renders the Economy section (Standardized in DOP - RD$): parameters form, then results.
    `econ` is the compute_economics() result already used by the other sections (computed here if omitted).
    `results` is accepted for the caller's signature and not used."""
    lang = get_lang()
    _render_header_with_save_button()
    st.markdown("---")

    render_economics_inputs()
    if econ is None:
        econ = compute_economics(summary, solver_inputs)

    _render_batch_calendar(econ, lang)

    _render_kpi_cards(econ, lang)
    _render_sludge_scenarios(econ, lang)

    st.markdown("---")
    _render_cumulative_cash_flow_chart(econ)
    _render_npv_vs_sludge_price(econ, lang)
    _render_cost_composition(econ, lang)

    col_table_l, col_table_r = st.columns(2)
    with col_table_l:
        _render_annual_quantities(econ, summary, lang)
    with col_table_r:
        _render_cash_flow_breakdown(econ)

    _render_monthly_cash_flow(econ, summary)
    _render_sensitivity_tornado(econ)

    render_pre_drying_evaluator(
        solver_inputs=solver_inputs,
        summary=summary,
        curr_sym=CURR_SYM,
        opex_fuel=econ['opex_fuel'],
        available_calendar_days=econ['available_calendar_days'],
        batches_per_year=econ['batches_per_year'],
        t_cycle_hours=econ['t_cycle_hours'],
        m=econ['m'],
        lang=lang
    )

    _render_yearly_projection_table(econ)


def _render_header_with_save_button():
    """Title, description and the button that saves every parameter to the browser's LocalStorage."""
    def _save_econ_to_ls_cb():
        st.session_state['trigger_save_ls'] = True
        st.session_state['econ_saved_flag'] = True

    col_hdr_txt, col_hdr_btn = st.columns([3, 2])
    with col_hdr_txt:
        st.markdown(f"### 💸 {t('econ_title')}")
        st.markdown(t('econ_desc'))
    with col_hdr_btn:
        st.button(t('econ_save_ls_btn'), key='btn_save_econ_ls', on_click=_save_econ_to_ls_cb, use_container_width=True)

    if st.session_state.get('trigger_save_ls', False):
        from pyrolysis.gui.config_manager import DEFAULT_PARAMS
        from pyrolysis.gui.local_storage import local_storage_set
        full_config_data = {k: st.session_state.get(k, DEFAULT_PARAMS.get(k)) for k in DEFAULT_PARAMS.keys()}
        res = local_storage_set("pyrolysis_config", full_config_data, key_suffix="econ_save")
        if res is True or st.session_state.get('econ_saved_flag', False):
            st.session_state['trigger_save_ls'] = False
            st.session_state['econ_saved_flag'] = False
            st.success(t('econ_save_ls_success'))


def _render_batch_calendar(econ, lang):
    """Annual calendar card of the batch campaign (same values the economics uses)."""
    e = econ
    bpy = e['batches_per_year']
    if lang == 'es':
        title_text = "📅 Calendario Anual y Capacidad (Base 365 días)"
        badge_text = f"{bpy:.0f} lotes/año"
        lbl_disp, sub_disp = "Días Disponibles de Planta", f"(365 - {e['shutdown_days']}d parada - {e['holidays_days']}d feriados)"
        lbl_op, sub_op = "Días de Operación Efectiva (Lotes)", f"({bpy * e['t_op_batch_hours']:.1f} h proceso)"
        lbl_clean, sub_clean = "Días de Parada por Limpieza / Mant.", f"({bpy * e['maint_penalty_per_batch_h']:.1f} h paradas)"
        lbl_tot, sub_tot = "Días Totales Activos de Campaña", f"(Ciclo: {e['t_cycle_hours']:.2f} h/lote)"
        days_unit = "días/año"
    else:
        title_text = "📅 Annual Calendar & Throughput (365 days base)"
        badge_text = f"{bpy:.0f} batches/yr"
        lbl_disp, sub_disp = "Plant Available Days", f"(365 - {e['shutdown_days']}d shutdown - {e['holidays_days']}d holidays)"
        lbl_op, sub_op = "Effective Batch Operating Days", f"({bpy * e['t_op_batch_hours']:.1f} h process)"
        lbl_clean, sub_clean = "Cleaning & Maintenance Downtime Days", f"({bpy * e['maint_penalty_per_batch_h']:.1f} h downtime)"
        lbl_tot, sub_tot = "Total Active Campaign Days", f"(Cycle: {e['t_cycle_hours']:.2f} h/batch)"
        days_unit = "days/yr"

    st.markdown(f"""
    <div style="background: rgba(128,128,128,0.08); border: 1px solid rgba(128,128,128,0.25); border-radius: 8px; padding: 12px 14px; margin-top: 10px; margin-bottom: 8px;">
        <div style="font-weight: 600; font-size: 0.90rem; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
            <span>{title_text}</span>
            <span style="background-color: rgba(14,165,233,0.15); color: #0ea5e9; font-size: 0.8rem; padding: 2px 8px; border-radius: 4px; border: 1px solid #0284c7;">{badge_text}</span>
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
            <tr style="border-bottom: 1px solid rgba(128,128,128,0.25);">
                <td style="padding: 5px 0; opacity: 0.75;">{lbl_disp}</td>
                <td style="padding: 5px 8px; text-align: right; font-weight: 600;">{e['available_calendar_days']} {days_unit}</td>
                <td style="padding: 5px 0; text-align: right; opacity: 0.6; font-size: 0.75rem;">{sub_disp}</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(128,128,128,0.25);">
                <td style="padding: 5px 0; opacity: 0.75;">{lbl_op}</td>
                <td style="padding: 5px 8px; text-align: right; font-weight: 600; color: #10b981;">{e['operating_days_batches']:.1f} {days_unit}</td>
                <td style="padding: 5px 0; text-align: right; opacity: 0.6; font-size: 0.75rem;">{sub_op}</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(128,128,128,0.25);">
                <td style="padding: 5px 0; opacity: 0.75;">{lbl_clean}</td>
                <td style="padding: 5px 8px; text-align: right; font-weight: 600; color: #f59e0b;">{e['cleaning_days_annual']:.1f} {days_unit}</td>
                <td style="padding: 5px 0; text-align: right; opacity: 0.6; font-size: 0.75rem;">{sub_clean}</td>
            </tr>
            <tr>
                <td style="padding: 5px 0; opacity: 0.75;">{lbl_tot}</td>
                <td style="padding: 5px 8px; text-align: right; font-weight: 700; color: #0ea5e9;">{e['campaign_active_days']:.1f} {days_unit}</td>
                <td style="padding: 5px 0; text-align: right; opacity: 0.6; font-size: 0.75rem;">{sub_tot}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)


def _render_kpi_cards(econ, lang):
    """Five KPI cards: NPV, IRR, payback (discounted, else simple), profitability index, break-even fee."""
    m = econ['m']
    project_lifetime = econ['project_lifetime']
    st.markdown(f"#### 📊 {t('econ_metrics')}")

    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)

    with col_kpi1:
        render_kpi_card(
            t('econ_metric_npv'),
            f"{CURR_SYM}{m['npv']:,.2f}",
            "Net Present Value / Valor Actual Neto",
            is_positive=(m['npv'] > 0)
        )

    with col_kpi2:
        render_kpi_card(
            t('econ_metric_irr'),
            format_irr(m['irr']),
            "Internal Rate of Return / TIR",
            is_positive=(m['irr'] is not None and m['irr'] > econ['discount_rate'])
        )

    with col_kpi3:
        if m['disc_payback'] != float('inf'):
            payback_label = t('econ_metric_disc_payback')
            payback_val_str = f"{m['disc_payback']:.2f} yr"
            payback_sub = "Discounted Return / Retorno Descontado"
            is_pos = (m['disc_payback'] < project_lifetime)
        else:
            payback_label = t('econ_metric_payback')
            payback_val_str = f"{m['payback']:.2f} yr" if m['payback'] != float('inf') else "N/A"
            payback_sub = "Simple Return / Retorno Simple"
            is_pos = (m['payback'] < project_lifetime)
        render_kpi_card(payback_label, payback_val_str, payback_sub, is_positive=is_pos)

    with col_kpi4:
        render_kpi_card(
            t('econ_metric_pi'),
            f"{m['pi']:.2f}",
            "Profitability Index / Índice Rentabilidad",
            is_positive=(m['pi'] > 1.0)
        )

    with col_kpi5:
        if m['breakeven_tipping'] <= 0:
            be_sub = "Autosostenible (Venta productos cubre costos)" if lang == 'es' else "Self-sustaining (Product sales cover costs)"
            is_pos = True
        else:
            be_sub = "Tarifa equilibrio (VAN=0)" if lang == 'es' else "Tipping fee for NPV=0"
            is_pos = (m['breakeven_tipping'] < econ['opex_tipping'])
        render_kpi_card(
            t('econ_metric_breakeven_tipping'),
            f"{CURR_SYM}{m['breakeven_tipping']:.2f}/gal",
            be_sub,
            is_positive=is_pos
        )


def _render_sludge_scenarios(econ, lang):
    """The three sludge scenarios (purchase / free / disposal fee) side by side, then the break-even note."""
    st.markdown("##### " + ("Escenarios del lodo" if lang == 'es' else "Sludge scenarios"))
    scenario_cols, scenario_rows = [], {}
    yrs = "años" if lang == 'es' else "yr"
    for sc in SLUDGE_SCENARIOS:
        fee = scenario_tipping_fee(sc, econ['sludge_cost'], econ['tipping_y'])
        ms = econ['_model'](fee)
        sludge_cost_y1 = max(0.0, -fee) * econ['sludge_treated_gal']   # what the plant pays for the sludge
        revenue_y1 = ms['rev_flows'][1] + sludge_cost_y1                # revenue without the purchase cost
        scenario_cols.append(f"{SLUDGE_SCENARIO_LABELS[sc][lang]} ({fee:+,.2f} RD$/gal)")
        for label, value in (
            ("Ingresos año 1 (RD$)" if lang == 'es' else "Year-1 revenue (RD$)", f"{revenue_y1:,.2f}"),
            ("Costo del lodo año 1 (RD$)" if lang == 'es' else "Year-1 sludge cost (RD$)", f"{sludge_cost_y1:,.2f}"),
            ("EBITDA año 1 (RD$)" if lang == 'es' else "Year-1 EBITDA (RD$)", f"{ms['rev_flows'][1] - ms['opex_flows'][1]:,.2f}"),
            ("VAN (RD$)" if lang == 'es' else "NPV (RD$)", f"{ms['npv']:,.2f}"),
            ("TIR" if lang == 'es' else "IRR", format_irr(ms['irr'])),
            ("Recuperación simple" if lang == 'es' else "Simple payback",
             f"{ms['payback']:.2f} {yrs}" if ms['payback'] != float('inf') else "N/A"),
            ("Recuperación descontada" if lang == 'es' else "Discounted payback",
             f"{ms['disc_payback']:.2f} {yrs}" if ms['disc_payback'] != float('inf') else "N/A"),
            ("Índice de rentabilidad" if lang == 'es' else "Profitability index", f"{ms['pi']:.2f}"),
        ):
            scenario_rows.setdefault(label, []).append(value)
    st.table(pd.DataFrame.from_dict(scenario_rows, orient='index', columns=scenario_cols))
    st.info(breakeven_note(econ['m']['breakeven_tipping'], lang))


def _cumulative_discounted(m):
    """Cumulative discounted cash flow per year, starting at -CAPEX in year 0."""
    return list(accumulate(m['disc_flows']))


def _render_cumulative_cash_flow_chart(econ):
    """Cumulative cash flow (bars) and cumulative discounted cash flow (line) over the project life."""
    m = econ['m']
    project_lifetime = econ['project_lifetime']
    st.markdown(f"##### 📈 {t('econ_metric_cashflow')}")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=m['years'],
        y=m['cum_flows'],
        name="Undiscounted Cumulative Cash Flow / Flujo Acumulado",
        marker_color="#3b82f6",
        opacity=0.85
    ))
    fig.add_trace(go.Scatter(
        x=m['years'],
        y=_cumulative_discounted(m),
        name="Discounted Cumulative Cash Flow (NPV) / Flujo Descontado",
        line=dict(color="#10b981", width=3, dash='dash'),
        mode='lines+markers',
        marker=dict(size=8)
    ))
    fig.add_trace(go.Scatter(   # zero line
        x=[0, project_lifetime],
        y=[0, 0],
        showlegend=False,
        line=dict(color="#64748b", width=1.5, dash='solid'),
        mode='lines'
    ))
    fig.update_layout(
        title=dict(
            text=f"{t('econ_metric_cashflow')} vs. Project Lifetime / Vida del Proyecto",
            font=dict(size=14)
        ),
        xaxis=dict(
            title="Project Year / Año del Proyecto",
            tickmode='linear',
            tick0=0,
            dtick=1,
        ),
        yaxis=dict(
            title=f"Cumulative Balance / Balance Acumulado ({CURR_SYM})",
        ),
        legend=_bottom_legend(-0.3, 10),
        margin=dict(l=40, r=40, t=40, b=40),
        height=380
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_npv_vs_sludge_price(econ, lang):
    """NPV as a function of what the plant receives per gallon of sludge (negative = it pays for it)."""
    es = lang == 'es'
    m, model = econ['m'], econ['_model']
    be = m['breakeven_tipping']
    scen = {sc: scenario_tipping_fee(sc, econ['sludge_cost'], econ['tipping_y']) for sc in SLUDGE_SCENARIOS}
    lo = min([be] + list(scen.values())) - 10.0
    hi = max([be] + list(scen.values())) + 10.0
    xs = list(np.linspace(lo, hi, 41))
    npvs = [model(x)['npv'] for x in xs]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=npvs, mode='lines', line=dict(color="#38bdf8", width=3),
                             name="VAN" if es else "NPV"))
    fig.add_trace(go.Scatter(x=[scen[s] for s in SLUDGE_SCENARIOS], y=[model(scen[s])['npv'] for s in SLUDGE_SCENARIOS],
                             mode='markers+text', marker=dict(size=10, color="#f59e0b"),
                             text=[SLUDGE_SCENARIO_LABELS[s][lang] for s in SLUDGE_SCENARIOS],
                             textposition="top center", name="Escenarios" if es else "Scenarios"))
    fig.add_hline(y=0, line=dict(color="#64748b", width=1))
    fig.add_vline(x=be, line=dict(color="#ef4444", dash='dash'),
                  annotation_text=(f"VAN = 0 en {be:,.2f} RD$/gal" if es else f"NPV = 0 at {be:,.2f} RD$/gal"),
                  annotation_font_color="#fca5a5")
    fig.update_layout(
        title=("VAN contra precio del lodo" if es else "NPV vs. sludge price"),
        xaxis=dict(title=("Precio del lodo para la planta (RD$/gal): negativo = costo de compra, positivo = tarifa"
                          if es else "Sludge price for the plant (RD$/gal): negative = purchase cost, positive = fee")),
        yaxis=dict(title="VAN (RD$)" if es else "NPV (RD$)"),
        showlegend=False, height=380, **_CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


def _render_cost_composition(econ, lang):
    """CAPEX and year-1 OPEX composition (same breakdown the cash-flow table uses)."""
    es = lang == 'es'
    capex = {
        ("Equipo principal" if es else "Main equipment"): econ['capex_equip'],
        ("Instalación" if es else "Installation"): econ['capex_install'],
        ("Obras civiles" if es else "Civil works"): econ['capex_civil'],
        ("Tuberías y electricidad" if es else "Piping & electrical"): econ['capex_piping_elec'],
        ("Ingeniería" if es else "Engineering"): econ['capex_eng'],
        ("Permisos" if es else "Permits"): econ['capex_permits'],
        ("Contingencias" if es else "Contingency"): econ['capex_cont'],
    }
    ob = econ['m']['opex_breakdown']
    opex = {
        ("Manejo de lodos" if es else "Sludge handling"): ob['handling'],
        ("Combustible auxiliar" if es else "Auxiliary fuel"): ob['fuel'],
        ("Electricidad" if es else "Electricity"): ob['electricity'],
        ("Insumos auxiliares" if es else "Aux. utilities"): ob['aux_utilities'],
        ("Diésel planta" if es else "Generator diesel"): ob['gen_diesel'],
        ("Mano de obra" if es else "Labor"): ob['labor'],
        ("Mantenimiento" if es else "Maintenance"): ob['maintenance'],
        ("Seguros y licencias" if es else "Insurance"): ob['insurance_tax'],
    }
    col_a, col_b = st.columns(2)
    for col, data, title in (
        (col_a, capex, f"CAPEX: RD$ {sum(capex.values()):,.2f}"),
        (col_b, opex, f"OPEX {'año' if es else 'year'} 1: RD$ {sum(opex.values()):,.2f}"),
    ):
        data = {k: v for k, v in data.items() if v > 0}
        fig = go.Figure(go.Pie(labels=list(data), values=list(data.values()), hole=0.5, sort=False,
                               textinfo='percent', hovertemplate="%{label}<br>RD$ %{value:,.2f}<extra></extra>"))
        fig.update_layout(title=title, height=360, legend=dict(font=dict(size=10)), **_CHART_LAYOUT)
        with col:
            st.plotly_chart(fig, use_container_width=True)


def _render_annual_quantities(econ, summary, lang):
    """Annual quantities table, then the cycle/calendar details of the operating mode."""
    e = econ
    st.markdown(f"##### 🎛️ {t('econ_summary_table')}")

    summary_data = {
        t('econ_table_param'): [
            t('econ_annual_sludge'),
            t('econ_annual_oil'),
            t('econ_annual_char'),
            t('econ_annual_gas'),
            t('econ_annual_fuel'),
            t('econ_annual_elec'),
            t('econ_annual_gen_fuel')
        ],
        t('econ_table_val'): [
            e['sludge_treated_gal'],
            e['oil_produced_gal'],
            e['char_produced_kg'],
            e['gas_produced_m3'],
            e['fuel_consumed_gal'],
            e['elec_consumed_kwh'],
            e['generator_fuel_consumed_gal']
        ],
        t('econ_table_units'): [
            "gal/yr",
            "gal/yr",
            "kg/yr",
            "m³/yr",
            "gal/yr",
            "kWh/yr",
            "gal/yr"
        ]
    }
    df_summary = pd.DataFrame(summary_data)
    df_summary[t('econ_table_val')] = df_summary[t('econ_table_val')].map(lambda x: f"{x:,.2f}")
    st.table(df_summary)

    holidays_days, shutdown_days = e['holidays_days'], e['shutdown_days']
    t_heat_min, t_hold_min = e['t_heat_min'], e['t_hold_min']
    batch_cooldown_h, batch_loading_h = e['batch_cooldown_h'], e['batch_loading_h']
    t_op_batch_hours, t_cycle_hours = e['t_op_batch_hours'], e['t_cycle_hours']
    maint_stop_total_h, maint_cooldown_h, cleaning_time_h = e['maint_stop_total_h'], e['maint_cooldown_h'], e['cleaning_time_h']
    batches_before_cleaning, maint_penalty_per_batch_h = e['batches_before_cleaning'], e['maint_penalty_per_batch_h']
    available_calendar_days, batches_per_year = e['available_calendar_days'], e['batches_per_year']
    operating_days_batches, cleaning_days_annual, campaign_active_days = e['operating_days_batches'], e['cleaning_days_annual'], e['campaign_active_days']
    gen_diesel_per_batch = e['gen_diesel_batch']
    burner_fuel_per_batch = summary['waste_oil_consumed_gal']
    if lang == 'es':
        st.info(f"⏱️ **Detalles del Ciclo, Mantenimiento y Calendario:**\n"
                f"- Proceso térmico: Calentamiento `{t_heat_min:.1f} min` | Retención `{t_hold_min:.1f} min`\n"
                f"- Turnaround de rutina: Enfriamiento `{batch_cooldown_h*60:.0f} min` (`{batch_cooldown_h:.2f} h`) | Carga y descarga `{batch_loading_h*60:.0f} min` (`{batch_loading_h:.2f} h`)\n"
                f"- Ciclo operativo por lote: `{t_op_batch_hours:.2f} horas`\n"
                f"- Mantenimiento programado: Parada de `{maint_stop_total_h:.2f} h` (`{maint_cooldown_h:.2f} h` enfriamiento + `{cleaning_time_h:.2f} h` limpieza) cada `{batches_before_cleaning}` lotes (+`{maint_penalty_per_batch_h:.2f} h/lote` ponderado)\n"
                f"- Tiempo efectivo promedio por lote: `{t_cycle_hours:.2f} horas`\n"
                f"- **Balance Calendario (365 días base):** Feriados: `{holidays_days} d` | Paradas mayores: `{shutdown_days} d` | Disponibles planta: `{available_calendar_days} d`\n"
                f"- **Días de Operación al Año:** `{operating_days_batches:.1f} días de proceso de lotes` + `{cleaning_days_annual:.1f} días de parada por limpieza` = `{campaign_active_days:.1f} días activos` (`{batches_per_year:.0f} lotes/año`)\n"
                f"- **Consumo por lote:** Diésel planta eléctrica: `{gen_diesel_per_batch:.2f} gal` | Combustible quemadores: `{burner_fuel_per_batch:.2f} gal`")
    else:
        st.info(f"⏱️ **Batch Timeline, Maintenance & Calendar Details:**\n"
                f"- Thermal process: Heating `{t_heat_min:.1f} min` | Holding `{t_hold_min:.1f} min`\n"
                f"- Routine turnaround: Cooldown `{batch_cooldown_h*60:.0f} min` (`{batch_cooldown_h:.2f} h`) | Loading/Unloading `{batch_loading_h*60:.0f} min` (`{batch_loading_h:.2f} h`)\n"
                f"- Operational batch cycle: `{t_op_batch_hours:.2f} hours`\n"
                f"- Scheduled maintenance: Downtime of `{maint_stop_total_h:.2f} h` (`{maint_cooldown_h:.2f} h` cooldown + `{cleaning_time_h:.2f} h` cleaning) every `{batches_before_cleaning}` batches (+`{maint_penalty_per_batch_h:.2f} h/batch` weighted)\n"
                f"- Effective average cycle time: `{t_cycle_hours:.2f} hours`\n"
                f"- **Annual Calendar (365 days):** Holidays: `{holidays_days} d` | Major shutdown: `{shutdown_days} d` | Plant available: `{available_calendar_days} d`\n"
                f"- **Operating Days per Year:** `{operating_days_batches:.1f} batch process days` + `{cleaning_days_annual:.1f} cleaning days` = `{campaign_active_days:.1f} active days` (`{batches_per_year:.0f} batches/year`)\n"
                f"- **Consumption per batch:** Generator diesel: `{gen_diesel_per_batch:.2f} gal` | Burner fuel: `{burner_fuel_per_batch:.2f} gal`")


def _render_cash_flow_breakdown(econ):
    """Year-1 (base) cash flow by item: CAPEX, each revenue and each cost."""
    m = econ['m']
    rev, cost = m['revenue_breakdown'], m['opex_breakdown']
    st.markdown("##### 💵 Cash Flow Breakdown / Desglose de Caja")

    col_flow_name = f"Base Annual Flow / Flujo Anual ({CURR_SYM})"
    financial_breakdown = {
        "Category / Categoría": [
            "Total CAPEX (Inversión Inicial)",
            "Disposal Tipping Fees Revenue (Disposición)",
            "Pyrolysis oil Sales Revenue (Venta Aceite pirolítico)",
            "Char Sales Revenue (Venta Carbón)",
            "Syngas Sales Revenue (Venta Syngas)",
            "Carbon Offset Revenue (Venta de Carbono)",
            "Feedstock Handling Costs (Costo Manejo Lodos)",
            "Burner Fuel Consumption Costs (Combustible)",
            "Electricity Utilities Costs (Electricidad)",
            "Water & Aux Utilities (Servicios Auxiliares)",
            "Generator Diesel Fuel Costs (Diésel Planta)",
            "Annual Labor & Operators (Mano de Obra)",
            "Annual Maintenance Cost (Mantenimiento)",
            "Insurance & Property Tax (Seguros y Tasas)"
        ],
        col_flow_name: [
            -econ['total_capex'],
            rev['tipping'],
            rev['oil'],
            rev['char'],
            rev['gas'],
            rev['carbon'],
            -cost['handling'],
            -cost['fuel'],
            -cost['electricity'],
            -cost['aux_utilities'],
            -cost['gen_diesel'],
            -cost['labor'],
            -cost['maintenance'],
            -cost['insurance_tax']
        ]
    }
    df_financial_disp = pd.DataFrame(financial_breakdown)
    df_financial_disp[col_flow_name] = df_financial_disp[col_flow_name].map(_fmt_money)
    st.table(df_financial_disp)


# --- monthly cash flow (year 1) ------------------------------------------------------------------
_COL_MONTH = "Month / Mes"
_COL_DAYS = "Days Operated / Días Operados"
_COL_OIL_PCT = "Pyrolysis oil Sales / Venta Aceite pirolítico (%)"
_COL_CHAR_PCT = "Char Sales / Venta Carbón (%)"
_COL_GAS_PCT = "Syngas Sales / Venta Syngas (%)"


def _render_monthly_cash_flow(econ, summary):
    """Editable month plan (days operated, % of stock sold), the resulting monthly table, CSV and charts."""
    st.markdown("---")
    st.markdown(f"#### {t('econ_monthly_title')}")
    st.markdown(t('econ_monthly_desc'))

    edited_df = _monthly_plan_editor(econ['annual_days'])
    months = _monthly_projection(econ, summary, edited_df)
    _render_monthly_table(months)
    _render_monthly_charts(months)


def _monthly_plan_editor(annual_days):
    """Month plan kept in session_state['monthly_config']; reset to an even split when the
    annual operating days change."""
    if 'monthly_config' not in st.session_state:
        avg_days = float(annual_days) / 12.0
        st.session_state.monthly_config = pd.DataFrame({
            _COL_MONTH: [f"Month / Mes {i:02d}" for i in range(1, 13)],
            _COL_DAYS: [round(avg_days, 1)] * 12,
            _COL_OIL_PCT: [100.0] * 12,
            _COL_CHAR_PCT: [100.0] * 12,
            _COL_GAS_PCT: [100.0] * 12
        })

    current_days_sum = st.session_state.monthly_config[_COL_DAYS].sum()
    if abs(current_days_sum - annual_days) > 0.5:
        avg_days = float(annual_days) / 12.0
        st.session_state.monthly_config[_COL_DAYS] = [round(avg_days, 1)] * 12

    edited_df = st.data_editor(
        st.session_state.monthly_config,
        num_rows="fixed",
        width='stretch',
        column_config={
            _COL_MONTH: st.column_config.TextColumn("Month / Mes", disabled=True),
            _COL_DAYS: st.column_config.NumberColumn("Days Operated", min_value=0.0, max_value=31.0, step=0.5),
            _COL_OIL_PCT: st.column_config.NumberColumn("Pyrolysis oil Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
            _COL_CHAR_PCT: st.column_config.NumberColumn("Char Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
            _COL_GAS_PCT: st.column_config.NumberColumn("Syngas Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
        },
        key="monthly_editor"
    )
    st.session_state.monthly_config = edited_df
    return edited_df


def _monthly_projection(econ, summary, plan_df):
    """Month-by-month production, sales with oil/char inventory carried over, revenue, OPEX and net cash
    flow after taxes. Returns a dict of 12-item lists keyed by the monthly table's column names."""
    e = econ
    inv_oil = 0.0
    inv_char = 0.0
    cols = {name: [] for name in (
        "Month", "Days Operated", "Sludge Treated (gal)",
        "Pyrolysis oil Produced (gal)", "Pyrolysis oil Sold (gal)", "Pyrolysis oil Inventory (gal)",
        "Char Produced (kg)", "Char Sold (kg)", "Char Inventory (kg)",
        "Syngas Produced (m³)", "Syngas Sold (m³)",
        f"Revenue ({CURR_SYM})", f"OPEX ({CURR_SYM})", f"Net Cash Flow ({CURR_SYM})")}

    for idx in range(12):
        row = plan_df.iloc[idx]
        days = row[_COL_DAYS]
        oil_pct = row[_COL_OIL_PCT]
        char_pct = row[_COL_CHAR_PCT]
        gas_pct = row.get(_COL_GAS_PCT, 100.0)

        # Production and consumption of the month
        batches = np.floor((days * 24.0) / e['t_cycle_hours']) if e['t_cycle_hours'] > 0 else 0.0
        sludge_kg = summary['batch_load_kg'] * batches
        oil_kg = summary['oil_yield_kg'] * batches
        char_kg = summary['char_yield_kg'] * batches
        gas_kg = summary.get('syngas_flare_kg', summary['gas_yield_kg']) * batches

        fuel_gal = summary['waste_oil_consumed_gal'] * batches
        elec_kwh = 0.0
        diesel_gal = e['gen_diesel_batch'] * batches

        sludge_gal = (sludge_kg / e['sludge_density']) * GAL_PER_M3
        oil_prod_gal = (oil_kg / e['oil_density']) * GAL_PER_M3
        char_prod_kg = char_kg
        gas_prod_m3 = gas_kg / e['gas_density']

        # Sales take a share of what is in stock; the rest stays as inventory (gas is not stored)
        avail_oil = inv_oil + oil_prod_gal
        avail_char = inv_char + char_prod_kg
        oil_sold = avail_oil * (oil_pct / 100.0)
        char_sold = avail_char * (char_pct / 100.0)
        gas_sold = gas_prod_m3 * (gas_pct / 100.0)
        inv_oil = avail_oil - oil_sold
        inv_char = avail_char - char_sold

        rev_tip = sludge_gal * e['opex_tipping']
        rev_o = oil_sold * e['price_oil']
        rev_c = char_sold * e['price_char']
        rev_g = gas_sold * e['price_gas']
        char_carbon_month_kg = summary.get('char_organic_kg', summary['char_yield_kg']) * batches
        rev_carb = ((char_carbon_month_kg * e['rate_carbon_offset']) / 1000.0) * e['price_carbon']
        total_rev = rev_tip + rev_o + rev_c + rev_g + rev_carb

        total_capex = e['total_capex']
        c_handling = sludge_gal * e['opex_handling']
        c_fuel = fuel_gal * e['opex_fuel']
        c_elec = elec_kwh * e['opex_electricity']
        c_aux = e['opex_aux_utilities'] / 12.0
        c_diesel = diesel_gal * e['price_generator_fuel']
        c_labor = e['opex_labor'] / 12.0
        c_maint = (total_capex * (e['opex_maint'] / 100.0)) / 12.0
        c_ins_tax = (total_capex * (e['opex_insurance_tax'] / 100.0)) / 12.0
        total_opex = c_handling + c_fuel + c_elec + c_aux + c_diesel + c_labor + c_maint + c_ins_tax

        ebitda = total_rev - total_opex
        depr = total_capex / (e['project_lifetime'] * 12.0) if e['project_lifetime'] > 0 else 0.0
        taxable = ebitda - depr
        taxes = max(0.0, taxable * (e['tax_rate'] / 100.0))
        net_cf = ebitda - taxes

        for name, value in zip(cols, (row[_COL_MONTH], days, sludge_gal,
                                      oil_prod_gal, oil_sold, inv_oil,
                                      char_prod_kg, char_sold, inv_char,
                                      gas_prod_m3, gas_sold,
                                      total_rev, total_opex, net_cf)):
            cols[name].append(value)
    return cols


def _render_monthly_table(months):
    """Monthly table (formatted) and its CSV download (raw numbers)."""
    df_monthly_proj = pd.DataFrame(months)
    df_monthly_disp = df_monthly_proj.copy()
    money_cols = (f"Revenue ({CURR_SYM})", f"OPEX ({CURR_SYM})", f"Net Cash Flow ({CURR_SYM})")
    for col in df_monthly_disp.columns[1:]:
        if col == "Days Operated":
            df_monthly_disp[col] = df_monthly_disp[col].map(lambda x: f"{x:.1f}")
        elif col in money_cols:
            df_monthly_disp[col] = df_monthly_disp[col].map(_fmt_money)
        else:
            df_monthly_disp[col] = df_monthly_disp[col].map(lambda x: f"{x:,.1f}")
    st.dataframe(df_monthly_disp, width='stretch')

    csv_monthly_buf = io.StringIO()
    df_monthly_proj.to_csv(csv_monthly_buf, index=False)
    st.download_button(
        label="📥 Download Monthly Cash Flows as CSV / Descargar Flujo Mensual (CSV)",
        data=csv_monthly_buf.getvalue().encode('utf-8'),
        file_name="pyrolysis_monthly_cash_flows.csv",
        mime="text/csv",
        key="download_monthly_cash_flows"
    )


def _bar(x, y, name, color, hover):
    return go.Bar(x=x, y=y, name=name, marker_color=color, opacity=0.85, hovertemplate=hover)


def _line(x, y, name, color, width, marker_size, hover, dash=None):
    line = dict(color=color, width=width) if dash is None else dict(color=color, width=width, dash=dash)
    return go.Scatter(x=x, y=y, name=name, line=line, mode='lines+markers', marker=dict(size=marker_size),
                      hovertemplate=hover)


def _render_monthly_charts(months):
    """Two tabs: monthly money (revenue, OPEX, net and cumulative flow) and oil/char volumes."""
    st.markdown("---")
    st.markdown(f"#### {t('econ_monthly_chart_title')}")
    st.markdown(t('econ_monthly_chart_desc'))

    m_net_flow = months[f"Net Cash Flow ({CURR_SYM})"]
    month_labels = [f"M{i+1:02d}" for i in range(12)]
    money_hover = '%{x}: ' + CURR_SYM + '%{y:,.2f}<extra></extra>'
    gal_hover = '%{x}: %{y:,.1f} gal<extra></extra>'
    kg_hover = '%{x}: %{y:,.1f} kg<extra></extra>'

    tab_m_fin, tab_m_vol = st.tabs([t('econ_monthly_tab_financial'), t('econ_monthly_tab_volumes')])

    with tab_m_fin:
        fig_m_fin = go.Figure()
        fig_m_fin.add_trace(_bar(month_labels, months[f"Revenue ({CURR_SYM})"], t('econ_monthly_rev_label'), "#10b981", money_hover))
        fig_m_fin.add_trace(_bar(month_labels, months[f"OPEX ({CURR_SYM})"], t('econ_monthly_opex_label'), "#ef4444", money_hover))
        fig_m_fin.add_trace(_line(month_labels, m_net_flow, t('econ_monthly_net_label'), "#3b82f6", 3, 7, money_hover))
        fig_m_fin.add_trace(_line(month_labels, np.cumsum(m_net_flow).tolist(), t('econ_monthly_cum_label'),
                                  "#f59e0b", 2.5, 6, money_hover, dash='dash'))
        fig_m_fin.add_hline(y=0, line_width=1, line_dash="solid", line_color="#64748b")
        fig_m_fin.update_layout(
            title=dict(
                text=f"{t('econ_monthly_chart_title')}",
                font=dict(size=14)
            ),
            xaxis=dict(
                title="Month / Mes",
            ),
            yaxis=dict(
                title=f"Amount / Monto ({CURR_SYM})",
            ),
            barmode='group',
            legend=_bottom_legend(-0.35, 10),
            margin=dict(l=50, r=40, t=40, b=50),
            height=400
        )
        st.plotly_chart(fig_m_fin, use_container_width=True)

    with tab_m_vol:
        fig_m_vol = go.Figure()
        fig_m_vol.add_trace(_bar(month_labels, months["Pyrolysis oil Produced (gal)"], t('econ_monthly_oil_prod'), "#8b5cf6", gal_hover))
        fig_m_vol.add_trace(_bar(month_labels, months["Pyrolysis oil Sold (gal)"], t('econ_monthly_oil_sold'), "#10b981", gal_hover))
        fig_m_vol.add_trace(_line(month_labels, months["Pyrolysis oil Inventory (gal)"], t('econ_monthly_oil_inv'),
                                  "#f43f5e", 2.5, 6, gal_hover, dash='dash'))
        fig_m_vol.add_trace(_bar(month_labels, months["Char Produced (kg)"], t('econ_monthly_char_prod'), "#0ea5e9", kg_hover))
        fig_m_vol.add_trace(_bar(month_labels, months["Char Sold (kg)"], t('econ_monthly_char_sold'), "#fde047", kg_hover))
        fig_m_vol.add_trace(_line(month_labels, months["Char Inventory (kg)"], t('econ_monthly_char_inv'),
                                  "#d97706", 2.5, 6, kg_hover, dash='dash'))
        fig_m_vol.update_layout(
            title=dict(
                text=f"{t('econ_monthly_tab_volumes')} - Pyrolysis oil (gal) & Char (kg) Dynamics",
                font=dict(size=14)
            ),
            xaxis=dict(
                title="Month / Mes",
            ),
            yaxis=dict(
                title="Quantity / Cantidad (gal / kg)",
                tickformat=",~f"
            ),
            barmode='group',
            legend=_bottom_legend(-0.35, 9),
            margin=dict(l=50, r=40, t=40, b=50),
            height=420
        )
        st.plotly_chart(fig_m_vol, use_container_width=True)


# --- sensitivity and yearly projection -----------------------------------------------------------
def _render_sensitivity_tornado(econ):
    """NPV when CAPEX, all OPEX, the tipping fee, the oil price or the char price move ±10 % and ±20 %,
    sorted by swing."""
    e = econ
    st.markdown("---")
    st.markdown(f"#### {t('econ_sensitivity_title')}")
    st.markdown(t('econ_sensitivity_desc'))

    def get_perturbed_npv(param, change_pct):
        mult = 1.0 + (change_pct / 100.0)

        def scaled(value, group):
            return value * mult if param == group else value

        res = run_financial_model(
            scaled(e['total_capex'], 'capex'), e['sludge_treated_gal'], e['oil_produced_gal'],
            e['char_produced_kg'], e['gas_produced_m3'],
            e['fuel_consumed_gal'], e['elec_consumed_kwh'], e['generator_fuel_consumed_gal'],
            scaled(e['opex_handling'], 'opex'), scaled(e['opex_fuel'], 'opex'), scaled(e['opex_electricity'], 'opex'),
            scaled(e['opex_aux_utilities'], 'opex'), scaled(e['price_generator_fuel'], 'opex'),
            scaled(e['opex_labor'], 'opex'), scaled(e['opex_maint'], 'opex'), scaled(e['opex_insurance_tax'], 'opex'),
            scaled(e['opex_tipping'], 'tipping'), scaled(e['price_oil'], 'oil'), scaled(e['price_char'], 'char'),
            e['price_gas'], e['price_carbon'], e['rate_carbon_offset'],
            e['discount_rate'], e['project_lifetime'], e['tax_rate'], e['inflation_rate'],
            char_carbon_kg=e['char_carbon_kg']
        )
        return res['npv']

    sens_keys = ['capex', 'opex', 'tipping', 'oil', 'char']
    sens_labels = [t('econ_param_capex'), t('econ_param_opex'), t('econ_param_tipping'), t('econ_param_oil'), t('econ_param_char')]
    npvs = {pct: [get_perturbed_npv(k, pct) for k in sens_keys] for pct in (-20, -10, +10, +20)}
    base_npv = e['m']['npv']

    # Widest swing at the top of the chart
    swings = [abs(npvs[20][i] - npvs[-20][i]) for i in range(len(sens_keys))]
    sorted_idx = np.argsort(swings)
    sorted_labels = [sens_labels[i] for i in sorted_idx]

    fig_sens = go.Figure()
    for pct, color, edge in ((+20, '#10b981', '#047857'), (+10, '#6ee7b7', '#34d399'),
                             (-10, '#fca5a5', '#f87171'), (-20, '#ef4444', '#dc2626')):
        fig_sens.add_trace(go.Bar(
            y=sorted_labels,
            x=[npvs[pct][i] - base_npv for i in sorted_idx],
            base=base_npv,
            orientation='h',
            name=f'{pct:+d}% Variation',
            marker=dict(color=color, line=dict(color=edge, width=1)),
            hovertemplate=f'NPV at {pct:+d}%: ' + CURR_SYM + '%{x:,.2f}<extra></extra>'
        ))

    fig_sens.add_vline(x=base_npv, line_width=2, line_dash="dash", line_color="gray", annotation_text=f"Base Case NPV: {CURR_SYM}{base_npv:,.2f}")
    fig_sens.update_layout(
        title=dict(
            text=f"NPV Sensitivity Tornado Chart ({CURR_SYM})",
            font=dict(size=14)
        ),
        xaxis=dict(
            title=f"Net Present Value (NPV) ({CURR_SYM})",
        ),
        yaxis=dict(
        ),
        barmode='overlay',
        legend=_bottom_legend(-0.25, 10),
        margin=dict(l=120, r=40, t=40, b=40),
        height=350
    )
    st.plotly_chart(fig_sens, use_container_width=True)


def _render_yearly_projection_table(econ):
    """Year-by-year projection table and its CSV download."""
    m = econ['m']
    st.markdown("---")
    st.markdown("#### 📅 Year-by-Year Financial Projections / Tabla de Proyecciones")

    proj_data = {
        "Year / Año": m['years'],
        f"CAPEX ({CURR_SYM})": [m['net_flows'][0] if yr == 0 else 0.0 for yr in m['years']],
        f"Revenue / Ingresos ({CURR_SYM})": m['rev_flows'],
        f"OPEX ({CURR_SYM})": m['opex_flows'],
        f"Depreciation ({CURR_SYM})": m['depr_flows'],
        f"Taxes / Impuestos ({CURR_SYM})": m['tax_flows'],
        f"Net Cash Flow ({CURR_SYM})": m['net_flows'],
        f"Discounted Cash Flow ({CURR_SYM})": m['disc_flows'],
        f"Cumulative NPV ({CURR_SYM})": _cumulative_discounted(m)
    }
    df_proj = pd.DataFrame(proj_data)
    df_proj_disp = df_proj.copy()
    for col in df_proj_disp.columns:
        if col != "Year / Año":
            df_proj_disp[col] = df_proj_disp[col].map(_fmt_money)
    st.dataframe(df_proj_disp, width='stretch')

    csv_buffer = io.StringIO()
    df_proj.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Download Projections as CSV / Descargar Proyecciones (CSV)",
        data=csv_buffer.getvalue().encode('utf-8'),
        file_name="pyrolysis_financial_projections.csv",
        mime="text/csv",
        key="download_financial_projections"
    )


# =============================================================================================
# 4. Sustainability section
# =============================================================================================
def render_sustainability_tab(summary, solver_inputs):
    """Renders the independent Sustainability & Carbon Offsets Dashboard."""
    lang = get_lang()
    st.markdown(f"### {t('econ_sustainability_title')}")
    st.markdown(
        t('econ_sustainability_desc', "Evaluate the carbon sequestration potential and environmental benefits of industrial pyrolysis sludge treatment.")
    )
    st.markdown("---")

    ss = st.session_state
    price_carbon = ss.get('price_carbon', 1200.0)
    rate_carbon_offset = ss.get('rate_carbon_offset', 2.2)

    batches_per_year = _sustainability_batches_per_year(summary, solver_inputs)
    # Carbon credit applies to carbon-bearing char only (ash excluded)
    char_produced_kg = summary.get('char_organic_kg', summary['char_yield_kg']) * batches_per_year

    co2_tons = (char_produced_kg * rate_carbon_offset) / 1000.0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label=t('econ_co2_sequestered_annually'),
            value=f"{co2_tons:,.2f} t CO2e/yr",
            delta=f"{CURR_SYM}{co2_tons * price_carbon:,.2f}/yr"
        )
    with col2:
        st.metric(
            label=t('econ_co2_trees_eq'),
            value=f"{int(co2_tons / CO2_T_PER_TREE_YEAR):,}"
        )
    with col3:
        st.metric(
            label=t('econ_co2_cars_eq'),
            value=f"{int(co2_tons / CO2_T_PER_CAR_YEAR):,}"
        )

    _render_process_emissions(summary, batches_per_year, co2_tons, lang)

    st.markdown(f"""
    <div style="
        background: rgba(16,185,129,0.10);
        padding: 22px;
        border-radius: 12px;
        border: 1px solid #10b981;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-top: 20px;
    ">
        <h4 style="margin: 0 0 10px 0; color: #10b981; font-size: 16px; font-weight: 600;">🌿 Char & Carbon Capture Sequestration</h4>
        <p style="margin: 0; font-size: 13.5px; line-height: 1.6;">
            Pyrolysis converts organic waste sludge into char, locking carbon in a highly stable solid form. 
            Unlike decomposition, which releases CO2 and methane, char stores carbon safely in soils for hundreds of years.
            Each kilogram of char prevents approx {rate_carbon_offset:.2f} kg of atmospheric CO2 equivalents from warming the planet.
        </p>
    </div>
    """, unsafe_allow_html=True)


def _sustainability_annual_days():
    """Operating days per year: the value compute_economics stored, else 365 minus stops and holidays."""
    shutdown_days = int(st.session_state.get('shutdown_days', 15))
    holidays_days = int(st.session_state.get('holidays_days', 15))
    available_calendar_days = max(1, 365 - shutdown_days - holidays_days)
    return st.session_state.get('annual_days', available_calendar_days)


def _sustainability_batches_per_year(summary, solver_inputs):
    """Batches per year from session_state, with the same cycle arithmetic as compute_economics."""
    ss = st.session_state
    t_cycle_min, _, _ = batch_thermal_cycle_min(summary, solver_inputs)
    batch_cooldown_h = float(ss.get('batch_cooldown_h', 0.50))
    batch_loading_h = float(ss.get('batch_loading_h', 0.50))
    batch_turnaround_h = float(ss.get('batch_turnaround_h', batch_cooldown_h + batch_loading_h))
    batches_before_cleaning = int(ss.get('batches_before_cleaning', 20))
    cleaning_time_h = float(ss.get('cleaning_time_h', 4.0))
    maint_cooldown_h = float(ss.get('maint_cooldown_h', 6.0))
    maint_penalty_per_batch_h = (maint_cooldown_h + cleaning_time_h) / max(batches_before_cleaning, 1)
    t_op_batch_hours = (t_cycle_min / 60.0) + batch_turnaround_h
    t_cycle_hours = t_op_batch_hours + maint_penalty_per_batch_h
    batches_fixed = int(ss.get('econ_batches_per_year', 0))
    if batches_fixed > 0:
        return float(batches_fixed)
    return np.floor((_sustainability_annual_days() * 24.0) / t_cycle_hours) if t_cycle_hours > 0 else 0.0


def _render_process_emissions(summary, batches_per_year, co2_tons, lang):
    """Batch mode: CO2 emitted by the burner fuel, generator diesel and syngas, and the net balance."""
    ss = st.session_state
    fuel_density = float(ss.get('fuel_density', 0.90))
    gen_diesel_batch = float(ss.get('gen_diesel_batch', 1.0))
    fuel_per_batch_gal = float(ss.get('econ_fuel_gal_per_batch', 0.0)) or summary['waste_oil_consumed_gal']
    co2_burner_t = fuel_per_batch_gal * batches_per_year * fuel_density * LITRES_PER_GAL * EF_CO2_FUEL_OIL_KG_PER_KG / 1000.0
    co2_diesel_t = gen_diesel_batch * batches_per_year * EF_CO2_DIESEL_KG_PER_GAL / 1000.0
    co2_syngas_t = summary['gas_yield_kg'] * batches_per_year * EF_CO2_SYNGAS_KG_PER_KG / 1000.0
    co2_emitted_t = co2_burner_t + co2_diesel_t + co2_syngas_t
    co2_net_t = co2_tons - co2_emitted_t

    st.markdown("#### " + ("Balance neto de CO₂e del proceso" if lang == 'es' else "Net process CO₂e balance"))
    ecol1, ecol2, ecol3, ecol4 = st.columns(4)
    ecol1.metric("Quemador / Burner (t CO₂/yr)", f"{co2_burner_t:,.2f}")
    ecol2.metric("Diésel / Diesel gen. (t CO₂/yr)", f"{co2_diesel_t:,.2f}")
    ecol3.metric("Syngas (t CO₂/yr)", f"{co2_syngas_t:,.2f}")
    ecol4.metric(
        "Neto / Net (t CO₂e/yr)", f"{co2_net_t:,.2f}",
        delta=f"-{co2_emitted_t:,.2f} emitido" if lang == 'es' else f"-{co2_emitted_t:,.2f} emitted"
    )
    st.caption(
        "Factores de emisión supuestos (ajustables en el código): aceite residual 3.15 kg CO₂/kg, diésel 10.2 kg CO₂/gal, "
        "syngas 0.84 kg CO₂/kg. No incluye la combustión posterior del bio-crudo vendido ni el transporte. "
        "Los créditos de carbono por biochar normalmente exigen biomasa (carbono biogénico); el char de lodo petrolero "
        "es mayormente carbono fósil y puede no ser elegible: confirme con el estándar de certificación antes de contar este ingreso."
        if lang == 'es' else
        "Assumed emission factors (editable in code): waste oil 3.15 kg CO₂/kg, diesel 10.2 kg CO₂/gal, "
        "syngas 0.84 kg CO₂/kg. Excludes later combustion of the sold bio-oil and transport. "
        "Biochar carbon credits normally require biogenic carbon; char from petroleum sludge is mostly fossil carbon "
        "and may not be eligible: confirm with the certification standard before counting this revenue."
    )
