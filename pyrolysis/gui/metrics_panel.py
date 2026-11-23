import streamlit as st
import pandas as pd
from pyrolysis import get_fuel_translation
from .utils import get_lang, t, product_volumes, sludge_gal

# Process milestones (timeline section)
DRYING_END_MOISTURE_FRAC = 0.005   # drying ends when 0.5 % of the initial moisture is left
MIN_CONVERSION = 0.01              # pyrolysis has started once 1 % of the volatiles converted
PYRO_START_TEMP_C = 220.0          # ... or once the bed reaches this temperature
PYRO_END_CONV_FRAC = 0.995         # pyrolysis ends at 99.5 % of the final conversion


def render_metrics_panel(summary, results):
    """
    Renders metrics cards for mass yield, estimated volumetric yields,
    and operational diagnostics along with necessary status warning cards.

    Args:
        summary (dict): The summary dictionary returned by the reactor simulation.
        results (dict): The full results dictionary containing profile arrays.
    """
    fuel_type = st.session_state.get('fuel_type', "Waste Oil / Aceite Residual")
    fuel_label = get_fuel_translation(get_lang(), 'waste_oil_consumed_metric', fuel_type)

    _render_batch_metrics(summary, results, fuel_label)


def _milestones(x_arr, moist_arr, conv_arr, temp_s_arr):
    """Values of x_arr (time) where drying ends, pyrolysis starts and pyrolysis ends.
    None when the milestone is never reached; drying is 0.0 for a feed without moisture."""
    x_drying_end = None
    initial_moisture = moist_arr[0]
    if initial_moisture > 0:
        for i, m in enumerate(moist_arr):
            if m <= DRYING_END_MOISTURE_FRAC * initial_moisture:
                x_drying_end = x_arr[i]
                break
    else:
        x_drying_end = 0.0

    x_pyro_start = None
    for i, c in enumerate(conv_arr):
        if c >= MIN_CONVERSION or temp_s_arr[i] >= PYRO_START_TEMP_C:
            x_pyro_start = x_arr[i]
            break

    x_pyro_end = None
    final_conv = conv_arr[-1]
    if final_conv > MIN_CONVERSION:
        for i, c in enumerate(conv_arr):
            if c >= PYRO_END_CONV_FRAC * final_conv:
                x_pyro_end = x_arr[i]
                break

    return x_drying_end, x_pyro_start, x_pyro_end


def _render_timeline(val_dry, val_start, val_end, subtitle):
    """Milestone cards plus the per-product end list."""
    st.markdown("---")
    st.markdown(f"### {t('timeline_header')}")

    tcol1, tcol2, tcol3 = st.columns(3)
    with tcol1:
        st.metric(label=t("timeline_drying_end"), value=val_dry)
    with tcol2:
        st.metric(label=t("timeline_pyro_start"), value=val_start)
    with tcol3:
        st.metric(label=t("timeline_pyro_end"), value=val_end)

    st.markdown(subtitle)
    col_lbl_l, col_lbl_r = st.columns(2)
    with col_lbl_l:
        st.write(f"* **{t('timeline_bio_oil_end')}:** `{val_end}`")
        st.write(f"* **{t('timeline_syngas_end')}:** `{val_end}`")
    with col_lbl_r:
        st.write(f"* **{t('timeline_char_end')}:** `{val_end}`")
        st.write(f"* **{t('timeline_drying_end')}:** `{val_dry}`")


def _render_yield_tables(results, summary, in_title, out_title, mass_col, gal_col):
    """Solids in (from the first profile point) and products out, in mass and volume."""
    st.markdown("---")
    st.markdown(f"### {t('summary_yields_header')}")

    scol1, scol2 = st.columns(2)
    with scol1:
        st.markdown(f"**{in_title}**")
        m_in = [results['moisture'][0], results['volatile'][0], results['char'][0], results['ash'][0]]
        m_in_total = m_in[0] + m_in[1] + m_in[2] + m_in[3]
        in_df = pd.DataFrame({
            t("analysis_component"): [
                t("analysis_moisture_name"),
                t("analysis_volatiles_name"),
                t("analysis_char_name"),
                t("analysis_ash_name"),
                "Total"
            ],
            mass_col: m_in + [m_in_total],
            gal_col: [sludge_gal(m) for m in m_in + [m_in_total]],
            "Fracción / Fraction (%)": [(m / m_in_total * 100.0) if m_in_total > 0 else 0.0 for m in m_in] + [100.0]
        })
        st.table(in_df.style.format({
            mass_col: "{:.2f}",
            gal_col: "{:.2f}",
            "Fracción / Fraction (%)": "{:.1f}%"
        }))

    with scol2:
        st.markdown(f"**{out_title}**")
        m_out = [summary['oil_yield_kg'], summary['gas_yield_kg'], summary['char_yield_kg'], summary['water_yield_kg']]
        m_out_total = m_out[0] + m_out[1] + m_out[2] + m_out[3]
        oil_gal, gas_m3, char_gal, water_gal = product_volumes(*m_out)

        out_df = pd.DataFrame({
            t("analysis_component"): [
                t("analysis_bio_oil_name"),
                t("analysis_syngas_name"),
                t("analysis_char_name"),
                t("water_vapor_metric"),
                "Total"
            ],
            mass_col: m_out + [m_out_total],
            "Volumen / Volume": [
                f"{oil_gal:.1f} gal",
                f"{gas_m3:.1f} m³",
                f"{char_gal:.1f} gal",
                f"{water_gal:.1f} gal",
                "-"
            ]
        })
        st.table(out_df.style.format({mass_col: "{:.2f}"}))


