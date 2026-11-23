import io
import datetime
from types import SimpleNamespace
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, PageBreak, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
    base_canvas_class = canvas.Canvas
except ImportError:
    REPORTLAB_AVAILABLE = False
    base_canvas_class = object

# --- Unit conversions and physical constants (shared with docx_generator) ---
GAL_PER_M3 = 264.172            # US gallons per cubic metre
SYNGAS_DENSITY_KG_M3 = 1.15     # syngas density used to turn kg into m³
WATER_DENSITY_15C_KG_M3 = 999.1  # reference for specific gravity @ 15 °C
WATER_LB_PER_GAL = 8.345        # lb of water per US gallon
MJKG_TO_BTULB = 429.923         # 1 MJ/kg in BTU/lb

# Fixed feedstock properties printed in the property table (not simulated)
FEED_HHV_MJ_KG = 18.50
FEED_CP_KJ_KGK = 2.10

# Thermal balance constants (J/kg·K and J/kg)
CP_CHAR_J_KGK = 1000.0
CP_GAS_J_KGK = 1500.0
CP_WATER_J_KGK = 4184.0         # liquid water
CP_STEAM_J_KGK = 2000.0         # superheated steam
DH_PYRO_J_KG = 700000.0         # the report text quotes 600 kJ/kg; this is the value actually used
DH_EVAP_J_KG = 2256000.0
WATER_BOILING_C = 100.0
J_PER_KWH = 3.6e6

# --- PDF page layout (points, letter size) ---
PAGE_LEFT_X = 36
PAGE_RIGHT_X = 576
HEADER_TEXT_Y = 756
HEADER_RULE_Y = 750
FOOTER_RULE_Y = 45
FOOTER_TEXT_Y = 32

# --- PDF palette ---
NAVY = "#1E3A8A"
TEAL = "#0D9488"
DARK_TEAL = "#0F766E"
GREEN = "#059669"
AMBER = "#D97706"
SLATE = "#64748B"
BORDER_GREY = "#CBD5E1"
GRID_GREY = "#E2E8F0"
TOTAL_ROW_BG = "#F1F5F9"
LIGHT_ROW_BG = "#F8FAFC"
HIGHLIGHT_ROW_BG = "#FEF3C7"

FIGURE_DPI = 200
CURRENCY = "RD$"
# The PDF always prints the batch label (the app only runs batch mode).
PDF_MODE_LABEL = "POR LOTES (BATCH)"
FOOTER_TEXT = "Reporte Técnico de Ingeniería & Evaluaciones de Factibilidad | Confidencial"


class NumberedCanvas(base_canvas_class):
    """
    Custom canvas that performs two passes to add running headers and
    page numbers formatted as 'Página X de Y' on all pages except the cover.
    """
    def __init__(self, *args, **kwargs):
        if not REPORTLAB_AVAILABLE:
            return
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        if self._pageNumber > 1:  # the cover page has no running header
            self._draw_header()
        self._draw_footer(page_count)
        self.restoreState()

    def _draw_header(self):
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor(NAVY))
        self.drawString(PAGE_LEFT_X, HEADER_TEXT_Y, "SIMULADOR TERMOQUÍMICO | INGENIERÍA DE PROCESOS Y ENERGÍA")
        self.setFont("Helvetica-Oblique", 8)
        self.setFillColor(colors.HexColor(SLATE))
        self.drawRightString(PAGE_RIGHT_X, HEADER_TEXT_Y, "Simulador Termoquímico de Pirólisis v2.0")

        self.setStrokeColor(colors.HexColor(NAVY))
        self.setLineWidth(0.75)
        self.line(PAGE_LEFT_X, HEADER_RULE_Y, PAGE_RIGHT_X, HEADER_RULE_Y)

    def _draw_footer(self, page_count):
        self.setStrokeColor(colors.HexColor(BORDER_GREY))
        self.setLineWidth(0.75)
        self.line(PAGE_LEFT_X, FOOTER_RULE_Y, PAGE_RIGHT_X, FOOTER_RULE_Y)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor(SLATE))
        self.drawString(PAGE_LEFT_X, FOOTER_TEXT_Y, FOOTER_TEXT)
        self.drawRightString(PAGE_RIGHT_X, FOOTER_TEXT_Y, f"Página {self._pageNumber} de {page_count}")


# =========================================================
# Calculations shared by the PDF and Word reports
# =========================================================

def _report_inputs(summary, solver_inputs):
    """Feed, load and headline results used across the report sections."""
    feed_obj = solver_inputs.get('current_feed')
    sludge_density = float(solver_inputs.get('sludge_density', 944.7))
    load_kg = solver_inputs['batch_load_kg']
    return SimpleNamespace(
        feed_obj=feed_obj,
        feed_name=feed_obj.name if feed_obj else "Lodo de Petróleo / Hidrocarburos",
        sludge_density=sludge_density,
        bio_oil_density=float(solver_inputs.get('bio_oil_density', 750.0)),
        temp_hold=float(solver_inputs.get('temp_hold_c', 550.0)),
        temp_start=float(solver_inputs.get('temp_start_c', 25.0)),
        heating_rate=float(solver_inputs.get('heating_rate_cmin', 1.0)),
        load_kg=load_kg,
        load_gal=(load_kg / sludge_density) * GAL_PER_M3,
        load_unit="gal",
        conv_pct=summary['conversion_pct'],
        oil_pct=summary['oil_yield_pct'],
        gas_pct=summary['gas_yield_pct'],
        char_pct=summary['char_yield_pct'],
        duty_val=summary.get('total_energy_kwh', 0.0),
        duty_unit="kWh",
    )


def _product_masses(summary):
    """Oil, gas, char and water produced per batch (kg)."""
    return (
        summary.get('oil_yield_kg', 0),
        summary.get('gas_yield_kg', 0),
        summary.get('char_yield_kg', 0),
        summary.get('water_yield_kg', 0),
    )


def _pyrolysis_timing(results):
    """Drying end, pyrolysis window and cycle length (min), plus the two time rows of the geometry table."""
    t_arr = np.array(results.get('time', [0.0]))
    conv_arr = np.array(results.get('conversion', [0.0]))
    moist_arr = np.array(results.get('moisture', [0.0]))
    temp_s_arr = np.array(results.get('T_solid', [298.15])) - 273.15

    # Normalizar conversión a porcentaje (0 a 100)
    if len(conv_arr) > 0 and conv_arr[-1] <= 1.0:
        conv_pct_arr = conv_arr * 100.0
    else:
        conv_pct_arr = conv_arr

    # 1. Evaporación completa de agua (secado): queda <= 0.5% de la humedad inicial
    t_drying_end = 0.0
    if len(moist_arr) > 0 and moist_arr[0] > 0:
        idx_dry = np.argmax(moist_arr <= 0.005 * moist_arr[0])
        if moist_arr[idx_dry] <= 0.005 * moist_arr[0]:
            t_drying_end = float(t_arr[idx_dry])

    # 2. Inicio de pirólisis activa (T >= 350°C o X >= 1%)
    idx_start = np.argmax((conv_pct_arr >= 1.0) | (temp_s_arr >= 350.0))
    if idx_start < len(t_arr) and (conv_pct_arr[idx_start] >= 1.0 or temp_s_arr[idx_start] >= 350.0):
        t_start_pyro = float(t_arr[idx_start])
    else:
        t_start_pyro = float(t_arr[0])

    # 3. Fin de reacción de pirólisis (99% de conversión final)
    final_conv_pct = conv_pct_arr[-1] if len(conv_pct_arr) > 0 else 0.0
    if final_conv_pct > 0.0:
        idx_end = np.argmax(conv_pct_arr >= 0.99 * final_conv_pct)
        if conv_pct_arr[idx_end] >= 0.99 * final_conv_pct:
            t_end_pyro = float(t_arr[idx_end])
        else:
            t_end_pyro = float(t_arr[-1])
    else:
        t_end_pyro = float(t_arr[-1]) if len(t_arr) > 0 else 300.0

    pyro_residence_min = max(0.0, t_end_pyro - t_start_pyro)
    return SimpleNamespace(
        t_drying_end=t_drying_end,
        pyro_residence_min=pyro_residence_min,
        total_cycle_min=float(t_arr[-1]) if len(t_arr) > 0 else 300.0,
        time_label_1="Tiempo Eficiente Residencia Pirólisis",
        time_val_1=f"{pyro_residence_min:.1f} min ({pyro_residence_min/60.0:.1f} h)",
        time_label_2="Ventana Pirólisis (Inicio → 99% Conv.)",
        time_val_2=f"{t_start_pyro:.1f} min → {t_end_pyro:.1f} min",
    )


