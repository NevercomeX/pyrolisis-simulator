import streamlit as st
import numpy as np
import pandas as pd
from pyrolysis.docx_generator import PYTHON_DOCX_AVAILABLE
from pyrolysis.pdf_generator import REPORTLAB_AVAILABLE
from .utils import get_lang, t, product_volumes, sludge_gal

# ==============================================================================
# CONTROL DE GENERACIÓN DE REPORTES (FEATURE FLAG)
# Cambie este valor a True si desea habilitar la generación y descarga de
# reportes ejecutivos/técnicos (PDF de Tesis y Word .docx).
# Por defecto está en False: la opción de generar reportes queda eliminada de la interfaz.
# ==============================================================================
ENABLE_REPORTS = False

# Properties of the analytic energy balance (balances tab)
CP_CHAR_J_KGK = 1000.0
CP_GAS_J_KGK = 1500.0
CP_WATER_J_KGK = 4184.0
CP_STEAM_J_KGK = 2000.0
DH_PYRO_J_KG = 700000.0       # pyrolysis cracking enthalpy
DH_EVAP_J_KG = 2256000.0      # latent heat of water at 100 °C
J_PER_KWH = 3.6e6


def _pct(part, total):
    """Share of total in %, guarded against a zero total."""
    return part / max(0.001, total) * 100.0

def render_properties_tab(current_feed, batch_load_kg, feed_option):
    """Renders the feedstock properties tab content."""
    lang = get_lang()
    col_prop_l, col_prop_r = st.columns(2)
    
    with col_prop_l:
        st.subheader(t("analysis_chem_comp"))
        load_val = batch_load_kg
        load_val_gal = sludge_gal(load_val)
        wt_pcts = [current_feed.moisture, current_feed.volatile, current_feed.fixed_carbon, current_feed.ash]
        comp_df = pd.DataFrame({
            t("analysis_component"): [t("analysis_moisture_name"), t("analysis_volatiles_name"), t("analysis_char_name"), t("analysis_ash_name")],
            t("analysis_wt_pct"): wt_pcts,
            t("analysis_input_load").format("kg"): [load_val * pct / 100.0 for pct in wt_pcts],
            t("analysis_input_load").format("gal"): [load_val_gal * pct / 100.0 for pct in wt_pcts]
        })
        st.table(comp_df)
        
    with col_prop_r:
        st.subheader(t("analysis_kinetics"))
        feed_name_display = current_feed.name
        if current_feed.name == 'Custom Sludge':
            feed_name_display = t('feed_custom') if lang == 'es' else 'Custom Sludge'
        st.markdown(f"**{t('analysis_feedstock_label')}**: `{feed_name_display}`")
        st.markdown(f"**{t('analysis_activation_energy')}**: `{current_feed.E_a / 1000:.1f} kJ/mol`")
        st.markdown(f"**{t('analysis_pre_exponential')}**: `{current_feed.A:.2e} s⁻¹`")
        yields_df = pd.DataFrame({
            t("analysis_prod_fraction"): [t("analysis_bio_oil_name"), t("analysis_syngas_name"), t("analysis_char_res_name")],
            t("analysis_frac_wt"): [current_feed.yield_oil, current_feed.yield_gas, current_feed.yield_char]
        })
        st.table(yields_df)

    # ASTM Standards Characterization Section for PROENERGETICOS Pyrolysis oil
    st.markdown("---")
    st.markdown("### 🔬 Caracterización fisicoquímica del aceite pirolítico")
    st.warning(
        "El simulador no predice propiedades del aceite (PCS, viscosidad, °API, agua). "
        "Las correlaciones anteriores no tenían respaldo y no coincidían con el laboratorio. "
        "Use los resultados del ensayo (ASTM D240, D445, D4052, D95)."
    )

def render_balances_tab(current_feed, results, summary, batch_load_kg, feed_option):
    """Renders the mass and energy balances tab content."""
    feed_name_display = t("feed_custom") if feed_option == "Custom Feedstock" else current_feed.name
    _render_batch_balances(results, summary, batch_load_kg, feed_name_display)
    _render_kinetics_section(current_feed)


