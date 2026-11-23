"""Summary section: the key technical and economic results, each with the criterion it is checked against."""
import streamlit as st

from .utils import get_lang
from .economics_panel import SLUDGE_SCENARIO_LABELS, breakeven_note, format_irr

# Technical criteria shown on the cards (explicit, so the reader sees what "meets" means)
MIN_CONVERSION_PCT = 95.0           # volatiles released by the end of the batch
THESIS_OIL_TOLERANCE_PCT = 0.5      # simulated vs measured oil at shutdown (thesis profile)

_COLORS = {True: "#10b981", False: "#ef4444", None: "#94a3b8"}
_MARKS = {True: "✓", False: "✗", None: "—"}


def _card(title, value, detail, ok=None, criterion=""):
    """Result card. ok=True/False marks whether the criterion is met; None means informative only."""
    color = _COLORS[ok]
    st.markdown(f"""
    <div style="background: rgba(128,128,128,0.08); padding: 14px 16px;
                border-radius: 12px; border: 1px solid rgba(128,128,128,0.25); border-top: 3px solid {color};
                margin-bottom: 12px; min-height: 150px;">
        <div style="opacity: 0.7; font-size: 12px; font-weight: 500; text-transform: uppercase;
                    letter-spacing: 0.04em;">{title}</div>
        <div style="font-size: 22px; font-weight: 700; margin: 6px 0 2px 0;">{value}</div>
        <div style="opacity: 0.6; font-size: 12px; min-height: 18px;">{detail}</div>
        <div style="color: {color}; font-size: 12px; font-weight: 600; margin-top: 8px;">{_MARKS[ok]} {criterion}</div>
    </div>
    """, unsafe_allow_html=True)