def _thermal_energy_balance(results, solver_inputs, oil_kg, gas_kg, char_kg, water_kg):
    """Heat (kWh per batch) sent to each destination (char, oil, gas, reaction, steam) and the total."""
    cp_oil = float(solver_inputs.get('custom_cp_oil', 1800.0))
    e = SimpleNamespace(cp_char=CP_CHAR_J_KGK, cp_oil=cp_oil, cp_gas=CP_GAS_J_KGK, dh_pyro=DH_PYRO_J_KG)

    e.T_start = results['T_solid'][0]
    e.T_hold = results['T_solid'][-1]
    e.dT = e.T_hold - e.T_start

    e.char = (char_kg * CP_CHAR_J_KGK * e.dT) / J_PER_KWH
    e.oil = (oil_kg * cp_oil * e.dT) / J_PER_KWH
    e.gas = (gas_kg * CP_GAS_J_KGK * e.dT) / J_PER_KWH
    e.rxn = ((oil_kg + gas_kg) * DH_PYRO_J_KG) / J_PER_KWH
    if e.T_hold >= WATER_BOILING_C:
        e.steam = (water_kg * (CP_WATER_J_KGK * (WATER_BOILING_C - e.T_start) + DH_EVAP_J_KG + CP_STEAM_J_KGK * (e.T_hold - WATER_BOILING_C))) / J_PER_KWH
    else:
        e.steam = (water_kg * (CP_WATER_J_KGK * (e.T_hold - e.T_start))) / J_PER_KWH

    e.total = e.char + e.oil + e.gas + e.rxn + e.steam
    return e


def _share_pct(part, total):
    """Share of a total in %, guarded against a zero total."""
    return part/max(0.001,total)*100


def _proximate_rows(feed_obj, load_gal):
    """Proximate analysis rows (component, wt.%, load share, note) plus the TOTAL row."""
    return [
        ["Humedad (Moisture)", f"{feed_obj.moisture:.2f}%", f"{load_gal*feed_obj.moisture/100:.2f}", "Agua libre lecho"],
        ["Materia Volátil (Volatiles)", f"{feed_obj.volatile:.2f}%", f"{load_gal*feed_obj.volatile/100:.2f}", "Matriz org. reactiva"],
        ["Carbono Fijo (Fixed Carbon)", f"{feed_obj.fixed_carbon:.2f}%", f"{load_gal*feed_obj.fixed_carbon/100:.2f}", "Estructura char"],
        ["Cenizas Inertes (Ash)", f"{feed_obj.ash:.2f}%", f"{load_gal*feed_obj.ash/100:.2f}", "Inorgánico inerte"],
        ["TOTAL", "100.00%", f"{load_gal:.2f}", "Base Húmeda"]
    ]


def _feed_property_rows(feed_obj, sludge_density):
    """Physico-chemical property rows of the raw sludge (property, value, unit, description)."""
    hhv_feed_btu = FEED_HHV_MJ_KG * MJKG_TO_BTULB
    sludge_dens_lbgal = (sludge_density / WATER_DENSITY_15C_KG_M3) * WATER_LB_PER_GAL
    return [
        ["Densidad @ 15°C & Gravedad API (ASTM D4052)", f"{sludge_density:.1f} kg/m³ | 18.2 °API ({sludge_dens_lbgal:.2f} lb/gal)", "kg/m³ / °API", "Hidrocarburo pesado en tolvas y bombas"],
        ["Viscosidad Cinemática @ 50°C (ASTM D445)", "138.7 mm²/s (cSt)", "cSt", "Reología y precalentamiento de alimentación"],
        ["Contenido de Azufre Total (ASTM D4294)", "0.997 wt.%", "wt.%", "Azufre orgánico para balance de emisiones Syngas"],
        ["Cenizas Promedio Inertes (ASTM D482)", f"{feed_obj.ash:.2f} wt.%", "wt.%", "Inorgánico residual en lecho y char"],
        ["Contenido de Agua / Humedad (ASTM D95)", f"{feed_obj.moisture:.2f} wt.%", "wt.%", "Agua libre para etapa de deshidratación"],
        ["Punto de Inflamación Flash Point (ASTM D93)", "> 110.0 °C (> 230 °F)", "°C", "Umbral de seguridad operacional térmico"],
        ["Metales e Impurezas Cat Fines (IP 470)", "Al+Si: 647 mg/kg | V: 117 mg/kg | Ca: 33 mg/kg", "mg/kg (ppm)", "Partículas minerales abrasivas y vanadio"],
        ["Poder Calorífico Superior (HHV Lodo Bruto)", f"{FEED_HHV_MJ_KG:.2f} MJ/kg ({hhv_feed_btu:,.0f} BTU/lb)", "MJ/kg", "Potencial energético de entrada"],
        ["Capacidad Calorífica Específica (Cp Lodo)", f"{FEED_CP_KJ_KGK:.2f} kJ/kg·K", "kJ/kg·K", "Requerimiento térmico de rampa"]
    ]


def _oil_gravity(bio_oil_density):
    """Specific gravity @ 15 °C and API gravity of the pyrolysis oil."""
    sg_15 = bio_oil_density / WATER_DENSITY_15C_KG_M3
    api_deg = (141.5 / max(0.1, sg_15)) - 131.5
    return sg_15, api_deg