def _render_batch_balances(results, summary, batch_load_kg, feed_name_display):
    """Mass and energy balance (kg, kWh) of one batch, with the closure against the simulated burner heat."""
    lang = get_lang()
    st.markdown("### ⚖️ Mass Balance / Balance de Materia")
    load_val = batch_load_kg
    load_val_gal = sludge_gal(load_val)
    oil_gal, gas_m3, char_gal, water_gal = product_volumes(
        summary['oil_yield_kg'], summary['gas_yield_kg'], summary['char_yield_kg'], summary['water_yield_kg'])

    mass_in_df = pd.DataFrame({
        t("analysis_component", "Component"): [feed_name_display],
        t("analysis_wt_pct", "wt%"): [100.0],
        "Load / Carga (kg)": [load_val],
        "Load / Carga (gal)": [load_val_gal]
    })
        
    mass_out_df = pd.DataFrame({
        t("analysis_component", "Component"): [
            t("analysis_bio_oil_name", "Pyrolysis oil"), 
            t("analysis_syngas_name", "Syngas"), 
            t("analysis_char_res_name", "Char"), 
            t("water_vapor_metric", "Water Vapor (Steam)")
        ],
        t("analysis_wt_pct", "wt%"): [
            summary['oil_yield_pct'],
            summary['gas_yield_pct'],
            summary['char_yield_pct'],
            summary['water_yield_pct']
        ],
        "Mass / Masa (kg)": [
            summary['oil_yield_kg'],
            summary['gas_yield_kg'],
            summary['char_yield_kg'],
            summary['water_yield_kg']
        ],
        "Volumen / Volume": [
            f"{oil_gal:.1f} gal",
            f"{gas_m3:.1f} m³",
            f"{char_gal:.1f} gal",
            f"{water_gal:.1f} gal"
        ]
    })
        
    m_col_l, m_col_r = st.columns(2)
    with m_col_l:
        st.markdown("**Inputs / Entradas:**")
        st.table(mass_in_df)
    with m_col_r:
        st.markdown("**Outputs / Salidas:**")
        st.table(mass_out_df)
            
    st.info(f"**Mass Balance Closure Error / Error de Cierre:** `{summary['mass_error_pct']:.2e} %`")
        
    if lang == 'es':
        st.markdown(r"""
        #### 📝 Ecuaciones del Balance de Materia (Lote)
        El balance de materia total en modo lote representa el inventario final acumulado frente a la carga inicial:
        $$M_{load} = M_{char} + M_{oil} + M_{gas} + M_{steam} + M_{moist, final}$$
        * **Aceite pirolítico (Pyrolysis oil)**: Acumulado a partir del rendimiento neto de lodo y craqueo secundario del vapor:
          $$M_{oil} = \int \left( dM_{\text{oil, primary}} - dM_{\text{oil, cracked}} \right)$$
        * **Gas de Síntesis (Syngas)**: Acumulado de la producción primaria y del craqueo secundario del vapor:
          $$M_{gas} = \int \left( dM_{\text{gas, primary}} + dM_{\text{oil, cracked}} \right)$$
        * **Carbón Residual (Char - Seco)**: Masa sólida remanente (carbón fijo, cenizas y volátiles residuales):
          $$M_{char} = M_{fixed\_carbon, initial} + M_{ash, initial} + M_{volatile, unreacted}$$
        * **Agua Evaporada (Steam)**: Humedad total vaporizada:
          $$M_{steam} = M_{moisture, initial} - M_{moisture, final}$$
        * **Error de Cierre de Balance**:
          $$\text{Error (\%)} = \frac{|M_{load} - M_{output\_total}|}{M_{load}} \times 100$$
        """)
    else:
        st.markdown(r"""
        #### 📝 Mass Balance Equations (Batch)
        The total batch mass balance represents the final accumulated inventory relative to the initial load:
        $$M_{load} = M_{char} + M_{oil} + M_{gas} + M_{steam} + M_{moist, final}$$
        * **Pyrolysis oil**: Accumulated from primary sludge conversion and secondary vapor cracking:
          $$M_{oil} = \int \left( dM_{\text{oil, primary}} - dM_{\text{oil, cracked}} \right)$$
        * **Syngas**: Accumulated from primary gasification and secondary vapor cracking:
          $$M_{gas} = \int \left( dM_{\text{gas, primary}} + dM_{\text{oil, cracked}} \right)$$
        * **Residual Char (Char - Dry)**: Remaining solid mass (fixed carbon, ash, and residual volatiles):
          $$M_{char} = M_{fixed\_carbon, initial} + M_{ash, initial} + M_{volatile, unreacted}$$
        * **Evaporated Water (Steam)**: Total vaporized moisture:
          $$M_{steam} = M_{moisture, initial} - M_{moisture, final}$$
        * **Ecuación Evaluada y Error de Cierre**:
          $$M_{load} = M_{char} + M_{oil} + M_{gas} + M_{steam}$$
          $${load_val:.2f}\text{{ kg}} = {summary['char_yield_kg']:.2f} + {summary['oil_yield_kg']:.2f} + {summary['gas_yield_kg']:.2f} + {summary['water_yield_kg']:.2f}\text{{ kg}}$$
          $$\text{{Error (\%)}}\ = \frac{{|M_{{load}} - M_{{output\_total}}|}}{{M_{{load}}}} \times 100 = \mathbf{{{summary['mass_error_pct']:.4f}\%}}$$
        """)
        
    st.markdown("---")
    st.markdown("### ⚡ Energy Balance / Balance de Energía")
        
    M_oil = summary['oil_yield_kg']
    M_gas = summary['gas_yield_kg']
    M_char = summary['char_yield_kg']
    M_steam = summary['water_yield_kg']
    T_start = results['T_solid'][0]
    T_hold = results['T_solid'][-1]
    dT = T_hold - T_start

    cp_oil = float(st.session_state.get('custom_cp_oil', 1800.0))

    E_char_kwh = (M_char * CP_CHAR_J_KGK * dT) / J_PER_KWH
    E_oil_sens_kwh = (M_oil * cp_oil * dT) / J_PER_KWH
    E_gas_sens_kwh = (M_gas * CP_GAS_J_KGK * dT) / J_PER_KWH
    E_rxn_kwh = ((M_oil + M_gas) * DH_PYRO_J_KG) / J_PER_KWH
    if T_hold >= 100.0:
        E_steam_kwh = (M_steam * (CP_WATER_J_KGK * (100.0 - T_start) + DH_EVAP_J_KG + CP_STEAM_J_KGK * (T_hold - 100.0))) / J_PER_KWH
    else:
        E_steam_kwh = (M_steam * (CP_WATER_J_KGK * (T_hold - T_start))) / J_PER_KWH
            
    E_total_kwh = E_char_kwh + E_oil_sens_kwh + E_gas_sens_kwh + E_rxn_kwh + E_steam_kwh
        
    energy_df = pd.DataFrame({
        "Process Stage / Etapa del Proceso": [
            "Sensible Heat of Bed Solids / Calor Sensible Char",
            "Sensible Heat Pyrolysis oil / Calor Sensible Vapores Aceite pirolítico (Líquido)",
            "Sensible Heat Syngas / Calor Sensible Gas de Síntesis (Gas)",
            "Pyrolysis Cracking Enthalpy / Reacción Química Craqueo",
            "Evaporation & Dehydration / Evaporación del Agua",
            "Total Thermal Energy Supplied / Energía Térmica Total"
        ],
        "Energy / Energía (kWh)": [
            E_char_kwh,
            E_oil_sens_kwh,
            E_gas_sens_kwh,
            E_rxn_kwh,
            E_steam_kwh,
            E_total_kwh
        ],
        "Fraction of Total / Porcentaje del Total (%)": [
            _pct(E_char_kwh, E_total_kwh),
            _pct(E_oil_sens_kwh, E_total_kwh),
            _pct(E_gas_sens_kwh, E_total_kwh),
            _pct(E_rxn_kwh, E_total_kwh),
            _pct(E_steam_kwh, E_total_kwh),
            100.0
        ]
    })
    st.table(energy_df)

    # Closure against the simulation: heat that the burners must deliver (bed + shell + losses)
    e_bed = summary.get('energy_bed_kwh', 0.0)
    e_shell = summary.get('energy_shell_kwh', 0.0)
    e_loss = summary.get('energy_loss_kwh', 0.0)
    e_sim_total = summary.get('total_energy_kwh', e_bed + e_shell + e_loss)
    bed_gap_pct = _pct(e_bed - E_total_kwh, E_total_kwh)
    st.markdown("**" + ("Cierre con la simulación: calor entregado por los quemadores" if lang == 'es' else "Closure vs. simulation: heat delivered by the burners") + "**")
    closure_df = pd.DataFrame({
        "Concept / Concepto": [
            "Bed heat (simulation) / Calor al lecho (simulación)",
            "Steel shell heating / Calentamiento del casco de acero",
            "Shell heat losses / Pérdidas de calor del casco",
            "Total heat delivered / Calor total entregado",
            "Analytic duty above / Calor analítico de la tabla anterior"
        ],
        "Energy / Energía (kWh)": [e_bed, e_shell, e_loss, e_sim_total, E_total_kwh],
        "%": [
            _pct(e_bed, e_sim_total),
            _pct(e_shell, e_sim_total),
            _pct(e_loss, e_sim_total),
            100.0,
            _pct(E_total_kwh, e_sim_total)
        ]
    })
    st.table(closure_df)
    st.caption(
        f"Calor al lecho (simulación) vs. suma analítica: desviación {bed_gap_pct:+.1f} %. La tabla analítica supone que todo el vapor "
        f"sale a T de retención (sobrestima el sobrecalentamiento del vapor); la simulación lo deja salir a la temperatura del lecho. "
        f"Combustible quemadores: {summary.get('waste_oil_consumed_gal', 0.0):.1f} gal; "
        f"syngas quemado: {summary.get('syngas_burned_kg', 0.0):.1f} kg ({summary.get('syngas_recirc_pct', 0.0):.0f} % del gas producido)."
        if lang == 'es' else
        f"Bed heat (simulation) vs. analytic sum: deviation {bed_gap_pct:+.1f} %. The analytic table assumes all vapor leaves at hold "
        f"temperature (overestimating steam superheat); the simulation lets it leave at bed temperature. "
        f"Burner fuel: {summary.get('waste_oil_consumed_gal', 0.0):.1f} gal; "
        f"syngas burned: {summary.get('syngas_burned_kg', 0.0):.1f} kg ({summary.get('syngas_recirc_pct', 0.0):.0f} % of produced gas)."
    )
        
    if lang == 'es':
        st.markdown(rf"""
        #### 📝 Ecuaciones del Balance de Energía con Sustitución Numérica
        La energía térmica total ($E_{{total}}$) suministrada en el lote se desglosa en cinco componentes caloríficos con sus valores reales evaluados:
        $$E_{{total}} = E_{{char}} + E_{{oil\_sens}} + E_{{gas\_sens}} + E_{{rxn}} + E_{{steam}} = \mathbf{{{E_total_kwh:.2f}\text{{ kWh}}}}$$
        * **Calor Sensible del Char ($E_{{char}}$)**:
          $$E_{{char}} = \frac{{M_{{char}} \cdot Cp_{{char}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_char:.2f}\text{{ kg}} \cdot 1000\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_char_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_char_kwh, E_total_kwh):.1f}\%)$$
        * **Calor Sensible del Aceite pirolítico Líquido ($E_{{oil\_sens}}$)**:
          $$E_{{oil}} = \frac{{M_{{oil}} \cdot Cp_{{oil}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_oil:.2f}\text{{ kg}} \cdot {cp_oil:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_oil_sens_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_oil_sens_kwh, E_total_kwh):.1f}\%)$$
        * **Calor Sensible del Syngas ($E_{{gas\_sens}}$)**:
          $$E_{{gas}} = \frac{{M_{{gas}} \cdot Cp_{{gas}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_gas:.2f}\text{{ kg}} \cdot {CP_GAS_J_KGK:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_gas_sens_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_gas_sens_kwh, E_total_kwh):.1f}\%)$$
        * **Reacción Química Endotérmica de Pirólisis ($E_{{rxn}}$)**:
          $$E_{{rxn}} = \frac{{(M_{{oil}} + M_{{gas}}) \cdot \Delta H_{{pyro}}}}{{3.6 \times 10^6}} = \frac{{{M_oil + M_gas:.2f}\text{{ kg}} \cdot 700,000\text{{ J/kg}}}}{{3.6 \times 10^6}} = \mathbf{{{E_rxn_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_rxn_kwh, E_total_kwh):.1f}\%)$$
        * **Secado y Evaporación del Agua ($E_{{steam}}$)**:
          $$E_{{steam}} = \frac{{M_{{steam}} \cdot \left[ Cp_{{water}} \cdot \Delta T + \Delta H_{{evap}} + Cp_{{steam}} \cdot \Delta T_{{steam}} \right]}}{{3.6 \times 10^6}} = \mathbf{{{E_steam_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_steam_kwh, E_total_kwh):.1f}\%)$$
        """)
    else:
        st.markdown(rf"""
        #### 📝 Energy Balance Equations with Evaluated Results
        The total thermal energy ($E_{{total}}$) is rigorously separated into five thermal duties:
        $$E_{{total}} = E_{{char}} + E_{{oil\_sens}} + E_{{gas\_sens}} + E_{{rxn}} + E_{{steam}} = \mathbf{{{E_total_kwh:.2f}\text{{ kWh}}}}$$
        * **Char Sensible Heat**: $E_{{char}} = \mathbf{{{E_char_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_char_kwh, E_total_kwh):.1f}\%)$
        * **Pyrolysis oil Sensible Heat**: $E_{{oil}} = \mathbf{{{E_oil_sens_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_oil_sens_kwh, E_total_kwh):.1f}\%)$
        * **Syngas Sensible Heat**: $E_{{gas}} = \mathbf{{{E_gas_sens_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_gas_sens_kwh, E_total_kwh):.1f}\%)$
        * **Pyrolysis Chemical Endotherm**: $E_{{rxn}} = \mathbf{{{E_rxn_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_rxn_kwh, E_total_kwh):.1f}\%)$
        * **Moisture Dehydration & Evaporation**: $E_{{steam}} = \mathbf{{{E_steam_kwh:.2f}\text{{ kWh}}}} \quad ({_pct(E_steam_kwh, E_total_kwh):.1f}\%)$
        """)


