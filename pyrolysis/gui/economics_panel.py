import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import io
from .utils import get_lang, t

# Assumed CO2 emission factors for the process-emissions balance (sustainability tab)
EF_CO2_FUEL_OIL_KG_PER_KG = 3.15   # waste / fuel oil combustion
EF_CO2_DIESEL_KG_PER_GAL = 10.21   # diesel generator
EF_CO2_SYNGAS_KG_PER_KG = 0.84     # pyrolysis gas at ~12 MJ/kg and ~0.07 kg CO2/MJ

IRR_SEARCH_MAX = 1000.0   # upper search bound for the IRR as a fraction (= 100,000 %)


def solve_irr(cash_flows):
    """
    Calculates the Internal Rate of Return (IRR) for a given series of cash flows.
    Returns the percentage, float('inf') when a conventional project (investment first, then non-negative
    flows) still has NPV > 0 at IRR_SEARCH_MAX, or None if it cannot be solved.
    """
    if not cash_flows or all(x >= 0 for x in cash_flows) or all(x <= 0 for x in cash_flows):
        return None

    def npv_func(r):
        return sum(cf / ((1.0 + r)**t) for t, cf in enumerate(cash_flows))

    low = -0.99
    high = 10.0

    val_low = npv_func(low)
    val_high = npv_func(high)
    # Very profitable projects: widen the bracket instead of giving up at 1,000 %
    while val_low * val_high > 0 and high < IRR_SEARCH_MAX:
        high = min(high * 10.0, IRR_SEARCH_MAX)
        val_high = npv_func(high)
    if val_low * val_high > 0 and val_high > 0 and cash_flows[0] < 0 and all(x >= 0 for x in cash_flows[1:]):
        return float('inf')

    if val_low * val_high > 0:
        found = False
        steps = 100
        for i in range(steps):
            r1 = low + (high - low) * i / steps
            r2 = low + (high - low) * (i + 1) / steps
            if npv_func(r1) * npv_func(r2) < 0:
                low = r1
                high = r2
                found = True
                break
        if not found:
            return None
            
    for _ in range(100):
        mid = (low + high) / 2.0
        val = npv_func(mid)
        if abs(val) < 1e-3:
            return mid * 100.0
        if val_low > 0:
            if val > 0:
                low = mid
            else:
                high = mid
        else:
            if val < 0:
                low = mid
            else:
                high = mid
                
    return ((low + high) / 2.0) * 100.0

def format_irr(irr, decimals=2):
    """IRR text: 'N/A' when undefined, '> 100,000 %' above the search bound, otherwise the value."""
    if irr is None:
        return "N/A"
    if irr == float('inf'):
        return f"> {IRR_SEARCH_MAX * 100.0:,.0f} %"
    return f"{irr:,.{decimals}f} %"


SLUDGE_SCENARIOS = ('purchase', 'free', 'tipping')
SLUDGE_SCENARIO_LABELS = {
    'purchase': {'es': "Lodo húmedo comprado", 'en': "Wet sludge purchased"},
    'free': {'es': "Lodo sin costo", 'en': "Sludge at no cost"},
    'tipping': {'es': "Lodo con tarifa de disposición", 'en': "Sludge with disposal fee"},
}


def scenario_tipping_fee(scenario, sludge_cost, tipping_fee):
    """Effective tipping fee (RD$/gal) of a sludge scenario: purchase = −X, free = 0, disposal fee = +Y."""
    return {'purchase': 0.0 - float(sludge_cost), 'free': 0.0, 'tipping': float(tipping_fee)}[scenario]  # 0.0 - x avoids "-0.00"


def breakeven_note(breakeven_tipping, lang='es'):
    """Sentence explaining the break-even tipping fee (NPV = 0), shown with two decimals."""
    v = round(breakeven_tipping, 2)
    if v < 0:
        return (f"El proyecto mantiene VAN ≥ 0 mientras el lodo cueste menos de RD$ {-v:,.2f}/gal." if lang == 'es'
                else f"The project keeps NPV ≥ 0 as long as sludge costs less than RD$ {-v:,.2f}/gal.")
    if v > 0:
        return (f"El proyecto necesita cobrar una tarifa de disposición de al menos RD$ {v:,.2f}/gal para tener VAN ≥ 0."
                if lang == 'es' else
                f"The project needs a disposal fee of at least RD$ {v:,.2f}/gal to reach NPV ≥ 0.")
    return ("El proyecto queda en equilibrio exacto sin costo ni tarifa por el lodo." if lang == 'es'
            else "The project breaks even exactly with no sludge cost or fee.")


def batch_thermal_cycle_min(summary, solver_inputs):
    """
    Returns (t_cycle_min, t_heat_min, t_hold_min) of the thermal process of one batch.
    Uses the simulated duration (drying + heating + hold) when available; the naive
    (T_hold - T_start) / heating_rate estimate ignores drying and underestimates the cycle.
    """
    t_hold_min = float(solver_inputs.get('hold_time_min', 60.0))
    sim_cycle = summary.get('cycle_time_min') if summary else None
    if sim_cycle:
        t_cycle_min = float(sim_cycle)
        t_heat_min = max(0.0, t_cycle_min - t_hold_min)
    else:
        rate = max(float(solver_inputs.get('heating_rate_cmin', 1.0)), 1e-6)
        t_heat_min = (float(solver_inputs.get('temp_hold_c', 400.0)) - float(solver_inputs.get('temp_start_c', 25.0))) / rate
        t_cycle_min = t_heat_min + t_hold_min
    return t_cycle_min, t_heat_min, t_hold_min

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

