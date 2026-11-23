"""Sludge pre-drying evaluator (Economy section): drying the sludge before the reactor vs. feeding it wet.
Inputs -> water/fuel/time balance -> KPI metrics, comparison table and verdict card. No LaTeX anywhere."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

from .economics_model import GAL_PER_M3

WATER_EVAP_KJ_PER_KG = 2570.0      # heating + evaporating 1 kg of water (sensible + latent heat)
FUEL_LHV_KJ_PER_GAL = 135000.0     # burner fuel (waste / fuel oil)
REACTOR_BURNER_EFF = 0.75
DRYING_PLATEAU_HEAT_KW = 25000.0   # heat flow assumed in the reactor's drying plateau (kJ/s), for the time saved
GEN_DIESEL_GAL_PER_KWH = 0.08      # diesel generator consumption, prices the dryer's electricity


def render_pre_drying_evaluator(solver_inputs, summary, curr_sym, opex_fuel,
                                available_calendar_days, batches_per_year, t_cycle_hours, m, lang):
    """
    Renders an interactive Sludge Pre-Drying Evaluator.
    Compares the energy, fuel savings, batch cycle reduction, throughput gain,
    and financial payback of installing an external pre-dryer vs direct wet sludge pyrolysis.
    """
    st.markdown("---")
    with st.expander(
        "♨️ Evaluador de Pre-Secado de Lodos (Análisis de Humedad y Ahorro)"
        if lang == 'es'
        else "♨️ Sludge Pre-Drying Evaluator (Moisture & Cost Analysis)",
        expanded=True
    ):
        if lang == 'es':
            st.markdown(
                "Evalúa la viabilidad técnica y financiera de instalar un sistema de pre-secado para reducir la humedad del lodo "
                "antes de ingresar al reactor pirolítico. Compara el costo de secado previo contra el ahorro de combustible en quemadores, "
                "la reducción del tiempo de ciclo y la ganancia en capacidad anual de lotes."
            )
        else:
            st.markdown(
                "Evaluate the technical and financial viability of installing a pre-drying system to reduce sludge moisture "
                "prior to entering the pyrolysis reactor. Compares pre-drying cost against burner fuel savings, cycle time reduction, "
                "and annual batch throughput gains."
            )

        inputs = _pre_dryer_inputs(solver_inputs, curr_sym, lang)
        b = _pre_drying_balance(inputs, summary, opex_fuel, available_calendar_days,
                                batches_per_year, t_cycle_hours, m, lang)
        _render_kpis(b, curr_sym, lang)
        _render_comparison_table(b, summary, curr_sym, opex_fuel, batches_per_year, t_cycle_hours, lang)
        _render_verdict(b, curr_sym, lang)


def _pre_dryer_inputs(solver_inputs, curr_sym, lang):
    """The six pre-dryer widgets: moistures, heat source, CAPEX, efficiency and auxiliary electricity."""
    current_feed = solver_inputs.get('current_feed')
    feed_moist = float(getattr(current_feed, 'moisture', 35.0)) if current_feed else 35.0
    default_moist = feed_moist if feed_moist >= 10.0 else 35.0

    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        init_val = float(st.session_state.get('pre_dry_init_moist', default_moist))
        init_val = max(1.0, min(95.0, init_val))
        initial_moist_pct = st.number_input(
            "Humedad Inicial del Lodo Bruto (%)" if lang == 'es' else "Raw Sludge Initial Moisture (%)",
            min_value=1.0,
            max_value=95.0,
            value=init_val,
            step=1.0,
            key='pre_dry_init_moist',
            help="Contenido de humedad en base húmeda con el que llega el lodo crudo a la planta." if lang == 'es' else "Raw sludge moisture content as received."
        )
    with col_d2:
        target_default = float(min(12.0, max(1.0, initial_moist_pct - 5.0)))
        target_val = float(st.session_state.get('pre_dry_target_moist', target_default))
        max_target = float(max(1.0, initial_moist_pct))
        target_val = max(0.5, min(max_target, target_val))
        target_moist_pct = st.number_input(
            "Humedad Objetivo tras Pre-Secado (%)" if lang == 'es' else "Target Pre-Dried Moisture (%)",
            min_value=0.5,
            max_value=max_target,
            value=target_val,
            step=1.0,
            key='pre_dry_target_moist',
            help="Contenido de humedad final del lodo a la salida del pre-secador hacia el reactor." if lang == 'es' else "Sludge moisture content after pre-drying feeding into reactor."
        )
    with col_d3:
        tech_options_es = [
            "Calor Residual de Gases de Escape (Sin costo de combustible)",
            "Quemador Dedicado a Combustible Líquido (Fuel Oil / Aceite Usado)",
            "Secador Solar / Invernadero Térmico"
        ]
        tech_options_en = [
            "Pyrolysis Flue Gas Waste Heat (Zero fuel cost)",
            "Dedicated Fuel Burner (Fuel Oil / Waste Oil)",
            "Solar / Thermal Greenhouse Dryer"
        ]
        selected_tech = st.selectbox(
            "Fuente Térmica del Pre-Secador" if lang == 'es' else "Pre-Dryer Thermal Source",
            options=tech_options_es if lang == 'es' else tech_options_en,
            key='pre_dry_tech'
        )

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        dryer_capex = st.number_input(
            f"Inversión Estimada en Pre-Secador ({curr_sym})" if lang == 'es' else f"Estimated Pre-Dryer CAPEX ({curr_sym})",
            min_value=0.0,
            value=float(st.session_state.get('pre_dry_capex', 1500000.0)),
            step=100000.0,
            key='pre_dry_capex',
            help="Costo total de compra, transporte, obras civiles e instalación del equipo pre-secador." if lang == 'es' else "Total purchase, civil works, and installation cost of the pre-dryer."
        )
    with col_e2:
        dryer_eff_pct = st.number_input(
            "Eficiencia Térmica del Secador (%)" if lang == 'es' else "Dryer Thermal Efficiency (%)",
            min_value=30.0,
            max_value=95.0,
            value=75.0,
            step=5.0,
            key='pre_dry_eff',
            help="Rendimiento térmico en la evaporación de agua (usualmente 70% a 80% en secadores industriales)." if lang == 'es' else "Thermal efficiency for water evaporation."
        )
    with col_e3:
        dryer_elec_kwh_ton = st.number_input(
            "Consumo Eléctrico Auxiliar (kWh / ton lodo)" if lang == 'es' else "Auxiliary Electricity (kWh / ton sludge)",
            min_value=0.0,
            max_value=100.0,
            value=12.0,
            step=1.0,
            key='pre_dry_elec_rate',
            help="Electricidad consumida por motores del tambor rotativo, ventiladores y bombas de tiro forzado." if lang == 'es' else "Electricity for dryer motors, pumps, and blowers."
        )
    return SimpleNamespace(initial_moist_pct=initial_moist_pct, target_moist_pct=target_moist_pct,
                           selected_tech=selected_tech, dryer_capex=dryer_capex, dryer_eff_pct=dryer_eff_pct,
                           dryer_elec_kwh_ton=dryer_elec_kwh_ton)


def _pre_drying_balance(inp, summary, opex_fuel, available_calendar_days,
                        batches_per_year, t_cycle_hours, m, lang):
    """Water removed, fuel and electricity per batch, time saved per batch,
    extra batches and the yearly net benefit / payback of the pre-dryer."""
    b = SimpleNamespace(**vars(inp))
    b.m_sludge_basis = float(summary.get('batch_load_kg', 5000.0))
    b.basis_label = "por lote" if lang == 'es' else "per batch"
    b.annual_multiplier = batches_per_year

    h_in = inp.initial_moist_pct / 100.0
    h_out = inp.target_moist_pct / 100.0

    m_solids = b.m_sludge_basis * (1.0 - h_in)
    b.m_water_initial = b.m_sludge_basis * h_in

    b.m_sludge_final = m_solids / (1.0 - h_out) if (1.0 - h_out) > 0 else b.m_sludge_basis
    b.m_water_final = b.m_sludge_final * h_out

    b.m_water_removed = max(0.0, b.m_sludge_basis - b.m_sludge_final)
    b.pct_water_removed = (b.m_water_removed / b.m_water_initial * 100.0) if b.m_water_initial > 0 else 0.0

    energy_needed_kj = b.m_water_removed * WATER_EVAP_KJ_PER_KG

    # Fuel the reactor burner no longer spends on that water
    b.fuel_saved_reactor_gal = energy_needed_kj / (REACTOR_BURNER_EFF * FUEL_LHV_KJ_PER_GAL)
    b.cost_saved_reactor = b.fuel_saved_reactor_gal * opex_fuel

    # Fuel the pre-dryer burns (only the dedicated-burner option burns fuel)
    is_fuel_burner = ("Quemador Dedicado" in inp.selected_tech) or ("Dedicated Fuel" in inp.selected_tech)
    if is_fuel_burner:
        b.fuel_used_dryer_gal = energy_needed_kj / ((inp.dryer_eff_pct / 100.0) * FUEL_LHV_KJ_PER_GAL)
        b.cost_fuel_dryer = b.fuel_used_dryer_gal * opex_fuel
    else:
        b.fuel_used_dryer_gal = 0.0
        b.cost_fuel_dryer = 0.0

    ton_sludge_basis = b.m_sludge_basis / 1000.0
    b.elec_kwh_dryer = ton_sludge_basis * inp.dryer_elec_kwh_ton
    cost_per_kwh = float(st.session_state.get('price_generator_fuel', 262.80)) * GEN_DIESEL_GAL_PER_KWH
    cost_elec_dryer = b.elec_kwh_dryer * cost_per_kwh

    # Time saved in the reactor
    t_dry_plateau_min = (b.m_water_initial * WATER_EVAP_KJ_PER_KG) / (DRYING_PLATEAU_HEAT_KW * 60.0)
    b.t_saved_min = t_dry_plateau_min * (b.pct_water_removed / 100.0)
    t_saved_hours = b.t_saved_min / 60.0
    b.t_cycle_new = max(1.0, t_cycle_hours - t_saved_hours)
    available_hours = available_calendar_days * 24.0
    b.batches_year_new = np.floor(available_hours / b.t_cycle_new) if b.t_cycle_new > 0 else batches_per_year
    b.extra_batches = max(0.0, b.batches_year_new - batches_per_year)
    if int(st.session_state.get('econ_batches_per_year', 0)) > 0:
        # Batches fixed by plant data: a shorter cycle adds no batches
        b.batches_year_new, b.extra_batches = batches_per_year, 0.0

    annual_rev_base = m['rev_flows'][1] if len(m['rev_flows']) > 1 else 0.0
    rev_per_batch = annual_rev_base / max(batches_per_year, 1)
    b.extra_revenue_annual = b.extra_batches * rev_per_batch

    b.annual_fuel_saved_cost = b.cost_saved_reactor * b.annual_multiplier
    b.annual_dryer_fuel_cost = b.cost_fuel_dryer * b.annual_multiplier
    b.annual_dryer_elec_cost = cost_elec_dryer * b.annual_multiplier
    annual_dryer_total_opex = b.annual_dryer_fuel_cost + b.annual_dryer_elec_cost

    b.annual_net_benefit = (b.annual_fuel_saved_cost - annual_dryer_total_opex) + b.extra_revenue_annual

    if b.annual_net_benefit > 0 and inp.dryer_capex > 0:
        b.payback_years = inp.dryer_capex / b.annual_net_benefit
        b.payback_months = b.payback_years * 12.0
    else:
        b.payback_years = float('inf')
        b.payback_months = float('inf')
    return b


def _render_kpis(b, curr_sym, lang):
    """Four metric cards: water removed, fuel saved, time saved, net benefit."""
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric(
            "Agua Retirada" if lang == 'es' else "Water Removed",
            f"{b.m_water_removed:,.0f} kg {b.basis_label}",
            delta=f"-{b.pct_water_removed:.1f}% de agua" if lang == 'es' else f"-{b.pct_water_removed:.1f}% water",
            delta_color="normal"
        )
    with col_m2:
        st.metric(
            "Ahorro Combustible" if lang == 'es' else "Fuel Saved in Reactor",
            f"{b.fuel_saved_reactor_gal:,.1f} gal {b.basis_label}",
            delta=f"+{curr_sym}{b.cost_saved_reactor:,.2f} {b.basis_label}"
        )
    with col_m3:
        st.metric(
            "Tiempo Ahorrado" if lang == 'es' else "Time Saved in Reactor",
            f"{b.t_saved_min:.0f} min {b.basis_label}",
            delta=f"+{b.extra_batches:.0f} lotes/año" if lang == 'es' else f"+{b.extra_batches:.0f} batches/yr"
        )
    with col_m4:
        st.metric(
            "Beneficio Neto Anual" if lang == 'es' else "Net Annual Benefit",
            f"{curr_sym}{b.annual_net_benefit:,.2f}/año" if lang == 'es' else f"{curr_sym}{b.annual_net_benefit:,.2f}/yr",
            delta=f"Retorno: {b.payback_months:.1f} meses" if b.payback_months < 60 else "Evaluación especial"
        )


def _render_comparison_table(b, summary, curr_sym, opex_fuel, batches_per_year, t_cycle_hours, lang):
    """Baseline (raw sludge) vs. with pre-dryer, row by row, with the favourable impact of each row."""
    st.markdown("##### 📊 Comparativo Técnico y Económico: Sin Pre-Secado vs. Con Pre-Secado" if lang == 'es' else "##### 📊 Technical & Economic Comparison: Baseline vs. With Pre-Drying")

    basis = b.basis_label
    burner_fuel_gal = summary.get('waste_oil_consumed_gal', 0.0)
    burner_fuel_dried_gal = max(0.0, burner_fuel_gal - b.fuel_saved_reactor_gal)
    comp_data = {
        "Concepto / Parámetro" if lang == 'es' else "Parameter": [
            "Humedad del lodo al entrar al reactor" if lang == 'es' else "Sludge moisture entering reactor",
            "Masa de carga al reactor" if lang == 'es' else "Sludge mass loaded into reactor",
            "Agua evaporada dentro del reactor" if lang == 'es' else "Water evaporated inside reactor",
            "Combustible consumido en reactor" if lang == 'es' else "Burner fuel consumed in reactor",
            "Combustible consumido por pre-secador" if lang == 'es' else "Fuel consumed by pre-dryer",
            "Costo de combustible de proceso" if lang == 'es' else "Process fuel operational cost",
            "Consumo eléctrico del pre-secador" if lang == 'es' else "Pre-dryer auxiliary electricity",
            "Tiempo de ciclo por lote" if lang == 'es' else "Batch cycle duration",
            "Capacidad anual de procesamiento" if lang == 'es' else "Annual batch capacity",
            "Beneficio económico neto anual" if lang == 'es' else "Net annual financial benefit"
        ],
        "Operación Actual (Lodo Crudo)" if lang == 'es' else "Current Baseline": [
            f"{b.initial_moist_pct:.1f} %",
            f"{b.m_sludge_basis:,.0f} kg {basis}",
            f"{b.m_water_initial:,.0f} kg ({b.m_water_initial * GAL_PER_M3 / 1000.0:,.0f} gal) {basis}",
            f"{burner_fuel_gal:,.1f} gal {basis}",
            "0.0 gal",
            f"{curr_sym}{burner_fuel_gal * opex_fuel * b.annual_multiplier:,.2f}/año",
            "0.0 kWh/año",
            f"{t_cycle_hours:.2f} horas",
            f"{batches_per_year:.0f} lotes/año",
            "Línea Base (RD$ 0.00)"
        ],
        "Con Sistema de Pre-Secado" if lang == 'es' else "With Pre-Drying System": [
            f"{b.target_moist_pct:.1f} %",
            f"{b.m_sludge_final:,.0f} kg {basis}",
            f"{b.m_water_final:,.0f} kg ({b.m_water_final * GAL_PER_M3 / 1000.0:,.0f} gal) {basis}",
            f"{burner_fuel_dried_gal:,.1f} gal {basis}",
            f"{b.fuel_used_dryer_gal:,.1f} gal {basis}",
            f"{curr_sym}{(burner_fuel_dried_gal * opex_fuel + b.cost_fuel_dryer) * b.annual_multiplier:,.2f}/año",
            f"{b.elec_kwh_dryer * b.annual_multiplier:,.0f} kWh/año ({curr_sym}{b.annual_dryer_elec_cost:,.2f})",
            f"{b.t_cycle_new:.2f} horas",
            f"{b.batches_year_new:.0f} lotes/año",
            f"+{curr_sym}{b.annual_net_benefit:,.2f}/año"
        ],
        "Ahorro / Impacto Favorable" if lang == 'es' else "Favorable Impact / Savings": [
            f"-{(b.initial_moist_pct - b.target_moist_pct):.1f} puntos de humedad",
            f"-{b.m_water_removed:,.0f} kg agua retirada antes del reactor",
            f"-{b.pct_water_removed:.1f} % menos agua a hervir",
            f"-{b.fuel_saved_reactor_gal:,.1f} gal {basis} ahorrados en reactor",
            "Incluido en balance",
            f"Ahorro combustible: +{curr_sym}{b.annual_fuel_saved_cost - b.annual_dryer_fuel_cost:,.2f}/año",
            f"Costo auxiliar secador: -{curr_sym}{b.annual_dryer_elec_cost:,.2f}/año",
            f"-{b.t_saved_min:.0f} min menos por lote",
            f"+{b.extra_batches:.0f} lotes extra (+{curr_sym}{b.extra_revenue_annual:,.2f}/año)",
            f"Retorno inversión: {b.payback_months:.1f} meses ({b.payback_years:.2f} años)" if b.payback_months < 60 else "Sin retorno directo"
        ]
    }
    st.table(pd.DataFrame(comp_data))


def _render_verdict(b, curr_sym, lang):
    """Verdict card coloured by the payback: <= 12 months, <= 24 months, or longer."""
    if b.payback_months <= 12.0:
        verdict_badge = "🟢 ALTAMENTE RECOMENDADO" if lang == 'es' else "🟢 HIGHLY RECOMMENDED"
        verdict_border = "#10b981"
        verdict_expl = (
            f"La inversión de {curr_sym}{b.dryer_capex:,.2f} en el pre-secador se recupera en apenas {b.payback_months:.1f} meses. "
            f"Al retirar {b.pct_water_removed:.1f}% del agua antes del reactor, se ahorran {b.fuel_saved_reactor_gal * b.annual_multiplier:,.0f} galones de combustible al año "
            f"y se liberan {b.t_saved_min:.0f} minutos por lote, generando un beneficio neto anual de {curr_sym}{b.annual_net_benefit:,.2f}."
            if lang == 'es' else
            f"The pre-dryer investment of {curr_sym}{b.dryer_capex:,.2f} pays back in just {b.payback_months:.1f} months, "
            f"saving {b.fuel_saved_reactor_gal * b.annual_multiplier:,.0f} gal/yr in burner fuel and releasing {b.t_saved_min:.0f} min per batch."
        )
    elif b.payback_months <= 24.0:
        verdict_badge = "🟡 VIABLE Y RENTABLE" if lang == 'es' else "🟡 FEASIBLE & PROFITABLE"
        verdict_border = "#f59e0b"
        verdict_expl = (
            f"El pre-secado ofrece un retorno sólido en {b.payback_months:.1f} meses ({b.payback_years:.1f} años). "
            f"El ahorro anual en combustible y la capacidad extra de procesamiento superan holgadamente los costos operativos del secador."
            if lang == 'es' else
            f"Pre-drying offers a solid payback of {b.payback_months:.1f} months ({b.payback_years:.1f} years), comfortably exceeding operational costs."
        )
    else:
        verdict_badge = "🔵 EVALUAR CON FUENTES RESIDUALES" if lang == 'es' else "🔵 OPTIMIZE WITH WASTE HEAT"
        verdict_border = "#0284c7"
        verdict_expl = (
            f"Para maximizar la rentabilidad, se recomienda operar el pre-secador utilizando los gases calientes de escape de la pirólisis "
            f"o secado solar, eliminando el consumo de combustible auxiliar y acortando el tiempo de amortización."
            if lang == 'es' else
            f"To maximize profitability, utilizing hot pyrolysis flue gases or solar drying is recommended to eliminate auxiliary fuel consumption."
        )

    st.markdown(f"""
        <div style="background-color: {verdict_border}22; border: 1px solid {verdict_border}; border-radius: 8px; padding: 14px 18px; margin-top: 10px;">
            <div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 6px;">
                Dictamen Técnico y Financiero: {verdict_badge}
            </div>
            <div style="font-size: 0.86rem; line-height: 1.5;">
                {verdict_expl}
            </div>
        </div>
        """, unsafe_allow_html=True)