def _render_kinetics_section(current_feed):
    """Kinetic scheme and the Arrhenius parameters of the current feedstock."""
    st.markdown("---")
    st.markdown("### 🔬 Chemical Kinetics / Cinética Química")
    st.markdown(r"""
    **First-Order Kinetic Differential Equations / Ecuaciones Diferenciales Cinéticas de Primer Orden:**
    
    $$
    \frac{dC_{\text{slug}}}{dt} = -(k_1 + k_2) \cdot C_{\text{slug}}
    $$
    $$
    \frac{dC_{\text{medios}}}{dt} = k_1 \cdot C_{\text{slug}} - k_3 \cdot C_{\text{medios}}
    $$
    $$
    \frac{dC_{\text{gases}}}{dt} = k_2 \cdot C_{\text{slug}} + k_3 \cdot C_{\text{medios}}
    $$
    
    *Where / Donde:*
    *   $C_{\text{slug}}$: Unreacted volatile matter / Materia volátil sin reaccionar ($M_{\text{volatile}}$).
    *   $C_{\text{medios}}$: Pyrolysis oil (tars / condensables) / Aceite pirolítico (condensables).
    *   $C_{\text{gases}}$: Pyrolysis gases (syngas / non-condensables) / Gases de pirólisis.
    """)
    
    st.markdown("---")
    st.markdown("**Arrhenius Parameters in Use / Parámetros de Arrhenius en Uso:**")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"**Reaction 1 / Reacción 1 (Sludge → Pyrolysis oil):**  \n"
            f"*   $E_{{a,1}} = {current_feed.Ea1 / 1000.0:.1f}\\text{{ kJ/mol}}$  \n"
            f"*   $A_1 = {current_feed.A1:.2e}\\text{{ s}}^{{-1}}$  \n"
            f"$$k_1 = A_1 \\cdot \\exp\\left(-\\frac{{E_{{a,1}}}}{{R \\cdot T_s}}\\right)$$"
        )
    with col2:
        st.markdown(
            f"**Reaction 2 / Reacción 2 (Sludge → Gases):**  \n"
            f"*   $E_{{a,2}} = {current_feed.Ea2 / 1000.0:.1f}\\text{{ kJ/mol}}$  \n"
            f"*   $A_2 = {current_feed.A2:.2e}\\text{{ s}}^{{-1}}$  \n"
            f"$$k_2 = A_2 \\cdot \\exp\\left(-\\frac{{E_{{a,2}}}}{{R \\cdot T_s}}\\right)$$"
        )
    with col3:
        st.markdown(
            f"**Reaction 3 / Reacción 3 (Pyrolysis oil → Gases):**  \n"
            f"*   $E_{{a,3}} = {current_feed.Ea3 / 1000.0:.1f}\\text{{ kJ/mol}}$  \n"
            f"*   $A_3 = {current_feed.A3:.2e}\\text{{ s}}^{{-1}}$  \n"
            f"$$k_3 = A_3 \\cdot \\exp\\left(-\\frac{{E_{{a,3}}}}{{R \\cdot T_s}}\\right)$$"
        )

