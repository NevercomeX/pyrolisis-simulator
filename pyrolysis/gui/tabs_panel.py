import streamlit as st
import numpy as np
import pandas as pd
from pyrolysis import TRANSLATIONS

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
        comp_df = pd.DataFrame({
            t("analysis_component"): [t("analysis_moisture_name"), t("analysis_volatiles_name"), t("analysis_char_name"), t("analysis_ash_name")],
            t("analysis_wt_pct"): [current_feed.moisture, current_feed.volatile, current_feed.fixed_carbon, current_feed.ash],
            t("analysis_input_load").format(load_unit): [
                load_val * current_feed.moisture / 100.0,
                load_val * current_feed.volatile / 100.0,
                load_val * current_feed.fixed_carbon / 100.0,
                load_val * current_feed.ash / 100.0
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
        st.markdown(f"**{t('analysis_volatile_splits')}**")
        yields_df = pd.DataFrame({
            t("analysis_prod_fraction"): [t("analysis_bio_oil_name"), t("analysis_syngas_name"), t("analysis_char_res_name")],
            t("analysis_frac_wt"): [current_feed.yield_oil, current_feed.yield_gas, current_feed.yield_char]
        })
        st.table(yields_df)

def render_balances_tab(mode_option, current_feed, results, summary, feed_rate_kgh, batch_load_kg, feed_option):
    """Renders the mass and energy balances tab content."""
    lang = get_lang()
    
    if mode_option == "Continuous Operation":
        st.markdown("### ⚖️ Mass Balance / Balance de Materia")
        load_val = feed_rate_kgh
        
        feed_name_display = t("feed_custom") if feed_option == "Custom Feedstock" else current_feed.name
        mass_in_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [feed_name_display],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [100.0],
            "Flow Rate / Flujo (kg/h)": [load_val]
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
            * **Error de Cierre de Balance**:
              $$\text{Error (\%)} = \frac{|F_{inlet} - F_{outlet\_total}|}{F_{inlet}} \times 100$$
            """)
        else:
            st.markdown(r"""
            #### 📝 Mass Balance Equations (Continuous)
            The mass balance is based on the conservation of mass entering and leaving the reactor:
            $$F_{inlet} = F_{char} + F_{oil} + F_{gas} + F_{steam} + F_{moist, final}$$
            * **Bio-Oil**: Integrated locally from primary formation and secondary cracking to syngas:
              $$F_{oil} = \int_{0}^{L} \left( k_1 \cdot C_{\text{slug}} - k_3 \cdot C_{\text{medios, local}} \right) \frac{dz}{v_s}$$
            * **Syngas**: Integrated locally from primary gasification and secondary tar cracking:
              $$F_{gas} = \int_{0}^{L} \left( k_2 \cdot C_{\text{slug}} + k_3 \cdot C_{\text{medios, local}} \right) \frac{dz}{v_s}$$
            * **Residual Bio-Char (Char - Dry)**: Sum of initial fixed carbon, ash, and unreacted volatiles:
              $$F_{char} = F_{fixed\_carbon, initial} + F_{ash, initial} + F_{volatile, unreacted}$$
            * **Water Vapor (Steam)**: Evaporated moisture from the solid bed:
              $$F_{steam} = F_{moisture, initial} - F_{moisture, final}$$
            * **Mass Balance Closure Error**:
              $$\text{Error (\%)} = \frac{|F_{inlet} - F_{outlet\_total}|}{F_{inlet}} \times 100$$
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
        
        Q_char = F_char_s * 1000.0 * (T_out - T_in)
        Q_pyro = (F_oil_s + F_gas_s) * (1800.0 * (T_out - T_in) + 600000.0)
        if T_in < 100.0:
            Q_steam = F_steam_s * (4184.0 * (100.0 - T_in) + 2256000.0 + 2000.0 * (max(T_gas_out, 100.0) - 100.0))
        else:
            Q_steam = F_steam_s * (2256000.0 + 2000.0 * (max(T_gas_out, T_in) - T_in))
            
        Q_char_kw = Q_char / 1000.0
        Q_pyro_kw = Q_pyro / 1000.0
        Q_steam_kw = Q_steam / 1000.0
        Q_total_kw = Q_char_kw + Q_pyro_kw + Q_steam_kw
        
        energy_df = pd.DataFrame({
            "Process Stage / Etapa del Proceso": [
                "Sensible Heat of Bed Solids (Calentamiento del Sólido)",
                "Evaporation & Dehydration (Evaporación del Agua)",
                "Pyrolysis Volatiles Cracking Heat (Reacción de Pirólisis)",
                "Total Thermal Heating Duty (Potencia Térmica Total)"
            ],
            "Heat Rate / Flujo de Calor (kW)": [
                Q_char_kw,
                Q_steam_kw,
                Q_pyro_kw,
                Q_total_kw
            ],
            "Fraction of Total / Porcentaje del Total (%)": [
                (Q_char_kw / Q_total_kw * 100.0) if Q_total_kw > 0 else 0,
                (Q_steam_kw / Q_total_kw * 100.0) if Q_total_kw > 0 else 0,
                (Q_pyro_kw / Q_total_kw * 100.0) if Q_total_kw > 0 else 0,
                100.0
            ]
        })
        st.table(energy_df)
        
        if lang == 'es':
            st.markdown(r"""
            #### 📝 Ecuaciones del Balance de Energía (Continuo)
            La demanda térmica total ($Q_{total}$) del reactor continuo se divide en tres flujos principales de transferencia calorífica:
            $$Q_{total} = Q_{solids} + Q_{steam} + Q_{pyro}$$
            * **Calor Sensible de Sólidos ($Q_{solids}$)**: Energía necesaria para calentar el lecho de sólidos desde la temperatura de entrada ($T_{in}$) hasta la de salida ($T_{out}$):
              $$Q_{solids} = F_{char} \cdot Cp_{char} \cdot (T_{out} - T_{in})$$
              Donde $Cp_{char} = 1000\text{ J/kg}\cdot\text{K}$ (capacidad calorífica promedio del char/carbón).
            * **Evaporación del Agua ($Q_{steam}$)**: Calor para precalentar la humedad, vaporizar el agua (secado endotérmico) y sobrecalentar el vapor saliente ($T_{gas, out}$):
              * Si $T_{in} < 100^\circ\text{C}$:
                $$Q_{steam} = F_{steam} \cdot \left[ Cp_{water} \cdot (100 - T_{in}) + \Delta H_{evap} + Cp_{steam} \cdot (\max(T_{gas, out}, 100) - 100) \right]$$
              * Si $T_{in} \ge 100^\circ\text{C}$:
                $$Q_{steam} = F_{steam} \cdot \left[ \Delta H_{evap} + Cp_{steam} \cdot (\max(T_{gas, out}, T_{in}) - T_{in}) \right]$$
              Donde $Cp_{water} = 4184\text{ J/kg}\cdot\text{K}$, calor latente de evaporación $\Delta H_{evap} = 2,256,000\text{ J/kg}$ y $Cp_{steam} = 2000\text{ J/kg}\cdot\text{K}$.
            * **Reacción de Pirólisis ($Q_{pyro}$)**: Calor sensible de los volátiles que reaccionan más la energía de reacción endotérmica de descomposición térmica ($\Delta H_{pyro}$):
              $$Q_{pyro} = (F_{oil} + F_{gas}) \cdot \left[ Cp_{volatile} \cdot (T_{out} - T_{in}) + \Delta H_{pyro} \right]$$
              Donde $Cp_{volatile} = 1800\text{ J/kg}\cdot\text{K}$ y entalpía de pirólisis $\Delta H_{pyro} = 600,000\text{ J/kg}$.
            """)
        else:
            st.markdown(r"""
            #### 📝 Energy Balance Equations (Continuous)
            The total thermal demand ($Q_{total}$) of the continuous reactor is divided into three main heat transfer duties:
            $$Q_{total} = Q_{solids} + Q_{steam} + Q_{pyro}$$
            * **Sensible Heat of Solids ($Q_{solids}$)**: Energy needed to heat the solid bed from the inlet temperature ($T_{in}$) to the outlet temperature ($T_{out}$):
              $$Q_{solids} = F_{char} \cdot Cp_{char} \cdot (T_{out} - T_{in})$$
              Where $Cp_{char} = 1000\text{ J/kg}\cdot\text{K}$ (average heat capacity of char/carbon).
            * **Evaporation of Water ($Q_{steam}$)**: Heat to preheat the moisture, vaporize the water (endothermic drying), and superheat the leaving steam ($T_{gas, out}$):
              * If $T_{in} < 100^\circ\text{C}$:
                $$Q_{steam} = F_{steam} \cdot \left[ Cp_{water} \cdot (100 - T_{in}) + \Delta H_{evap} + Cp_{steam} \cdot (\max(T_{gas, out}, 100) - 100) \right]$$
              * If $T_{in} \ge 100^\circ\text{C}$:
                $$Q_{steam} = F_{steam} \cdot \left[ \Delta H_{evap} + Cp_{steam} \cdot (\max(T_{gas, out}, T_{in}) - T_{in}) \right]$$
              Where $Cp_{water} = 4184\text{ J/kg}\cdot\text{K}$, latent heat of vaporization $\Delta H_{evap} = 2,256,000\text{ J/kg}$, and $Cp_{steam} = 2000\text{ J/kg}\cdot\text{K}$.
            * **Pyrolysis Reaction ($Q_{pyro}$)**: Sensible heat of the volatiles that react plus the endothermic thermal cracking reaction energy ($\Delta H_{pyro}$):
              $$Q_{pyro} = (F_{oil} + F_{gas}) \cdot \left[ Cp_{volatile} \cdot (T_{out} - T_{in}) + \Delta H_{pyro} \right]$$
              Where $Cp_{volatile} = 1800\text{ J/kg}\cdot\text{K}$ and pyrolysis enthalpy $\Delta H_{pyro} = 600,000\text{ J/kg}$.
            """)
        
    else:
        st.markdown("### ⚖️ Mass Balance / Balance de Materia")
        load_val = batch_load_kg
        
        feed_name_display = t("feed_custom") if feed_option == "Custom Feedstock" else current_feed.name
        mass_in_df = pd.DataFrame({
            t("analysis_component") if "analysis_component" in TRANSLATIONS[lang] else "Component": [feed_name_display],
            t("analysis_wt_pct") if "analysis_wt_pct" in TRANSLATIONS[lang] else "wt%": [100.0],
            "Load / Carga (kg)": [load_val]
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
            * **Mass Balance Closure Error**:
              $$\text{Error (\%)} = \frac{|M_{load} - M_{output\_total}|}{M_{load}} \times 100$$
            """)
        
        st.markdown("---")
        st.markdown("### ⚡ Energy Balance / Balance de Energía")
        
        M_oil = summary['oil_yield_kg']
        M_gas = summary['gas_yield_kg']
        M_char = summary['char_yield_kg']
        M_steam = summary['water_yield_kg']
        T_start = results['T_solid'][0]
        T_hold = results['T_solid'][-1]
        
        # Energies in Joules
        E_char = M_char * 1000.0 * (T_hold - T_start)
        E_pyro = (M_oil + M_gas) * (1800.0 * (T_hold - T_start) + 600000.0)
        if T_hold >= 100.0:
            E_steam = M_steam * (4184.0 * (100.0 - T_start) + 2256000.0 + 2000.0 * (T_hold - 100.0))
        else:
            E_steam = M_steam * (4184.0 * (T_hold - T_start))
            
        # Convert to kWh
        E_char_kwh = E_char / 3.6e6
        E_pyro_kwh = E_pyro / 3.6e6
        E_steam_kwh = E_steam / 3.6e6
        E_total_kwh = E_char_kwh + E_pyro_kwh + E_steam_kwh
        
        energy_df = pd.DataFrame({
            "Process Stage / Etapa del Proceso": [
                "Sensible Heat of Bed Solids (Calentamiento del Sólido)",
                "Evaporation & Dehydration (Evaporación del Agua)",
                "Pyrolysis Volatiles Cracking Heat (Reacción de Pirólisis)",
                "Total Thermal Energy Supplied (Energía Térmica Total)"
            ],
            "Energy / Energía (kWh)": [
                E_char_kwh,
                E_steam_kwh,
                E_pyro_kwh,
                E_total_kwh
            ],
            "Fraction of Total / Porcentaje del Total (%)": [
                (E_char_kwh / E_total_kwh * 100.0) if E_total_kwh > 0 else 0,
                (E_steam_kwh / E_total_kwh * 100.0) if E_total_kwh > 0 else 0,
                (E_pyro_kwh / E_total_kwh * 100.0) if E_total_kwh > 0 else 0,
                100.0
            ]
        })
        st.table(energy_df)
        
        if lang == 'es':
            st.markdown(r"""
            #### 📝 Ecuaciones del Balance de Energía (Lote)
            La energía térmica total suministrada ($E_{total}$) durante todo el ciclo del lote (en kWh) se desglosa en:
            $$E_{total} = E_{solids} + E_{steam} + E_{pyro}$$
            * **Calor Sensible de Sólidos ($E_{solids}$)**: Energía transferida para calentar los sólidos del lecho desde la temperatura inicial ($T_{start}$) hasta la final ($T_{hold}$):
              $$E_{solids} = M_{char} \cdot Cp_{char} \cdot (T_{hold} - T_{start}) / 3.6\times 10^6$$
              Donde $Cp_{char} = 1000\text{ J/kg}\cdot\text{K}$ y la división por $3.6\times 10^6$ convierte Julios a kWh.
            * **Evaporación y Deshidratación ($E_{steam}$)**: Energía para calentar el agua líquida hasta 100°C, vaporizarla por completo y sobrecalentar el vapor:
              * Si $T_{hold} \ge 100^\circ\text{C}$:
                $$E_{steam} = M_{steam} \cdot \left[ Cp_{water} \cdot (100 - T_{start}) + \Delta H_{evap} + Cp_{steam} \cdot (T_{hold} - 100) \right] / 3.6\times 10^6$$
              * Si $T_{hold} < 100^\circ\text{C}$:
                $$E_{steam} = M_{steam} \cdot \left[ Cp_{water} \cdot (T_{hold} - T_{start}) \right] / 3.6\times 10^6$$
              Donde $Cp_{water} = 4184\text{ J/kg}\cdot\text{K}$, calor latente $\Delta H_{evap} = 2,256,000\text{ J/kg}$ y $Cp_{steam} = 2000\text{ J/kg}\cdot\text{K}$.
            * **Reacción de Pirólisis ($E_{pyro}$)**: Calor sensible de volátiles reaccionados más calor de craqueo químico endotérmico:
              $$E_{pyro} = (M_{oil} + M_{gas}) \cdot \left[ Cp_{volatile} \cdot (T_{hold} - T_{start}) + \Delta H_{pyro} \right] / 3.6\times 10^6$$
              Donde $Cp_{volatile} = 1800\text{ J/kg}\cdot\text{K}$ y calor de pirólisis $\Delta H_{pyro} = 600,000\text{ J/kg}$.
            """)
        else:
            st.markdown(r"""
            #### 📝 Energy Balance Equations (Batch)
            The total thermal energy supplied ($E_{total}$) during the entire batch cycle (in kWh) is broken down into:
            $$E_{total} = E_{solids} + E_{steam} + E_{pyro}$$
            * **Sensible Heat of Solids ($E_{solids}$)**: Energy transferred to heat the bed solids from the initial temperature ($T_{start}$) to the final hold temperature ($T_{hold}$):
              $$E_{solids} = M_{char} \cdot Cp_{char} \cdot (T_{hold} - T_{start}) / 3.6\times 10^6$$
              Where $Cp_{char} = 1000\text{ J/kg}\cdot\text{K}$ and division by $3.6\times 10^6$ converts Joules to kWh.
            * **Evaporation & Dehydration ($E_{steam}$)**: Energy to heat liquid water to 100°C, vaporize it completely, and superheat the steam:
              * If $T_{hold} \ge 100^\circ\text{C}$:
                $$E_{steam} = M_{steam} \cdot \left[ Cp_{water} \cdot (100 - T_{start}) + \Delta H_{evap} + Cp_{steam} \cdot (T_{hold} - 100) \right] / 3.6\times 10^6$$
              * If $T_{hold} < 100^\circ\text{C}$:
                $$E_{steam} = M_{steam} \cdot \left[ Cp_{water} \cdot (T_{hold} - T_{start}) \right] / 3.6\times 10^6$$
              Where $Cp_{water} = 4184\text{ J/kg}\cdot\text{K}$, latent heat $\Delta H_{evap} = 2,256,000\text{ J/kg}$, and $Cp_{steam} = 2000\text{ J/kg}\cdot\text{K}$.
            * **Pyrolysis Reaction ($E_{pyro}$)**: Sensible heat of reacted volatiles plus endothermic chemical cracking heat:
              $$E_{pyro} = (M_{oil} + M_{gas}) \cdot \left[ Cp_{volatile} \cdot (T_{hold} - T_{start}) + \Delta H_{pyro} \right] / 3.6\times 10^6$$
              Where $Cp_{volatile} = 1800\text{ J/kg}\cdot\text{K}$ and pyrolysis heat $\Delta H_{pyro} = 600,000\text{ J/kg}$.
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
    
    st.subheader(t("guide_sec_1"))
    st.markdown(t("guide_sec_1_text"))
    
    st.subheader(t("guide_sec_2"))
    st.markdown(t("guide_sec_2_text"))
    
    st.subheader(t("guide_sec_3"))
    st.markdown(t("guide_sec_3_text"))
    
    st.subheader(t("guide_sec_4"))
    st.markdown(t("guide_sec_4_text"))

def render_export_tab(mode_option, results, summary):
    """Renders the data export tab content."""
    st.subheader(t("export_title"))
    st.markdown(t("export_desc"))
    
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
    
    st.subheader(t("export_summary_title"))
    st.write(summary)