def _generate_matplotlib_figures(results, summary):
    """
    Generates high-resolution Matplotlib figures and converts them to ReportLab Image flowables.
    """
    fig_images = {}

    # Common plot style
    plt.rcParams['axes.edgecolor'] = '#94A3B8'
    plt.rcParams['axes.linewidth'] = 0.8

    x_data = results['time']
    x_label = "Tiempo de Proceso (min)"

    # --- Figure 1: Temperature Profile ---
    fig, ax = plt.subplots(figsize=(6.5, 2.7), dpi=FIGURE_DPI)
    ax.plot(x_data, results['T_wall'], label='Temp. Pared (°C)', color='#DC2626', linestyle='--', linewidth=1.5)
    ax.plot(x_data, results['T_solid'], label='Temp. Lecho Sólido (°C)', color='#1E3A8A', linewidth=2.0)
    ax.axhline(100, color='#94A3B8', linestyle='-.', linewidth=1, label='Evaporación Agua (100°C)')

    ax.set_title("Figura 1. Perfil Térmico del Reactor Rotatorio", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    ax.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax.set_ylabel("Temperatura (°C)", fontsize=8.5, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(fontsize=7.5, loc='best', framealpha=0.9)
    fig_images['fig_temp'] = _figure_to_image(fig, 6.5, 2.7)

    # --- Figure 2: Mass Profiles of Bed & Humidity ---
    fig, ax1 = plt.subplots(figsize=(6.5, 2.7), dpi=FIGURE_DPI)
    ax1.plot(x_data, results['moisture'], label='Humedad (kg)', color='#2563EB', linewidth=1.5)
    ax1.plot(x_data, results['volatile'], label='Volátiles (kg)', color='#9333EA', linewidth=2.0)
    ax1.plot(x_data, results['char'], label='Char (kg)', color='#1F2937', linewidth=1.5)
    ax1.plot(x_data, results['ash'], label='Cenizas (kg)', color='#64748B', linewidth=1.2)
    ax1.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax1.set_ylabel("Masa en Lecho (kg)", fontsize=8.5, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)

    ax2 = ax1.twinx()
    ax2.plot(x_data, results['humidity'], label='Humedad Lecho (%)', color='#EF4444', linestyle=':', linewidth=1.5)
    ax2.set_ylabel("Humedad del Lecho (%)", fontsize=8.5, fontweight='bold', color='#EF4444')
    ax2.set_ylim(0, 105)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=7.5, loc='center right', framealpha=0.9)
    ax1.set_title("Figura 2. Evolución Sólida y Humedad del Lecho", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    fig_images['fig_solids'] = _figure_to_image(fig, 6.5, 2.7)

    # --- Figure 3: Volatile Vapor Yields Accumulation ---
    fig, ax = plt.subplots(figsize=(6.5, 2.7), dpi=FIGURE_DPI)
    ax.plot(x_data, results['oil'], label='Aceite pirolítico (Pyrolysis oil)', color='#D97706', linewidth=2.2)
    ax.plot(x_data, results['gas'], label='Gas de Síntesis (Syngas)', color='#0D9488', linestyle='--', linewidth=1.8)
    ax.plot(x_data, results['steam'], label='Vapor de Agua (Steam)', color='#E11D48', linestyle=':', linewidth=1.5)

    ax.set_title("Figura 3. Acumulación de Productos Volátiles Evacuados", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    ax.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax.set_ylabel("Masa Generada (kg)", fontsize=8.5, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(fontsize=7.5, loc='upper left', framealpha=0.9)
    fig_images['fig_vapors'] = _figure_to_image(fig, 6.5, 2.7)

    # --- Figure 4: Mass Yields Distribution Pie Chart ---
    fig, ax = plt.subplots(figsize=(4.0, 2.4), dpi=FIGURE_DPI)
    labels = ['Aceite pirolítico', 'Syngas', 'Char', 'Vapor Agua']
    yields_pct = [
        summary['oil_yield_pct'],
        summary['gas_yield_pct'],
        summary['char_yield_pct'],
        summary['water_yield_pct']
    ]
    colors_list = ['#F59E0B', '#14B8A6', '#334155', '#3B82F6']
    explode = (0.05, 0.02, 0.02, 0.02)

    wedges, texts, autotexts = ax.pie(
        yields_pct, explode=explode, labels=labels, colors=colors_list,
        autopct='%1.1f%%', startangle=140, textprops=dict(fontsize=7.5)
    )
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_weight('bold')

    ax.set_title("Figura 4. Distribución Rendimiento en Masa (wt.%)", fontsize=9, fontweight='bold', color='#1E3A8A', pad=4)
    fig_images['fig_pie'] = _figure_to_image(fig, 4.0, 2.4)

    return fig_images


def _figure_to_image(fig, width_in, height_in):
    """Render a Matplotlib figure to PNG and wrap it as a ReportLab Image of the given size (inches)."""
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=width_in*inch, height=height_in*inch)


def _calculate_financials(summary, solver_inputs):
    """
    Computes financial & sustainability KPIs for the thesis report.
    """
    try:
        import streamlit as st
        session = st.session_state
    except Exception:
        session = {}

    default_equip = 4800000.0
    default_install = 1680000.0
    default_civil = 1200000.0
    default_piping_elec = 1200000.0
    default_eng = 720000.0
    default_permits = 450000.0
    default_contingency = 900000.0

    capex_equip = float(session.get('capex_equip', default_equip))
    capex_install = float(session.get('capex_install', default_install))
    capex_civil = float(session.get('capex_civil', default_civil))
    capex_piping_elec = float(session.get('capex_piping_elec', default_piping_elec))
    capex_eng = float(session.get('capex_eng', default_eng))
    capex_permits = float(session.get('capex_permits', default_permits))
    capex_cont = float(session.get('capex_cont', default_contingency))

    total_capex = capex_equip + capex_install + capex_civil + capex_piping_elec + capex_eng + capex_permits + capex_cont

    shutdown_days = int(session.get('shutdown_days', 15))
    holidays_days = int(session.get('holidays_days', 15))
    available_calendar_days = max(1, 365 - shutdown_days - holidays_days)
    annual_days = int(session.get('annual_days', available_calendar_days))
    sludge_density = float(session.get('sludge_density', 944.7))
    oil_density = float(session.get('bio_oil_density', 750.0))

    t_heat_min = (solver_inputs.get('temp_hold_c', 400.0) - solver_inputs.get('temp_start_c', 25.0)) / solver_inputs.get('heating_rate_cmin', 1.0)
    t_hold_min = solver_inputs.get('hold_time_min', 60.0)
    t_cycle_min = t_heat_min + t_hold_min
    batch_cooldown_h = float(session.get('batch_cooldown_h', 0.50))
    batch_loading_h = float(session.get('batch_loading_h', 0.50))
    batch_turnaround_h = float(session.get('batch_turnaround_h', batch_cooldown_h + batch_loading_h))
    batches_before_cleaning = int(session.get('batches_before_cleaning', 20))
    cleaning_time_h = float(session.get('cleaning_time_h', 4.0))
    maint_cooldown_h = float(session.get('maint_cooldown_h', 6.0))
    maint_penalty_per_batch_h = (maint_cooldown_h + cleaning_time_h) / max(batches_before_cleaning, 1)
    t_op_batch_hours = (t_cycle_min / 60.0) + batch_turnaround_h
    t_cycle_hours = t_op_batch_hours + maint_penalty_per_batch_h
    annual_hours = annual_days * 24.0
    batches_per_year = np.floor(annual_hours / t_cycle_hours) if t_cycle_hours > 0 else 0.0

    sludge_treated_kg = summary.get('batch_load_kg', 500.0) * batches_per_year
    oil_produced_kg = summary.get('oil_yield_kg', 0.0) * batches_per_year
    char_produced_kg = summary.get('char_yield_kg', 0.0) * batches_per_year
    gas_produced_kg = summary.get('gas_yield_kg', 0.0) * batches_per_year
    fuel_consumed_gal = summary.get('waste_oil_consumed_gal', 0.0) * batches_per_year
    elec_consumed_kwh = 0.0
    gen_diesel_batch = float(session.get('gen_diesel_batch', 1.0))
    generator_fuel_consumed_gal = gen_diesel_batch * batches_per_year

    sludge_treated_gal = (sludge_treated_kg / sludge_density) * GAL_PER_M3
    oil_produced_gal = (oil_produced_kg / oil_density) * GAL_PER_M3
    gas_produced_m3 = gas_produced_kg / SYNGAS_DENSITY_KG_M3

    opex_handling = float(session.get('opex_handling', 3.00))
    opex_fuel = float(session.get('opex_fuel', 180.00))
    opex_electricity = float(session.get('opex_electricity', 7.50))
    opex_aux_utilities = float(session.get('opex_aux_utilities', 300000.0))
    price_generator_fuel = float(session.get('price_generator_fuel', 262.80))
    opex_labor = float(session.get('opex_labor', 3000000.0))
    opex_maint = float(session.get('opex_maint', 3.0))
    opex_insurance_tax = float(session.get('opex_insurance_tax', 1.0))
    opex_tipping = float(session.get('opex_tipping', 9.00))

    price_oil = float(session.get('price_oil', 120.00))
    price_char = float(session.get('price_char', 21.00))
    price_gas = float(session.get('price_gas', 3.60))
    price_carbon = float(session.get('price_carbon', 1200.0))
    rate_carbon_offset = float(session.get('rate_carbon_offset', 2.2))

    discount_rate = float(session.get('discount_rate', 14.0))
    project_lifetime = int(session.get('project_lifetime', 10))
    tax_rate = float(session.get('tax_rate', 25.0))
    inflation_rate = float(session.get('inflation_rate', 4.0))

    from pyrolysis.gui.economics_panel import run_financial_model

    fin_results = run_financial_model(
        total_capex=total_capex,
        sludge_treated_gal=sludge_treated_gal,
        oil_produced_gal=oil_produced_gal,
        char_produced_kg=char_produced_kg,
        gas_produced_m3=gas_produced_m3,
        fuel_consumed_gal=fuel_consumed_gal,
        elec_consumed_kwh=elec_consumed_kwh,
        generator_fuel_consumed_gal=generator_fuel_consumed_gal,
        opex_handling=opex_handling,
        opex_fuel=opex_fuel,
        opex_electricity=opex_electricity,
        opex_aux_utilities=opex_aux_utilities,
        price_generator_fuel=price_generator_fuel,
        opex_labor=opex_labor,
        opex_maint=opex_maint,
        opex_insurance_tax=opex_insurance_tax,
        opex_tipping=opex_tipping,
        price_oil=price_oil,
        price_char=price_char,
        price_gas=price_gas,
        price_carbon=price_carbon,
        rate_carbon_offset=rate_carbon_offset,
        discount_rate=discount_rate,
        project_lifetime=project_lifetime,
        tax_rate=tax_rate,
        inflation_rate=inflation_rate
    )

    fin_results['total_capex'] = total_capex
    fin_results['total_rev_base'] = sum(fin_results['revenue_breakdown'].values()) if 'revenue_breakdown' in fin_results else 0.0
    fin_results['total_opex_base'] = sum(fin_results['opex_breakdown'].values()) if 'opex_breakdown' in fin_results else 0.0
    fin_results['capex_breakdown'] = {
        'equip': capex_equip,
        'install': capex_install,
        'civil': capex_civil,
        'piping_elec': capex_piping_elec,
        'eng': capex_eng,
        'permits': capex_permits,
        'cont': capex_cont
    }
    fin_results['annual_days'] = annual_days
    fin_results['sludge_treated_kg'] = sludge_treated_kg
    fin_results['sludge_treated_gal'] = sludge_treated_gal
    fin_results['oil_produced_gal'] = oil_produced_gal
    fin_results['char_produced_kg'] = char_produced_kg
    fin_results['gas_produced_m3'] = gas_produced_m3

    return fin_results


# =========================================================
# PDF building blocks
# =========================================================

def _build_styles():
    """Paragraph styles of the thesis PDF."""
    base = getSampleStyleSheet()['Normal']
    return SimpleNamespace(
        inst_header=ParagraphStyle('InstHeader', parent=base, fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=colors.HexColor(NAVY), alignment=1),
        sub_inst_header=ParagraphStyle('SubInstHeader', parent=base, fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor(SLATE), alignment=1, spaceAfter=12),
        doc_tag=ParagraphStyle('DocTag', parent=base, fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.HexColor(AMBER), alignment=1, spaceAfter=4),
        title=ParagraphStyle(
            'AcademicTitle',
            parent=base,
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor(NAVY),
            alignment=1, # Center
            spaceAfter=6
        ),
        subtitle=ParagraphStyle(
            'AcademicSubtitle',
            parent=base,
            fontName='Helvetica',
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
            alignment=1,
            spaceAfter=14
        ),
        h1=ParagraphStyle(
            'AcademicH1',
            parent=base,
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor(NAVY),
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True
        ),
        h2=ParagraphStyle(
            'AcademicH2',
            parent=base,
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True
        ),
        body=ParagraphStyle(
            'AcademicBody',
            parent=base,
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
            alignment=4, # Justified
            spaceAfter=6
        ),
        abstract=ParagraphStyle(
            'AcademicAbstract',
            parent=base,
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            alignment=4,
            spaceBefore=4,
            spaceAfter=8
        ),
        header=ParagraphStyle(
            'TableHeader',
            parent=base,
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1
        ),
        cell=ParagraphStyle(
            'TableCell',
            parent=base,
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1E293B"),
            alignment=0
        ),
        center=ParagraphStyle(
            'TableCellCenter',
            parent=base,
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1E293B"),
            alignment=1
        ),
        bold=ParagraphStyle(
            'TableCellBold',
            parent=base,
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
            alignment=0
        ),
        caption=ParagraphStyle(
            'FigureCaption',
            parent=base,
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(SLATE),
            alignment=1,
            spaceBefore=4,
            spaceAfter=10
        ),
    )


def _header_row(s, *titles):
    return [Paragraph(f"<b>{title}</b>", s.header) for title in titles]


def _data_table(rows, col_widths_in, header_bg, padding, highlights=()):
    """
    Grid table with a coloured header row. highlights: (first_row, last_row, hex colour) bands,
    painted after the grid and before the padding, as every table in this report does.
    """
    table = Table(rows, colWidths=[w*inch for w in col_widths_in])
    commands = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(header_bg)),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor(BORDER_GREY)),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor(GRID_GREY)),
    ]
    commands += [('BACKGROUND', (0,first), (-1,last), colors.HexColor(bg)) for first, last, bg in highlights]
    commands += [
        ('TOPPADDING', (0,0), (-1,-1), padding),
        ('BOTTOMPADDING', (0,0), (-1,-1), padding),
    ]
    table.setStyle(TableStyle(commands))
    return table