def render_guide_tab():
    """Renders the theoretical equations and guide tab content."""
    st.header(t("guide_title"))
    
    st.markdown("---")
    st.markdown("### 🏢 Resumen Ejecutivo Industrial: Planta PROENERGETICOS (3,700 gal)")
    st.success(
        "**Evaluación de Viabilidad Técnica & Operación Autógena (Sin N₂):**  \n"
        "1. **Operación Autógena y Purga de Aire:** El desplazamiento volumétrico inicial del aire contenido en el domo del reactor (14.0 m³) se completa de forma autógena en los primeros minutos del ciclo mediante la rápida expansión del agua de humedad y primeros volátiles, garantizando una atmósfera inerte sin consumo de nitrógeno comercial.  \n"
        "2. **Hidrodinámica del Manifold (8'' / 4x4''):** El manifold de evacuación de 8 pulgadas conectado a las 4 líneas secundarias de 4 pulgadas ofrece una sección transversal amplia (0.0324 m²), manteniendo las velocidades de vapor por debajo de los límites erosinadores y limitando la contrapresión a niveles seguros de operación.  \n"
        "3. **Autosuficiencia Energética y Antorcha (Flare):** El syngas generado cubre la demanda térmica del quemador principal, canalizándose el excedente incondensable hacia la antorcha (flare) para su destrucción limpia conforme a normativas ambientales.  \n"
        "4. **Condensación en 2 Etapas (Tanque 28,000 gal & Furgón Sellado):** La condensación secuencial permite recuperar el aceite pirolítico con alta eficiencia térmica, separando el agua de arrastre (BS&W) y concentrando una fracción pesada directamente comercializable."
    )
    
    st.subheader(t("guide_sec_1"))
    st.markdown(t("guide_sec_1_text"))
    
    st.subheader(t("guide_sec_2"))
    st.markdown(t("guide_sec_2_text"))
    
    st.subheader(t("guide_sec_3"))
    st.markdown(t("guide_sec_3_text"))

