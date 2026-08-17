import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import io
from pyrolysis import TRANSLATIONS

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def solve_irr(cash_flows):
    """
    Calculates the Internal Rate of Return (IRR) for a given series of cash flows.
    Returns the percentage or None if it cannot be solved.
    """
    if not cash_flows or all(x >= 0 for x in cash_flows) or all(x <= 0 for x in cash_flows):
        return None
    
    def npv_func(r):
        return sum(cf / ((1.0 + r)**t) for t, cf in enumerate(cash_flows))
    
    low = -0.99
    high = 10.0
    
    val_low = npv_func(low)
    val_high = npv_func(high)
    
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

def render_kpi_card(title, value_str, subtitle=None, is_positive=True):
    """Renders a premium visual card for financial KPIs."""
    color = "#10b981" if is_positive else "#ef4444"
    border_color = "#334155"
    text_color_sub = "#94a3b8"
    
    html = f"""
    <div style="
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 18px;
        border-radius: 12px;
        border: 1px solid {border_color};
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        text-align: center;
        margin-bottom: 15px;
        height: 100%;
    ">
        <h4 style="color: {text_color_sub}; margin: 0; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;">{title}</h4>
        <h2 style="color: {color}; margin: 8px 0; font-size: 24px; font-weight: 700;">{value_str}</h2>
        {f'<p style="color: #64748b; margin: 0; font-size: 11px;">{subtitle}</p>' if subtitle else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def run_financial_model(
    total_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
    fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
    opex_handling, opex_fuel, opex_electricity, opex_aux_utilities, price_generator_fuel,
    opex_labor, opex_maint, opex_insurance_tax,
    opex_tipping, price_oil, price_char, price_gas, price_carbon, rate_carbon_offset,
    discount_rate, project_lifetime, tax_rate, inflation_rate
):
    """
    Runs the detailed cash flow model over the project lifetime and returns year-by-year cash flows
    and advanced economic indicators (computed in gallons, kg, and m3).
    """
    r = discount_rate / 100.0
    inf = inflation_rate / 100.0
    tax = tax_rate / 100.0
    
    # Year 1 base values (uninflated)
    rev_tipping = sludge_treated_gal * opex_tipping
    rev_oil = oil_produced_gal * price_oil
    rev_char = char_produced_kg * price_char
    rev_gas = gas_produced_m3 * price_gas
    
    annual_co2_sequestered_ton = (char_produced_kg * rate_carbon_offset) / 1000.0
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

    t0 = 0.0
    t1 = 5.0
    n0 = get_npv_for_tipping(t0)
    n1 = get_npv_for_tipping(t1)
    
    if abs(n1 - n0) > 1e-3:
        breakeven_tipping = t1 - n1 * (t1 - t0) / (n1 - n0)
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

def render_economics_tab(mode_option, results, summary, solver_inputs):
    """Renders the interactive Economic Viability tab (Standardized in DOP - RD$)."""
    lang = get_lang()
    
    st.markdown(f"### 💸 {t('econ_title')}")
    st.markdown(t('econ_desc'))
    st.markdown("---")
    
    curr_sym = "RD$"
    
    # Default values based on operational mode (Standardized in DOP RD$)
    is_continuous = (mode_option == "Continuous Operation")
    default_equip = 9000000.0 if is_continuous else 4800000.0
    default_install = 3150000.0 if is_continuous else 1680000.0
    default_civil = 2250000.0 if is_continuous else 1200000.0
    default_piping_elec = 2250000.0 if is_continuous else 1200000.0
    default_eng = 1350000.0 if is_continuous else 720000.0
    default_permits = 450000.0
    default_contingency = 900000.0
    
    default_handling = 3.00
    default_tipping = 9.00
    default_fuel_price = 180.00
    default_electricity = 7.50
    default_aux_utilities = 300000.0
    default_gen_fuel_price = 262.80
    default_labor = 3000000.0
    default_maint_rate = 3.0
    default_insurance_tax = 1.0
    
    default_oil_price = 120.00
    default_char_price = 21.00
    default_gas_price = 3.60
    default_price_carbon = 1200.0
    default_rate_carbon_offset = 2.2
    
    default_discount = 14.0
    default_lifetime = 10
    default_days = 246
    default_motor_kw = 15.0 if is_continuous else 7.5
    default_tax_rate = 25.0
    default_inflation_rate = 4.0

    # Precalculate default generator consumption based on mode
    if is_continuous:
        default_gen_consumption = float(default_motor_kw * 0.08)
    else:
        t_heat_min = (solver_inputs.get('temp_hold_c', 400.0) - solver_inputs.get('temp_start_c', 25.0)) / solver_inputs.get('heating_rate_cmin', 1.0)
        t_hold_min = solver_inputs.get('hold_time_min', 60.0)
        t_cycle_min = t_heat_min + t_hold_min
        default_gen_consumption = float(default_motor_kw * (t_cycle_min / 60.0) * 0.08)
    
    # Columns for parameters (using expanders)
    col_param_l, col_param_r = st.columns(2)
    
    with col_param_l:
        with st.expander(f"🏗️ {t('econ_section_capex')}", expanded=True):
            col_cx1, col_cx2 = st.columns(2)
            with col_cx1:
                capex_equip = st.number_input(t('econ_input_reactor_cost'), min_value=0.0, value=float(st.session_state.get('capex_equip', default_equip)), step=250000.0, key='capex_equip')
                capex_civil = st.number_input(t('econ_input_civil_works'), min_value=0.0, value=float(st.session_state.get('capex_civil', default_civil)), step=100000.0, key='capex_civil')
                capex_eng = st.number_input(t('econ_input_engineering'), min_value=0.0, value=float(st.session_state.get('capex_eng', default_eng)), step=100000.0, key='capex_eng')
            with col_cx2:
                capex_install = st.number_input(t('econ_input_installation'), min_value=0.0, value=float(st.session_state.get('capex_install', default_install)), step=100000.0, key='capex_install')
                capex_piping_elec = st.number_input(t('econ_input_piping_elec'), min_value=0.0, value=float(st.session_state.get('capex_piping_elec', default_piping_elec)), step=100000.0, key='capex_piping_elec')
                capex_permits = st.number_input(t('econ_input_permits'), min_value=0.0, value=float(st.session_state.get('capex_permits', default_permits)), step=50000.0, key='capex_permits')
            capex_cont = st.number_input(t('econ_input_contingency'), min_value=0.0, value=float(st.session_state.get('capex_cont', default_contingency)), step=50000.0, key='capex_cont')
            
            if st.button(t('econ_btn_apply_ratios'), key='btn_apply_capex_ratios'):
                eq_val = st.session_state.get('capex_equip', default_equip)
                st.session_state['capex_install'] = float(round(eq_val * 0.35, 2))
                st.session_state['capex_civil'] = float(round(eq_val * 0.25, 2))
                st.session_state['capex_piping_elec'] = float(round(eq_val * 0.25, 2))
                st.session_state['capex_eng'] = float(round(eq_val * 0.15, 2))
                st.session_state['capex_permits'] = float(round(eq_val * 0.05, 2))
                st.session_state['capex_cont'] = float(round(eq_val * 0.10, 2))
                st.rerun()

        with st.expander(f"⚙️ {t('econ_section_opex')}", expanded=True):
            col_ox1, col_ox2 = st.columns(2)
            with col_ox1:
                opex_handling = st.number_input(t('econ_input_handling'), min_value=0.0, value=float(st.session_state.get('opex_handling', default_handling)), step=0.5, key='opex_handling')
                opex_electricity = st.number_input(t('econ_input_electricity'), min_value=0.0, value=float(st.session_state.get('opex_electricity', default_electricity)), step=0.5, key='opex_electricity')
                price_generator_fuel = st.number_input(t('econ_input_gen_fuel'), min_value=0.0, value=float(st.session_state.get('price_generator_fuel', default_gen_fuel_price)), step=5.0, key='price_generator_fuel')
                opex_labor = st.number_input(t('econ_input_labor'), min_value=0.0, value=float(st.session_state.get('opex_labor', default_labor)), step=250000.0, key='opex_labor')
            with col_ox2:
                opex_fuel = st.number_input(t('econ_input_fuel'), min_value=0.0, value=float(st.session_state.get('opex_fuel', default_fuel_price)), step=5.0, key='opex_fuel')
                opex_aux_utilities = st.number_input(t('econ_input_aux_utilities'), min_value=0.0, value=float(st.session_state.get('opex_aux_utilities', default_aux_utilities)), step=25000.0, key='opex_aux_utilities')
                if is_continuous:
                    gen_diesel_rate = st.number_input(t('econ_input_gen_fuel_rate'), min_value=0.0, value=float(st.session_state.get('gen_diesel_rate', default_gen_consumption)), step=0.1, key='gen_diesel_rate')
                else:
                    gen_diesel_batch = st.number_input(t('econ_input_gen_fuel_batch'), min_value=0.0, value=float(st.session_state.get('gen_diesel_batch', default_gen_consumption)), step=0.5, key='gen_diesel_batch')
                opex_maint = st.number_input(t('econ_input_maintenance'), min_value=0.0, max_value=25.0, value=float(st.session_state.get('opex_maint', default_maint_rate)), step=0.5, key='opex_maint')
            opex_insurance_tax = st.number_input(t('econ_input_insurance_tax'), min_value=0.0, max_value=10.0, value=float(st.session_state.get('opex_insurance_tax', default_insurance_tax)), step=0.1, key='opex_insurance_tax')
            
    with col_param_r:
        with st.expander(f"🏷️ {t('econ_section_revenue')}", expanded=True):
            opex_tipping = st.number_input(t('econ_input_tipping'), min_value=0.0, value=float(st.session_state.get('opex_tipping', default_tipping)), step=1.0, key='opex_tipping')
            col_rv1, col_rv2 = st.columns(2)
            with col_rv1:
                price_oil = st.number_input(t('econ_input_price_oil'), min_value=0.0, value=float(st.session_state.get('price_oil', default_oil_price)), step=5.0, key='price_oil')
                price_char = st.number_input(t('econ_input_price_char'), min_value=0.0, value=float(st.session_state.get('price_char', default_char_price)), step=1.0, key='price_char')
            with col_rv2:
                price_gas = st.number_input(t('econ_input_price_gas'), min_value=0.0, value=float(st.session_state.get('price_gas', default_gas_price)), step=0.5, key='price_gas')
                price_carbon = st.number_input(t('econ_input_carbon_price'), min_value=0.0, value=float(st.session_state.get('price_carbon', default_price_carbon)), step=50.0, key='price_carbon')
            rate_carbon_offset = st.number_input(t('econ_input_carbon_rate'), min_value=0.0, value=float(st.session_state.get('rate_carbon_offset', default_rate_carbon_offset)), step=0.1, key='rate_carbon_offset')
            
        with st.expander(f"📈 {t('econ_section_params')}", expanded=True):
            col_pr1, col_pr2 = st.columns(2)
            with col_pr1:
                discount_rate = st.number_input(t('econ_input_discount'), min_value=0.0, max_value=50.0, value=float(st.session_state.get('discount_rate', default_discount)), step=0.5, key='discount_rate')
                annual_days = st.number_input(t('econ_input_days'), min_value=50, max_value=365, value=int(st.session_state.get('annual_days', default_days)), step=10, key='annual_days')
                tax_rate = st.number_input(t('econ_input_income_tax'), min_value=0.0, max_value=80.0, value=float(st.session_state.get('tax_rate', default_tax_rate)), step=1.0, key='tax_rate')
            with col_pr2:
                project_lifetime = st.number_input(t('econ_input_lifetime'), min_value=1, max_value=30, value=int(st.session_state.get('project_lifetime', default_lifetime)), step=1, key='project_lifetime')
                motor_power = st.number_input(t('econ_input_motor_kw'), min_value=0.0, value=float(st.session_state.get('motor_power', default_motor_kw)), step=1.0, key='motor_power')
                inflation_rate = st.number_input(t('econ_input_inflation'), min_value=0.0, max_value=50.0, value=float(st.session_state.get('inflation_rate', default_inflation_rate)), step=0.5, key='inflation_rate')
            
            # Special batch variables
            if not is_continuous:
                batch_turnaround_h = st.slider("Cooldown & Loading time per Batch (h) / Tiempo de enfriado y carga por Lote (h)", 0.25, 4.0, float(st.session_state.get('batch_turnaround_h', 1.0)), 0.25, key='batch_turnaround_h')
            else:
                batch_turnaround_h = 1.0

    total_capex = capex_equip + capex_install + capex_civil + capex_piping_elec + capex_eng + capex_permits + capex_cont

    # ----------------------------------------------------
    # CORE COMPUTATIONS PREPARATION
    # ----------------------------------------------------
    sludge_density = float(st.session_state.get('sludge_density', 900.0))
    oil_density = float(st.session_state.get('bio_oil_density', 750.0))
    gas_density = 1.15
    
    if is_continuous:
        annual_hours = annual_days * 24.0
        batches_per_year = 0.0
        
        sludge_treated_kg = summary['feed_rate_kgh'] * annual_hours
        oil_produced_kg = summary['oil_yield_kgh'] * annual_hours
        char_produced_kg = summary['char_yield_kgh'] * annual_hours
        gas_produced_kg = summary['gas_yield_kgh'] * annual_hours
        
        fuel_consumed_gal = summary['waste_oil_consumed_galh'] * annual_hours
        elec_consumed_kwh = motor_power * annual_hours
        generator_fuel_consumed_gal = gen_diesel_rate * annual_hours
    else:
        t_heat_min = (solver_inputs['temp_hold_c'] - solver_inputs['temp_start_c']) / solver_inputs['heating_rate_cmin']
        t_hold_min = solver_inputs['hold_time_min']
        t_cycle_min = t_heat_min + t_hold_min
        t_cycle_hours = (t_cycle_min / 60.0) + batch_turnaround_h
        
        annual_hours = annual_days * 24.0
        batches_per_year = np.floor(annual_hours / t_cycle_hours) if t_cycle_hours > 0 else 0.0
        
        sludge_treated_kg = summary['batch_load_kg'] * batches_per_year
        oil_produced_kg = summary['oil_yield_kg'] * batches_per_year
        char_produced_kg = summary['char_yield_kg'] * batches_per_year
        gas_produced_kg = summary['gas_yield_kg'] * batches_per_year
        
        fuel_consumed_gal = summary['waste_oil_consumed_gal'] * batches_per_year
        elec_consumed_kwh = motor_power * (t_cycle_min / 60.0) * batches_per_year
        generator_fuel_consumed_gal = gen_diesel_batch * batches_per_year
        
    # Volumetric Conversions for Liquids & Gases
    sludge_treated_gal = (sludge_treated_kg / sludge_density) * 264.172
    oil_produced_gal = (oil_produced_kg / oil_density) * 264.172
    gas_produced_m3 = gas_produced_kg / gas_density

    # ----------------------------------------------------
    # RUN DETAILED FINANCIAL MODEL (BIO-CHAR IN KG)
    # ----------------------------------------------------
    m = run_financial_model(
        total_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
        fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
        opex_handling, opex_fuel, opex_electricity, opex_aux_utilities, price_generator_fuel,
        opex_labor, opex_maint, opex_insurance_tax,
        opex_tipping, price_oil, price_char, price_gas, price_carbon, rate_carbon_offset,
        discount_rate, project_lifetime, tax_rate, inflation_rate
    )
        
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
        irr_val_str = f"{m['irr']:.2f}%" if m['irr'] is not None else "N/A"
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
        render_kpi_card(
            t('econ_metric_breakeven_tipping'),
            f"{curr_sym}{m['breakeven_tipping']:.4f}/gal",
            "Tipping fee for NPV=0 / Tarifa equilibrio",
            is_positive=(m['breakeven_tipping'] < opex_tipping)
        )

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
            font=dict(size=14, color="#f8fafc")
        ),
        xaxis=dict(
            title="Project Year / Año del Proyecto",
            tickmode='linear',
            tick0=0,
            dtick=1,
            gridcolor="#334155",
            tickfont=dict(color="#94a3b8")
        ),
        yaxis=dict(
            title=f"Cumulative Balance / Balance Acumulado ({curr_sym})",
            gridcolor="#334155",
            tickfont=dict(color="#94a3b8")
        ),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5,
            font=dict(color="#94a3b8", size=10)
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        height=380
    )
    st.plotly_chart(fig, use_container_width=True)

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
            elec_per_batch = motor_power * (t_cycle_min / 60.0)
            gen_diesel_per_batch = elec_per_batch * 0.08
            burner_fuel_per_batch = summary['waste_oil_consumed_gal']
            if lang == 'es':
                st.info(f"⏱️ **Detalles del Ciclo por Lote:**\n"
                        f"- Tiempo de calentamiento: `{t_heat_min:.1f} min` | Retención: `{t_hold_min:.1f} min` | Enfriado/Carga: `{batch_turnaround_h*60:.0f} min` \n"
                        f"- Duración del lote: `{t_cycle_hours:.2f} horas` \n"
                        f"- Capacidad de procesamiento anual: `{batches_per_year:.0f} lotes/año` a `{annual_days} días/año` de operación.\n"
                        f"- **Consumo por lote:** Diésel planta eléctrica: `{gen_diesel_per_batch:.2f} gal` | Combustible quemadores: `{burner_fuel_per_batch:.2f} gal`")
            else:
                st.info(f"⏱️ **Batch Timeline Details:**\n"
                        f"- Heating time: `{t_heat_min:.1f} min` | Holding time: `{t_hold_min:.1f} min` | Unload/Cool: `{batch_turnaround_h*60:.0f} min` \n"
                        f"- Total single batch duration: `{t_cycle_hours:.2f} hours` \n"
                        f"- Annual throughput capacity: `{batches_per_year:.0f} batches/year` at `{annual_days} days/year` operation.\n"
                        f"- **Consumption per batch:** Generator diesel: `{gen_diesel_per_batch:.2f} gal` | Burner fuel: `{burner_fuel_per_batch:.2f} gal`")
        else:
            gen_diesel_per_hour = motor_power * 0.08
            burner_fuel_per_hour = summary['waste_oil_consumed_galh']
            if lang == 'es':
                st.info(f"⚡ **Detalles de la Operación Continua:**\n"
                        f"- Horas de operación al año: `{annual_hours:.0f} horas` ({annual_days} días/año × 24h).\n"
                        f"- **Consumo horario:** Diésel planta eléctrica: `{gen_diesel_per_hour:.2f} gal/h` | Combustible quemadores: `{burner_fuel_per_hour:.2f} gal/h`")
            else:
                st.info(f"⚡ **Continuous Operation Details:**\n"
                        f"- Operating hours per year: `{annual_hours:.0f} hours` ({annual_days} days/year × 24h).\n"
                        f"- **Consumption per hour:** Generator diesel: `{gen_diesel_per_hour:.2f} gal/h` | Burner fuel: `{burner_fuel_per_hour:.2f} gal/h`")
            
    with col_table_r:
        st.markdown(f"##### 💵 Cash Flow Breakdown / Desglose de Caja")
        
        financial_breakdown = {
            "Category / Categoría": [
                "Total CAPEX (Inversión Inicial)",
                "Disposal Tipping Fees Revenue (Disposición)",
                "Bio-Oil Sales Revenue (Venta Bio-Crudo)",
                "Bio-Char Sales Revenue (Venta Bio-Carbón)",
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
            "Bio-Oil Sales / Venta Bio-Crudo (%)": [100.0] * 12,
            "Bio-Char Sales / Venta Bio-Carbón (%)": [100.0] * 12,
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
            "Bio-Oil Sales / Venta Bio-Crudo (%)": st.column_config.NumberColumn("Bio-Oil Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
            "Bio-Char Sales / Venta Bio-Carbón (%)": st.column_config.NumberColumn("Bio-Char Sales (%)", min_value=0.0, max_value=100.0, step=5.0),
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
        o_pct = row["Bio-Oil Sales / Venta Bio-Crudo (%)"]
        c_pct = row["Bio-Char Sales / Venta Bio-Carbón (%)"]
        g_pct = row["Bio-Syngas Sales / Venta Syngas (%)"] if "Bio-Syngas Sales / Venta Syngas (%)" in row else row.get("Syngas Sales / Venta Syngas (%)", 100.0)
        
        # Calculate monthly production and utilities
        if is_continuous:
            sludge_kg = summary['feed_rate_kgh'] * 24.0 * days
            oil_kg = summary['oil_yield_kgh'] * 24.0 * days
            char_kg = summary['char_yield_kgh'] * 24.0 * days
            gas_kg = summary['gas_yield_kgh'] * 24.0 * days
            
            fuel_gal = summary['waste_oil_consumed_galh'] * 24.0 * days
            elec_kwh = motor_power * 24.0 * days
            diesel_gal = gen_diesel_rate * 24.0 * days
        else:
            batches = np.floor((days * 24.0) / t_cycle_hours) if t_cycle_hours > 0 else 0.0
            sludge_kg = summary['batch_load_kg'] * batches
            oil_kg = summary['oil_yield_kg'] * batches
            char_kg = summary['char_yield_kg'] * batches
            gas_kg = summary['gas_yield_kg'] * batches
            
            fuel_gal = summary['waste_oil_consumed_gal'] * batches
            elec_kwh = motor_power * (t_cycle_min / 60.0) * batches
            diesel_gal = gen_diesel_batch * batches
            
        # Volumetric conversion for liquids & gases; mass for bio-char
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
        rev_carb = ((char_prod_kg * rate_carbon_offset) / 1000.0) * price_carbon
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
        "Bio-Oil Produced (gal)": m_oil_prod,
        "Bio-Oil Sold (gal)": m_oil_sold,
        "Bio-Oil Inventory (gal)": m_oil_inv,
        "Bio-Char Produced (kg)": m_char_prod,
        "Bio-Char Sold (kg)": m_char_sold,
        "Bio-Char Inventory (kg)": m_char_inv,
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
    df_monthly_disp["Bio-Oil Produced (gal)"] = df_monthly_disp["Bio-Oil Produced (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Bio-Oil Sold (gal)"] = df_monthly_disp["Bio-Oil Sold (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Bio-Oil Inventory (gal)"] = df_monthly_disp["Bio-Oil Inventory (gal)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Bio-Char Produced (kg)"] = df_monthly_disp["Bio-Char Produced (kg)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Bio-Char Sold (kg)"] = df_monthly_disp["Bio-Char Sold (kg)"].map(lambda x: f"{x:,.1f}")
    df_monthly_disp["Bio-Char Inventory (kg)"] = df_monthly_disp["Bio-Char Inventory (kg)"].map(lambda x: f"{x:,.1f}")
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
                font=dict(size=14, color="#f8fafc")
            ),
            xaxis=dict(
                title="Month / Mes",
                gridcolor="#334155",
                tickfont=dict(color="#94a3b8")
            ),
            yaxis=dict(
                title=f"Amount / Monto ({curr_sym})",
                gridcolor="#334155",
                tickfont=dict(color="#94a3b8")
            ),
            barmode='group',
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5,
                font=dict(color="#94a3b8", size=10)
            ),
            margin=dict(l=50, r=40, t=40, b=50),
            height=400
        )
        st.plotly_chart(fig_m_fin, use_container_width=True)

    with tab_m_vol:
        fig_m_vol = go.Figure()

        # Bio-Oil Production vs Sales vs Inventory
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
            marker_color="#a7f3d0",
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

        # Bio-Char Production vs Sales vs Inventory (in kg)
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
                text=f"{t('econ_monthly_tab_volumes')} - Bio-Oil (gal) & Bio-Char (kg) Dynamics",
                font=dict(size=14, color="#f8fafc")
            ),
            xaxis=dict(
                title="Month / Mes",
                gridcolor="#334155",
                tickfont=dict(color="#94a3b8")
            ),
            yaxis=dict(
                title="Quantity / Cantidad (gal / kg)",
                gridcolor="#334155",
                tickfont=dict(color="#94a3b8"),
                tickformat=",~f"
            ),
            barmode='group',
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5,
                font=dict(color="#94a3b8", size=9)
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
            discount_rate, project_lifetime, tax_rate, inflation_rate
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
    fig_sens.add_vline(x=base_npv, line_width=2, line_dash="dash", line_color="#f8fafc", annotation_text=f"Base Case NPV: {curr_sym}{base_npv:,.2f}")
    
    fig_sens.update_layout(
        title=dict(
            text=f"NPV Sensitivity Tornado Chart ({curr_sym})",
            font=dict(size=14, color="#f8fafc")
        ),
        xaxis=dict(
            title=f"Net Present Value (NPV) ({curr_sym})",
            gridcolor="#334155",
            tickfont=dict(color="#94a3b8")
        ),
        yaxis=dict(
            tickfont=dict(color="#94a3b8")
        ),
        barmode='overlay',
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(color="#94a3b8", size=10)
        ),
        margin=dict(l=120, r=40, t=40, b=40),
        height=350
    )
    
    st.plotly_chart(fig_sens, use_container_width=True)

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
        t('econ_sustainability_desc') if 'econ_sustainability_desc' in TRANSLATIONS[lang] 
        else "Evaluate the carbon sequestration potential and environmental benefits of industrial pyrolysis sludge treatment."
    )
    st.markdown("---")
    
    is_continuous = (st.session_state.get('mode_option', 'Continuous Operation') == "Continuous Operation")
    annual_days = st.session_state.get('annual_days', 246)
    
    # Financial keys & currency retrieval (Standardized in DOP - RD$)
    curr_sym = "RD$"
    price_carbon = st.session_state.get('price_carbon', 1200.0)
    rate_carbon_offset = st.session_state.get('rate_carbon_offset', 2.2)
    
    if is_continuous:
        annual_hours = annual_days * 24.0
        char_produced_kg = summary['char_yield_kgh'] * annual_hours
    else:
        t_heat_min = (solver_inputs.get('temp_hold_c', 400.0) - solver_inputs.get('temp_start_c', 25.0)) / solver_inputs.get('heating_rate_cmin', 1.0)
        t_hold_min = solver_inputs.get('hold_time_min', 60.0)
        t_cycle_min = t_heat_min + t_hold_min
        batch_turnaround_h = st.session_state.get('batch_turnaround_h', 1.0)
        t_cycle_hours = (t_cycle_min / 60.0) + batch_turnaround_h
        batches_per_year = np.floor((annual_days * 24.0) / t_cycle_hours) if t_cycle_hours > 0 else 0.0
        char_produced_kg = summary['char_yield_kg'] * batches_per_year
        
    co2_tons = (char_produced_kg * rate_carbon_offset) / 1000.0
    trees_planted = co2_tons / 0.022
    cars_removed = co2_tons / 4.6
    
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
        
    # Visual green impact description
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1e3a2f 0%, #064e3b 100%);
        padding: 22px;
        border-radius: 12px;
        border: 1px solid #047857;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-top: 20px;
        color: #e6f4ea;
    ">
        <h4 style="margin: 0 0 10px 0; color: #a7f3d0; font-size: 16px; font-weight: 600;">🌿 Bio-Char & Carbon Capture Sequestration</h4>
        <p style="margin: 0; font-size: 13.5px; line-height: 1.6; color: #d1fae5;">
            Pyrolysis converts organic waste sludge into bio-char, locking carbon in a highly stable solid form. 
            Unlike decomposition, which releases CO2 and methane, bio-char stores carbon safely in soils for hundreds of years.
            Each kilogram of bio-char prevents approx {rate_carbon_offset:.2f} kg of atmospheric CO2 equivalents from warming the planet.
        </p>
    </div>
    """, unsafe_allow_html=True)
