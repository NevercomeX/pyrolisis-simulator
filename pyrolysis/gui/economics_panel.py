import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pyrolysis import TRANSLATIONS

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'English')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def solve_irr(capex, net_cash_flow, lifetime):
    """
    Calculates the Internal Rate of Return (IRR) using binary search.
    Returns the percentage or None if it cannot be solved.
    """
    if net_cash_flow <= 0:
        return None
    
    # If the sum of all undiscounted cash flows is less than initial investment,
    # the IRR is negative. We allow searching down to -99%.
    def npv_func(r):
        if abs(r) < 1e-8:
            return -capex + net_cash_flow * lifetime
        return -capex + net_cash_flow * (1.0 - (1.0 + r)**(-lifetime)) / r
    
    low = -0.99
    high = 10.0  # Cap at 1000%
    
    # Check if a solution exists in the range
    val_low = npv_func(low)
    val_high = npv_func(high)
    
    if val_low < 0:
        # Even at -99% discount, NPV is negative
        return None
    if val_high > 0:
        # Even at 1000% discount, NPV is positive (unusually profitable)
        return high * 100.0

    # Binary search to find the root
    for _ in range(100):
        mid = (low + high) / 2.0
        val = npv_func(mid)
        if abs(val) < 1e-5:
            return mid * 100.0
        if val > 0:
            low = mid
        else:
            high = mid
            
    return ((low + high) / 2.0) * 100.0

