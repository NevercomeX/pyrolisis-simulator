import streamlit as st
import numpy as np
import pandas as pd
from pyrolysis import TRANSLATIONS, generate_word_report
from pyrolysis.pdf_generator import generate_thesis_pdf, REPORTLAB_AVAILABLE

try:
    import docx
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def render_properties_tab(current_feed, mode_option, feed_rate_kgh, batch_load_kg, feed_option):
    """Renders the feedstock properties tab content."""
    lang = get_lang()
    col_prop_l, col_prop_r = st.columns(2)
    
    with col_prop_l:
        st.subheader(t("analysis_chem_comp"))
        load_val = feed_rate_kgh if mode_option == "Continuous Operation" else batch_load_kg
        load_unit = "kg/h" if mode_option == "Continuous Operation" else "kg"
        load_unit_gal = "gal/h" if mode_option == "Continuous Operation" else "gal"
        sludge_density = float(st.session_state.get('sludge_density', 944.7))
        load_val_gal = (load_val / sludge_density) * 264.172
        
        comp_df = pd.DataFrame({
            t("analysis_component"): [t("analysis_moisture_name"), t("analysis_volatiles_name"), t("analysis_char_name"), t("analysis_ash_name")],
            t("analysis_wt_pct"): [current_feed.moisture, current_feed.volatile, current_feed.fixed_carbon, current_feed.ash],
            t("analysis_input_load").format(load_unit): [
                load_val * current_feed.moisture / 100.0,
                load_val * current_feed.volatile / 100.0,
                load_val * current_feed.fixed_carbon / 100.0,
                load_val * current_feed.ash / 100.0
            ],
            t("analysis_input_load").format(load_unit_gal): [
                load_val_gal * current_feed.moisture / 100.0,
                load_val_gal * current_feed.volatile / 100.0,
                load_val_gal * current_feed.fixed_carbon / 100.0,
                load_val_gal * current_feed.ash / 100.0
            ]
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

    # ASTM Standards Characterization Section for PROENERGETICOS Bio-Oil
    st.markdown("---")
    st.markdown(f"### 🔬 Caracterización Físico-Química del Bio-Crudo (Normas ASTM)")
    
    astm_col1, astm_col2, astm_col3, astm_col4 = st.columns(4)
    
    # HHV / PCS ASTM D240
    temp_hold = float(st.session_state.get('holding_temp', 550.0))
    vol_pct = current_feed.volatile
    hhv_oil = min(43.5, max(36.0, 38.0 + 0.008 * (temp_hold - 450.0) + 0.10 * (vol_pct - 50.0)))
    hhv_btu = hhv_oil * 429.923
    factor_enh = hhv_oil / 18.5
    
    # Viscosity ASTM D445
    visc_40c = max(12.0, 45.0 - 0.08 * (temp_hold - 400.0))
    pump_status = "Directamente Bombeable @ 25°C" if visc_40c <= 25.0 else ("Bombeable con Precalentamiento a 40°C" if visc_40c <= 50.0 else "Alta Viscosidad - Precalentar a 60°C")
    
    # Density ASTM D1298
    bio_oil_dens = float(st.session_state.get('bio_oil_density', 750.0))
    sg_15 = bio_oil_dens / 999.1
    api_deg = (141.5 / max(0.1, sg_15)) - 131.5
    
    # BS&W ASTM D95
    bsw_pct = min(8.0, max(1.5, 3.5 * (current_feed.moisture / 30.0)))
    
    with astm_col1:
        st.info(
            f"**🔥 Poder Calorífico Superior (ASTM D240)**  \n"
            f"* **PCS / HHV:** `{hhv_oil:.2f} MJ/kg` (`{hhv_btu:,.0f} BTU/lb`)  \n"
            f"* **PCS Lodo Original:** `18.50 MJ/kg`  \n"
            f"* **Factor de Mejora:** `x{factor_enh:.2f}`"
        )
    with astm_col2:
        st.info(
            f"**🧪 Viscosidad Cinemática (ASTM D445)**  \n"
            f"* **Viscosidad @ 40°C:** `{visc_40c:.1f} cSt (mm²/s)`  \n"
            f"* **Diagnóstico Bombeo:** `{pump_status}`"
        )
    with astm_col3:
        st.info(
            f"**⚖️ Densidad & °API (ASTM D1298)**  \n"
            f"* **Densidad @ 15°C:** `{bio_oil_dens:.1f} kg/m³`  \n"
            f"* **Gravedad Específica (SG):** `{sg_15:.4f}`  \n"
            f"* **Gravedad °API:** `{api_deg:.1f} °API`"
        )
    with astm_col4:
        st.info(
            f"**💧 Humedad & BS&W (ASTM D95)**  \n"
            f"* **Humedad en Condensado:** `{bsw_pct:.2f} wt.%`  \n"
            f"* **Sistema Condensación:** `Tanque 28,000 gal`  \n"
            f"* **Separación:** `Furgón Sellado Etapa 2`"
        )

def render_balances_tab(mode_option, current_feed, results, summary, feed_rate_kgh, batch_load_kg, feed_option):
    """Renders the mass and energy balances tab content."""
    lang = get_lang()
    
    if mode_option == "Continuous Operation":
        st.markdown("### ⚖️ Mass Balance / Balance de Materia")
        load_val = feed_rate_kgh
        sludge_density = float(st.session_state.get('sludge_density', 944.7))
        oil_density = float(st.session_state.get('bio_oil_density', 750.0))
        char_density = float(st.session_state.get('bio_char_density', 500.0))
        
        load_val_gal = (load_val / sludge_density) * 264.172
        oil_gal_h = (summary['oil_yield_kgh'] / oil_density) * 264.172
        gas_m3_h = summary['gas_yield_kgh'] / 1.15
        char_gal_h = (summary['char_yield_kgh'] / char_density) * 264.172
        water_gal_h = (summary['water_yield_kgh'] / 1000.0) * 264.172
        
        feed_name_display = t("feed_custom") if feed_option == "Custom Feedstock" else current_feed.name
        mass_in_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [feed_name_display],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [100.0],
            "Flow Rate / Flujo (kg/h)": [load_val],
            "Flow Rate / Flujo (gal/h)": [load_val_gal]
        })
        
        mass_out_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [
                t("bio_oil_name") if "bio_oil_name" in TRANSLATIONS[lang] else "Bio-Oil", 
                t("syngas_name") if "syngas_name" in TRANSLATIONS[lang] else "Syngas", 
                t("analysis_char_name") if "analysis_char_name" in TRANSLATIONS[lang] else "Bio-Char", 
                t("water_vapor_metric") if "water_vapor_metric" in TRANSLATIONS[lang] else "Water Vapor (Steam)"
            ],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [
                summary['oil_yield_pct'],
                summary['gas_yield_pct'],
                summary['char_yield_pct'],
                summary['water_yield_pct']
            ],
            "Flow Rate / Flujo (kg/h)": [
                summary['oil_yield_kgh'],
                summary['gas_yield_kgh'],
                summary['char_yield_kgh'],
                summary['water_yield_kgh']
            ],
            "Volumen / Volume": [
                f"{oil_gal_h:.1f} gal/h",
                f"{gas_m3_h:.1f} m³/h",
                f"{char_gal_h:.1f} gal/h",
                f"{water_gal_h:.1f} gal/h"
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
            #### 📝 Ecuaciones del Balance de Materia (Continuo)
            El balance de materia se basa en la conservación de la masa de sólidos y gases en el reactor:
            $$F_{inlet} = F_{char} + F_{oil} + F_{gas} + F_{steam} + F_{moist, final}$$
            * **Bio-Crudo (Bio-Oil)**: Integrado localmente a partir de la formación primaria y craqueo secundario a gas:
              $$F_{oil} = \int_{0}^{L} \left( k_1 \cdot C_{\text{slug}} - k_3 \cdot C_{\text{medios, local}} \right) \frac{dz}{v_s}$$
            * **Gas de Síntesis (Syngas)**: Integrado localmente a partir del craqueo primario y secundario de bio-oil:
              $$F_{gas} = \int_{0}^{L} \left( k_2 \cdot C_{\text{slug}} + k_3 \cdot C_{\text{medios, local}} \right) \frac{dz}{v_s}$$
            * **Bio-Carbón Residual (Char - Seco)**: Suma del carbón fijo inicial, cenizas iniciales y materia volátil sin reaccionar:
              $$F_{char} = F_{fixed\_carbon, initial} + F_{ash, initial} + F_{volatile, unreacted}$$
            * **Vapor de Agua (Steam)**: Humedad evaporada del lecho sólido:
              $$F_{steam} = F_{moisture, initial} - F_{moisture, final}$$
            * **Ecuación Evaluada y Error de Cierre**:
              $$F_{inlet} = F_{char} + F_{oil} + F_{gas} + F_{steam}$$
              $${load_val:.2f}\text{{ kg/h}} = {summary['char_yield_kgh']:.2f} + {summary['oil_yield_kgh']:.2f} + {summary['gas_yield_kgh']:.2f} + {summary['water_yield_kgh']:.2f}\text{{ kg/h}}$$
              $$\text{{Error (\%)}}\ = \frac{{|F_{{inlet}} - F_{{outlet\_total}}|}}{{F_{{inlet}}}} \times 100 = \mathbf{{{summary['mass_error_pct']:.4f}\%}}$$
            """)
        else:
            st.markdown(rf"""
            #### 📝 Mass Balance Equations (Continuous)
            The mass balance is based on the conservation of mass entering and leaving the reactor:
            $$F_{{inlet}} = F_{{char}} + F_{{oil}} + F_{{gas}} + F_{{steam}}$$
            $${load_val:.2f}\text{{ kg/h}} = {summary['char_yield_kgh']:.2f} + {summary['oil_yield_kgh']:.2f} + {summary['gas_yield_kgh']:.2f} + {summary['water_yield_kgh']:.2f}\text{{ kg/h}}$$
            $$\text{{Error (\%)}} = \frac{{|F_{{inlet}} - F_{{outlet\_total}}|}}{{F_{{inlet}}}} \times 100 = \mathbf{{{summary['mass_error_pct']:.4f}\%}}$$
            """)
        
        st.markdown("---")
        st.markdown("### ⚡ Energy Balance / Balance de Energía")
        
        F_oil_s = summary['oil_yield_kgh'] / 3600.0
        F_gas_s = summary['gas_yield_kgh'] / 3600.0
        F_char_s = summary['char_yield_kgh'] / 3600.0
        F_steam_s = summary['water_yield_kgh'] / 3600.0
        T_in = results['T_solid'][0]
        T_out = results['T_solid'][-1]
        T_gas_out = results['T_gas'][-1]
        dT = T_out - T_in

        cp_char = 1000.0
        cp_oil = float(st.session_state.get('custom_cp_oil', 1800.0))
        cp_gas = 1500.0
        dh_pyro = 600000.0
        dh_evap = 2256000.0
        
        Q_char_kw = (F_char_s * cp_char * dT) / 1000.0
        Q_oil_sens_kw = (F_oil_s * cp_oil * dT) / 1000.0
        Q_gas_sens_kw = (F_gas_s * cp_gas * dT) / 1000.0
        Q_rxn_kw = ((F_oil_s + F_gas_s) * dh_pyro) / 1000.0
        if T_in < 100.0:
            Q_steam_kw = (F_steam_s * (4184.0 * (100.0 - T_in) + dh_evap + 2000.0 * (max(T_gas_out, 100.0) - 100.0))) / 1000.0
        else:
            Q_steam_kw = (F_steam_s * (dh_evap + 2000.0 * (max(T_gas_out, T_in) - T_in))) / 1000.0
            
        Q_total_kw = Q_char_kw + Q_oil_sens_kw + Q_gas_sens_kw + Q_rxn_kw + Q_steam_kw
        
        energy_df = pd.DataFrame({
            "Process Stage / Etapa del Proceso": [
                "Sensible Heat of Bed Solids / Calor Sensible Char",
                "Sensible Heat Bio-Oil / Calor Sensible Vapores Bio-Crudo (Líquido)",
                "Sensible Heat Syngas / Calor Sensible Gas de Síntesis (Gas)",
                "Pyrolysis Cracking Enthalpy / Reacción Química Craqueo",
                "Evaporation & Dehydration / Evaporación del Agua",
                "Total Thermal Heating Duty / Potencia Térmica Total"
            ],
            "Heat Rate / Flujo de Calor (kW)": [
                Q_char_kw,
                Q_oil_sens_kw,
                Q_gas_sens_kw,
                Q_rxn_kw,
                Q_steam_kw,
                Q_total_kw
            ],
            "Fraction of Total / Porcentaje del Total (%)": [
                (Q_char_kw / max(0.001, Q_total_kw) * 100.0),
                (Q_oil_sens_kw / max(0.001, Q_total_kw) * 100.0),
                (Q_gas_sens_kw / max(0.001, Q_total_kw) * 100.0),
                (Q_rxn_kw / max(0.001, Q_total_kw) * 100.0),
                (Q_steam_kw / max(0.001, Q_total_kw) * 100.0),
                100.0
            ]
        })
        st.table(energy_df)
        
        if lang == 'es':
            st.markdown(rf"""
            #### 📝 Ecuaciones del Balance de Energía con Sustitución Numérica
            La demanda térmica total ($Q_{{total}}$) del reactor continuo se divide en cinco contribuciones caloríficas rigurosas:
            $$Q_{{total}} = Q_{{char}} + Q_{{oil\_sens}} + Q_{{gas\_sens}} + Q_{{rxn}} + Q_{{steam}} = \mathbf{{{Q_total_kw:.2f}\text{{ kW}}}}$$
            * **Calor Sensible del Char ($Q_{{char}}$)**:
              $$Q_{{char}} = F_{{char}} \cdot Cp_{{char}} \cdot (T_{{out}} - T_{{in}}) = {F_char_s*3600:.2f}\text{{ kg/h}} \cdot 1000\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}} = \mathbf{{{Q_char_kw:.2f}\text{{ kW}}}} \quad ({(Q_char_kw/max(0.001,Q_total_kw)*100):.1f}\%)$$
            * **Calor Sensible del Bio-Crudo Líquido ($Q_{{oil\_sens}}$)**:
              $$Q_{{oil}} = F_{{oil}} \cdot Cp_{{oil}} \cdot (T_{{out}} - T_{{in}}) = {F_oil_s*3600:.2f}\text{{ kg/h}} \cdot {cp_oil:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}} = \mathbf{{{Q_oil_sens_kw:.2f}\text{{ kW}}}} \quad ({(Q_oil_sens_kw/max(0.001,Q_total_kw)*100):.1f}\%)$$
            * **Calor Sensible del Syngas ($Q_{{gas\_sens}}$)**:
              $$Q_{{gas}} = F_{{gas}} \cdot Cp_{{gas}} \cdot (T_{{out}} - T_{{in}}) = {F_gas_s*3600:.2f}\text{{ kg/h}} \cdot {cp_gas:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}} = \mathbf{{{Q_gas_sens_kw:.2f}\text{{ kW}}}} \quad ({(Q_gas_sens_kw/max(0.001,Q_total_kw)*100):.1f}\%)$$
            * **Reacción Química Endotérmica de Pirólisis ($Q_{{rxn}}$)**:
              $$Q_{{rxn}} = (F_{{oil}} + F_{{gas}}) \cdot \Delta H_{{pyro}} = {(F_oil_s+F_gas_s)*3600:.2f}\text{{ kg/h}} \cdot 600,000\text{{ J/kg}} = \mathbf{{{Q_rxn_kw:.2f}\text{{ kW}}}} \quad ({(Q_rxn_kw/max(0.001,Q_total_kw)*100):.1f}\%)$$
            * **Secado y Evaporación del Agua ($Q_{{steam}}$)**:
              $$Q_{{steam}} = F_{{steam}} \cdot \left[ Cp_{{water}} \cdot \Delta T + \Delta H_{{evap}} + Cp_{{steam}} \cdot \Delta T_{{steam}} \right] = \mathbf{{{Q_steam_kw:.2f}\text{{ kW}}}} \quad ({(Q_steam_kw/max(0.001,Q_total_kw)*100):.1f}\%)$$
            """)
        else:
            st.markdown(rf"""
            #### 📝 Energy Balance Equations with Evaluated Results
            The total thermal demand ($Q_{{total}}$) is rigorously separated into five thermal duties:
            $$Q_{{total}} = Q_{{char}} + Q_{{oil\_sens}} + Q_{{gas\_sens}} + Q_{{rxn}} + Q_{{steam}} = \mathbf{{{Q_total_kw:.2f}\text{{ kW}}}}$$
            * **Char Sensible Heat**: $Q_{{char}} = \mathbf{{{Q_char_kw:.2f}\text{{ kW}}}} \quad ({(Q_char_kw/max(0.001,Q_total_kw)*100):.1f}\%)$
            * **Bio-Oil Sensible Heat**: $Q_{{oil}} = \mathbf{{{Q_oil_sens_kw:.2f}\text{{ kW}}}} \quad ({(Q_oil_sens_kw/max(0.001,Q_total_kw)*100):.1f}\%)$
            * **Syngas Sensible Heat**: $Q_{{gas}} = \mathbf{{{Q_gas_sens_kw:.2f}\text{{ kW}}}} \quad ({(Q_gas_sens_kw/max(0.001,Q_total_kw)*100):.1f}\%)$
            * **Pyrolysis Chemical Endotherm**: $Q_{{rxn}} = \mathbf{{{Q_rxn_kw:.2f}\text{{ kW}}}} \quad ({(Q_rxn_kw/max(0.001,Q_total_kw)*100):.1f}\%)$
            * **Moisture Dehydration & Evaporation**: $Q_{{steam}} = \mathbf{{{Q_steam_kw:.2f}\text{{ kW}}}} \quad ({(Q_steam_kw/max(0.001,Q_total_kw)*100):.1f}\%)$
            """)
        
    else:
        st.markdown("### ⚖️ Mass Balance / Balance de Materia")
        load_val = batch_load_kg
        sludge_density = float(st.session_state.get('sludge_density', 944.7))
        oil_density = float(st.session_state.get('bio_oil_density', 750.0))
        char_density = float(st.session_state.get('bio_char_density', 500.0))
        
        load_val_gal = (load_val / sludge_density) * 264.172
        oil_gal = (summary['oil_yield_kg'] / oil_density) * 264.172
        gas_m3 = summary['gas_yield_kg'] / 1.15
        char_gal = (summary['char_yield_kg'] / char_density) * 264.172
        water_gal = (summary['water_yield_kg'] / 1000.0) * 264.172
        
        feed_name_display = t("feed_custom") if feed_option == "Custom Feedstock" else current_feed.name
        mass_in_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [feed_name_display],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [100.0],
            "Load / Carga (kg)": [load_val],
            "Load / Carga (gal)": [load_val_gal]
        })
        
        mass_out_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [
                t("bio_oil_name") if "bio_oil_name" in TRANSLATIONS[lang] else "Bio-Oil", 
                t("syngas_name") if "syngas_name" in TRANSLATIONS[lang] else "Syngas", 
                t("analysis_char_name") if "analysis_char_name" in TRANSLATIONS[lang] else "Bio-Char", 
                t("water_vapor_metric") if "water_vapor_metric" in TRANSLATIONS[lang] else "Water Vapor (Steam)"
            ],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [
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
            * **Bio-Crudo (Bio-Oil)**: Acumulado a partir del rendimiento neto de lodo y craqueo secundario del vapor:
              $$M_{oil} = \int \left( dM_{\text{oil, primary}} - dM_{\text{oil, cracked}} \right)$$
            * **Gas de Síntesis (Syngas)**: Acumulado de la producción primaria y del craqueo secundario del vapor:
              $$M_{gas} = \int \left( dM_{\text{gas, primary}} + dM_{\text{oil, cracked}} \right)$$
            * **Bio-Carbón Residual (Char - Seco)**: Masa sólida remanente (carbón fijo, cenizas y volátiles residuales):
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
            * **Bio-Oil**: Accumulated from primary sludge conversion and secondary vapor cracking:
              $$M_{oil} = \int \left( dM_{\text{oil, primary}} - dM_{\text{oil, cracked}} \right)$$
            * **Syngas**: Accumulated from primary gasification and secondary vapor cracking:
              $$M_{gas} = \int \left( dM_{\text{gas, primary}} + dM_{\text{oil, cracked}} \right)$$
            * **Residual Bio-Char (Char - Dry)**: Remaining solid mass (fixed carbon, ash, and residual volatiles):
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

        cp_char = 1000.0
        cp_oil = float(st.session_state.get('custom_cp_oil', 1800.0))
        cp_gas = 1500.0
        dh_pyro = 600000.0
        dh_evap = 2256000.0

        E_char_kwh = (M_char * cp_char * dT) / 3.6e6
        E_oil_sens_kwh = (M_oil * cp_oil * dT) / 3.6e6
        E_gas_sens_kwh = (M_gas * cp_gas * dT) / 3.6e6
        E_rxn_kwh = ((M_oil + M_gas) * dh_pyro) / 3.6e6
        if T_hold >= 100.0:
            E_steam_kwh = (M_steam * (4184.0 * (100.0 - T_start) + dh_evap + 2000.0 * (T_hold - 100.0))) / 3.6e6
        else:
            E_steam_kwh = (M_steam * (4184.0 * (T_hold - T_start))) / 3.6e6
            
        E_total_kwh = E_char_kwh + E_oil_sens_kwh + E_gas_sens_kwh + E_rxn_kwh + E_steam_kwh
        
        energy_df = pd.DataFrame({
            "Process Stage / Etapa del Proceso": [
                "Sensible Heat of Bed Solids / Calor Sensible Char",
                "Sensible Heat Bio-Oil / Calor Sensible Vapores Bio-Crudo (Líquido)",
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
                (E_char_kwh / max(0.001, E_total_kwh) * 100.0),
                (E_oil_sens_kwh / max(0.001, E_total_kwh) * 100.0),
                (E_gas_sens_kwh / max(0.001, E_total_kwh) * 100.0),
                (E_rxn_kwh / max(0.001, E_total_kwh) * 100.0),
                (E_steam_kwh / max(0.001, E_total_kwh) * 100.0),
                100.0
            ]
        })
        st.table(energy_df)
        
        if lang == 'es':
            st.markdown(rf"""
            #### 📝 Ecuaciones del Balance de Energía con Sustitución Numérica
            La energía térmica total ($E_{{total}}$) suministrada en el lote se desglosa en cinco componentes caloríficos con sus valores reales evaluados:
            $$E_{{total}} = E_{{char}} + E_{{oil\_sens}} + E_{{gas\_sens}} + E_{{rxn}} + E_{{steam}} = \mathbf{{{E_total_kwh:.2f}\text{{ kWh}}}}$$
            * **Calor Sensible del Char ($E_{{char}}$)**:
              $$E_{{char}} = \frac{{M_{{char}} \cdot Cp_{{char}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_char:.2f}\text{{ kg}} \cdot 1000\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_char_kwh:.2f}\text{{ kWh}}}} \quad ({(E_char_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$$
            * **Calor Sensible del Bio-Crudo Líquido ($E_{{oil\_sens}}$)**:
              $$E_{{oil}} = \frac{{M_{{oil}} \cdot Cp_{{oil}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_oil:.2f}\text{{ kg}} \cdot {cp_oil:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_oil_sens_kwh:.2f}\text{{ kWh}}}} \quad ({(E_oil_sens_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$$
            * **Calor Sensible del Syngas ($E_{{gas\_sens}}$)**:
              $$E_{{gas}} = \frac{{M_{{gas}} \cdot Cp_{{gas}} \cdot (T_{{hold}} - T_{{start}})}}{{3.6 \times 10^6}} = \frac{{{M_gas:.2f}\text{{ kg}} \cdot {cp_gas:.0f}\text{{ J/kg}}\cdot\text{{K}} \cdot {dT:.1f}\text{{ K}}}}{{3.6 \times 10^6}} = \mathbf{{{E_gas_sens_kwh:.2f}\text{{ kWh}}}} \quad ({(E_gas_sens_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$$
            * **Reacción Química Endotérmica de Pirólisis ($E_{{rxn}}$)**:
              $$E_{{rxn}} = \frac{{(M_{{oil}} + M_{{gas}}) \cdot \Delta H_{{pyro}}}}{{3.6 \times 10^6}} = \frac{{{M_oil + M_gas:.2f}\text{{ kg}} \cdot 600,000\text{{ J/kg}}}}{{3.6 \times 10^6}} = \mathbf{{{E_rxn_kwh:.2f}\text{{ kWh}}}} \quad ({(E_rxn_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$$
            * **Secado y Evaporación del Agua ($E_{{steam}}$)**:
              $$E_{{steam}} = \frac{{M_{{steam}} \cdot \left[ Cp_{{water}} \cdot \Delta T + \Delta H_{{evap}} + Cp_{{steam}} \cdot \Delta T_{{steam}} \right]}}{{3.6 \times 10^6}} = \mathbf{{{E_steam_kwh:.2f}\text{{ kWh}}}} \quad ({(E_steam_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$$
            """)
        else:
            st.markdown(rf"""
            #### 📝 Energy Balance Equations with Evaluated Results
            The total thermal energy ($E_{{total}}$) is rigorously separated into five thermal duties:
            $$E_{{total}} = E_{{char}} + E_{{oil\_sens}} + E_{{gas\_sens}} + E_{{rxn}} + E_{{steam}} = \mathbf{{{E_total_kwh:.2f}\text{{ kWh}}}}$$
            * **Char Sensible Heat**: $E_{{char}} = \mathbf{{{E_char_kwh:.2f}\text{{ kWh}}}} \quad ({(E_char_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$
            * **Bio-Oil Sensible Heat**: $E_{{oil}} = \mathbf{{{E_oil_sens_kwh:.2f}\text{{ kWh}}}} \quad ({(E_oil_sens_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$
            * **Syngas Sensible Heat**: $E_{{gas}} = \mathbf{{{E_gas_sens_kwh:.2f}\text{{ kWh}}}} \quad ({(E_gas_sens_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$
            * **Pyrolysis Chemical Endotherm**: $E_{{rxn}} = \mathbf{{{E_rxn_kwh:.2f}\text{{ kWh}}}} \quad ({(E_rxn_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$
            * **Moisture Dehydration & Evaporation**: $E_{{steam}} = \mathbf{{{E_steam_kwh:.2f}\text{{ kWh}}}} \quad ({(E_steam_kwh/max(0.001,E_total_kwh)*100):.1f}\%)$
            """)
        
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
    *   $C_{\text{medios}}$: Bio-oil (tars / condensables) / Bio-crudo (condensables).
    *   $C_{\text{gases}}$: Pyrolysis gases (syngas / non-condensables) / Gases de pirólisis.
    """)
    
    st.markdown("---")
    st.markdown("**Arrhenius Parameters in Use / Parámetros de Arrhenius en Uso:**")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"**Reaction 1 / Reacción 1 (Sludge → Bio-oil):**  \n"
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
            f"**Reaction 3 / Reacción 3 (Bio-oil → Gases):**  \n"
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
        "4. **Condensación en 2 Etapas (Tanque 28,000 gal & Furgón Sellado):** La condensación secuencial permite recuperar el bio-crudo con alta eficiencia térmica, separando el agua de arrastre (BS&W) y concentrando una fracción pesada directamente comercializable."
    )
    
    st.subheader(t("guide_sec_1"))
    st.markdown(t("guide_sec_1_text"))
    
    st.subheader(t("guide_sec_2"))
    st.markdown(t("guide_sec_2_text"))
    
    st.subheader(t("guide_sec_3"))
    st.markdown(t("guide_sec_3_text"))
    
    st.subheader(t("guide_sec_4"))
    st.markdown(t("guide_sec_4_text"))

def render_export_tab(mode_option, results, summary, solver_inputs=None, config_dict=None):
    """Renders the data export tab content including Thesis PDF generation."""
    st.subheader(t("export_title"))
    st.markdown(t("export_desc"))
    
    col_pdf, col_word, col_csv = st.columns(3)
    
    with col_pdf:
        st.markdown("### 🎓 Reporte de Tesis (PDF)")
        st.info(t("export_pdf_desc"))
        
        if not REPORTLAB_AVAILABLE:
            st.warning("⚠️ **La librería `reportlab` no está instalada en el entorno de Python de su servidor.**\n\nPara habilitar la generación y descarga del reporte de tesis en PDF, ejecute en su servidor / consola:\n```bash\npip install reportlab\n```")
        elif solver_inputs is not None:
            if config_dict is None:
                config_dict = {'lang_option': st.session_state.get('lang_option', 'Español'), 'mode_option': mode_option}
            
            try:
                import importlib
                import pyrolysis.pdf_generator as pdf_mod
                importlib.reload(pdf_mod)
                pdf_bytes = pdf_mod.generate_thesis_pdf(mode_option, results, summary, solver_inputs, config_dict)
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
            if config_dict is None:
                config_dict = {'lang_option': st.session_state.get('lang_option', 'Español'), 'mode_option': mode_option}
            
            try:
                import importlib
                import pyrolysis.docx_generator as docx_mod
                importlib.reload(docx_mod)
                docx_bytes = docx_mod.generate_word_report(mode_option, results, summary, solver_inputs, config_dict)
                word_filename = "Informe_Tecnico_Pirolisis_Reactor_Rotatorio_PROENERGETICOS.docx"
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
        st.markdown("### 📊 Datos de Perfil (CSV)")
        st.caption("Descargue las series temporales/espaciales de temperatura, masa y rendimiento.")
        
        if mode_option == "Continuous Operation":
            export_df = pd.DataFrame({
                'Length_z_m': results['z'],
                'T_Wall_C': results['T_wall'],
                'T_Solids_C': results['T_solid'],
                'T_Gas_C': results['T_gas'],
                'Moisture_Flow_kgh': results['moisture'],
                'Volatiles_Flow_kgh': results['volatile'],
                'Char_Flow_kgh': results['char'],
                'Ash_Flow_kgh': results['ash'],
                'Oil_Vapor_Flow_kgh': results['oil'],
                'Syngas_Flow_kgh': results['gas'],
                'Steam_Flow_kgh': results['steam'],
                'Volatiles_Conversion_pct': np.array(results['conversion']) * 100.0,
                'Bed_Humidity_pct': results['humidity']
            })
            file_name_out = "pyrolysis_continuous_reactor_profile.csv"
        else:
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
    
    st.markdown("---")
    st.subheader(t("export_summary_title"))
    st.write(summary)