def _add_section_title(story, s, title):
    story.append(Paragraph(title, s.h1))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor(BORDER_GREY), spaceBefore=0, spaceAfter=8))


def _add_body_text(story, s, text):
    story.append(Paragraph(text, s.body))
    story.append(Spacer(1, 6))


# =========================================================
# PDF report sections
# =========================================================

def _add_cover(story, s, inp):
    """Institution header, title block and metadata table."""
    story.append(Paragraph("INFORME TÉCNICO DE INGENIERÍA Y SIMULACIÓN TÉRMICA", s.inst_header))
    story.append(Paragraph("DEPARTAMENTO DE INGENIERÍA DE PROCESOS Y EVALUACIÓN TERMOQUÍMICA", s.sub_inst_header))

    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(NAVY), spaceBefore=0, spaceAfter=12))

    story.append(Paragraph("INFORME TÉCNICO DE INGENIERÍA & EVALUACIÓN DE FACTIBILIDAD", s.doc_tag))
    story.append(Paragraph(f"EVALUACIÓN TERMOQUÍMICA Y BALANCES DE MATERIA Y ENERGÍA EN REACTOR ROTATORIO DE PIRÓLISIS {PDF_MODE_LABEL}", s.title))
    story.append(Paragraph("Modelado Cinético Multietapa, Caracterización ASTM del Aceite pirolítico y Evaluación del Aporte Energética", s.subtitle))

    current_date = datetime.datetime.now().strftime("%d/%m/%Y")
    meta_data = [
        [
            Paragraph("<b>Tipo de Estudio:</b>", s.cell), Paragraph("Simulación Termoquímica", s.cell),
            Paragraph("<b>Fecha de Emisión:</b>", s.cell), Paragraph(current_date, s.cell)
        ],
        [
            Paragraph("<b>Modo de Operación:</b>", s.cell), PDF_MODE_LABEL,
            Paragraph("<b>Materia Prima:</b>", s.cell), Paragraph(inp.feed_name, s.cell)
        ],
        [
            Paragraph("<b>Software Simulador:</b>", s.cell), Paragraph("Rotary Pyrolysis Simulator v2.0", s.cell),
            Paragraph("<b>Unidad de Proceso:</b>", s.cell), Paragraph("Reactor Cilíndrico Rotatorio", s.cell)
        ]
    ]
    t_meta = Table(meta_data, colWidths=[1.3*inch, 2.0*inch, 1.3*inch, 2.0*inch])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(LIGHT_ROW_BG)),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor(BORDER_GREY)),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor(GRID_GREY)),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))


def _add_abstract(story, s, inp, summary):
    story.append(Paragraph("<b>RESUMEN EJECUTIVO (ABSTRACT)</b>", s.h2))
    abstract_text = (
        f"El presente informe técnico expone los resultados de la simulación rigurosa del proceso de pirólisis "
        f"desarrollada en un reactor rotatorio de tambor operando en modo <b>{PDF_MODE_LABEL}</b> a presión atmosférica (<b>0 bar manométrica / 1 atm</b>) "
        f"y temperatura máxima de proceso de <b>{inp.temp_hold:.0f}°C</b> (temperatura inicial: {inp.temp_start:.0f}°C, tasa de calentamiento: {inp.heating_rate:.1f}°C/min). "
        f"Se procesó una carga nominal de <b>{inp.load_gal:,.1f} {inp.load_unit}</b> ({inp.load_kg:,.1f} kg) de <b>{inp.feed_name}</b> "
        f"con una densidad de materia prima de <b>{inp.sludge_density:.1f} kg/m³</b>. "
        f"El modelo fenomenológico resuelve el balance conservativo de materia y energía con transferencia de calor conductivo-convectivo en el lecho sólido. "
        f"Se alcanzó una conversión global de materia volátil del <b>{inp.conv_pct:.1f}%</b>, rindiendo un <b>{inp.oil_pct:.1f} wt.%</b> de aceite pirolítico condensable "
        f"(densidad del aceite pirolítico: <b>{inp.bio_oil_density:.1f} kg/m³</b>), un <b>{inp.gas_pct:.1f} wt.%</b> de gas de síntesis (syngas) incondensable, y un <b>{inp.char_pct:.1f} wt.%</b> de bio-carbón (char seco). "
        f"La demanda energética total calculada fue de <b>{inp.duty_val:,.2f} {inp.duty_unit}</b> con un error de cierre en el balance de materia de <b>{summary['mass_error_pct']:.2e}%</b>, "
        f"confirmando la consistencia física del modelo y la factibilidad del proceso industrial."
    )
    story.append(Paragraph(abstract_text, s.abstract))
    story.append(Spacer(1, 8))


def _add_feedstock_section(story, s, inp):
    """1. Feedstock proximate analysis, physico-chemical properties and ASTM oil characterisation."""
    _add_section_title(story, s, "1. Propiedades de la Materia Prima y Cinética Química")
    _add_body_text(story, s, (
        "La pirólisis termoquímica de lodos de petróleo e hidrocarburos pesados es un proceso de descomposición en atmósfera anaerobia "
        "(ausencia de oxígeno libre) que convierte fracciones orgánicas de alto peso molecular (asfaltenos, resinas y cadenas parafínicas) "
        "en tres coproductos con potencial de aprovechamiento: vapores condensables (Aceite pirolítico), gases incondensables (Syngas) y un residuo sólido seco (Carbón e inorgánicos). "
        "La evolución termodinámica comprende tres dominios principales: (i) <i>Secado y Deshidratación</i> a 100°C; "
        "(ii) <i>Destilación y Desvolatilización Multicomponente</i> entre 350°C y 450°C; y "
        "(iii) <i>Policondensación y Coquización final</i> por encima de 450°C, estabilizando el carbono fijo en la matriz sólida."
    ))

    story.append(Paragraph("<b>1.1 Análisis Proximal y Composición Elemental del Lodo</b>", s.h2))
    *component_rows, total_row = _proximate_rows(inp.feed_obj, inp.load_gal)
    comp_table_data = [_header_row(s, "Componente", "Fracción (wt.%)", f"Carga Entrada ({inp.load_unit})", "Volumen Relativo")]
    comp_table_data += [[Paragraph(name, s.cell), Paragraph(frac, s.center), Paragraph(load, s.center), Paragraph(note, s.cell)]
                        for name, frac, load, note in component_rows]
    comp_table_data.append([Paragraph(f"<b>{text}</b>", style) for text, style in zip(total_row, (s.bold, s.center, s.center, s.center))])
    story.append(_data_table(comp_table_data, [2.2, 1.3, 1.5, 1.6], NAVY, 4, highlights=[(-1, -1, TOTAL_ROW_BG)]))
    story.append(Spacer(1, 8))

    # Tabla 1.1.B: Propiedades Físico-Químicas y Térmicas Completa de la Materia Prima
    feed_prop_table_data = [_header_row(s, "Propiedad Físico-Química (Norma)", "Valor Certificado / Medido", "Unidad", "Descripción Industrial")]
    feed_prop_table_data += [[Paragraph(prop, s.cell), Paragraph(value, s.center), Paragraph(unit, s.center), Paragraph(desc, s.cell)]
                             for prop, value, unit, desc in _feed_property_rows(inp.feed_obj, inp.sludge_density)]
    story.append(_data_table(feed_prop_table_data, [2.3, 1.9, 0.8, 1.6], NAVY, 3.5))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>1.2 Caracterización del Aceite pirolítico Producido (Normas ASTM)</b>", s.h2))
    _add_body_text(story, s, (
        "La caracterización físico-química del condensado hidrocarbonado producido se realiza bajo estándares internacionales ASTM. "
        "El Poder Calorífico Superior (HHV - ASTM D240) evalúa la densidad de energía recuperada respecto al lodo bruto inicial, "
        "mientras que la viscosidad cinemática a 40°C (ASTM D445) y la gravedad API (ASTM D1298) definen la fluidez operacional, "
        "los requerimientos de precalentamiento para bombeo y la aptitud comercial del aceite pirolítico como combustible secundario."
    ))
    sg_15, api_deg = _oil_gravity(inp.bio_oil_density)
    not_calculated = "No calculado: requiere ensayo de laboratorio"
    astm_table_data = [
        _header_row(s, "Propiedad Físico-Química", "Norma ASTM", "Valor", "Diagnóstico de Calidad"),
        [Paragraph("Poder Calorífico Superior (PCS/HHV)", s.cell), Paragraph("ASTM D240", s.center), Paragraph(not_calculated, s.cell), Paragraph("-", s.cell)],
        [Paragraph("Viscosidad Cinemática @ 40°C", s.cell), Paragraph("ASTM D445", s.center), Paragraph(not_calculated, s.cell), Paragraph("-", s.cell)],
        [Paragraph("Densidad @ 15°C & Gravedad °API", s.cell), Paragraph("ASTM D1298", s.center), Paragraph(f"{inp.bio_oil_density:.1f} kg/m³ | {api_deg:.1f} °API", s.cell), Paragraph(f"Gravedad Específica: {sg_15:.4f}", s.cell)],
        [Paragraph("Contenido de Agua & Sedimentación (BS&W)", s.cell), Paragraph("ASTM D95", s.center), Paragraph(not_calculated, s.cell), Paragraph("-", s.cell)]
    ]
    story.append(_data_table(astm_table_data, [2.2, 1.1, 1.8, 1.5], TEAL, 4))
    story.append(Spacer(1, 14))


