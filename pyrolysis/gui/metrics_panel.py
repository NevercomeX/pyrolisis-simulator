import streamlit as st
import pandas as pd
import numpy as np
from pyrolysis import TRANSLATIONS, get_fuel_translation

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def render_metrics_panel(mode_option, summary, results):
    """
    Renders metrics cards for mass yield, estimated volumetric yields,
    and operational diagnostics along with necessary status warning cards.
    
    Args:
        mode_option (str): "Continuous Operation" or "Batch Operation".
        summary (dict): The summary dictionary returned by the reactor simulation.
        results (dict): The full results dictionary containing profile arrays.
    """
    lang = get_lang()
    fuel_type = st.session_state.get('fuel_type', "Waste Oil / Aceite Residual")
    fuel_label = get_fuel_translation(lang, 'waste_oil_consumed_metric', fuel_type)

    if mode_option == "Continuous Operation":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(t("bio_oil_yield_metric"), f"{summary['oil_yield_kgh']:.1f} kg/h", f"{summary['oil_yield_pct']:.1f} wt.%")
        with col2:
            st.metric(t("syngas_yield_metric"), f"{summary['gas_yield_kgh']:.1f} kg/h", f"{summary['gas_yield_pct']:.1f} wt.%")
        with col3:
            st.metric(t("char_yield_metric"), f"{summary['char_yield_kgh']:.1f} kg/h", f"{summary['char_yield_pct']:.1f} wt.%")
        with col4:
            st.metric(t("water_vapor_metric"), f"{summary['water_yield_kgh']:.1f} kg/h", f"{summary['water_yield_pct']:.1f} wt.%")
            
        st.markdown(t("volumetric_yields_header"))
        vcol1, vcol2, vcol3, vcol4, vcol5 = st.columns(5)
        oil_density = float(st.session_state.get('bio_oil_density', 750.0))
        oil_gal_h = (summary['oil_yield_kgh'] / oil_density) * 264.172
        gas_m3_h = summary['gas_yield_kgh'] / 1.15
        char_gal_h = (summary['char_yield_kgh'] / 500.0) * 264.172
        water_gal_h = (summary['water_yield_kgh'] / 1000.0) * 264.172
        waste_oil_gal_h = summary.get('waste_oil_consumed_galh', 0.0)
        
        with vcol1:
            st.metric(t("bio_oil_vol_metric"), f"{oil_gal_h:.1f} gal/h")
        with vcol2:
            st.metric(t("syngas_vol_metric"), f"{gas_m3_h:.1f} m³/h")
        with vcol3:
            st.metric(t("char_vol_metric"), f"{char_gal_h:.1f} gal/h")
        with vcol4:
            st.metric(t("water_vol_metric"), f"{water_gal_h:.1f} gal/h")
        with vcol5:
            st.metric(fuel_label, f"{waste_oil_gal_h:.1f} gal/h")
            
        st.markdown(t("diagnostics"))
        dcol1, dcol2, dcol3, dcol4, dcol5, dcol6 = st.columns(6)
        with dcol1:
            st.metric(t("mrt"), f"{summary['residence_time_min']:.1f} min")
        with dcol2:
            fill_deg = summary['filling_degree_pct']
            st.metric(t("filling_degree"), f"{fill_deg:.2f} %")
        with dcol3:
            st.metric(t("heating_duty"), f"{summary['heating_duty_kw']:.2f} kW")
        with dcol4:
            st.metric(t("volatiles_conv"), f"{summary['conversion_pct']:.1f} %")
        with dcol5:
            st.metric(t("inlet_humidity"), f"{summary['inlet_humidity_pct']:.1f} wt.%")
        with dcol6:
            st.metric(t("outlet_humidity"), f"{summary['outlet_humidity_pct']:.1f} wt.%")
            
        if fill_deg > 15.0:
            st.warning(t("warn_high_fill"))
        elif fill_deg < 2.0:
            st.info(t("warn_low_fill"))
        if summary['conversion_pct'] < 95.0:
            st.error(t("warn_incomplete_pyro").format(summary['conversion_pct']))

        # --- Continuous Process Timeline & Milestones ---
        z_arr = results['z']
        moist_arr = results['moisture']
        conv_arr = results['conversion']
        temp_s_arr = results['T_solid']
        length_total = z_arr[-1] if len(z_arr) > 0 else 1.0
        res_time_total = summary['residence_time_min']
        
        time_arr = [(z / length_total) * res_time_total if length_total > 0 else 0.0 for z in z_arr]
        
        # 1. Drying complete
        z_drying_end, t_drying_end = None, None
        initial_moisture = moist_arr[0]
        if initial_moisture > 0:
            for i, m in enumerate(moist_arr):
                if m <= 0.005 * initial_moisture:
                    z_drying_end = z_arr[i]
                    t_drying_end = time_arr[i]
                    break
        else:
            z_drying_end, t_drying_end = 0.0, 0.0
            
        # 2. Pyrolysis start
        z_pyro_start, t_pyro_start = None, None
        for i, c in enumerate(conv_arr):
            if c >= 0.01 or temp_s_arr[i] >= 220.0:
                z_pyro_start = z_arr[i]
                t_pyro_start = time_arr[i]
                break
                
        # 3. Pyrolysis end
        z_pyro_end, t_pyro_end = None, None
        final_conv = conv_arr[-1]
        if final_conv > 0.01:
            for i, c in enumerate(conv_arr):
                if c >= 0.995 * final_conv:
                    z_pyro_end = z_arr[i]
                    t_pyro_end = time_arr[i]
                    break
                    
        st.markdown("---")
        st.markdown(f"### {t('timeline_header')}")
        
        tcol1, tcol2, tcol3 = st.columns(3)
        with tcol1:
            val_dry = f"{z_drying_end:.2f} m ({t_drying_end:.1f} min)" if t_drying_end is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_drying_end"), value=val_dry)
        with tcol2:
            val_start = f"{z_pyro_start:.2f} m ({t_pyro_start:.1f} min)" if t_pyro_start is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_pyro_start"), value=val_start)
        with tcol3:
            val_end = f"{z_pyro_end:.2f} m ({t_pyro_end:.1f} min)" if t_pyro_end is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_pyro_end"), value=val_end)
            
        st.markdown(f"##### 📅 {t('timeline_time_elapsed')} / {t('timeline_distance')}")
        col_lbl_l, col_lbl_r = st.columns(2)
        with col_lbl_l:
            st.write(f"* **{t('timeline_bio_oil_end')}:** `{val_end}`")
            st.write(f"* **{t('timeline_syngas_end')}:** `{val_end}`")
        with col_lbl_r:
            st.write(f"* **{t('timeline_char_end')}:** `{val_end}`")
            st.write(f"* **{t('timeline_drying_end')}:** `{val_dry}`")
        
        st.markdown("---")
        st.markdown(f"### {t('summary_yields_header')}")
        
        scol1, scol2 = st.columns(2)
        with scol1:
            st.markdown(f"**{t('summary_solid_in_rate')}**")
            m_in_moist = results['moisture'][0]
            m_in_volatile = results['volatile'][0]
            m_in_char = results['char'][0]
            m_in_ash = results['ash'][0]
            m_in_total = m_in_moist + m_in_volatile + m_in_char + m_in_ash
            
            in_df = pd.DataFrame({
                t("analysis_component"): [
                    t("analysis_moisture_name"),
                    t("analysis_volatiles_name"),
                    t("analysis_char_name"),
                    t("analysis_ash_name"),
                    "Total"
                ],
                "Flujo / Flow Rate (kg/h)": [
                    m_in_moist,
                    m_in_volatile,
                    m_in_char,
                    m_in_ash,
                    m_in_total
                ],
                "Fracción / Fraction (%)": [
                    (m_in_moist / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_volatile / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_char / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_ash / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    100.0
                ]
            })
            st.table(in_df.style.format({"Flujo / Flow Rate (kg/h)": "{:.2f}", "Fracción / Fraction (%)": "{:.1f}%"}))
            
        with scol2:
            st.markdown(f"**{t('summary_products_out_rate')}**")
            m_out_oil = summary['oil_yield_kgh']
            m_out_gas = summary['gas_yield_kgh']
            m_out_char = summary['char_yield_kgh']
            m_out_water = summary['water_yield_kgh']
            m_out_total = m_out_oil + m_out_gas + m_out_char + m_out_water
            
            oil_density = float(st.session_state.get('bio_oil_density', 750.0))
            oil_gal_h = (m_out_oil / oil_density) * 264.172
            gas_m3_h = m_out_gas / 1.15
            water_gal_h = (m_out_water / 1000.0) * 264.172
            
            out_df = pd.DataFrame({
                t("analysis_component"): [
                    t("analysis_bio_oil_name"),
                    t("analysis_syngas_name"),
                    t("analysis_char_name"),
                    t("water_vapor_metric"),
                    "Total"
                ],
                "Flujo / Flow Rate (kg/h)": [
                    m_out_oil,
                    m_out_gas,
                    m_out_char,
                    m_out_water,
                    m_out_total
                ],
                "Volumen / Volume": [
                    f"{oil_gal_h:.1f} gal/h",
                    f"{gas_m3_h:.1f} m³/h",
                    "-",
                    f"{water_gal_h:.1f} gal/h",
                    "-"
                ]
            })
            st.table(out_df.style.format({"Flujo / Flow Rate (kg/h)": "{:.2f}"}))

    else:  # Batch Operation
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(t("bio_oil_prod_metric"), f"{summary['oil_yield_kg']:.1f} kg", f"{summary['oil_yield_pct']:.1f} wt.%")
        with col2:
            st.metric(t("syngas_prod_metric"), f"{summary['gas_yield_kg']:.1f} kg", f"{summary['gas_yield_pct']:.1f} wt.%")
        with col3:
            st.metric(t("char_rem_metric"), f"{summary['char_yield_kg']:.1f} kg", f"{summary['char_yield_pct']:.1f} wt.%")
        with col4:
            st.metric(t("water_evap_metric"), f"{summary['water_yield_kg']:.1f} kg", f"{summary['water_yield_pct']:.1f} wt.%")
            
        st.markdown(t("volumetric_yields_header"))
        vcol1, vcol2, vcol3, vcol4, vcol5 = st.columns(5)
        oil_density = float(st.session_state.get('bio_oil_density', 750.0))
        oil_gal = (summary['oil_yield_kg'] / oil_density) * 264.172
        gas_m3 = summary['gas_yield_kg'] / 1.15
        char_gal = (summary['char_yield_kg'] / 500.0) * 264.172
        water_gal = (summary['water_yield_kg'] / 1000.0) * 264.172
        waste_oil_gal = summary.get('waste_oil_consumed_gal', 0.0)
        
        with vcol1:
            st.metric(t("bio_oil_vol_metric"), f"{oil_gal:.1f} gal")
        with vcol2:
            st.metric(t("syngas_vol_metric"), f"{gas_m3:.1f} m³")
        with vcol3:
            st.metric(t("char_vol_metric"), f"{char_gal:.1f} gal")
        with vcol4:
            st.metric(t("water_vol_metric"), f"{water_gal:.1f} gal")
        with vcol5:
            st.metric(fuel_label, f"{waste_oil_gal:.1f} gal")
            
        st.markdown(t("diagnostics_batch"))
        dcol1, dcol2, dcol3, dcol4, dcol5, dcol6 = st.columns(6)
        with dcol1:
            st.metric(t("filling_degree_static"), f"{summary['filling_degree_pct']:.2f} %")
        with dcol2:
            st.metric(t("total_cycle_energy"), f"{summary['total_energy_kwh']:.2f} kWh")
        with dcol3:
            st.metric(t("volatiles_conv"), f"{summary['conversion_pct']:.1f} %")
        with dcol4:
            st.metric(t("mass_balance_error"), f"{summary['mass_error_pct']:.2e} %")
        with dcol5:
            st.metric(t("initial_humidity"), f"{summary['initial_humidity_pct']:.1f} wt.%")
        with dcol6:
            st.metric(t("final_humidity"), f"{summary['final_humidity_pct']:.1f} wt.%")
            
        fill_deg = summary['filling_degree_pct']
        if fill_deg > 50.0:
            st.error(t("warn_max_load_batch").format(fill_deg))
        elif 30.0 <= fill_deg <= 35.0:
            st.success(t("info_optimal_load_batch").format(fill_deg))
        elif fill_deg < 30.0:
            st.info(t("info_suboptimal_load_batch").format(fill_deg))
        else: # 35.0 < fill_deg <= 50.0
            st.warning(t("warn_high_load_batch_acceptable").format(fill_deg))
            
        if summary['conversion_pct'] < 95.0:
            st.error(t("warn_incomplete_batch").format(summary['conversion_pct']))

        # --- Batch Process Timeline & Milestones ---
        time_arr = results['time']
        moist_arr = results['moisture']
        conv_arr = results['conversion']
        temp_s_arr = results['T_solid']
        
        # 1. Drying complete
        t_drying_end = None
        initial_moisture = moist_arr[0]
        if initial_moisture > 0:
            for i, m in enumerate(moist_arr):
                if m <= 0.005 * initial_moisture:
                    t_drying_end = time_arr[i]
                    break
        else:
            t_drying_end = 0.0
            
        # 2. Pyrolysis start
        t_pyro_start = None
        for i, c in enumerate(conv_arr):
            if c >= 0.01 or temp_s_arr[i] >= 220.0:
                t_pyro_start = time_arr[i]
                break
                
        # 3. Pyrolysis end
        t_pyro_end = None
        final_conv = conv_arr[-1]
        if final_conv > 0.01:
            for i, c in enumerate(conv_arr):
                if c >= 0.995 * final_conv:
                    t_pyro_end = time_arr[i]
                    break
                    
        st.markdown("---")
        st.markdown(f"### {t('timeline_header')}")
        
        tcol1, tcol2, tcol3 = st.columns(3)
        with tcol1:
            val_dry = f"{t_drying_end:.1f} min" if t_drying_end is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_drying_end"), value=val_dry)
        with tcol2:
            val_start = f"{t_pyro_start:.1f} min" if t_pyro_start is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_pyro_start"), value=val_start)
        with tcol3:
            val_end = f"{t_pyro_end:.1f} min" if t_pyro_end is not None else t("timeline_not_completed")
            st.metric(label=t("timeline_pyro_end"), value=val_end)
            
        st.markdown(f"##### 📅 {t('timeline_time_elapsed')}")
        col_lbl_l, col_lbl_r = st.columns(2)
        with col_lbl_l:
            st.write(f"* **{t('timeline_bio_oil_end')}:** `{val_end}`")
            st.write(f"* **{t('timeline_syngas_end')}:** `{val_end}`")
        with col_lbl_r:
            st.write(f"* **{t('timeline_char_end')}:** `{val_end}`")
            st.write(f"* **{t('timeline_drying_end')}:** `{val_dry}`")
            
        st.markdown("---")
        st.markdown(f"### {t('summary_yields_header')}")
        
        scol1, scol2 = st.columns(2)
        with scol1:
            st.markdown(f"**{t('summary_solid_in')}**")
            m_in_moist = results['moisture'][0]
            m_in_volatile = results['volatile'][0]
            m_in_char = results['char'][0]
            m_in_ash = results['ash'][0]
            m_in_total = m_in_moist + m_in_volatile + m_in_char + m_in_ash
            
            in_df = pd.DataFrame({
                t("analysis_component"): [
                    t("analysis_moisture_name"),
                    t("analysis_volatiles_name"),
                    t("analysis_char_name"),
                    t("analysis_ash_name"),
                    "Total"
                ],
                "Masa / Mass (kg)": [
                    m_in_moist,
                    m_in_volatile,
                    m_in_char,
                    m_in_ash,
                    m_in_total
                ],
                "Fracción / Fraction (%)": [
                    (m_in_moist / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_volatile / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_char / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    (m_in_ash / m_in_total * 100.0) if m_in_total > 0 else 0.0,
                    100.0
                ]
            })
            st.table(in_df.style.format({"Masa / Mass (kg)": "{:.2f}", "Fracción / Fraction (%)": "{:.1f}%"}))
            
        with scol2:
            st.markdown(f"**{t('summary_products_out')}**")
            m_out_oil = summary['oil_yield_kg']
            m_out_gas = summary['gas_yield_kg']
            m_out_char = summary['char_yield_kg']
            m_out_water = summary['water_yield_kg']
            m_out_total = m_out_oil + m_out_gas + m_out_char + m_out_water
            
            oil_density = float(st.session_state.get('bio_oil_density', 750.0))
            oil_gal = (m_out_oil / oil_density) * 264.172
            gas_m3 = m_out_gas / 1.15
            water_gal = (m_out_water / 1000.0) * 264.172
            
            out_df = pd.DataFrame({
                t("analysis_component"): [
                    t("analysis_bio_oil_name"),
                    t("analysis_syngas_name"),
                    t("analysis_char_name"),
                    t("water_vapor_metric"),
                    "Total"
                ],
                "Masa / Mass (kg)": [
                    m_out_oil,
                    m_out_gas,
                    m_out_char,
                    m_out_water,
                    m_out_total
                ],
                "Volumen / Volume": [
                    f"{oil_gal:.1f} gal",
                    f"{gas_m3:.1f} m³",
                    "-",
                    f"{water_gal:.1f} gal",
                    "-"
                ]
            })
            st.table(out_df.style.format({"Masa / Mass (kg)": "{:.2f}"}))