def _render_csv_export(results):
    """Renders the numerical simulation profile CSV export button."""
    st.markdown("### 📊 Datos de Perfil (CSV)")
    st.caption("Descargue las series temporales de temperatura, masa y rendimiento.")
    
    export_df = pd.DataFrame({
        'Time_min': results['time'],
        'T_Wall_C': results['T_wall'],
        'T_Solids_C': results['T_solid'],
        'Moisture_kg': results['moisture'],
        'Volatiles_kg': results['volatile'],
        'Char_kg': results['char'],
        'Ash_kg': results['ash'],
        'Oil_Produced_kg': results['oil'],
        'Syngas_Produced_kg': results['gas'],
        'Steam_Produced_kg': results['steam'],
        'Volatiles_Conversion_pct': np.array(results['conversion']) * 100.0,
        'Bed_Humidity_pct': results['humidity']
    })
    file_name_out = "pyrolysis_batch_reactor_profile.csv"
        
    csv_data = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=t("export_button"),
        data=csv_data,
        file_name=file_name_out,
        mime="text/csv"
    )

def render_export_tab(results, summary, solver_inputs=None, config_dict=None, enable_reports=None):
    """Renders the data export tab content. Report generation (PDF/Word) is enabled only if enable_reports is True."""
    if enable_reports is None:
        enable_reports = ENABLE_REPORTS

    st.subheader(t("export_title"))
    st.markdown(t("export_desc"))
    
    if enable_reports:
        if config_dict is None:
            config_dict = {'lang_option': st.session_state.get('lang_option', 'Español')}
        col_pdf, col_word, col_csv = st.columns(3)
        
        with col_pdf:
            st.markdown("### 🎓 Reporte de Tesis (PDF)")
            st.info(t("export_pdf_desc"))
            
            if not REPORTLAB_AVAILABLE:
                st.warning("⚠️ **La librería `reportlab` no está instalada en el entorno de Python de su servidor.**\n\nPara habilitar la generación y descarga del reporte de tesis en PDF, ejecute en su servidor / consola:\n```bash\npip install reportlab\n```")
            elif solver_inputs is not None:
                try:
                    # reload so edits to the generator show up without restarting Streamlit
                    import importlib
                    import pyrolysis.pdf_generator as pdf_mod
                    importlib.reload(pdf_mod)
                    pdf_bytes = pdf_mod.generate_thesis_pdf(results, summary, solver_inputs, config_dict)
                    pdf_filename = "Tesis_Simulacion_Pirolisis_Reactor_Rotatorio.pdf"
                    st.download_button(
                        label=t("export_pdf_button"),
                        data=pdf_bytes,
                        file_name=pdf_filename,
                        mime="application/pdf",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error al generar el reporte de Tesis PDF: {e}")
            else:
                st.warning("Complete la simulación para habilitar la descarga del reporte en PDF.")

        with col_word:
            st.markdown("### 📝 Reporte Técnico (Word)")
            st.info("Descargue el informe técnico completo editable en formato Microsoft Word (.docx).")
            
            if not PYTHON_DOCX_AVAILABLE:
                st.warning("⚠️ **La librería `python-docx` no está instalada en el entorno.**\n\nEjecute:\n```bash\npip install python-docx\n```")
            elif solver_inputs is not None:
                try:
                    import importlib
                    import pyrolysis.docx_generator as docx_mod
                    importlib.reload(docx_mod)
                    docx_bytes = docx_mod.generate_word_report(results, summary, solver_inputs, config_dict)
                    word_filename = "Informe_Tecnico_Pirolisis_Reactor_Rotatorio.docx"
                    st.download_button(
                        label="📥 Descargar Informe en Word (.docx)",
                        data=docx_bytes,
                        file_name=word_filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error al generar el reporte en Word: {e}")
            else:
                st.warning("Complete la simulación para habilitar la descarga del reporte en Word.")

        with col_csv:
            _render_csv_export(results)
    else:
        # Modo con reportes desactivados: solo exportación de datos crudos (CSV)
        _render_csv_export(results)
    
    st.markdown("---")
    st.subheader(t("export_summary_title"))
    st.write(summary)