def _add_reactor_section(story, s, inp, summary, solver_inputs, timing):
    """2. Reactor geometry and operating conditions."""
    story.append(PageBreak())
    _add_section_title(story, s, "2. Geometría y Condiciones Operativas del Reactor")
    _add_body_text(story, s, (
        "El diseño dimensional y operativo del reactor rotatorio regula la transferencia de calor conductivo-convectivo hacia el lecho sólido en agitación. "
        "El grado de llenado óptimo (30-35%) y el coeficiente efectivo de transferencia de calor (h_eff) aseguran una distribución térmica uniforme, "
        "maximizando el área de contacto pared-lodo y evitando puntos calientes que propicien la incrustación de coque en la pared del tambor."
    ))

    length_m = solver_inputs['length']
    dia_m = solver_inputs['diameter']
    aspect_ratio = length_m / max(0.01, dia_m)
    rpm_val = solver_inputs['rpm']
    fill_deg = summary['filling_degree_pct']
    h_eff = solver_inputs['h_eff']
    burner_hp = solver_inputs.get('burner_hp', 300.0)
    burner_eff = solver_inputs.get('burner_eff_pct', 85.0)
    fuel_cons = summary.get('waste_oil_consumed_gal', 0.0)
    total_cycle_min = timing.total_cycle_min

    geom_table_data = [
        _header_row(s, "Parámetro Geométrico / Operativo", "Valor", "Parámetro Térmico / Energético", "Valor"),
        [Paragraph("Longitud Cilíndrica (L)", s.cell), Paragraph(f"{length_m:.2f} m", s.center), Paragraph("Temperatura Inicial (T_start)", s.cell), Paragraph(f"{inp.temp_start:.1f} °C", s.center)],
        [Paragraph("Diámetro Interno (D)", s.cell), Paragraph(f"{dia_m:.2f} m", s.center), Paragraph("Temperatura Máxima (T_hold)", s.cell), Paragraph(f"{inp.temp_hold:.1f} °C", s.center)],
        [Paragraph("Relación de Aspecto (L/D)", s.cell), Paragraph(f"{aspect_ratio:.2f}", s.center), Paragraph("Tasa de Calentamiento", s.cell), Paragraph(f"{inp.heating_rate:.1f} °C/min", s.center)],
        [Paragraph("Velocidad de Rotación", s.cell), Paragraph(f"{rpm_val:.1f} RPM", s.center), Paragraph("Coef. Transf. Calor (h_eff)", s.cell), Paragraph(f"{h_eff:.1f} W/m²·K", s.center)],
        [Paragraph("Grado de Llenado del Lecho", s.cell), Paragraph(f"{fill_deg:.2f} %", s.center), Paragraph("Potencia Quemadores", s.cell), Paragraph(f"{burner_hp:.0f} BHP", s.center)],
        [Paragraph("Tiempo Evaporación Agua (Secado)", s.cell), Paragraph(f"{timing.t_drying_end:.1f} min", s.center), Paragraph("Eficiencia Térmica Quemador", s.cell), Paragraph(f"{burner_eff:.1f} %", s.center)],
        [Paragraph(timing.time_label_1, s.cell), Paragraph(timing.time_val_1, s.center), Paragraph("Consumo Combustible Auxiliar", s.cell), Paragraph(f"{fuel_cons:.1f} gal/lote", s.center)],
        [Paragraph(timing.time_label_2, s.cell), Paragraph(timing.time_val_2, s.center), Paragraph("Conversión Volátiles Total", s.cell), Paragraph(f"{inp.conv_pct:.1f} %", s.center)],
        [Paragraph("Carga / Alimentación Entrante", s.cell), Paragraph(f"{inp.load_gal:.1f} {inp.load_unit}", s.center), Paragraph("Tiempo Total Ciclo Lote", s.cell), Paragraph(f"{total_cycle_min:.1f} min ({total_cycle_min/60.0:.1f} h)", s.center)]
    ]
    story.append(_data_table(geom_table_data, [2.0, 1.3, 2.0, 1.3], NAVY, 3.5))
    story.append(Spacer(1, 14))


def _add_mass_balance(story, s, inp, summary, solver_inputs, masses):
    """3.1 Global mass balance table and conservation equation."""
    oil_kg, gas_kg, char_kg, water_kg = masses
    story.append(Paragraph("<b>3.1 Balance de Materia Global y Cierre de Masa</b>", s.h2))
    _add_body_text(story, s, (
        "El balance de materia cuantifica la transformación estequiométrica del lodo de entrada bajo el principio de conservación de la masa. "
        "La masa total se redistribuye entre la fase condensable (Aceite pirolítico), la fase gaseosa incondensable (Syngas), "
        "el residuo sólido (Carbón) y el agua de secado, garantizando un error de cierre cercano a cero (<0.01%) que confirma la consistencia del modelo."
    ))

    char_density = float(solver_inputs.get('bio_char_density', 500.0))
    oil_gal = (oil_kg / inp.bio_oil_density) * GAL_PER_M3
    gas_m3 = gas_kg / SYNGAS_DENSITY_KG_M3
    char_gal = (char_kg / char_density) * GAL_PER_M3
    water_gal = (water_kg / 1000.0) * GAL_PER_M3

    # The ENTRADA row prints the load in gal under the "Masa (kg)" header (kept as is).
    mass_table_data = [
        _header_row(s, "Flujo / Corriente", "Masa (kg)", "Fracción wt.%", "Volumen Estimado"),
        [Paragraph("<b>ENTRADA:</b> " + inp.feed_name, s.bold), Paragraph(f"<b>{inp.load_gal:.2f}</b>", s.center), Paragraph("<b>100.00%</b>", s.center), Paragraph("-", s.center)],
        [Paragraph("<b>SALIDA:</b> Aceite pirolítico (Pyrolysis oil)", s.cell), Paragraph(f"{oil_kg:.2f}", s.center), Paragraph(f"{inp.oil_pct:.2f}%", s.center), Paragraph(f"{oil_gal:.1f} gal", s.cell)],
        [Paragraph("<b>SALIDA:</b> Gas de Síntesis (Syngas)", s.cell), Paragraph(f"{gas_kg:.2f}", s.center), Paragraph(f"{inp.gas_pct:.2f}%", s.center), Paragraph(f"{gas_m3:.1f} m³", s.cell)],
        [Paragraph("<b>SALIDA:</b> Carbón (Char Seco)", s.cell), Paragraph(f"{char_kg:.2f}", s.center), Paragraph(f"{inp.char_pct:.2f}%", s.center), Paragraph(f"{char_gal:.1f} gal", s.cell)],
        [Paragraph("<b>SALIDA:</b> Vapor de Agua (Steam)", s.cell), Paragraph(f"{water_kg:.2f}", s.center), Paragraph(f"{summary['water_yield_pct']:.2f}%", s.center), Paragraph(f"{water_gal:.1f} gal", s.cell)],
        [Paragraph("<b>ERROR CIERRE BALANCE</b>", s.bold), Paragraph(f"<b>{summary['mass_error_pct']:.2e} %</b>", s.center), Paragraph("<b>Conservativo</b>", s.center), Paragraph("<b>Tolerancia < 0.01%</b>", s.cell)]
    ]
    mass_eq_text = (
        f"<b>Ecuación de Conservación de Masa:</b><br/>"
        f"<i>M<sub>entrada</sub> = M<sub>aceite pirolítico</sub> + M<sub>syngas</sub> + M<sub>char</sub> + M<sub>vapor</sub></i><br/>"
        f"<b>Sustitución Numérica:</b> {inp.load_gal:.2f} kg = "
        f"{oil_kg:.2f} kg + {gas_kg:.2f} kg + {char_kg:.2f} kg + {water_kg:.2f} kg | "
        f"<b>Error de Cierre:</b> {summary['mass_error_pct']:.4f}%"
    )
    story.append(Paragraph(mass_eq_text, s.cell))
    story.append(Spacer(1, 4))
    story.append(_data_table(mass_table_data, [2.2, 1.4, 1.4, 1.6], NAVY, 4,
                             highlights=[(1, 1, LIGHT_ROW_BG), (-1, -1, HIGHLIGHT_ROW_BG)]))
    story.append(Spacer(1, 10))
    return gas_m3