def run_financial_model(
    total_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
    fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
    opex_handling, opex_fuel, opex_electricity, opex_aux_utilities, price_generator_fuel,
    opex_labor, opex_maint, opex_insurance_tax,
    opex_tipping, price_oil, price_char, price_gas, price_carbon, rate_carbon_offset,
    discount_rate, project_lifetime, tax_rate, inflation_rate,
    char_carbon_kg=None
):
    """
    Runs the detailed cash flow model over the project lifetime and returns year-by-year cash flows
    and advanced economic indicators (computed in gallons, kg, and m3).

    `char_carbon_kg` is the carbon-bearing char (residue without ash) used for carbon credits;
    defaults to `char_produced_kg` when not given.
    """
    if char_carbon_kg is None:
        char_carbon_kg = char_produced_kg
    r = discount_rate / 100.0
    inf = inflation_rate / 100.0
    tax = tax_rate / 100.0
    
    # Year 1 base values (uninflated)
    rev_tipping = sludge_treated_gal * opex_tipping
    rev_oil = oil_produced_gal * price_oil
    rev_char = char_produced_kg * price_char
    rev_gas = gas_produced_m3 * price_gas
    
    annual_co2_sequestered_ton = (char_carbon_kg * rate_carbon_offset) / 1000.0
    rev_carbon = annual_co2_sequestered_ton * price_carbon

    total_rev_base = rev_tipping + rev_oil + rev_char + rev_gas + rev_carbon
    
    cost_handling = sludge_treated_gal * opex_handling
    cost_fuel = fuel_consumed_gal * opex_fuel
    cost_electricity = elec_consumed_kwh * opex_electricity
    cost_aux_utilities = opex_aux_utilities
    cost_generator_fuel = generator_fuel_consumed_gal * price_generator_fuel
    cost_labor = opex_labor
    cost_maintenance = total_capex * (opex_maint / 100.0)
    cost_insurance_tax = total_capex * (opex_insurance_tax / 100.0)
    
    total_opex_base = (
        cost_handling + cost_fuel + cost_electricity + cost_aux_utilities + 
        cost_generator_fuel + cost_labor + cost_maintenance + cost_insurance_tax
    )
    
    years = list(range(0, int(project_lifetime) + 1))
    
    rev_flows = [0.0] * len(years)
    opex_flows = [0.0] * len(years)
    depr_flows = [0.0] * len(years)
    taxable_flows = [0.0] * len(years)
    tax_flows = [0.0] * len(years)
    net_flows = [0.0] * len(years)
    disc_flows = [0.0] * len(years)
    cum_flows = [0.0] * len(years)
    
    net_flows[0] = -total_capex
    disc_flows[0] = -total_capex
    cum_flows[0] = -total_capex
    
    depreciation_annual = total_capex / project_lifetime if project_lifetime > 0 else 0.0
    
    for yr in range(1, int(project_lifetime) + 1):
        inf_factor = (1.0 + inf) ** (yr - 1)
        r_t = total_rev_base * inf_factor
        o_t = total_opex_base * inf_factor
        
        ebitda = r_t - o_t
        depr = depreciation_annual
        taxable_income = ebitda - depr
        taxes = max(0.0, taxable_income * tax)
        
        net_cf = ebitda - taxes
        
        rev_flows[yr] = r_t
        opex_flows[yr] = o_t
        depr_flows[yr] = depr
        taxable_flows[yr] = taxable_income
        tax_flows[yr] = taxes
        net_flows[yr] = net_cf
        
        disc_cf = net_cf / ((1.0 + r) ** yr)
        disc_flows[yr] = disc_cf
        cum_flows[yr] = cum_flows[yr-1] + net_cf
        
    npv = sum(disc_flows)
    irr = solve_irr(net_flows)
    
    # Simple payback (undiscounted)
    payback = float('inf')
    cum_undisc = -total_capex
    for yr in range(1, int(project_lifetime) + 1):
        prev = cum_undisc
        cum_undisc += net_flows[yr]
        if cum_undisc >= 0:
            payback = (yr - 1) + (-prev / net_flows[yr]) if net_flows[yr] > 0 else (yr - 1)
            break
            
    # Discounted payback
    disc_payback = float('inf')
    cum_disc = -total_capex
    for yr in range(1, int(project_lifetime) + 1):
        prev = cum_disc
        cum_disc += disc_flows[yr]
        if cum_disc >= 0:
            disc_payback = (yr - 1) + (-prev / disc_flows[yr]) if disc_flows[yr] > 0 else (yr - 1)
            break
            
    pi = 1.0 + (npv / total_capex) if total_capex > 0 else 0.0
    
    # Break-even tipping fee (Secant method)
    def get_npv_for_tipping(t_fee):
        temp_rev_tipping = sludge_treated_gal * t_fee
        temp_total_rev_base = temp_rev_tipping + rev_oil + rev_char + rev_gas + rev_carbon
        
        temp_disc_flows = [-total_capex]
        for yr in range(1, int(project_lifetime) + 1):
            inf_factor = (1.0 + inf) ** (yr - 1)
            r_t = temp_total_rev_base * inf_factor
            o_t = total_opex_base * inf_factor
            
            ebitda = r_t - o_t
            depr = depreciation_annual
            taxable_income = ebitda - depr
            taxes = max(0.0, taxable_income * tax)
            net_cf = ebitda - taxes
            
            temp_disc_flows.append(net_cf / ((1.0 + r) ** yr))
        return sum(temp_disc_flows)

    # Bisection: NPV rises with the fee but not in a straight line (taxes only apply to profit),
    # so a two-point secant misses the break-even.
    if sludge_treated_gal > 0:
        lo, hi = -1.0, 1.0
        while get_npv_for_tipping(lo) > 0 and lo > -1e9:
            lo *= 2.0
        while get_npv_for_tipping(hi) < 0 and hi < 1e9:
            hi *= 2.0
        for _ in range(100):
            mid = (lo + hi) / 2.0
            if get_npv_for_tipping(mid) < 0:
                lo = mid
            else:
                hi = mid
        breakeven_tipping = (lo + hi) / 2.0
    else:
        breakeven_tipping = 0.0
        
    return {
        'npv': npv,
        'irr': irr,
        'payback': payback,
        'disc_payback': disc_payback,
        'pi': pi,
        'breakeven_tipping': breakeven_tipping,
        'annual_co2_sequestered_ton': annual_co2_sequestered_ton,
        'years': years,
        'net_flows': net_flows,
        'disc_flows': disc_flows,
        'cum_flows': cum_flows,
        'rev_flows': rev_flows,
        'opex_flows': opex_flows,
        'depr_flows': depr_flows,
        'tax_flows': tax_flows,
        'revenue_breakdown': {
            'tipping': rev_tipping,
            'oil': rev_oil,
            'char': rev_char,
            'gas': rev_gas,
            'carbon': rev_carbon
        },
        'opex_breakdown': {
            'handling': cost_handling,
            'fuel': cost_fuel,
            'electricity': cost_electricity,
            'aux_utilities': cost_aux_utilities,
            'gen_diesel': cost_generator_fuel,
            'labor': cost_labor,
            'maintenance': cost_maintenance,
            'insurance_tax': cost_insurance_tax
        }
    }