def _render_volume_metrics(summary, fuel_label, fuel_gal):
    """Row of product volumes plus the burner fuel used."""
    st.markdown(t("volumetric_yields_header"))
    vcol1, vcol2, vcol3, vcol4, vcol5 = st.columns(5)
    oil_gal, gas_m3, char_gal, water_gal = product_volumes(
        summary['oil_yield_kg'], summary['gas_yield_kg'], summary['char_yield_kg'], summary['water_yield_kg'])
    with vcol1:
        st.metric(t("bio_oil_vol_metric"), f"{oil_gal:.1f} gal")
    with vcol2:
        st.metric(t("syngas_vol_metric"), f"{gas_m3:.1f} m³")
    with vcol3:
        st.metric(t("char_vol_metric"), f"{char_gal:.1f} gal")
    with vcol4:
        st.metric(t("water_vol_metric"), f"{water_gal:.1f} gal")
    with vcol5:
        st.metric(fuel_label, f"{fuel_gal:.1f} gal")


def _render_batch_metrics(summary, results, fuel_label):
    """Batch yields, diagnostics, plant metrics, load warnings, milestones in time and yield tables."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(t("bio_oil_prod_metric"), f"{summary['oil_yield_kg']:.1f} kg", f"{summary['oil_yield_pct']:.1f} wt.%")
    with col2:
        st.metric(t("syngas_prod_metric"), f"{summary['gas_yield_kg']:.1f} kg", f"{summary['gas_yield_pct']:.1f} wt.%")
    with col3:
        st.metric(t("char_rem_metric"), f"{summary['char_yield_kg']:.1f} kg", f"{summary['char_yield_pct']:.1f} wt.%")
    with col4:
        st.metric(t("water_evap_metric"), f"{summary['water_yield_kg']:.1f} kg", f"{summary['water_yield_pct']:.1f} wt.%")

    _render_volume_metrics(summary, fuel_label, summary.get('waste_oil_consumed_gal', 0.0))

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

    # PROENERGETICOS Industrial Plant Specs Metrics
    if 'peak_pressure_kpa' in summary:
        st.markdown("---")
        st.markdown(f"### ⚙️ {t('proenergeticos_title')}")
        pcol1, pcol2, pcol3, pcol4, pcol5, pcol6 = st.columns(6)
        with pcol1:
            st.metric(t("auto_pressure_metric"), f"{summary.get('peak_pressure_kpa', 101.3):.1f} kPa", f"{summary.get('peak_pressure_psig', 0.0):.2f} psig")
        with pcol2:
            air_disp_min = summary.get('air_disp_complete_min', float('nan'))
            st.metric(t("air_disp_time_metric"), "N/A" if air_disp_min != air_disp_min else f"{air_disp_min:.1f} min")
        with pcol3:
            st.metric(t("manifold_velocity_metric"), f"{summary.get('max_v_main_ms', 0.0):.2f} m/s", "8'' Manifold / 4x4''")
        with pcol4:
            st.metric(t("syngas_flare_metric"), f"{summary.get('syngas_flare_m3', 0.0):.1f} m³", f"{summary.get('syngas_flare_kg', 0.0):.1f} kg")
        with pcol5:
            st.metric(t("astm_hhv_metric"), "N/D", "Requiere ensayo ASTM D240", delta_color="off")
        with pcol6:
            st.metric(t("astm_viscosity_metric"), "N/D", "Requiere ensayo ASTM D445", delta_color="off")

    # Filling degree: 30-35 % is the target load of the rotary batch reactor
    fill_deg = summary['filling_degree_pct']
    if fill_deg > 50.0:
        st.error(t("warn_max_load_batch").format(fill_deg))
    elif 30.0 <= fill_deg <= 35.0:
        st.success(t("info_optimal_load_batch").format(fill_deg))
    elif fill_deg < 30.0:
        st.info(t("info_suboptimal_load_batch").format(fill_deg))
    else:  # 35.0 < fill_deg <= 50.0
        st.warning(t("warn_high_load_batch_acceptable").format(fill_deg))

    if summary['conversion_pct'] < 95.0:
        st.error(t("warn_incomplete_batch").format(summary['conversion_pct']))

    if summary.get('burner_shortfall_min', 0.0) > 0.0:
        if get_lang() == 'es':
            st.warning(
                f"⚠️ Los quemadores no alcanzan la rampa programada: faltan hasta {summary['burner_shortfall_peak_kw']:.0f} kW "
                f"durante {summary['burner_shortfall_min']:.0f} min. El consumo de combustible y el ciclo reales serían mayores. "
                "Aumente la potencia del quemador, reduzca la rampa o use el modo de calentamiento automático."
            )
        else:
            st.warning(
                f"⚠️ The burners cannot deliver the programmed ramp: short by up to {summary['burner_shortfall_peak_kw']:.0f} kW "
                f"for {summary['burner_shortfall_min']:.0f} min. Real fuel use and cycle time would be higher. "
                "Increase burner power, lower the ramp rate, or use auto heating mode."
            )

    t_dry, t_start, t_end = _milestones(results['time'], results['moisture'], results['conversion'], results['T_solid'])
    not_done = t("timeline_not_completed")
    _render_timeline(
        f"{t_dry:.1f} min" if t_dry is not None else not_done,
        f"{t_start:.1f} min" if t_start is not None else not_done,
        f"{t_end:.1f} min" if t_end is not None else not_done,
        f"##### 📅 {t('timeline_time_elapsed')}")

    _render_yield_tables(results, summary, t('summary_solid_in'), t('summary_products_out'),
                         "Masa / Mass (kg)", "Masa / Mass (gal)")