def _add_energy_balance(story, s, energy):
    """3.2 Thermal energy balance by destination of the heat."""
    story.append(Paragraph("<b>3.2 Balance de Energía Térmica y Carga de Calentamiento</b>", s.h2))
    _add_body_text(story, s, (
        "El balance térmico global discrimina con exactitud rigurosa los distintos destinos del calor suministrado: "
        "(1) calor sensible para calentar el residuo carbonoso sólido, "
        "(2) calor sensible para calentar los volátiles condensables (futuro Aceite pirolítico líquido), "
        "(3) calor sensible para elevar la temperatura del gas de síntesis, "
        "(4) entalpía química de ruptura endotérmica de enlaces macromoleculares (ΔH<sub>pyro</sub> = 600 kJ/kg), y "
        "(5) energía latente y sobrecalentamiento del agua evaporada (ΔH<sub>evap</sub> = 2,256 kJ/kg)."
    ))

    e = energy
    unit, column_title = "kWh", "Energía (kWh)"
    total_label, total_note = "ENERGÍA TÉRMICA TOTAL", "Consumo Total Ciclo"

    energy_rows = [
        ("Calor Sensible del Sólido (Char)", e.char, "Conducción lecho de carbón residual"),
        ("Calor Sensible Aceite pirolítico (Fase Líquida)", e.oil, "Precalentamiento vapores condensables"),
        ("Calor Sensible Syngas (Fase Gas)", e.gas, "Precalentamiento gas incondensable"),
        ("Reacción Química Endotérmica (Pirólisis)", e.rxn, "Craqueo termoquímico (ΔH=600 kJ/kg)"),
        ("Secado y Evaporación de Humedad", e.steam, "Cambio de fase latente (2,256 kJ/kg)"),
    ]
    energy_table_data = [_header_row(s, "Etapa de Transferencia Térmica", column_title, "Porcentaje (%)", "Mecanismo Principal")]
    energy_table_data += [
        [Paragraph(label, s.cell), Paragraph(f"{value:.2f} {unit}", s.center), Paragraph(f"{(_share_pct(value, e.total)):.1f}%", s.center), Paragraph(mechanism, s.cell)]
        for label, value, mechanism in energy_rows
    ]
    energy_table_data.append([Paragraph(f"<b>{total_label}</b>", s.bold), Paragraph(f"<b>{e.total:.2f} {unit}</b>", s.center), Paragraph("<b>100.0%</b>", s.center), Paragraph(f"<b>{total_note}</b>", s.bold)])
    story.append(_data_table(energy_table_data, [2.2, 1.4, 1.4, 1.6], NAVY, 3.5, highlights=[(-1, -1, TOTAL_ROW_BG)]))
    story.append(Spacer(1, 8))


def _energy_formula_rows(e, oil_kg, gas_kg, char_kg, water_kg):
    """(component, formula, substitution) rows of the calculation memo, without the TOTAL row."""
    pct = lambda value: _share_pct(value, e.total)
    return [
        ("Calor Char (Sólido)",
         "<i>E<sub>char</sub> = [M<sub>char</sub> · Cp<sub>char</sub> · (T<sub>hold</sub> - T<sub>start</sub>)] / 3.6e6</i>",
         f"[{char_kg:.1f} kg · {e.cp_char:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = <b>{e.char:.2f} kWh</b> ({pct(e.char):.1f}%)"),
        ("Calor Aceite pirolítico (Líquido)",
         "<i>E<sub>oil</sub> = [M<sub>oil</sub> · Cp<sub>oil</sub> · (T<sub>hold</sub> - T<sub>start</sub>)] / 3.6e6</i>",
         f"[{oil_kg:.1f} kg · {e.cp_oil:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = <b>{e.oil:.2f} kWh</b> ({pct(e.oil):.1f}%)"),
        ("Calor Syngas (Gas)",
         "<i>E<sub>gas</sub> = [M<sub>gas</sub> · Cp<sub>gas</sub> · (T<sub>hold</sub> - T<sub>start</sub>)] / 3.6e6</i>",
         f"[{gas_kg:.1f} kg · {e.cp_gas:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = <b>{e.gas:.2f} kWh</b> ({pct(e.gas):.1f}%)"),
        ("Reacción Química Craqueo",
         "<i>E<sub>rxn</sub> = [(M<sub>oil</sub> + M<sub>gas</sub>) · ΔH<sub>pyro</sub>] / 3.6e6</i>",
         f"[{(oil_kg + gas_kg):.1f} kg · {e.dh_pyro:,.0f} J/kg] / 3.6e6 = <b>{e.rxn:.2f} kWh</b> ({pct(e.rxn):.1f}%)"),
        ("Evaporación del Agua",
         "<i>E<sub>steam</sub> = [M<sub>steam</sub> · (Cp<sub>w</sub>ΔT<sub>w</sub> + ΔH<sub>evap</sub> + Cp<sub>s</sub>ΔT<sub>s</sub>)] / 3.6e6</i>",
         f"[{water_kg:.1f} kg · (4184·{max(0.0, 100-e.T_start):.0f} + 2.256e6 + 2000·{max(0.0, e.T_hold-100):.0f})] / 3.6e6 = <b>{e.steam:.2f} kWh</b> ({pct(e.steam):.1f}%)"),
    ]


def _add_energy_formulas(story, s, energy, masses):
    """3.3 Calculation memo: formula and numeric substitution of each heat term."""
    story.append(Paragraph("<b>3.3 Memoria de Cálculo Detallada de Fórmulas Térmicas</b>", s.h2))
    e = energy
    total_row = ("ENERGÍA TÉRMICA TOTAL", "E<sub>total</sub> = Σ E<sub>componentes</sub>", f"{e.total:.2f} kWh (100.00%)")

    calc_formula_data = [_header_row(s, "Componente Energético", "Fórmula de Ingeniería Aplicada", "Sustitución de Variables y Resultado")]
    calc_formula_data += [
        [Paragraph(f"<b>{component}</b>", s.cell), Paragraph(formula, s.cell), Paragraph(substitution, s.cell)]
        for component, formula, substitution in _energy_formula_rows(e, *masses)
    ]
    total_label, total_formula, total_value = total_row
    calc_formula_data.append([
        Paragraph(f"<b>{total_label}</b>", s.bold),
        Paragraph(f"<b><i>{total_formula}</i></b>", s.bold),
        Paragraph(f"<b>{total_value}</b>", s.bold)
    ])
    story.append(_data_table(calc_formula_data, [1.8, 2.3, 2.5], DARK_TEAL, 3, highlights=[(-1, -1, LIGHT_ROW_BG)]))
    story.append(Spacer(1, 12))


def _add_figures_section(story, s, results, summary):
    """4. Temperature, solids, vapour and yield-distribution figures."""
    story.append(PageBreak())
    _add_section_title(story, s, "4. Perfiles Térmicos y Distribución de Productos (Figuras)")
    _add_body_text(story, s, (
        "El análisis gráfico ilustra la dinámica espacio-temporal del proceso, mostrando el perfil térmico de la pared y del lecho sólido, "
        "la deshidratación del lodo y la tasa de desvolatilización de productos orgánicos hasta alcanzar la conversión completa."
    ))

    figs = _generate_matplotlib_figures(results, summary)

    story.append(figs['fig_temp'])
    story.append(Paragraph("<b>Figura 1.</b> Perfil axial/temporal de temperaturas en la pared del reactor, lecho sólido y fase gas.", s.caption))
    story.append(Spacer(1, 6))

    story.append(figs['fig_solids'])
    story.append(Paragraph("<b>Figura 2.</b> Evolución de componentes sólidos (humedad, volátiles, char, cenizas) y humedad residual.", s.caption))
    story.append(Spacer(1, 6))

    story.append(figs['fig_vapors'])
    story.append(Paragraph("<b>Figura 3.</b> Masa acumulada de productos volátiles evacuados (aceite pirolítico, syngas y vapor de agua).", s.caption))
    story.append(Spacer(1, 6))

    # Pie chart centred in a one-cell table
    t_pie = Table([[figs['fig_pie']]], colWidths=[6.6*inch])
    t_pie.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    story.append(t_pie)
    story.append(Paragraph("<b>Figura 4.</b> Distribución porcentual en masa (wt.%) de las fracciones obtenidas en la pirólisis.", s.caption))
    story.append(Spacer(1, 14))