def render_pre_drying_evaluator(
    solver_inputs,
    summary,
    results,
    is_continuous,
    curr_sym,
    opex_fuel,
    available_calendar_days,
    batches_per_year,
    t_cycle_hours,
    t_op_batch_hours,
    maint_penalty_per_batch_h,
    m,
    lang
):
    """
    Renders an interactive Sludge Pre-Drying Evaluator.
    Compares the energy, fuel savings, batch cycle reduction, throughput gain,
    and financial payback of installing an external pre-dryer vs direct wet sludge pyrolysis.
    NO LATEX is used anywhere in the text or formulas.
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
            tech_options = tech_options_es if lang == 'es' else tech_options_en
            selected_tech = st.selectbox(
                "Fuente Térmica del Pre-Secador" if lang == 'es' else "Pre-Dryer Thermal Source",
                options=tech_options,
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
            
        # Calculation logic
        if is_continuous:
            m_sludge_basis = float(summary.get('feed_rate_kgh', 500.0))
            basis_label = "por hora" if lang == 'es' else "per hour"
            annual_multiplier = available_calendar_days * 24.0
        else:
            m_sludge_basis = float(summary.get('batch_load_kg', 5000.0))
            basis_label = "por lote" if lang == 'es' else "per batch"
            annual_multiplier = batches_per_year

        h_in = initial_moist_pct / 100.0
        h_out = target_moist_pct / 100.0

        m_solids = m_sludge_basis * (1.0 - h_in)
        m_water_initial = m_sludge_basis * h_in

        m_sludge_final = m_solids / (1.0 - h_out) if (1.0 - h_out) > 0 else m_sludge_basis
        m_water_final = m_sludge_final * h_out

        m_water_removed = max(0.0, m_sludge_basis - m_sludge_final)
        water_removed_gal = (m_water_removed / 1000.0) * 264.172
        pct_water_removed = (m_water_removed / m_water_initial * 100.0) if m_water_initial > 0 else 0.0

        # Thermal energy required for water evaporation: 2,570 kJ/kg (sensible + latent heat)
        energy_kj_per_kg_water = 2570.0
        energy_needed_kj = m_water_removed * energy_kj_per_kg_water

        fuel_lhv_kj_gal = 135000.0
        reactor_burner_eff = 0.75

        # Fuel saved in pyrolysis reactor
        fuel_saved_reactor_gal = energy_needed_kj / (reactor_burner_eff * fuel_lhv_kj_gal)
        cost_saved_reactor = fuel_saved_reactor_gal * opex_fuel

        # Fuel used in pre-dryer
        is_fuel_burner = ("Quemador Dedicado" in selected_tech) or ("Dedicated Fuel" in selected_tech)
        if is_fuel_burner:
            fuel_used_dryer_gal = energy_needed_kj / ((dryer_eff_pct / 100.0) * fuel_lhv_kj_gal)
            cost_fuel_dryer = fuel_used_dryer_gal * opex_fuel
        else:
            fuel_used_dryer_gal = 0.0
            cost_fuel_dryer = 0.0

        # Electricity cost
        ton_sludge_basis = m_sludge_basis / 1000.0
        elec_kwh_dryer = ton_sludge_basis * dryer_elec_kwh_ton
        cost_per_kwh = float(st.session_state.get('price_generator_fuel', 262.80)) * 0.08
        cost_elec_dryer = elec_kwh_dryer * cost_per_kwh

        # Time savings in reactor
        if not is_continuous:
            t_dry_plateau_min = (m_water_initial * energy_kj_per_kg_water) / (25000.0 * 60.0)
            t_saved_min = t_dry_plateau_min * (pct_water_removed / 100.0)
            t_saved_hours = t_saved_min / 60.0
            t_cycle_new = max(1.0, t_cycle_hours - t_saved_hours)
            available_hours = available_calendar_days * 24.0
            batches_year_new = np.floor(available_hours / t_cycle_new) if t_cycle_new > 0 else batches_per_year
            extra_batches = max(0.0, batches_year_new - batches_per_year)
            if int(st.session_state.get('econ_batches_per_year', 0)) > 0:
                # Batches fixed by plant data: a shorter cycle adds no batches
                batches_year_new, extra_batches = batches_per_year, 0.0

            annual_rev_base = m['rev_flows'][1] if len(m['rev_flows']) > 1 else 0.0
            rev_per_batch = annual_rev_base / max(batches_per_year, 1)
            extra_revenue_annual = extra_batches * rev_per_batch
        else:
            t_saved_min = 0.0
            t_saved_hours = 0.0
            t_cycle_new = 0.0
            batches_year_new = 0.0
            extra_batches = 0.0
            extra_revenue_annual = 0.0

        annual_fuel_saved_cost = cost_saved_reactor * annual_multiplier
        annual_dryer_fuel_cost = cost_fuel_dryer * annual_multiplier
        annual_dryer_elec_cost = cost_elec_dryer * annual_multiplier
        annual_dryer_total_opex = annual_dryer_fuel_cost + annual_dryer_elec_cost
        
        # Net annual financial gain
        annual_net_benefit = (annual_fuel_saved_cost - annual_dryer_total_opex) + extra_revenue_annual

        if annual_net_benefit > 0 and dryer_capex > 0:
            payback_years = dryer_capex / annual_net_benefit
            payback_months = payback_years * 12.0
        else:
            payback_years = float('inf')
            payback_months = float('inf')

        # KPI Metrics Cards
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric(
                "Agua Retirada" if lang == 'es' else "Water Removed",
                f"{m_water_removed:,.0f} kg {basis_label}",
                delta=f"-{pct_water_removed:.1f}% de agua" if lang == 'es' else f"-{pct_water_removed:.1f}% water",
                delta_color="normal"
            )
        with col_m2:
            st.metric(
                "Ahorro Combustible" if lang == 'es' else "Fuel Saved in Reactor",
                f"{fuel_saved_reactor_gal:,.1f} gal {basis_label}",
                delta=f"+{curr_sym}{cost_saved_reactor:,.2f} {basis_label}"
            )
        with col_m3:
            if not is_continuous:
                st.metric(
                    "Tiempo Ahorrado" if lang == 'es' else "Time Saved in Reactor",
                    f"{t_saved_min:.0f} min {basis_label}",
                    delta=f"+{extra_batches:.0f} lotes/año" if lang == 'es' else f"+{extra_batches:.0f} batches/yr"
                )
            else:
                st.metric(
                    "Ahorro Neto Combustible" if lang == 'es' else "Net Fuel Saved",
                    f"{(fuel_saved_reactor_gal - fuel_used_dryer_gal):,.1f} gal/h",
                    delta=f"{fuel_saved_reactor_gal * annual_multiplier:,.0f} gal/año" if lang == 'es' else f"{fuel_saved_reactor_gal * annual_multiplier:,.0f} gal/yr"
                )
        with col_m4:
            st.metric(
                "Beneficio Neto Anual" if lang == 'es' else "Net Annual Benefit",
                f"{curr_sym}{annual_net_benefit:,.2f}/año" if lang == 'es' else f"{curr_sym}{annual_net_benefit:,.2f}/yr",
                delta=f"Retorno: {payback_months:.1f} meses" if payback_months < 60 else "Evaluación especial"
            )

        # Comparison Table
        st.markdown("##### 📊 Comparativo Técnico y Económico: Sin Pre-Secado vs. Con Pre-Secado" if lang == 'es' else "##### 📊 Technical & Economic Comparison: Baseline vs. With Pre-Drying")
        
        comp_data = {
            "Concepto / Parámetro" if lang == 'es' else "Parameter": [
                "Humedad del lodo al entrar al reactor" if lang == 'es' else "Sludge moisture entering reactor",
                "Masa de carga al reactor" if lang == 'es' else "Sludge mass loaded into reactor",
                "Agua evaporada dentro del reactor" if lang == 'es' else "Water evaporated inside reactor",
                "Combustible consumido en reactor" if lang == 'es' else "Burner fuel consumed in reactor",
                "Combustible consumido por pre-secador" if lang == 'es' else "Fuel consumed by pre-dryer",
                "Costo de combustible de proceso" if lang == 'es' else "Process fuel operational cost",
                "Consumo eléctrico del pre-secador" if lang == 'es' else "Pre-dryer auxiliary electricity",
                "Tiempo de ciclo por lote" if not is_continuous and lang == 'es' else ("Batch cycle duration" if not is_continuous else "Régimen de operación"),
                "Capacidad anual de procesamiento" if not is_continuous and lang == 'es' else ("Annual batch capacity" if not is_continuous else "Horas anuales"),
                "Beneficio económico neto anual" if lang == 'es' else "Net annual financial benefit"
            ],
            "Operación Actual (Lodo Crudo)" if lang == 'es' else "Current Baseline": [
                f"{initial_moist_pct:.1f} %",
                f"{m_sludge_basis:,.0f} kg {basis_label}",
                f"{m_water_initial:,.0f} kg ({m_water_initial * 264.172 / 1000.0:,.0f} gal) {basis_label}",
                f"{summary.get('waste_oil_consumed_gal', 0.0) if not is_continuous else summary.get('waste_oil_consumed_galh', 0.0):,.1f} gal {basis_label}",
                "0.0 gal",
                f"{curr_sym}{(summary.get('waste_oil_consumed_gal', 0.0) if not is_continuous else summary.get('waste_oil_consumed_galh', 0.0)) * opex_fuel * annual_multiplier:,.2f}/año",
                "0.0 kWh/año",
                f"{t_cycle_hours:.2f} horas" if not is_continuous else f"{available_calendar_days * 24:.0f} horas",
                f"{batches_per_year:.0f} lotes/año" if not is_continuous else f"{available_calendar_days:.0f} días",
                "Línea Base (RD$ 0.00)"
            ],
            "Con Sistema de Pre-Secado" if lang == 'es' else "With Pre-Drying System": [
                f"{target_moist_pct:.1f} %",
                f"{m_sludge_final:,.0f} kg {basis_label}",
                f"{m_water_final:,.0f} kg ({m_water_final * 264.172 / 1000.0:,.0f} gal) {basis_label}",
                f"{max(0.0, (summary.get('waste_oil_consumed_gal', 0.0) if not is_continuous else summary.get('waste_oil_consumed_galh', 0.0)) - fuel_saved_reactor_gal):,.1f} gal {basis_label}",
                f"{fuel_used_dryer_gal:,.1f} gal {basis_label}",
                f"{curr_sym}{(max(0.0, (summary.get('waste_oil_consumed_gal', 0.0) if not is_continuous else summary.get('waste_oil_consumed_galh', 0.0)) - fuel_saved_reactor_gal) * opex_fuel + cost_fuel_dryer) * annual_multiplier:,.2f}/año",
                f"{elec_kwh_dryer * annual_multiplier:,.0f} kWh/año ({curr_sym}{annual_dryer_elec_cost:,.2f})",
                f"{t_cycle_new:.2f} horas" if not is_continuous else f"{available_calendar_days * 24:.0f} horas",
                f"{batches_year_new:.0f} lotes/año" if not is_continuous else f"{available_calendar_days:.0f} días",
                f"+{curr_sym}{annual_net_benefit:,.2f}/año"
            ],
            "Ahorro / Impacto Favorable" if lang == 'es' else "Favorable Impact / Savings": [
                f"-{(initial_moist_pct - target_moist_pct):.1f} puntos de humedad",
                f"-{m_water_removed:,.0f} kg agua retirada antes del reactor",
                f"-{pct_water_removed:.1f} % menos agua a hervir",
                f"-{fuel_saved_reactor_gal:,.1f} gal {basis_label} ahorrados en reactor",
                "Incluido en balance",
                f"Ahorro combustible: +{curr_sym}{annual_fuel_saved_cost - annual_dryer_fuel_cost:,.2f}/año",
                f"Costo auxiliar secador: -{curr_sym}{annual_dryer_elec_cost:,.2f}/año",
                f"-{t_saved_min:.0f} min menos por lote" if not is_continuous else "Régimen continuo",
                f"+{extra_batches:.0f} lotes extra (+{curr_sym}{extra_revenue_annual:,.2f}/año)" if not is_continuous else "Mismo tiempo",
                f"Retorno inversión: {payback_months:.1f} meses ({payback_years:.2f} años)" if payback_months < 60 else "Sin retorno directo"
            ]
        }
        df_comp = pd.DataFrame(comp_data)
        st.table(df_comp)

        # Technical Verdict Card
        if payback_months <= 12.0:
            verdict_badge = "🟢 ALTAMENTE RECOMENDADO" if lang == 'es' else "🟢 HIGHLY RECOMMENDED"
            verdict_border = "#10b981"
            verdict_expl = (
                f"La inversión de {curr_sym}{dryer_capex:,.2f} en el pre-secador se recupera en apenas {payback_months:.1f} meses. "
                f"Al retirar {pct_water_removed:.1f}% del agua antes del reactor, se ahorran {fuel_saved_reactor_gal * annual_multiplier:,.0f} galones de combustible al año "
                f"y se liberan {t_saved_min:.0f} minutos por lote, generando un beneficio neto anual de {curr_sym}{annual_net_benefit:,.2f}."
                if lang == 'es' else
                f"The pre-dryer investment of {curr_sym}{dryer_capex:,.2f} pays back in just {payback_months:.1f} months, "
                f"saving {fuel_saved_reactor_gal * annual_multiplier:,.0f} gal/yr in burner fuel and releasing {t_saved_min:.0f} min per batch."
            )
        elif payback_months <= 24.0:
            verdict_badge = "🟡 VIABLE Y RENTABLE" if lang == 'es' else "🟡 FEASIBLE & PROFITABLE"
            verdict_border = "#f59e0b"
            verdict_expl = (
                f"El pre-secado ofrece un retorno sólido en {payback_months:.1f} meses ({payback_years:.1f} años). "
                f"El ahorro anual en combustible y la capacidad extra de procesamiento superan holgadamente los costos operativos del secador."
                if lang == 'es' else
                f"Pre-drying offers a solid payback of {payback_months:.1f} months ({payback_years:.1f} years), comfortably exceeding operational costs."
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

def _econ_defaults(is_continuous):
    """Fallback values of the economic inputs (session_state normally already holds them via DEFAULT_PARAMS)."""
    return {
        'capex_equip': 9000000.0 if is_continuous else 4800000.0,
        'capex_install': 3150000.0 if is_continuous else 1680000.0,
        'capex_civil': 2250000.0 if is_continuous else 1200000.0,
        'capex_piping_elec': 2250000.0 if is_continuous else 1200000.0,
        'capex_eng': 1350000.0 if is_continuous else 720000.0,
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
        'gen_diesel_rate': 1.2,    # gal/h (continuous)
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


def render_economics_inputs(mode_option):
    """Economic parameters inside a form: new values reach session_state (and every section) only when the
    user presses "Recalcular", so typing a number does not reload the page."""
    lang = get_lang()
    is_continuous = (mode_option == "Continuous Operation")
    d = _econ_defaults(is_continuous)
    ss = st.session_state

    def num(label, key, **kw):
        cast = int if isinstance(d[key], int) else float
        return st.number_input(label, value=cast(ss.get(key, d[key])), key=key, **kw)

    def _apply_capex_ratios_cb():
        eq_val = ss.get('capex_equip', d['capex_equip'])
        ss['capex_install'] = float(round(eq_val * 0.35, 2))
        ss['capex_civil'] = float(round(eq_val * 0.25, 2))
        ss['capex_piping_elec'] = float(round(eq_val * 0.25, 2))
        ss['capex_eng'] = float(round(eq_val * 0.15, 2))
        ss['capex_permits'] = float(round(eq_val * 0.05, 2))
        ss['capex_cont'] = float(round(eq_val * 0.10, 2))

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
                    if is_continuous:
                        num(t('econ_input_gen_fuel_rate'), 'gen_diesel_rate', min_value=0.0, step=0.1)
                    else:
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

                if not is_continuous:
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


def compute_economics(mode_option, summary, solver_inputs):
    """Every economic result, computed from the parameters stored in session_state (no widgets).
    The Summary and Economy sections both use it, so they always show the same numbers."""
    ss = st.session_state
    is_continuous = (mode_option == "Continuous Operation")
    d = _econ_defaults(is_continuous)

    def g(key):
        return ss.get(key, d[key])

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

    if not is_continuous:
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
    else:
        gen_diesel_rate = float(g('gen_diesel_rate'))
        batch_cooldown_h = 0.50
        batch_loading_h = 0.50
        batch_turnaround_h = 1.0
        batches_before_cleaning = 20
        cleaning_time_h = 4.0
        maint_cooldown_h = 6.0
        maint_stop_total_h = 10.0
        maint_penalty_per_batch_h = 0.0
        econ_batches_fixed, econ_oil_gal_batch, econ_fuel_gal_batch = 0, 0.0, 0.0
        ss['batch_turnaround_h'] = 1.0

    total_capex = capex_equip + capex_install + capex_civil + capex_piping_elec + capex_eng + capex_permits + capex_cont

    # ----------------------------------------------------
    # CORE COMPUTATIONS PREPARATION
    # ----------------------------------------------------
    sludge_density = float(ss.get('sludge_density', 944.7))
    oil_density = float(ss.get('bio_oil_density', 750.0))
    gas_density = 1.15

    if is_continuous:
        annual_hours = annual_days * 24.0
        batches_per_year = 0.0
        t_cycle_hours = 0.0
        t_op_batch_hours = 0.0
        maint_penalty_per_batch_h = 0.0
        operating_days_batches = float(annual_days)
        cleaning_days_annual = 0.0
        campaign_active_days = float(annual_days)

        sludge_treated_kg = summary['feed_rate_kgh'] * annual_hours
        oil_produced_kg = summary['oil_yield_kgh'] * annual_hours
        char_produced_kg = summary['char_yield_kgh'] * annual_hours
        char_carbon_kg = char_produced_kg
        gas_produced_kg = summary['gas_yield_kgh'] * annual_hours

        fuel_consumed_gal = summary['waste_oil_consumed_galh'] * annual_hours
        elec_consumed_kwh = 0.0
        generator_fuel_consumed_gal = gen_diesel_rate * annual_hours
    else:
        t_cycle_min, t_heat_min, t_hold_min = batch_thermal_cycle_min(summary, solver_inputs)
        t_op_batch_hours = (t_cycle_min / 60.0) + batch_turnaround_h
        t_cycle_hours = t_op_batch_hours + maint_penalty_per_batch_h

        annual_hours = annual_days * 24.0
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

    # Volumetric Conversions for Liquids & Gases
    sludge_treated_gal = (sludge_treated_kg / sludge_density) * 264.172
    if econ_oil_gal_batch > 0:
        oil_produced_gal = econ_oil_gal_batch * batches_per_year
    else:
        oil_produced_gal = (oil_produced_kg / oil_density) * 264.172
    gas_produced_m3 = gas_produced_kg / gas_density

    # ----------------------------------------------------
    # RUN DETAILED FINANCIAL MODEL (BIO-CHAR IN KG)
    # ----------------------------------------------------
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


_CHART_LAYOUT = dict(margin=dict(l=40, r=20, t=50, b=40))   # colours come from the Streamlit theme


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


def render_economics_tab(mode_option, results, summary, solver_inputs, econ=None):
    """Renders the Economy section (Standardized in DOP - RD$): parameters form, then results.
    `econ` is the compute_economics() result already used by the other sections (computed here if omitted)."""
    lang = get_lang()

    # Callback for saving current financial parameters to browser LocalStorage
    def _save_econ_to_ls_cb():
        st.session_state['trigger_save_ls'] = True
        st.session_state['econ_saved_flag'] = True

    # Header with LocalStorage Save Button
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

    st.markdown("---")

    curr_sym = "RD$"

    render_economics_inputs(mode_option)
    if econ is None:
        econ = compute_economics(mode_option, summary, solver_inputs)
    # Same names the result code below has always used, now taken from compute_economics()
    annual_days, annual_hours, available_calendar_days, batch_cooldown_h, batch_loading_h, batches_before_cleaning = econ.get('annual_days'), econ.get('annual_hours'), econ.get('available_calendar_days'), econ.get('batch_cooldown_h'), econ.get('batch_loading_h'), econ.get('batches_before_cleaning')
    batches_per_year, campaign_active_days, char_carbon_kg, char_produced_kg, cleaning_days_annual, cleaning_time_h = econ.get('batches_per_year'), econ.get('campaign_active_days'), econ.get('char_carbon_kg'), econ.get('char_produced_kg'), econ.get('cleaning_days_annual'), econ.get('cleaning_time_h')
    discount_rate, elec_consumed_kwh, fuel_consumed_gal, gas_density, gas_produced_m3, gen_diesel_batch = econ.get('discount_rate'), econ.get('elec_consumed_kwh'), econ.get('fuel_consumed_gal'), econ.get('gas_density'), econ.get('gas_produced_m3'), econ.get('gen_diesel_batch')
    gen_diesel_rate, generator_fuel_consumed_gal, holidays_days, inflation_rate, is_continuous, m = econ.get('gen_diesel_rate'), econ.get('generator_fuel_consumed_gal'), econ.get('holidays_days'), econ.get('inflation_rate'), econ.get('is_continuous'), econ.get('m')
    maint_cooldown_h, maint_penalty_per_batch_h, maint_stop_total_h, oil_density, oil_produced_gal, operating_days_batches = econ.get('maint_cooldown_h'), econ.get('maint_penalty_per_batch_h'), econ.get('maint_stop_total_h'), econ.get('oil_density'), econ.get('oil_produced_gal'), econ.get('operating_days_batches')
    opex_aux_utilities, opex_electricity, opex_fuel, opex_handling, opex_insurance_tax, opex_labor = econ.get('opex_aux_utilities'), econ.get('opex_electricity'), econ.get('opex_fuel'), econ.get('opex_handling'), econ.get('opex_insurance_tax'), econ.get('opex_labor')
    opex_maint, opex_tipping, price_carbon, price_char, price_gas, price_generator_fuel = econ.get('opex_maint'), econ.get('opex_tipping'), econ.get('price_carbon'), econ.get('price_char'), econ.get('price_gas'), econ.get('price_generator_fuel')
    price_oil, project_lifetime, rate_carbon_offset, shutdown_days, sludge_cost, sludge_density = econ.get('price_oil'), econ.get('project_lifetime'), econ.get('rate_carbon_offset'), econ.get('shutdown_days'), econ.get('sludge_cost'), econ.get('sludge_density')
    sludge_treated_gal, t_cycle_hours, t_heat_min, t_hold_min, t_op_batch_hours, tax_rate = econ.get('sludge_treated_gal'), econ.get('t_cycle_hours'), econ.get('t_heat_min'), econ.get('t_hold_min'), econ.get('t_op_batch_hours'), econ.get('tax_rate')
    tipping_y, total_capex = econ.get('tipping_y'), econ.get('total_capex')
    _model = econ['_model']   # financial model for any tipping fee (scenarios, charts)

    if not is_continuous:
        _render_batch_calendar(econ, lang)
    else:
        st.caption(f"📅 **Calendario Anual Continuo:** `{available_calendar_days} días disponibles/año` (365 días base - `{shutdown_days}` días parada - `{holidays_days}` feriados = `{available_calendar_days * 24:.0f} h/año`).")

    # ----------------------------------------------------
    # RENDERING FINANCIAL KPI CARDS
    # ----------------------------------------------------
    st.markdown(f"#### 📊 {t('econ_metrics')}")
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    
    with col_kpi1:
        render_kpi_card(
            t('econ_metric_npv'),
            f"{curr_sym}{m['npv']:,.2f}",
            "Net Present Value / Valor Actual Neto",
            is_positive=(m['npv'] > 0)
        )
        
    with col_kpi2:
        irr_val_str = format_irr(m['irr'])
        render_kpi_card(
            t('econ_metric_irr'),
            irr_val_str,
            "Internal Rate of Return / TIR",
            is_positive=(m['irr'] is not None and m['irr'] > discount_rate)
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
            
        render_kpi_card(
            payback_label,
            payback_val_str,
            payback_sub,
            is_positive=is_pos
        )
        
    with col_kpi4:
        render_kpi_card(
            t('econ_metric_pi'),
            f"{m['pi']:.2f}",
            "Profitability Index / Índice Rentabilidad",
            is_positive=(m['pi'] > 1.0)
        )
        
    with col_kpi5:
        be_val_str = f"{curr_sym}{m['breakeven_tipping']:.2f}/gal"
        if m['breakeven_tipping'] <= 0:
            be_sub = "Autosostenible (Venta productos cubre costos)" if lang == 'es' else "Self-sustaining (Product sales cover costs)"
            is_pos = True
        else:
            be_sub = "Tarifa equilibrio (VAN=0)" if lang == 'es' else "Tipping fee for NPV=0"
            is_pos = (m['breakeven_tipping'] < opex_tipping)
            
        render_kpi_card(
            t('econ_metric_breakeven_tipping'),
            be_val_str,
            be_sub,
            is_positive=is_pos
        )

    # ----------------------------------------------------
    # SLUDGE SCENARIOS SIDE BY SIDE
    # ----------------------------------------------------
    st.markdown("##### " + ("Escenarios del lodo" if lang == 'es' else "Sludge scenarios"))
    scenario_cols, scenario_rows = [], {}
    yrs = "años" if lang == 'es' else "yr"
    for sc in SLUDGE_SCENARIOS:
        fee = scenario_tipping_fee(sc, sludge_cost, tipping_y)
        ms = _model(fee)
        sludge_cost_y1 = max(0.0, -fee) * sludge_treated_gal   # what the plant pays for the sludge
        revenue_y1 = ms['rev_flows'][1] + sludge_cost_y1        # revenue without the purchase cost
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
    st.info(breakeven_note(m['breakeven_tipping'], lang))

    # ----------------------------------------------------
    # PROJECTION CHART (CUMULATIVE CASH FLOW)
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f"##### 📈 {t('econ_metric_cashflow')}")
    
    # Calculate cumulative undiscounted cash flows
    cum_cash = [-total_capex]
    cum_discounted = [-total_capex]
    
    for yr in range(1, int(project_lifetime) + 1):
        cum_cash.append(cum_cash[-1] + m['net_flows'][yr])
        cum_discounted.append(cum_discounted[-1] + m['disc_flows'][yr])
        
    fig = go.Figure()
    
    # Add Undiscounted Cash Flow Bar
    fig.add_trace(go.Bar(
        x=m['years'],
        y=cum_cash,
        name="Undiscounted Cumulative Cash Flow / Flujo Acumulado",
        marker_color="#3b82f6",
        opacity=0.85
    ))
    
    # Add Discounted Cash Flow Line
    fig.add_trace(go.Scatter(
        x=m['years'],
        y=cum_discounted,
        name="Discounted Cumulative Cash Flow (NPV) / Flujo Descontado",
        line=dict(color="#10b981", width=3, dash='dash'),
        mode='lines+markers',
        marker=dict(size=8)
    ))
    
    # Add horizontal line at zero
    fig.add_trace(go.Scatter(
        x=[0, project_lifetime],
        y=[0, 0],
        showlegend=False,
        line=dict(color="#64748b", width=1.5, dash='solid'),
        mode='lines'
    ))
    
    # Style plot layout
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
            title=f"Cumulative Balance / Balance Acumulado ({curr_sym})",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5,
            font=dict(size=10)
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        height=380
    )
    st.plotly_chart(fig, use_container_width=True)

    _render_npv_vs_sludge_price(econ, lang)
    _render_cost_composition(econ, lang)

    # ----------------------------------------------------
    # DATA TABLES AND BREAKDOWNS
    # ----------------------------------------------------
    col_table_l, col_table_r = st.columns(2)
    
    with col_table_l:
        st.markdown(f"##### 🎛️ {t('econ_summary_table')}")
        
        # Compile quantities to display
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
                sludge_treated_gal,
                oil_produced_gal,
                char_produced_kg,
                gas_produced_m3,
                fuel_consumed_gal,
                elec_consumed_kwh,
                generator_fuel_consumed_gal
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
        
        # Display Batch/Continuous Info
        if not is_continuous:
            gen_diesel_per_batch = gen_diesel_batch
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
        else:
            gen_diesel_per_hour = gen_diesel_rate
            burner_fuel_per_hour = summary['waste_oil_consumed_galh']
            if lang == 'es':
                st.info(f"⚡ **Detalles de la Operación Continua:**\n"
                        f"- Horas de operación al año: `{annual_hours:.0f} horas` ({annual_days} días/año × 24h).\n"
                        f"- **Balance Calendario (365 días base):** Feriados: `{holidays_days} d` | Paradas mayores: `{shutdown_days} d` | Disponibles planta: `{annual_days} días`\n"
                        f"- **Consumo horario:** Diésel planta eléctrica: `{gen_diesel_per_hour:.2f} gal/h` | Combustible quemadores: `{burner_fuel_per_hour:.2f} gal/h`")
            else:
                st.info(f"⚡ **Continuous Operation Details:**\n"
                        f"- Operating hours per year: `{annual_hours:.0f} hours` ({annual_days} days/year × 24h).\n"
                        f"- **Annual Calendar (365 days):** Holidays: `{holidays_days} d` | Major shutdown: `{shutdown_days} d` | Plant available: `{annual_days} days`\n"
                        f"- **Consumption per hour:** Generator diesel: `{gen_diesel_per_hour:.2f} gal/h` | Burner fuel: `{burner_fuel_per_hour:.2f} gal/h`")
            
    with col_table_r:
        st.markdown(f"##### 💵 Cash Flow Breakdown / Desglose de Caja")
        
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
            f"Base Annual Flow / Flujo Anual ({curr_sym})": [
                -total_capex,
                m['revenue_breakdown']['tipping'],
                m['revenue_breakdown']['oil'],
                m['revenue_breakdown']['char'],
                m['revenue_breakdown']['gas'],
                m['revenue_breakdown']['carbon'],
                -m['opex_breakdown']['handling'],
                -m['opex_breakdown']['fuel'],
                -m['opex_breakdown']['electricity'],
                -m['opex_breakdown']['aux_utilities'],
                -m['opex_breakdown']['gen_diesel'],
                -m['opex_breakdown']['labor'],
                -m['opex_breakdown']['maintenance'],
                -m['opex_breakdown']['insurance_tax']
            ]
        }
        df_financial = pd.DataFrame(financial_breakdown)
        df_financial_disp = df_financial.copy()
        col_flow_name = f"Base Annual Flow / Flujo Anual ({curr_sym})"
        df_financial_disp[col_flow_name] = df_financial_disp[col_flow_name].map(lambda x: f"{curr_sym}{x:,.2f}" if x >= 0 else f"-{curr_sym}{abs(x):,.2f}")
        st.table(df_financial_disp)

    # ----------------------------------------------------
    # MONTHLY CASH FLOW SIMULATOR (YEAR 1)
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f"#### {t('econ_monthly_title')}")
    st.markdown(t('econ_monthly_desc'))
    
    # Initialize config in session state if not present
    if 'monthly_config' not in st.session_state:
        avg_days = float(annual_days) / 12.0
        st.session_state.monthly_config = pd.DataFrame({
            "Month / Mes": [f"Month / Mes {i:02d}" for i in range(1, 13)],
            "Days Operated / Días Operados": [round(avg_days, 1)] * 12,
            "Pyrolysis oil Sales / Venta Aceite pirolítico (%)": [100.0] * 12,
            "Char Sales / Venta Carbón (%)": [100.0] * 12,
            "Syngas Sales / Venta Syngas (%)": [100.0] * 12
        })
        
    # Sync with annual_days if changed externally
    current_days_sum = st.session_state.monthly_config["Days Operated / Días Operados"].sum()
    if abs(current_days_sum - annual_days) > 0.5:
        avg_days = float(annual_days) / 12.0
        st.session_state.monthly_config["Days Operated / Días Operados"] = [round(avg_days, 1)] * 12

    # Render st.data_editor
    edited_df = st.data_editor(
        st.session_state.monthly_config,
        num_rows="fixed",
        width='stretch',
        column_config={
            "Month / Mes": st.column_config.TextColumn("Month / Mes", disabled=True),
            "Days Operated / Días Operados": st.column_config.NumberColumn("Days Operated", min_value=0.0, max_value=31.0, step=0.5),
            "Pyrolysis oil Sales / Venta Aceite pirolítico (%)": st.column_config.NumberColumn("Pyrolysis oil Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
            "Char Sales / Venta Carbón (%)": st.column_config.NumberColumn("Char Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
            "Syngas Sales / Venta Syngas (%)": st.column_config.NumberColumn("Syngas Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
        },
        key="monthly_editor"
    )
    st.session_state.monthly_config = edited_df

    # Run month-by-month projection
    inv_oil = 0.0
    inv_char = 0.0
    
    m_names = []
    m_days = []
    m_sludge = []
    m_oil_prod = []
    m_oil_sold = []
    m_oil_inv = []
    m_char_prod = []
    m_char_sold = []
    m_char_inv = []
    m_gas_prod = []
    m_gas_sold = []
    m_revenues = []
    m_opex = []
    m_net_flow = []
    
    for idx in range(12):
        row = edited_df.iloc[idx]
        m_name = row["Month / Mes"]
        days = row["Days Operated / Días Operados"]
        o_pct = row["Pyrolysis oil Sales / Venta Aceite pirolítico (%)"]
        c_pct = row["Char Sales / Venta Carbón (%)"]
        g_pct = row["Syngas Sales / Venta Syngas (%)"] if "Syngas Sales / Venta Syngas (%)" in row else row.get("Syngas Sales / Venta Syngas (%)", 100.0)
        
        # Calculate monthly production and utilities
        if is_continuous:
            sludge_kg = summary['feed_rate_kgh'] * 24.0 * days
            oil_kg = summary['oil_yield_kgh'] * 24.0 * days
            char_kg = summary['char_yield_kgh'] * 24.0 * days
            gas_kg = summary['gas_yield_kgh'] * 24.0 * days
            
            fuel_gal = summary['waste_oil_consumed_galh'] * 24.0 * days
            elec_kwh = 0.0
            diesel_gal = gen_diesel_rate * 24.0 * days
        else:
            batches = np.floor((days * 24.0) / t_cycle_hours) if t_cycle_hours > 0 else 0.0
            sludge_kg = summary['batch_load_kg'] * batches
            oil_kg = summary['oil_yield_kg'] * batches
            char_kg = summary['char_yield_kg'] * batches
            gas_kg = summary.get('syngas_flare_kg', summary['gas_yield_kg']) * batches
            
            fuel_gal = summary['waste_oil_consumed_gal'] * batches
            elec_kwh = 0.0
            diesel_gal = gen_diesel_batch * batches
            
        # Volumetric conversion for liquids & gases; mass for char
        sludge_gal = (sludge_kg / sludge_density) * 264.172
        oil_prod_gal = (oil_kg / oil_density) * 264.172
        char_prod_kg = char_kg
        gas_prod_m3 = gas_kg / gas_density
        
        # Inventory flow calculations
        avail_oil = inv_oil + oil_prod_gal
        avail_char = inv_char + char_prod_kg
        
        oil_sold = avail_oil * (o_pct / 100.0)
        char_sold = avail_char * (c_pct / 100.0)
        gas_sold = gas_prod_m3 * (g_pct / 100.0)
        
        inv_oil = avail_oil - oil_sold
        inv_char = avail_char - char_sold
        
        # Revenues
        rev_tip = sludge_gal * opex_tipping
        rev_o = oil_sold * price_oil
        rev_c = char_sold * price_char
        rev_g = gas_sold * price_gas
        char_carbon_month_kg = char_prod_kg if is_continuous else (
            summary.get('char_organic_kg', summary['char_yield_kg']) * batches)
        rev_carb = ((char_carbon_month_kg * rate_carbon_offset) / 1000.0) * price_carbon
        total_rev = rev_tip + rev_o + rev_c + rev_g + rev_carb
        
        # OPEX
        c_handling = sludge_gal * opex_handling
        c_fuel = fuel_gal * opex_fuel
        c_elec = elec_kwh * opex_electricity
        c_aux = opex_aux_utilities / 12.0
        c_diesel = diesel_gal * price_generator_fuel
        c_labor = opex_labor / 12.0
        c_maint = (total_capex * (opex_maint / 100.0)) / 12.0
        c_ins_tax = (total_capex * (opex_insurance_tax / 100.0)) / 12.0
        total_opex = c_handling + c_fuel + c_elec + c_aux + c_diesel + c_labor + c_maint + c_ins_tax
        
        # Net Cash Flow after monthly taxes
        ebitda = total_rev - total_opex
        depr = total_capex / (project_lifetime * 12.0) if project_lifetime > 0 else 0.0
        taxable = ebitda - depr
        taxes = max(0.0, taxable * (tax_rate / 100.0))
        net_cf = ebitda - taxes
        
        m_names.append(m_name)
        m_days.append(days)
        m_sludge.append(sludge_gal)
        m_oil_prod.append(oil_prod_gal)
        m_oil_sold.append(oil_sold)
        m_oil_inv.append(inv_oil)
        m_char_prod.append(char_prod_kg)
        m_char_sold.append(char_sold)
        m_char_inv.append(inv_char)
        m_gas_prod.append(gas_prod_m3)
        m_gas_sold.append(gas_sold)
        m_revenues.append(total_rev)
        m_opex.append(total_opex)
        m_net_flow.append(net_cf)
        
    df_monthly_proj = pd.DataFrame({
        "Month": m_names,
        "Days Operated": m_days,
        "Sludge Treated (gal)": m_sludge,
        "Pyrolysis oil Produced (gal)": m_oil_prod,
        "Pyrolysis oil Sold (gal)": m_oil_sold,
        "Pyrolysis oil Inventory (gal)": m_oil_inv,
        "Char Produced (kg)": m_char_prod,
        "Char Sold (kg)": m_char_sold,
        "Char Inventory (kg)": m_char_inv,
        "Syngas Produced (m³)": m_gas_prod,
        "Syngas Sold (m³)": m_gas_sold,
        f"Revenue ({curr_sym})": m_revenues,
        f"OPEX ({curr_sym})": m_opex,
        f"Net Cash Flow ({curr_sym})": m_net_flow
    })
    
    # Format monthly table for display
    df_monthly_disp = df_monthly_proj.copy()
    df_monthly_disp["Days Operated"] = df_monthly_disp["Days Operated"].map(lambda x: f"{x:.1f}")
    df_monthly_disp["Sludge Treated (gal)"] = df_monthly_disp["Sludge Treated (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Pyrolysis oil Produced (gal)"] = df_monthly_disp["Pyrolysis oil Produced (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Pyrolysis oil Sold (gal)"] = df_monthly_disp["Pyrolysis oil Sold (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Pyrolysis oil Inventory (gal)"] = df_monthly_disp["Pyrolysis oil Inventory (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Char Produced (kg)"] = df_monthly_disp["Char Produced (kg)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Char Sold (kg)"] = df_monthly_disp["Char Sold (kg)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Char Inventory (kg)"] = df_monthly_disp["Char Inventory (kg)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Syngas Produced (m³)"] = df_monthly_disp["Syngas Produced (m³)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Syngas Sold (m³)"] = df_monthly_disp["Syngas Sold (m³)"] .map(lambda x: f"{x:,.1f}")
    df_monthly_disp[f"Revenue ({curr_sym})"] = df_monthly_disp[f"Revenue ({curr_sym})"].map(lambda x: f"{curr_sym}{x:,.2f}" if x >= 0 else f"-{curr_sym}{abs(x):,.2f}")
    df_monthly_disp[f"OPEX ({curr_sym})"] = df_monthly_disp[f"OPEX ({curr_sym})"].map(lambda x: f"{curr_sym}{x:,.2f}" if x >= 0 else f"-{curr_sym}{abs(x):,.2f}")
    df_monthly_disp[f"Net Cash Flow ({curr_sym})"] = df_monthly_disp[f"Net Cash Flow ({curr_sym})"].map(lambda x: f"{curr_sym}{x:,.2f}" if x >= 0 else f"-{curr_sym}{abs(x):,.2f}")
    
    st.dataframe(df_monthly_disp, width='stretch')
    
    # Export to CSV
    csv_monthly_buf = io.StringIO()
    df_monthly_proj.to_csv(csv_monthly_buf, index=False)
    csv_monthly_bytes = csv_monthly_buf.getvalue().encode('utf-8')
    
    st.download_button(
        label="📥 Download Monthly Cash Flows as CSV / Descargar Flujo Mensual (CSV)",
        data=csv_monthly_bytes,
        file_name="pyrolysis_monthly_cash_flows.csv",
        mime="text/csv",
        key="download_monthly_cash_flows"
    )

    # ----------------------------------------------------
    # MONTHLY VISUALIZATION CHARTS
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f"#### {t('econ_monthly_chart_title')}")
    st.markdown(t('econ_monthly_chart_desc'))

    m_cum_flow = np.cumsum(m_net_flow).tolist()
    month_labels = [f"M{i+1:02d}" for i in range(12)]

    tab_m_fin, tab_m_vol = st.tabs([t('econ_monthly_tab_financial'), t('econ_monthly_tab_volumes')])

    with tab_m_fin:
        fig_m_fin = go.Figure()

        # Monthly Revenue Bar
        fig_m_fin.add_trace(go.Bar(
            x=month_labels,
            y=m_revenues,
            name=t('econ_monthly_rev_label'),
            marker_color="#10b981",
            opacity=0.85,
            hovertemplate='%{x}: ' + curr_sym + '%{y:,.2f}<extra></extra>'
        ))

        # Monthly OPEX Bar
        fig_m_fin.add_trace(go.Bar(
            x=month_labels,
            y=m_opex,
            name=t('econ_monthly_opex_label'),
            marker_color="#ef4444",
            opacity=0.85,
            hovertemplate='%{x}: ' + curr_sym + '%{y:,.2f}<extra></extra>'
        ))

        # Monthly Net Cash Flow Line
        fig_m_fin.add_trace(go.Scatter(
            x=month_labels,
            y=m_net_flow,
            name=t('econ_monthly_net_label'),
            line=dict(color="#3b82f6", width=3),
            mode='lines+markers',
            marker=dict(size=7),
            hovertemplate='%{x}: ' + curr_sym + '%{y:,.2f}<extra></extra>'
        ))

        # Cumulative Net Cash Flow Line
        fig_m_fin.add_trace(go.Scatter(
            x=month_labels,
            y=m_cum_flow,
            name=t('econ_monthly_cum_label'),
            line=dict(color="#f59e0b", width=2.5, dash='dash'),
            mode='lines+markers',
            marker=dict(size=6),
            hovertemplate='%{x}: ' + curr_sym + '%{y:,.2f}<extra></extra>'
        ))

        # Zero reference line
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
                title=f"Amount / Monto ({curr_sym})",
            ),
            barmode='group',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5,
                font=dict(size=10)
            ),
            margin=dict(l=50, r=40, t=40, b=50),
            height=400
        )
        st.plotly_chart(fig_m_fin, use_container_width=True)

    with tab_m_vol:
        fig_m_vol = go.Figure()

        # Pyrolysis oil Production vs Sales vs Inventory
        fig_m_vol.add_trace(go.Bar(
            x=month_labels,
            y=m_oil_prod,
            name=t('econ_monthly_oil_prod'),
            marker_color="#8b5cf6",
            opacity=0.85,
            hovertemplate='%{x}: %{y:,.1f} gal<extra></extra>'
        ))

        fig_m_vol.add_trace(go.Bar(
            x=month_labels,
            y=m_oil_sold,
            name=t('econ_monthly_oil_sold'),
            marker_color="#10b981",
            opacity=0.85,
            hovertemplate='%{x}: %{y:,.1f} gal<extra></extra>'
        ))

        fig_m_vol.add_trace(go.Scatter(
            x=month_labels,
            y=m_oil_inv,
            name=t('econ_monthly_oil_inv'),
            line=dict(color="#f43f5e", width=2.5, dash='dash'),
            mode='lines+markers',
            marker=dict(size=6),
            hovertemplate='%{x}: %{y:,.1f} gal<extra></extra>'
        ))

        # Char Production vs Sales vs Inventory (in kg)
        fig_m_vol.add_trace(go.Bar(
            x=month_labels,
            y=m_char_prod,
            name=t('econ_monthly_char_prod'),
            marker_color="#0ea5e9",
            opacity=0.85,
            hovertemplate='%{x}: %{y:,.1f} kg<extra></extra>'
        ))

        fig_m_vol.add_trace(go.Bar(
            x=month_labels,
            y=m_char_sold,
            name=t('econ_monthly_char_sold'),
            marker_color="#fde047",
            opacity=0.85,
            hovertemplate='%{x}: %{y:,.1f} kg<extra></extra>'
        ))

        fig_m_vol.add_trace(go.Scatter(
            x=month_labels,
            y=m_char_inv,
            name=t('econ_monthly_char_inv'),
            line=dict(color="#d97706", width=2.5, dash='dash'),
            mode='lines+markers',
            marker=dict(size=6),
            hovertemplate='%{x}: %{y:,.1f} kg<extra></extra>'
        ))

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
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5,
                font=dict(size=9)
            ),
            margin=dict(l=50, r=40, t=40, b=50),
            height=420
        )
        st.plotly_chart(fig_m_vol, use_container_width=True)

    # ----------------------------------------------------
    # TORNADO CHART (SENSITIVITY ANALYSIS)
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f"#### {t('econ_sensitivity_title')}")
    st.markdown(t('econ_sensitivity_desc'))
    
    # Sensitivity calculation helper
    def get_perturbed_npv(param, change_pct):
        mult = 1.0 + (change_pct / 100.0)
        
        p_capex = total_capex * mult if param == 'capex' else total_capex
        p_handling = opex_handling * mult if param == 'opex' else opex_handling
        p_fuel = opex_fuel * mult if param == 'opex' else opex_fuel
        p_elec = opex_electricity * mult if param == 'opex' else opex_electricity
        p_aux = opex_aux_utilities * mult if param == 'opex' else opex_aux_utilities
        p_gen_fuel = price_generator_fuel * mult if param == 'opex' else price_generator_fuel
        p_labor = opex_labor * mult if param == 'opex' else opex_labor
        p_maint = opex_maint * mult if param == 'opex' else opex_maint
        p_ins = opex_insurance_tax * mult if param == 'opex' else opex_insurance_tax
        
        p_tipping = opex_tipping * mult if param == 'tipping' else opex_tipping
        p_oil = price_oil * mult if param == 'oil' else price_oil
        p_char = price_char * mult if param == 'char' else price_char
        
        res = run_financial_model(
            p_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
            fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
            p_handling, p_fuel, p_elec, p_aux, p_gen_fuel,
            p_labor, p_maint, p_ins,
            p_tipping, p_oil, p_char, price_gas, price_carbon, rate_carbon_offset,
            discount_rate, project_lifetime, tax_rate, inflation_rate,
            char_carbon_kg=char_carbon_kg
        )
        return res['npv']

    sens_keys = ['capex', 'opex', 'tipping', 'oil', 'char']
    sens_labels = [t('econ_param_capex'), t('econ_param_opex'), t('econ_param_tipping'), t('econ_param_oil'), t('econ_param_char')]
    
    npvs_minus20 = [get_perturbed_npv(k, -20) for k in sens_keys]
    npvs_minus10 = [get_perturbed_npv(k, -10) for k in sens_keys]
    npvs_plus10 = [get_perturbed_npv(k, +10) for k in sens_keys]
    npvs_plus20 = [get_perturbed_npv(k, +20) for k in sens_keys]
    
    base_npv = m['npv']
    
    # Dynamic Sorting: Sort parameters by total swing range
    swings = [abs(npvs_plus20[i] - npvs_minus20[i]) for i in range(len(sens_keys))]
    sorted_idx = np.argsort(swings)
    
    sorted_labels = [sens_labels[i] for i in sorted_idx]
    sorted_minus20 = [npvs_minus20[i] for i in sorted_idx]
    sorted_minus10 = [npvs_minus10[i] for i in sorted_idx]
    sorted_plus10 = [npvs_plus10[i] for i in sorted_idx]
    sorted_plus20 = [npvs_plus20[i] for i in sorted_idx]
    
    fig_sens = go.Figure()
    
    # Add +20% variation bar
    fig_sens.add_trace(go.Bar(
        y=sorted_labels,
        x=[val - base_npv for val in sorted_plus20],
        base=base_npv,
        orientation='h',
        name='+20% Variation',
        marker=dict(color='#10b981', line=dict(color='#047857', width=1)),
        hovertemplate='NPV at +20%: ' + curr_sym + '%{x:,.2f}<extra></extra>'
    ))
    
    # Add +10% variation bar
    fig_sens.add_trace(go.Bar(
        y=sorted_labels,
        x=[val - base_npv for val in sorted_plus10],
        base=base_npv,
        orientation='h',
        name='+10% Variation',
        marker=dict(color='#6ee7b7', line=dict(color='#34d399', width=1)),
        hovertemplate='NPV at +10%: ' + curr_sym + '%{x:,.2f}<extra></extra>'
    ))
    
    # Add -10% variation bar
    fig_sens.add_trace(go.Bar(
        y=sorted_labels,
        x=[val - base_npv for val in sorted_minus10],
        base=base_npv,
        orientation='h',
        name='-10% Variation',
        marker=dict(color='#fca5a5', line=dict(color='#f87171', width=1)),
        hovertemplate='NPV at -10%: ' + curr_sym + '%{x:,.2f}<extra></extra>'
    ))
    
    # Add -20% variation bar
    fig_sens.add_trace(go.Bar(
        y=sorted_labels,
        x=[val - base_npv for val in sorted_minus20],
        base=base_npv,
        orientation='h',
        name='-20% Variation',
        marker=dict(color='#ef4444', line=dict(color='#dc2626', width=1)),
        hovertemplate='NPV at -20%: ' + curr_sym + '%{x:,.2f}<extra></extra>'
    ))
    
    # Vertical line representing base case NPV
    fig_sens.add_vline(x=base_npv, line_width=2, line_dash="dash", line_color="gray", annotation_text=f"Base Case NPV: {curr_sym}{base_npv:,.2f}")
    
    fig_sens.update_layout(
        title=dict(
            text=f"NPV Sensitivity Tornado Chart ({curr_sym})",
            font=dict(size=14)
        ),
        xaxis=dict(
            title=f"Net Present Value (NPV) ({curr_sym})",
        ),
        yaxis=dict(
        ),
        barmode='overlay',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=10)
        ),
        margin=dict(l=120, r=40, t=40, b=40),
        height=350
    )
    
    st.plotly_chart(fig_sens, use_container_width=True)

    # ----------------------------------------------------
    # SLUDGE PRE-DRYING EVALUATOR (OPTION 2)
    # ----------------------------------------------------
    render_pre_drying_evaluator(
        solver_inputs=solver_inputs,
        summary=summary,
        results=results,
        is_continuous=is_continuous,
        curr_sym=curr_sym,
        opex_fuel=opex_fuel,
        available_calendar_days=available_calendar_days,
        batches_per_year=batches_per_year,
        t_cycle_hours=t_cycle_hours,
        t_op_batch_hours=t_op_batch_hours,
        maint_penalty_per_batch_h=maint_penalty_per_batch_h,
        m=m,
        lang=lang
    )

    # ----------------------------------------------------
    # PROJECTION DATA FRAME AND DOWNLOAD SECTION
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown(f"#### 📅 Year-by-Year Financial Projections / Tabla de Proyecciones")
    
    proj_data = {
        "Year / Año": m['years'],
        f"CAPEX ({curr_sym})": [m['net_flows'][0] if yr == 0 else 0.0 for yr in m['years']],
        f"Revenue / Ingresos ({curr_sym})": m['rev_flows'],
        f"OPEX ({curr_sym})": m['opex_flows'],
        f"Depreciation ({curr_sym})": m['depr_flows'],
        f"Taxes / Impuestos ({curr_sym})": m['tax_flows'],
        f"Net Cash Flow ({curr_sym})": m['net_flows'],
        f"Discounted Cash Flow ({curr_sym})": m['disc_flows'],
        f"Cumulative NPV ({curr_sym})": cum_discounted
    }
    
    df_proj = pd.DataFrame(proj_data)
    df_proj_disp = df_proj.copy()
    
    for col in df_proj_disp.columns:
        if col != "Year / Año":
            df_proj_disp[col] = df_proj_disp[col].map(lambda x: f"{curr_sym}{x:,.2f}" if x >= 0 else f"-{curr_sym}{abs(x):,.2f}")
            
    st.dataframe(df_proj_disp, width='stretch')
    
    csv_buffer = io.StringIO()
    df_proj.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode('utf-8')
    
    st.download_button(
        label="📥 Download Projections as CSV / Descargar Proyecciones (CSV)",
        data=csv_bytes,
        file_name="pyrolysis_financial_projections.csv",
        mime="text/csv",
        key="download_financial_projections"
    )

def render_sustainability_tab(summary, solver_inputs):
    """Renders the independent Sustainability & Carbon Offsets Dashboard."""
    lang = get_lang()
    st.markdown(f"### {t('econ_sustainability_title')}")
    st.markdown(
        t('econ_sustainability_desc', "Evaluate the carbon sequestration potential and environmental benefits of industrial pyrolysis sludge treatment.")
    )
    st.markdown("---")
    
    is_continuous = (st.session_state.get('mode_option', 'Continuous Operation') == "Continuous Operation")
    shutdown_days = int(st.session_state.get('shutdown_days', 15))
    holidays_days = int(st.session_state.get('holidays_days', 15))
    available_calendar_days = max(1, 365 - shutdown_days - holidays_days)
    annual_days = st.session_state.get('annual_days', available_calendar_days)
    
    # Financial keys & currency retrieval (Standardized in DOP - RD$)
    curr_sym = "RD$"
    price_carbon = st.session_state.get('price_carbon', 1200.0)
    rate_carbon_offset = st.session_state.get('rate_carbon_offset', 2.2)
    
    if is_continuous:
        annual_hours = annual_days * 24.0
        char_produced_kg = summary['char_yield_kgh'] * annual_hours
    else:
        t_cycle_min, _, _ = batch_thermal_cycle_min(summary, solver_inputs)
        batch_cooldown_h = float(st.session_state.get('batch_cooldown_h', 0.50))
        batch_loading_h = float(st.session_state.get('batch_loading_h', 0.50))
        batch_turnaround_h = float(st.session_state.get('batch_turnaround_h', batch_cooldown_h + batch_loading_h))
        batches_before_cleaning = int(st.session_state.get('batches_before_cleaning', 20))
        cleaning_time_h = float(st.session_state.get('cleaning_time_h', 4.0))
        maint_cooldown_h = float(st.session_state.get('maint_cooldown_h', 6.0))
        maint_penalty_per_batch_h = (maint_cooldown_h + cleaning_time_h) / max(batches_before_cleaning, 1)
        t_op_batch_hours = (t_cycle_min / 60.0) + batch_turnaround_h
        t_cycle_hours = t_op_batch_hours + maint_penalty_per_batch_h
        batches_fixed = int(st.session_state.get('econ_batches_per_year', 0))
        if batches_fixed > 0:
            batches_per_year = float(batches_fixed)
        else:
            batches_per_year = np.floor((annual_days * 24.0) / t_cycle_hours) if t_cycle_hours > 0 else 0.0
        # Carbon credit applies to carbon-bearing char only (ash excluded)
        char_produced_kg = summary.get('char_organic_kg', summary['char_yield_kg']) * batches_per_year

    co2_tons = (char_produced_kg * rate_carbon_offset) / 1000.0
    trees_planted = co2_tons / 0.022
    cars_removed = co2_tons / 4.6

    # Process emissions (batch mode): burner fuel, generator diesel and syngas combustion
    if not is_continuous:
        fuel_density = float(st.session_state.get('fuel_density', 0.90))
        gen_diesel_batch = float(st.session_state.get('gen_diesel_batch', 1.0))
        fuel_per_batch_gal = float(st.session_state.get('econ_fuel_gal_per_batch', 0.0)) or summary['waste_oil_consumed_gal']
        co2_burner_t = fuel_per_batch_gal * batches_per_year * fuel_density * 3.785 * EF_CO2_FUEL_OIL_KG_PER_KG / 1000.0
        co2_diesel_t = gen_diesel_batch * batches_per_year * EF_CO2_DIESEL_KG_PER_GAL / 1000.0
        co2_syngas_t = summary['gas_yield_kg'] * batches_per_year * EF_CO2_SYNGAS_KG_PER_KG / 1000.0
        co2_emitted_t = co2_burner_t + co2_diesel_t + co2_syngas_t
    else:
        co2_burner_t = co2_diesel_t = co2_syngas_t = co2_emitted_t = 0.0
    co2_net_t = co2_tons - co2_emitted_t

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label=t('econ_co2_sequestered_annually'),
            value=f"{co2_tons:,.2f} t CO2e/yr",
            delta=f"{curr_sym}{co2_tons * price_carbon:,.2f}/yr"
        )
    with col2:
        st.metric(
            label=t('econ_co2_trees_eq'),
            value=f"{int(trees_planted):,}"
        )
    with col3:
        st.metric(
            label=t('econ_co2_cars_eq'),
            value=f"{int(cars_removed):,}"
        )
        
    if not is_continuous:
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

    # Visual green impact description
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