def render_summary_section(summary, econ):
    """First screen: technical results of the simulated batch and economic indicators of the project."""
    lang = get_lang()
    es = lang == 'es'
    ss = st.session_state
    thesis = ss.get('profile') == 'tesis'

    st.markdown("### " + ("Resumen de resultados" if es else "Results summary"))
    if thesis:
        st.caption("Perfil: caso de estudio, corrida PROENERGÉTICOS (tesis)." if es
                   else "Profile: case study, PROENERGÉTICOS run (thesis).")

    # ---------------------------------------------------------------- technical
    st.markdown("#### " + ("Proceso (lote simulado)" if es else "Process (simulated batch)"))
    c1, c2, c3, c4, c5 = st.columns(5)
    oil_kg = summary.get('oil_yield_kg', 0.0)
    oil_gal = oil_kg / float(ss.get('bio_oil_density', 750.0)) * 264.172
    with c1:
        if thesis:
            from pyrolysis.profiles import THESIS_OIL_AT_SHUTDOWN_PCT as measured
            ok = abs(summary['oil_yield_pct'] - measured) <= THESIS_OIL_TOLERANCE_PCT
            crit = (f"Medido al apagar: {measured:.2f} % (±{THESIS_OIL_TOLERANCE_PCT})" if es
                    else f"Measured at shutdown: {measured:.2f} % (±{THESIS_OIL_TOLERANCE_PCT})")
        else:
            ok, crit = None, ("Informativo" if es else "Informative")
        _card("Aceite pirolítico" if es else "Pyrolysis oil", f"{summary['oil_yield_pct']:.2f} %",
              f"{oil_kg:,.0f} kg · {oil_gal:,.0f} gal", ok, crit)
    with c2:
        gas_kg = summary.get('gas_yield_kg', 0.0)
        _card("Gas no condensable" if es else "Non-condensable gas", f"{summary['gas_yield_pct']:.2f} %",
              f"{gas_kg:,.0f} kg", None, "Informativo" if es else "Informative")
    with c3:
        char_kg = summary.get('char_yield_kg', 0.0)
        _card("Residuo carbonoso" if es else "Char residue", f"{summary['char_yield_pct']:.2f} %",
              f"{char_kg:,.0f} kg", None, "Informativo" if es else "Informative")
    with c4:
        conv = summary['conversion_pct']
        _card("Conversión de volátiles" if es else "Volatile conversion", f"{conv:.1f} %",
              f"{'Error de balance de masa' if es else 'Mass balance error'}: {summary.get('mass_error_pct', 0.0):.2e} %",
              conv >= MIN_CONVERSION_PCT, f"≥ {MIN_CONVERSION_PCT:.0f} %")
    with c5:
        fuel_sim = summary.get('waste_oil_consumed_gal', 0.0)
        shortfall = summary.get('burner_shortfall_min', 0.0)
        fuel_econ = float(ss.get('econ_fuel_gal_per_batch', 0.0))
        if fuel_econ > 0:
            detail = (f"Economía usa {fuel_econ:,.0f} gal/lote (planta)" if es
                      else f"Economics uses {fuel_econ:,.0f} gal/batch (plant)")
        else:
            detail = "Simulado por lote" if es else "Simulated per batch"
        _card("Combustible auxiliar" if es else "Auxiliary fuel", f"{fuel_sim:,.1f} gal", detail,
              shortfall <= 0.0,
              ("El quemador cubre la rampa" if es else "Burner covers the ramp") if shortfall <= 0.0 else
              (f"Falta potencia durante {shortfall:.0f} min" if es else f"Burner short for {shortfall:.0f} min"))

    # ---------------------------------------------------------------- economics
    m = econ['m']
    scenario = SLUDGE_SCENARIO_LABELS[econ['sludge_scenario']][lang]
    st.markdown("#### " + ("Viabilidad económica" if es else "Economic viability"))
    st.caption((f"Escenario: {scenario} ({econ['opex_tipping']:+,.2f} RD$/gal) · tasa de descuento "
                f"{econ['discount_rate']:.1f} % · horizonte {econ['project_lifetime']} años") if es else
               (f"Scenario: {scenario} ({econ['opex_tipping']:+,.2f} RD$/gal) · discount rate "
                f"{econ['discount_rate']:.1f} % · horizon {econ['project_lifetime']} years"))
    e1, e2, e3, e4, e5 = st.columns(5)
    years = "años" if es else "years"
    with e1:
        _card("VAN" if es else "NPV", f"RD$ {m['npv'] / 1e6:,.2f} M", f"RD$ {m['npv']:,.2f}",
              m['npv'] >= 0, "VAN ≥ 0" if es else "NPV ≥ 0")
    with e2:
        irr = m['irr']
        _card("TIR" if es else "IRR", format_irr(irr),
              "", irr is not None and irr >= econ['discount_rate'],
              (f"TIR ≥ tasa de descuento ({econ['discount_rate']:.1f} %)" if es
               else f"IRR ≥ discount rate ({econ['discount_rate']:.1f} %)"))
    with e3:
        pbd = m['disc_payback']
        _card("Recuperación descontada" if es else "Discounted payback",
              f"{pbd:.2f} {years}" if pbd != float('inf') else ("No se recupera" if es else "Not recovered"),
              f"Simple: {m['payback']:.2f} {years}" if m['payback'] != float('inf') else "",
              pbd <= econ['project_lifetime'],
              f"≤ {econ['project_lifetime']} {years}")
    with e4:
        _card("Índice de rentabilidad" if es else "Profitability index", f"{m['pi']:.2f}", "",
              m['pi'] >= 1.0, "IR ≥ 1" if es else "PI ≥ 1")
    with e5:
        be = m['breakeven_tipping']
        _card("Tarifa de equilibrio" if es else "Break-even fee", f"RD$ {be:,.2f}/gal",
              ("VAN = 0; negativo = el lodo puede costar" if es else "NPV = 0; negative = sludge may cost"),
              econ['opex_tipping'] >= be,
              (f"Tarifa del escenario ({econ['opex_tipping']:+,.2f}) ≥ equilibrio" if es
               else f"Scenario fee ({econ['opex_tipping']:+,.2f}) ≥ break-even"))
    st.info(breakeven_note(m['breakeven_tipping'], lang))