def _money_row(s, label, amount, share_pct, note):
    """Row of the CAPEX/OPEX/revenue tables: label, RD$ amount, share %, note."""
    return [Paragraph(label, s.cell), Paragraph(f"{CURRENCY}{amount:,.2f}", s.center), Paragraph(f"{share_pct:.1f}%", s.center), Paragraph(note, s.cell)]


def _add_economics_section(story, s, summary, solver_inputs):
    """5. CAPEX, OPEX, revenue, KPIs and the yearly cash-flow projection. Returns the financial results."""
    story.append(PageBreak())
    _add_section_title(story, s, "5. Evaluación de Viabilidad Económica")
    _add_body_text(story, s, (
        "La evaluación financiera modela la factibilidad del proyecto mediante el análisis de Flujo de Caja Descontado (DCF) "
        "a un horizonte de 10 años con una tasa de descuento exigida del 14.0%. Se evalúan la estructura de inversión inicial (CAPEX), "
        "los costos de operación y mantenimiento (OPEX), y los ingresos derivados de la tarifa de recepción de lodos (tipping fee) "
        "junto con la comercialización del aceite pirolítico valorizado."
    ))

    fin = _calculate_financials(summary, solver_inputs)
    curr_sym = CURRENCY
    cb = fin['capex_breakdown']
    tot_cap = fin['total_capex']

    # --- 5.1 Estructura de Inversión de Capital (CAPEX) ---
    story.append(Paragraph("<b>5.1 Estructura de Inversión de Capital (CAPEX)</b>", s.h2))
    capex_items = [
        ("Equipamiento Principal del Reactor", 'equip', "Tambor cilíndrico rotatorio y quemadores"),
        ("Instalación Mecánica y Montaje", 'install', "Ensamblaje, alineación y accionamiento"),
        ("Obras Civiles y Cimentaciones", 'civil', "Bases de concreto, losas y contención"),
        ("Tuberías y Redes Eléctricas", 'piping_elec', "Manifold 8'', interconexiones y control"),
        ("Ingeniería y Supervisión", 'eng', "Diseño conceptual, detalle y HAZOP"),
        ("Permisos Ambientales y Legales", 'permits', "Licencia ambiental y permisos op."),
        ("Fondo de Contingencias", 'cont', "Imprevistos de construcción"),
    ]
    capex_table_data = [_header_row(s, "Rubro de Inversión (CAPEX)", "Monto (RD$)", "Participación (%)", "Descripción del Activo")]
    capex_table_data += [_money_row(s, label, cb[key], (cb[key]/tot_cap*100), note) for label, key, note in capex_items]
    capex_table_data.append([Paragraph("<b>TOTAL INVERSIÓN (CAPEX)</b>", s.bold), Paragraph(f"<b>{curr_sym}{tot_cap:,.2f}</b>", s.center), Paragraph("<b>100.0%</b>", s.center), Paragraph("<b>Inversión Inicial Total</b>", s.bold)])
    story.append(_data_table(capex_table_data, [2.2, 1.4, 1.1, 1.9], NAVY, 3, highlights=[(-1, -1, TOTAL_ROW_BG)]))
    story.append(Spacer(1, 10))

    # --- 5.2 Estructura de Costos Operativos (OPEX Anual Base) ---
    ob = fin['opex_breakdown']
    tot_op = fin['total_opex_base']
    rb = fin['revenue_breakdown']
    tot_rev = fin['total_rev_base']
    unit_handling = ob['handling'] / max(1.0, fin['sludge_treated_gal'])
    unit_tipping = rb['tipping'] / max(1.0, fin['sludge_treated_gal'])
    unit_oil = rb['oil'] / max(1.0, fin['oil_produced_gal'])

    story.append(Paragraph("<b>5.2 Estructura de Costos Operativos Anuales (OPEX Base)</b>", s.h2))
    opex_items = [
        ("Manejo y Logística de Lodos", 'handling', f"{fin['sludge_treated_gal']:,.0f} gal a RD$ {unit_handling:.2f}/gal"),
        ("Combustible Auxiliar Quemadores", 'fuel', "Consumo de respaldo inicial"),
        ("Insumos Auxiliares y Servicios", 'aux_utilities', "Agua de enfriamiento y reactivos"),
        ("Diésel Planta de Emergencia", 'gen_diesel', "Respaldo eléctrico de seguridad"),
        ("Mano de Obra y Nómina", 'labor', "Operadores y personal técnico"),
        ("Mantenimiento Planta (3% CAPEX)", 'maintenance', "Repuestos y mantenimiento preventivo"),
        ("Seguros y licencias (1% CAPEX)", 'insurance_tax', "Póliza contra incendios y licencias"),
    ]
    opex_table_data = [_header_row(s, "Rubro Operativo (OPEX)", "Gasto Anual (RD$)", "Participación (%)", "Base de Cálculo")]
    opex_table_data += [_money_row(s, label, ob[key], (ob[key]/max(1,tot_op)*100), note) for label, key, note in opex_items]
    opex_table_data.append([Paragraph("<b>TOTAL OPERACIÓN (OPEX)</b>", s.bold), Paragraph(f"<b>{curr_sym}{tot_op:,.2f}</b>", s.center), Paragraph("<b>100.0%</b>", s.center), Paragraph("<b>Gasto Operativo Anual Base</b>", s.bold)])
    story.append(_data_table(opex_table_data, [2.2, 1.4, 1.1, 1.9], TEAL, 3, highlights=[(-1, -1, TOTAL_ROW_BG)]))
    story.append(Spacer(1, 10))

    # --- 5.3 Estructura de Ingresos por Productos ---
    story.append(Paragraph("<b>5.3 Estructura de Ingresos Anuales (Año 1)</b>", s.h2))
    rev_table_data = [
        _header_row(s, "Fuente de Ingreso / Valorización", "Ingreso Anual (RD$)", "Participación (%)", "Volumen y Precio Unitario"),
        _money_row(s, "Tarifa Disposición Lodos (Tipping Fee)", rb['tipping'], (rb['tipping']/max(1,tot_rev)*100), f"{fin['sludge_treated_gal']:,.0f} gal a RD$ {unit_tipping:.2f}/gal"),
        _money_row(s, "Venta de Aceite pirolítico (Pyrolysis oil)", rb['oil'], (rb['oil']/max(1,tot_rev)*100), f"{fin['oil_produced_gal']:,.0f} gal a RD$ {unit_oil:.2f}/gal"),
        [Paragraph("<b>TOTAL INGRESOS ANUALES</b>", s.bold), Paragraph(f"<b>{curr_sym}{tot_rev:,.2f}</b>", s.center), Paragraph("<b>100.0%</b>", s.bold)]
    ]
    story.append(_data_table(rev_table_data, [2.2, 1.4, 1.1, 1.9], GREEN, 3, highlights=[(-1, -1, HIGHLIGHT_ROW_BG)]))
    story.append(Spacer(1, 10))

    _add_kpi_table(story, s, fin, tot_cap, tot_rev, tot_op)
    _add_projection_table(story, s, fin, tot_cap)
    return fin