def render_kpi_card(title, value_str, subtitle=None, is_positive=True):
    """Renders a premium visual card for financial KPIs."""
    color = "#10b981" if is_positive else "#ef4444"
    border_color = "#1e293b"
    text_color_sub = "#94a3b8"
    
    html = f"""
    <div style="
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        text-align: center;
        margin-bottom: 15px;
    ">
        <h4 style="color: {text_color_sub}; margin: 0; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;">{title}</h4>
        <h2 style="color: {color}; margin: 8px 0; font-size: 26px; font-weight: 700;">{value_str}</h2>
        {f'<p style="color: #64748b; margin: 0; font-size: 11px;">{subtitle}</p>' if subtitle else ''}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_economics_tab(mode_option, results, summary, solver_inputs):
    """Renders the interactive Economic Viability tab."""
    lang = get_lang()
    
    st.markdown(f"### 💸 {t('econ_title')}")
    st.markdown(t('econ_desc'))
    st.markdown("---")
    
    # Define default values based on operational mode
    is_continuous = (mode_option == "Continuous Operation")
    default_equip = 150000.0 if is_continuous else 80000.0
    default_install = 40000.0 if is_continuous else 20000.0
    default_permits = 15000.0
    default_contingency = 10000.0
    
    default_handling = 10.0
    default_tipping = 40.0
    default_fuel_price = 3.0
    default_gen_fuel_price = 3.0
    default_labor = 50000.0
    default_maint_rate = 3.0
    
    default_oil_price = 0.40
    default_char_price = 0.15
    default_gas_price = 0.05
    
    default_discount = 8.0
    default_lifetime = 10
    default_days = 246
    default_motor_kw = 15.0 if is_continuous else 7.5

    # Precalculate default generator consumption based on mode
    if is_continuous:
        default_gen_consumption = float(default_motor_kw * 0.08)
    else:
        t_heat_min = (solver_inputs.get('temp_hold_c', 400.0) - solver_inputs.get('temp_start_c', 25.0)) / solver_inputs.get('heating_rate_cmin', 1.0)
        t_hold_min = solver_inputs.get('hold_time_min', 60.0)
        t_cycle_min = t_heat_min + t_hold_min
        default_gen_consumption = float(default_motor_kw * (t_cycle_min / 60.0) * 0.08)
    
    # Columns for parameters (using expanders to keep clean)
    col_param_l, col_param_r = st.columns(2)
    
    with col_param_l:
        with st.expander(f"🏗️ {t('econ_section_capex')}", expanded=True):
            capex_equip = st.number_input(t('econ_input_reactor_cost'), min_value=0.0, value=float(st.session_state.get('capex_equip', default_equip)), step=5000.0, key='capex_equip')
            capex_install = st.number_input(t('econ_input_installation'), min_value=0.0, value=float(st.session_state.get('capex_install', default_install)), step=2000.0, key='capex_install')
            capex_permits = st.number_input(t('econ_input_permits'), min_value=0.0, value=float(st.session_state.get('capex_permits', default_permits)), step=1000.0, key='capex_permits')
            capex_cont = st.number_input(t('econ_input_contingency'), min_value=0.0, value=float(st.session_state.get('capex_cont', default_contingency)), step=1000.0, key='capex_cont')
            
        with st.expander(f"⚙️ {t('econ_section_opex')}", expanded=True):
            opex_handling = st.number_input(t('econ_input_handling'), min_value=0.0, value=float(st.session_state.get('opex_handling', default_handling)), step=1.0, key='opex_handling')
            opex_fuel = st.number_input(t('econ_input_fuel'), min_value=0.0, value=float(st.session_state.get('opex_fuel', default_fuel_price)), step=0.1, key='opex_fuel')
            price_generator_fuel = st.number_input(t('econ_input_gen_fuel'), min_value=0.0, value=float(st.session_state.get('price_generator_fuel', default_gen_fuel_price)), step=0.1, key='price_generator_fuel')
            if is_continuous:
                gen_diesel_rate = st.number_input(t('econ_input_gen_fuel_rate'), min_value=0.0, value=float(st.session_state.get('gen_diesel_rate', default_gen_consumption)), step=0.1, key='gen_diesel_rate')
            else:
                gen_diesel_batch = st.number_input(t('econ_input_gen_fuel_batch'), min_value=0.0, value=float(st.session_state.get('gen_diesel_batch', default_gen_consumption)), step=0.5, key='gen_diesel_batch')
            opex_labor = st.number_input(t('econ_input_labor'), min_value=0.0, value=float(st.session_state.get('opex_labor', default_labor)), step=5000.0, key='opex_labor')
            opex_maint = st.number_input(t('econ_input_maintenance'), min_value=0.0, max_value=25.0, value=float(st.session_state.get('opex_maint', default_maint_rate)), step=0.5, key='opex_maint')
            
    with col_param_r:
        with st.expander(f"🏷️ {t('econ_section_revenue')}", expanded=True):
            opex_tipping = st.number_input(t('econ_input_tipping'), min_value=0.0, value=float(st.session_state.get('opex_tipping', default_tipping)), step=5.0, key='opex_tipping')
            price_oil = st.number_input(t('price_bio_oil') if 'price_bio_oil' in TRANSLATIONS[lang] else t('econ_input_price_oil'), min_value=0.0, value=float(st.session_state.get('price_oil', default_oil_price)), step=0.05, key='price_oil')
            price_char = st.number_input(t('price_bio_char') if 'price_bio_char' in TRANSLATIONS[lang] else t('econ_input_price_char'), min_value=0.0, value=float(st.session_state.get('price_char', default_char_price)), step=0.02, key='price_char')
            price_gas = st.number_input(t('price_syngas') if 'price_syngas' in TRANSLATIONS[lang] else t('econ_input_price_gas'), min_value=0.0, value=float(st.session_state.get('price_gas', default_gas_price)), step=0.01, key='price_gas')
            
        with st.expander(f"📈 {t('econ_section_params')}", expanded=True):
            discount_rate = st.number_input(t('econ_input_discount'), min_value=0.0, max_value=50.0, value=float(st.session_state.get('discount_rate', default_discount)), step=0.5, key='discount_rate')
            project_lifetime = st.number_input(t('econ_input_lifetime'), min_value=1, max_value=30, value=int(st.session_state.get('project_lifetime', default_lifetime)), step=1, key='project_lifetime')
            annual_days = st.number_input(t('econ_input_days'), min_value=50, max_value=365, value=int(st.session_state.get('annual_days', default_days)), step=10, key='annual_days')
            motor_power = st.number_input(t('econ_input_motor_kw'), min_value=0.0, value=float(st.session_state.get('motor_power', default_motor_kw)), step=1.0, key='motor_power')
            
            # Special batch variables
            if not is_continuous:
                batch_turnaround_h = st.slider("Cooldown & Loading time per Batch (h) / Tiempo de enfriado y carga por Lote (h)", 0.25, 4.0, float(st.session_state.get('batch_turnaround_h', 1.0)), 0.25, key='batch_turnaround_h')
            else:
                batch_turnaround_h = 1.0

    # ----------------------------------------------------
    # FINANCIAL COMPUTATIONS
    # ----------------------------------------------------
    total_capex = capex_equip + capex_install + capex_permits + capex_cont
    
    if is_continuous:
        annual_hours = annual_days * 24.0
        batches_per_year = 0.0
        
        # Annual operational rates
        sludge_treated_kg = summary['feed_rate_kgh'] * annual_hours
        oil_produced_kg = summary['oil_yield_kgh'] * annual_hours
        char_produced_kg = summary['char_yield_kgh'] * annual_hours
        gas_produced_kg = summary['gas_yield_kgh'] * annual_hours
        fuel_consumed_gal = summary['waste_oil_consumed_galh'] * annual_hours
        elec_consumed_kwh = motor_power * annual_hours
        generator_fuel_consumed_gal = gen_diesel_rate * annual_hours
    else:
        # Calculate single batch duration
        # time to heat up: (T_hold - T_start) / heating_rate
        t_heat_min = (solver_inputs['temp_hold_c'] - solver_inputs['temp_start_c']) / solver_inputs['heating_rate_cmin']
        t_hold_min = solver_inputs['hold_time_min']
        t_cycle_min = t_heat_min + t_hold_min
        t_cycle_hours = (t_cycle_min / 60.0) + batch_turnaround_h
        
        annual_hours = annual_days * 24.0
        batches_per_year = np.floor(annual_hours / t_cycle_hours)
        
        # Annual operational rates
        sludge_treated_kg = summary['batch_load_kg'] * batches_per_year
        oil_produced_kg = summary['oil_yield_kg'] * batches_per_year
        char_produced_kg = summary['char_yield_kg'] * batches_per_year
        gas_produced_kg = summary['gas_yield_kg'] * batches_per_year
        fuel_consumed_gal = summary['waste_oil_consumed_gal'] * batches_per_year
        elec_consumed_kwh = motor_power * (t_cycle_min / 60.0) * batches_per_year
        generator_fuel_consumed_gal = gen_diesel_batch * batches_per_year
        
    # Convert sludge treated to metric tons (1 ton = 1000 kg)
    sludge_treated_ton = sludge_treated_kg / 1000.0
    
    # ----------------------------------------------------
    # REVENUE AND OPEX CALCULATIONS
    # ----------------------------------------------------
    rev_tipping = sludge_treated_ton * opex_tipping
    rev_oil = oil_produced_kg * price_oil
    rev_char = char_produced_kg * price_char
    rev_gas = gas_produced_kg * price_gas
    total_revenue = rev_tipping + rev_oil + rev_char + rev_gas
    
    cost_handling = sludge_treated_ton * opex_handling
    cost_fuel = fuel_consumed_gal * opex_fuel
    cost_generator_fuel = generator_fuel_consumed_gal * price_generator_fuel
    cost_maintenance = total_capex * (opex_maint / 100.0)
    cost_labor = opex_labor
    total_opex = cost_handling + cost_fuel + cost_generator_fuel + cost_maintenance + cost_labor
    
    net_cash_flow = total_revenue - total_opex
    
    # Discounted cash flow computations
    r = discount_rate / 100.0
    if r > 0:
        discount_factor = (1.0 - (1.0 + r)**(-project_lifetime)) / r
        npv = -total_capex + net_cash_flow * discount_factor
    else:
        npv = -total_capex + net_cash_flow * project_lifetime
        
    irr = solve_irr(total_capex, net_cash_flow, project_lifetime)
    
    if net_cash_flow > 0:
        payback = total_capex / net_cash_flow
    else:
        payback = float('inf')
        
    # ----------------------------------------------------
    # RENDERING FINANCIAL KPI CARDS
    # ----------------------------------------------------
    st.markdown(f"#### 📊 {t('econ_metrics')}")
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    
    with col_kpi1:
        npv_label = t('econ_metric_npv')
        npv_sub = "Discounted / Descontado"
        render_kpi_card(npv_label, f"${npv:,.2f}", npv_sub, is_positive=(npv > 0))
        
    with col_kpi2:
        irr_label = t('econ_metric_irr')
        irr_val_str = f"{irr:.2f}%" if irr is not None else "N/A"
        irr_sub = "Internal Profitability / Rentabilidad"
        render_kpi_card(irr_label, irr_val_str, irr_sub, is_positive=(irr is not None and irr > discount_rate))
        
    with col_kpi3:
        payback_label = t('econ_metric_payback')
        payback_val_str = f"{payback:.2f} {t('econ_input_lifetime').split(' ')[-1].lower() if 'econ_input_lifetime' in TRANSLATIONS[lang] else 'Years'}" if payback != float('inf') else "N/A"
        payback_sub = "Investment Return / Retorno"
        render_kpi_card(payback_label, payback_val_str, payback_sub, is_positive=(payback < project_lifetime))
        
    with col_kpi4:
        profit_label = t('econ_metric_profit')
        render_kpi_card(profit_label, f"${net_cash_flow:,.2f}/yr", "Net Cash Flow / Flujo Neto", is_positive=(net_cash_flow > 0))
        
    # ----------------------------------------------------
    # RENDERING DATA TABLES AND BREAKDOWNS
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
                t('econ_annual_gen_fuel')
            ],
            t('econ_table_val'): [
                sludge_treated_ton,
                oil_produced_kg,
                char_produced_kg,
                gas_produced_kg,
                fuel_consumed_gal,
                generator_fuel_consumed_gal
            ],
            t('econ_table_units'): [
                "tons/yr",
                "kg/yr",
                "kg/yr",
                "kg/yr",
                "gal/yr",
                "gal/yr"
            ]
        }
        
        # Translate header titles based on language and format values to 2 decimals
        df_summary = pd.DataFrame(summary_data)
        df_summary[t('econ_table_val')] = df_summary[t('econ_table_val')].map(lambda x: f"{x:,.2f}")
        st.table(df_summary)
        
        # Display Batch Info
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
        
        # Financial entries table
        financial_breakdown = {
            "Category / Categoría": [
                "Total CAPEX (Inversión Inicial)",
                "Disposal Tipping Fees Revenue (Ingreso Disposición)",
                "Bio-Oil Sales Revenue (Venta de Bio-Crudo)",
                "Bio-Char Sales Revenue (Venta de Bio-Carbón)",
                "Syngas Sales Revenue (Venta de Syngas)",
                "Feedstock Handling Costs (Costo Manejo Lodos)",
                "Burner Fuel Consumption Costs (Combustible)",
                "Generator Diesel Fuel Costs (Diésel Planta)",
                "Annual Labor & Operators (Mano de Obra)",
                "Annual Maintenance Cost (Mantenimiento CAPEX)"
            ],
            "Annual Cash Flow / Flujo Anual ($)": [
                -total_capex,
                rev_tipping,
                rev_oil,
                rev_char,
                rev_gas,
                -cost_handling,
                -cost_fuel,
                -cost_generator_fuel,
                -cost_labor,
                -cost_maintenance
            ]
        }
        df_financial = pd.DataFrame(financial_breakdown)
        # Format cash flows for table
        df_financial_disp = df_financial.copy()
        df_financial_disp["Annual Cash Flow / Flujo Anual ($)"] = df_financial_disp["Annual Cash Flow / Flujo Anual ($)"].map(lambda x: f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}")
        st.table(df_financial_disp)

    # ----------------------------------------------------
    # PROJECTION CHART (CUMULATIVE CASH FLOW)
    # ----------------------------------------------------
    st.markdown(f"##### 📈 {t('econ_metric_cashflow')}")
    
    years = list(range(0, int(project_lifetime) + 1))
    
    # Calculate cumulative undiscounted and discounted cash flows
    cum_cash = [-total_capex]
    cum_discounted = [-total_capex]
    
    for yr in range(1, int(project_lifetime) + 1):
        cum_cash.append(cum_cash[-1] + net_cash_flow)
        discounted_flow = net_cash_flow / ((1.0 + r)**yr)
        cum_discounted.append(cum_discounted[-1] + discounted_flow)
        
    # Generate plotly chart
    fig = go.Figure()
    
    # Add Undiscounted Cash Flow Bar
    fig.add_trace(go.Bar(
        x=years,
        y=cum_cash,
        name="Undiscounted Cumulative Cash Flow / Flujo Acumulado",
        marker_color="#3b82f6",
        opacity=0.85
    ))
    
    # Add Discounted Cash Flow Line
    fig.add_trace(go.Scatter(
        x=years,
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
            title="Cumulative Balance / Balance Acumulado ($)",
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