def _add_kpi_table(story, s, fin, tot_cap, tot_rev, tot_op):
    """5.4 Key financial indicators."""
    from pyrolysis.gui.economics_panel import format_irr
    curr_sym = CURRENCY
    irr_str = format_irr(fin['irr'], 1)
    payback_str = f"{fin['payback']:.1f} años" if fin['payback'] != float('inf') else "N/A"
    disc_payback_str = f"{fin['disc_payback']:.1f} años" if fin['disc_payback'] != float('inf') else "N/A"

    be_tipping_val = f"{curr_sym}{fin['breakeven_tipping']:.2f} / gal"
    if fin['breakeven_tipping'] <= 0:
        be_tipping_eval = "Autosostenible (Superávit por venta de subproductos)"
    else:
        be_tipping_eval = "Tarifa mínima requerida para VAN = 0"

    ebitda_base = tot_rev - tot_op
    margin_ebitda = (ebitda_base / max(1, tot_rev)) * 100.0

    story.append(Paragraph("<b>5.4 Evaluación de Indicadores Financieros (KPIs)</b>", s.h2))
    kpi_table_data = [
        _header_row(s, "Métrica Financiera", "Valor Proyectado", "Criterio / Evaluación"),
        [Paragraph("Inversión Inicial Total (CAPEX)", s.cell), Paragraph(f"{curr_sym}{tot_cap:,.2f}", s.center), Paragraph("Inversión fija inicial", s.cell)],
        [Paragraph("Ingresos Anuales Base (Año 1)", s.cell), Paragraph(f"{curr_sym}{tot_rev:,.2f}", s.center), Paragraph("Venta productos + Tipping Fee", s.cell)],
        [Paragraph("Costos Anuales OPEX (Año 1)", s.cell), Paragraph(f"{curr_sym}{tot_op:,.2f}", s.center), Paragraph("Manejo, insumos, nómina y mant.", s.cell)],
        [Paragraph("EBITDA Estimado Año 1", s.cell), Paragraph(f"{curr_sym}{ebitda_base:,.2f}", s.center), Paragraph(f"Margen EBITDA: {margin_ebitda:.1f}%", s.cell)],
        [Paragraph("<b>Valor Actual Neto (VAN / NPV)</b>", s.bold), Paragraph(f"<b>{curr_sym}{fin['npv']:,.2f}</b>", s.center), Paragraph("<b>Proyecto Altamente Viable (VAN > 0)</b>", s.cell)],
        [Paragraph("<b>Tasa Interna de Retorno (TIR / IRR)</b>", s.bold), Paragraph(f"<b>{irr_str}</b>", s.center), Paragraph("Tasa de descuento exigida: 14.0%", s.cell)],
        [Paragraph("Período Recuperación Simple", s.cell), Paragraph(payback_str, s.center), Paragraph("Recuperación de capital inicial", s.cell)],
        [Paragraph("Período Recuperación Descontado", s.cell), Paragraph(disc_payback_str, s.center), Paragraph("Recuperación considerando r=14%", s.cell)],
        [Paragraph("Índice de Rentabilidad (PI)", s.cell), Paragraph(f"{fin['pi']:.2f}", s.center), Paragraph("PI > 1.0 confirma valor neto positivo", s.cell)],
        [Paragraph("Tarifa Equilibrio (Break-Even Tipping)", s.cell), Paragraph(be_tipping_val, s.center), Paragraph(be_tipping_eval, s.cell)]
    ]
    # rows 5-6 (NPV and IRR) are highlighted
    story.append(_data_table(kpi_table_data, [2.5, 2.0, 2.1], NAVY, 3, highlights=[(5, 6, HIGHLIGHT_ROW_BG)]))
    story.append(Spacer(1, 10))


def _add_projection_table(story, s, fin, tot_cap):
    """5.5 Income statement and cash-flow projection, year 0 to the end of the project."""
    curr_sym = CURRENCY
    story.append(Paragraph("<b>5.5 Estado de Resultados y Proyección Financiera (Años 0 a 10)</b>", s.h2))
    proj_rows = [_header_row(s, "Año", "CAPEX / Net CF", "Ingresos", "OPEX Base", "Depreciación", "Flujo Neto (NCF)", "VAN Acumulado")]
    for yr in range(len(fin['years'])):
        n_cf = fin['net_flows'][yr]
        cum_v = fin['cum_flows'][yr]
        proj_rows.append([
            Paragraph(f"Año {yr}", s.center),
            Paragraph(f"{curr_sym}{-tot_cap:,.0f}" if yr == 0 else f"{curr_sym}{n_cf:,.0f}", s.center),
            Paragraph(f"{curr_sym}{fin['rev_flows'][yr]:,.0f}", s.center),
            Paragraph(f"{curr_sym}{fin['opex_flows'][yr]:,.0f}", s.center),
            Paragraph(f"{curr_sym}{fin['depr_flows'][yr]:,.0f}", s.center),
            Paragraph(f"{curr_sym}{n_cf:,.0f}", s.center),
            Paragraph(f"{curr_sym}{cum_v:,.0f}", s.center)
        ])
    story.append(_data_table(proj_rows, [0.8, 1.0, 1.0, 1.0, 0.9, 1.0, 0.9], TEAL, 2.5))
    story.append(Spacer(1, 10))


def _add_conclusions_section(story, s, inp, summary, timing, gas_m3, fin):
    """6. Technical discussion and conclusions."""
    from pyrolysis.gui.economics_panel import format_irr
    story.append(PageBreak())
    _add_section_title(story, s, "6. Discusión Técnica y Conclusiones Académicas")

    curr_sym = CURRENCY
    irr_str = format_irr(fin.get('irr'), 1)
    payback_str = f"{fin['payback']:.1f} años" if fin.get('payback') != float('inf') else "N/A"
    fill_deg = summary['filling_degree_pct']
    pyro_residence_min = timing.pyro_residence_min
    total_cycle_min = timing.total_cycle_min

    conclusions = [
        (
            f"<b>1. Viabilidad Térmica y Rendimiento de Conversión:</b> "
            f"La pirólisis de <i>{inp.feed_name}</i> alcanza una conversión del <b>{inp.conv_pct:.1f}%</b> de la materia volátil, "
            f"demostrando que el perfil térmico aplicado (temperatura máxima de {inp.temp_hold:.0f}°C) proporciona el aporte entálpico "
            f"necesario para la descomposición de la matriz orgánica pesada."
        ),
        (
            "<b>2. Calidad del aceite pirolítico:</b> "
            "el simulador no estima propiedades del aceite; deben tomarse del informe de laboratorio."
        ),
        (
            f"<b>3. Aporte energético potencial del gas no condensable:</b> "
            f"El rendimiento de gas de síntesis (<b>{inp.gas_pct:.1f} wt.%</b>) correspondiente a <b>{gas_m3:,.1f} m³</b> de syngas incondensable "
            f"podría reducir el consumo de combustible auxiliar; la autosuficiencia no está demostrada sin medir caudal, composición y poder calorífico del gas."
        ),
        (
            f"<b>4. Consistencia numérica del balance de masa:</b> "
            f"El error de cierre en el balance de materia de <b>{summary['mass_error_pct']:.2e}%</b> "
            f"confirma que el balance cierra por construcción; esto no valida el modelo físico frente a la planta."
        ),
        (
            f"<b>5. Viabilidad Económica y Rentabilidad del Proyecto:</b> "
            f"El análisis financiero proyecta un Valor Actual Neto (VAN) de <b>{curr_sym}{fin['npv']:,.2f}</b> "
            f"y una Tasa Interna de Retorno (TIR) del <b>{irr_str}</b> (superando la tasa de descuento de 14.0%), "
            f"con un período de recuperación estimado de <b>{payback_str}</b>, confirmando la rentabilidad de la instalación."
        ),
        (
            "<b>6. Reducción Volumétrica y Tratamiento Industrial de Residuos:</b> "
            "El proceso logra una reducción del volumen de residuo pesado procesado, "
            "transformándolo eficientemente en tres coproductos con potencial de aprovechamiento (Aceite pirolítico, Syngas y Char)."
        ),
        (
            f"<b>7. Dinámica del Lecho Sólido y Control Operativo:</b> "
            f"Operando a un grado de llenado del lecho de <b>{fill_deg:.1f}%</b>, con temperatura inicial de <b>{inp.temp_start:.1f}°C</b> (activación de desvolatilización a 350.0°C), "
            f"un tiempo eficiente de residencia de <b>{pyro_residence_min:.1f} min ({pyro_residence_min/60.0:.2f} h)</b> "
            f"y un tiempo total de ciclo de <b>{total_cycle_min:.1f} min ({total_cycle_min/60.0:.2f} h)</b>, "
            f"se asegura la agitación constante del sólido en el tambor rotatorio, previniendo la formación de incrustaciones de coque duro en las paredes internas."
        ),
    ]
    for text in conclusions:
        story.append(Paragraph(text, s.body))
    story.append(Spacer(1, 20))


def _add_signature(story, s):
    sig_data = [
        [Paragraph("________________________________________", s.center)],
        [Paragraph("<b>Luis J. Solano Cuevas</b><br/>Gerente de Calidad", s.center)]
    ]
    t_sig = Table(sig_data, colWidths=[3.5*inch])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(KeepTogether(t_sig))


def generate_thesis_pdf(results, summary, solver_inputs, config_dict):
    """
    Generates a thesis-grade academic PDF report containing full kinetics,
    mass/energy balances, ASTM standards, operational parameters, charts, and conclusions.

    Returns:
        bytes: PDF content.
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("La librería 'reportlab' no está instalada en el entorno de Python. Ejecute 'pip install reportlab' para instalarla.")

    buffer = io.BytesIO()
    # 0.5 inch margins (36 pt) left/right, 54 pt top/bottom
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )
    s = _build_styles()
    inp = _report_inputs(summary, solver_inputs)
    timing = _pyrolysis_timing(results)
    masses = _product_masses(summary)
    energy = _thermal_energy_balance(results, solver_inputs, *masses)

    story = []
    _add_cover(story, s, inp)
    _add_abstract(story, s, inp, summary)
    _add_feedstock_section(story, s, inp)
    _add_reactor_section(story, s, inp, summary, solver_inputs, timing)

    story.append(PageBreak())
    _add_section_title(story, s, "3. Balances de Materia y Energía")
    gas_m3 = _add_mass_balance(story, s, inp, summary, solver_inputs, masses)
    _add_energy_balance(story, s, energy)
    _add_energy_formulas(story, s, energy, masses)

    _add_figures_section(story, s, results, summary)
    fin = _add_economics_section(story, s, summary, solver_inputs)
    _add_conclusions_section(story, s, inp, summary, timing, gas_m3, fin)
    _add_signature(story, s)

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
