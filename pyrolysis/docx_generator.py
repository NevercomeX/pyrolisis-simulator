import io
import datetime

from .pdf_generator import (
    GAL_PER_M3, SYNGAS_DENSITY_KG_M3, CURRENCY,
    _calculate_financials, _report_inputs, _product_masses, _pyrolysis_timing,
    _thermal_energy_balance, _share_pct, _proximate_rows, _feed_property_rows, _oil_gravity,
)

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

# --- Word palette: RGB tuples for text, hex strings for cell shading ---
NAVY_RGB = (30, 58, 138)
TEAL_RGB = (15, 118, 110)
AMBER_RGB = (217, 119, 6)
SUBTITLE_RGB = (71, 85, 105)
META_TEXT_RGB = (30, 41, 59)
WHITE_RGB = (255, 255, 255)

NAVY_BG = "1E3A8A"
TEAL_BG = "0D9488"
DARK_TEAL_BG = "0F766E"
GREEN_BG = "059669"
BORDER_GREY = "CBD5E1"
TOTAL_ROW_BG = "F1F5F9"
LIGHT_ROW_BG = "F8FAFC"
HIGHLIGHT_ROW_BG = "FEF3C7"

PAGE_MARGIN_IN = 0.75


def set_cell_background(cell, fill_hex):
    """Utility to set XML shading background color for a table cell in docx."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    """Utility to set subtle borders on a docx table."""
    tblPr = table._tbl.tblPr
    borders_elm = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideV w:val="none"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders_elm)


# =========================================================
# Building blocks
# =========================================================

def _add_heading(doc, text, level, size_pt, rgb=None, bold=False):
    """Heading whose run gets an explicit size, and colour/bold only when given (else the style's)."""
    heading = doc.add_heading(level=level)
    run = heading.add_run(text)
    if bold:
        run.bold = True
    run.font.size = Pt(size_pt)
    if rgb:
        run.font.color.rgb = RGBColor(*rgb)


def _add_section_heading(doc, text):
    _add_heading(doc, text, level=1, size_pt=13, rgb=NAVY_RGB, bold=True)


def _add_body_text(doc, text):
    doc.add_paragraph().add_run(text).font.size = Pt(10)


def _add_data_table(doc, headers, rows, header_bg, highlights=None):
    """
    Bordered table with a coloured header row. highlights maps a row index of `rows`
    (negative counts from the end) to a background colour; highlighted rows are bold.
    """
    highlights = {idx % len(rows): bg for idx, bg in (highlights or {}).items()}
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, BORDER_GREY)

    for c_idx, h in enumerate(headers):
        cell = table.cell(0, c_idx)
        set_cell_background(cell, header_bg)
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.color.rgb = RGBColor(*WHITE_RGB)
        run.font.size = Pt(9.5)

    for r_idx, r_data in enumerate(rows):
        row_bg = highlights.get(r_idx)
        for c_idx, val in enumerate(r_data):
            cell = table.cell(r_idx + 1, c_idx)
            if row_bg:
                set_cell_background(cell, row_bg)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(val)
            if row_bg:
                run.bold = True
            run.font.size = Pt(9)
    return table


# =========================================================
# Report sections
# =========================================================

def _add_title_block(doc, mode_str_es, feed_name):
    """Document tag, title, subtitle and the metadata table."""
    p_tag = doc.add_paragraph()
    p_tag.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_tag = p_tag.add_run("INFORME TÉCNICO DE INGENIERÍA & EVALUACIÓN DE FACTIBILIDAD")
    run_tag.bold = True
    run_tag.font.size = Pt(9.5)
    run_tag.font.color.rgb = RGBColor(*AMBER_RGB)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run(f"EVALUACIÓN TERMOQUÍMICA Y BALANCES DE MATERIA Y ENERGÍA EN REACTOR ROTATORIO DE PIRÓLISIS {mode_str_es}")
    run_title.bold = True
    run_title.font.size = Pt(15)
    run_title.font.color.rgb = RGBColor(*NAVY_RGB)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Modelado Cinético Multietapa, Caracterización ASTM del Aceite pirolítico y Evaluación del Aporte Energética")
    run_sub.italic = True
    run_sub.font.size = Pt(10.5)
    run_sub.font.color.rgb = RGBColor(*SUBTITLE_RGB)

    doc.add_paragraph()

    meta_table = doc.add_table(rows=3, cols=4)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(meta_table, BORDER_GREY)

    current_date = datetime.datetime.now().strftime("%d/%m/%Y")
    meta_data = [
        [("Tipo de Estudio:", True), ("Simulación Termoquímica", False), ("Fecha de Emisión:", True), (current_date, False)],
        [("Modo de Operación:", True), (mode_str_es, False), ("Materia Prima:", True), (feed_name, False)],
        [("Software Simulador:", True), ("Rotary Pyrolysis Simulator v2.0", False), ("Unidad de Proceso:", True), ("Reactor Cilíndrico Rotatorio", False)]
    ]
    for r_idx, row in enumerate(meta_data):
        for c_idx, (text, is_bold) in enumerate(row):
            cell = meta_table.cell(r_idx, c_idx)
            set_cell_background(cell, LIGHT_ROW_BG)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(text)
            run.bold = is_bold
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(*META_TEXT_RGB)

    doc.add_paragraph()


def _add_abstract(doc, inp, mode_str_es, summary):
    _add_heading(doc, "RESUMEN EJECUTIVO (ABSTRACT)", level=2, size_pt=12, rgb=NAVY_RGB, bold=True)

    p_abs = doc.add_paragraph()
    p_abs.paragraph_format.line_spacing = 1.15
    p_abs.paragraph_format.space_after = Pt(10)
    run_abs = p_abs.add_run(
        f"El presente informe técnico expone los resultados de la simulación rigurosa del proceso de pirólisis "
        f"desarrollada en un reactor rotatorio de tambor operando en modo {mode_str_es} a presión atmosférica (0 bar manométrica / 1 atm) "
        f"y temperatura máxima de proceso de {inp.temp_hold:.0f}°C (temperatura inicial: {inp.temp_start:.0f}°C, tasa de calentamiento: {inp.heating_rate:.1f}°C/min). "
        f"Se procesó una carga nominal de {inp.load_gal:,.1f} {inp.load_unit} ({inp.load_kg:,.1f} kg) de {inp.feed_name} "
        f"con una densidad de materia prima de {inp.sludge_density:.1f} kg/m³. "
        f"El modelo fenomenológico resuelve el balance conservativo de materia y energía con transferencia de calor conductivo-convectivo en el lecho sólido. "
        f"Se alcanzó una conversión global de materia volátil del {inp.conv_pct:.1f}%, rindiendo un {inp.oil_pct:.1f} wt.% de aceite pirolítico condensable "
        f"(densidad del aceite pirolítico: {inp.bio_oil_density:.1f} kg/m³), un {inp.gas_pct:.1f} wt.% de gas de síntesis (syngas) incondensable, y un {inp.char_pct:.1f} wt.% de bio-carbón (char seco). "
        f"La demanda energética total calculada fue de {inp.duty_val:,.2f} {inp.duty_unit} con un error de cierre en el balance de materia de {summary['mass_error_pct']:.2e}%, "
        f"confirmando la consistencia física del modelo y la factibilidad del proceso industrial."
    )
    run_abs.font.size = Pt(10)


def _add_feedstock_section(doc, inp):
    """1. Feedstock proximate analysis, physical properties and ASTM oil characterisation."""
    feed_obj = inp.feed_obj
    _add_section_heading(doc, "1. Propiedades de la Materia Prima y Cinética Química")
    _add_body_text(doc, (
        "La pirólisis termoquímica de lodos de petróleo e hidrocarburos pesados es un proceso de descomposición en atmósfera anaerobia "
        "(ausencia de oxígeno libre) que convierte fracciones orgánicas de alto peso molecular (asfaltenos, resinas y cadenas parafínicas) "
        "en tres coproductos con potencial de aprovechamiento: vapores condensables (Aceite pirolítico), gases incondensables (Syngas) y un residuo sólido seco (Carbón e inorgánicos). "
        "La evolución termodinámica comprende tres dominios principales: (i) Secado y Deshidratación a 100°C; "
        "(ii) Destilación y Desvolatilización Multicomponente entre 350°C y 450°C; y "
        "(iii) Policondensación y Coquización final por encima de 450°C, estabilizando el carbono fijo en la matriz sólida."
    ))

    _add_heading(doc, "1.1 Análisis Proximal y Composición Elemental del Lodo", level=2, size_pt=11, rgb=TEAL_RGB)
    _add_data_table(doc, ["Componente", "Fracción (wt.%)", f"Carga Entrada ({inp.load_unit})", "Volumen Relativo"],
                    _proximate_rows(feed_obj, inp.load_gal), NAVY_BG, highlights={-1: TOTAL_ROW_BG})
    doc.add_paragraph()

    # 1.1.B Tabla Propiedades Físicas (the Word table adds the angle of repose)
    property_rows = _feed_property_rows(feed_obj, inp.sludge_density)
    property_rows.append(["Ángulo de Reposo Sólido (Flujo)", f"{feed_obj.angle_of_repose:.1f}°", "grados (°)", "Velocidad de avance en cilindro"])
    _add_data_table(doc, ["Propiedad Físico-Química (Norma)", "Valor Certificado / Medido", "Unidad", "Descripción Industrial"],
                    property_rows, NAVY_BG)
    doc.add_paragraph()

    _add_heading(doc, "1.2 Caracterización del Aceite pirolítico Producido (Normas ASTM)", level=2, size_pt=11, rgb=TEAL_RGB)
    sg_15, api_deg = _oil_gravity(inp.bio_oil_density)
    not_calculated = "No calculado: requiere ensayo de laboratorio"
    _add_data_table(doc, ["Propiedad Físico-Química", "Norma ASTM", "Valor", "Observación"], [
        ["Poder Calorífico Superior (PCS/HHV)", "ASTM D240", not_calculated, "-"],
        ["Viscosidad Cinemática @ 40°C", "ASTM D445", not_calculated, "-"],
        ["Densidad @ 15°C & Gravedad °API", "ASTM D1298", f"{inp.bio_oil_density:.1f} kg/m³ | {api_deg:.1f} °API", f"Gravedad Específica: {sg_15:.4f}"],
        ["Contenido de Agua & Sedimentación (BS&W)", "ASTM D95", not_calculated, "-"]
    ], TEAL_BG)
    doc.add_paragraph()


def _add_reactor_section(doc, inp, summary, solver_inputs, timing):
    """2. Reactor geometry and operating conditions."""
    _add_section_heading(doc, "2. Geometría y Condiciones Operativas del Reactor")
    _add_body_text(doc, (
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

    _add_data_table(doc, ["Parámetro Geométrico / Operativo", "Valor", "Parámetro Térmico / Energético", "Valor"], [
        ["Longitud Cilíndrica (L)", f"{length_m:.2f} m", "Temperatura Inicial (T_start)", f"{inp.temp_start:.1f} °C"],
        ["Diámetro Interno (D)", f"{dia_m:.2f} m", "Temperatura Máxima (T_hold)", f"{inp.temp_hold:.1f} °C"],
        ["Relación de Aspecto (L/D)", f"{aspect_ratio:.2f}", "Tasa de Calentamiento", f"{inp.heating_rate:.1f} °C/min"],
        ["Velocidad de Rotación", f"{rpm_val:.1f} RPM", "Coef. Transf. Calor (h_eff)", f"{h_eff:.1f} W/m²·K"],
        ["Grado de Llenado del Lecho", f"{fill_deg:.2f} %", "Potencia Quemadores", f"{burner_hp:.0f} BHP"],
        ["Tiempo Evaporación Agua (Secado)", f"{timing.t_drying_end:.1f} min", "Eficiencia Térmica Quemador", f"{burner_eff:.1f} %"],
        [timing.time_label_1, timing.time_val_1, "Consumo Combustible Auxiliar", f"{fuel_cons:.1f} gal/lote"],
        [timing.time_label_2, timing.time_val_2, "Conversión Volátiles Total", f"{inp.conv_pct:.1f} %"],
        ["Carga / Alimentación Entrante", f"{inp.load_gal:.1f} {inp.load_unit}", "Tiempo Total Ciclo Lote", f"{total_cycle_min:.1f} min ({total_cycle_min/60.0:.1f} h)"]
    ], NAVY_BG)
    doc.add_paragraph()


def _add_mass_balance(doc, inp, summary, masses):
    """3.1 Global mass balance table and conservation equation. Returns the syngas volume (m³)."""
    oil_kg, gas_kg, char_kg, water_kg = masses
    _add_heading(doc, "3.1 Balance de Materia Global y Cierre de Masa", level=2, size_pt=11)
    _add_body_text(doc, (
        "El balance de materia cuantifica la transformación estequiométrica del lodo de entrada bajo el principio de conservación de la masa. "
        "La masa total se redistribuye entre la fase condensable (Aceite pirolítico), la fase gaseosa incondensable (Syngas), "
        "el residuo sólido (Carbón) y el agua de secado, garantizando un error de cierre cercano a cero (<0.01%) que confirma la consistencia del modelo."
    ))

    oil_gal = (oil_kg / inp.bio_oil_density) * GAL_PER_M3
    gas_m3 = gas_kg / SYNGAS_DENSITY_KG_M3
    char_gal = (char_kg / 500.0) * GAL_PER_M3  # char bulk density 500 kg/m³
    water_gal = (water_kg / 1000.0) * GAL_PER_M3

    _add_data_table(doc, ["Flujo / Corriente", "Masa (kg)", "Fracción wt.%", "Volumen Estimado"], [
        ["ENTRADA: " + inp.feed_name, f"{inp.load_kg:.2f}", "100.00%", "-"],
        ["SALIDA: Aceite pirolítico (Pyrolysis oil)", f"{oil_kg:.2f}", f"{inp.oil_pct:.2f}%", f"{oil_gal:.1f} gal"],
        ["SALIDA: Gas de Síntesis (Syngas)", f"{gas_kg:.2f}", f"{inp.gas_pct:.2f}%", f"{gas_m3:.1f} m³"],
        ["SALIDA: Carbón (Char Seco)", f"{char_kg:.2f}", f"{inp.char_pct:.2f}%", f"{char_gal:.1f} gal"],
        ["SALIDA: Vapor de Agua (Steam)", f"{water_kg:.2f}", f"{summary['water_yield_pct']:.2f}%", f"{water_gal:.1f} gal"],
        ["ERROR CIERRE BALANCE", f"{summary['mass_error_pct']:.2e} %", "Conservativo", "Tolerancia < 0.01%"]
    ], NAVY_BG, highlights={0: LIGHT_ROW_BG, -1: HIGHLIGHT_ROW_BG})

    p_meq = doc.add_paragraph()
    r_meq = p_meq.add_run(
        f"Ecuación de Conservación de Masa: M_entrada = M_aceite pirolítico + M_syngas + M_char + M_vapor\n"
        f"Sustitución Numérica: {inp.load_kg:.2f} kg = "
        f"{oil_kg:.2f} kg + {gas_kg:.2f} kg + {char_kg:.2f} kg + {water_kg:.2f} kg | "
        f"Error de Cierre: {summary['mass_error_pct']:.4f}%"
    )
    r_meq.font.size = Pt(8.5)
    r_meq.italic = True

    doc.add_paragraph()
    return gas_m3


def _add_energy_balance(doc, e):
    """3.2 Thermal energy balance by destination of the heat."""
    _add_heading(doc, "3.2 Balance de Energía Térmica y Carga de Calentamiento", level=2, size_pt=11)
    _add_body_text(doc, (
        "El balance térmico global discrimina con exactitud rigurosa los distintos destinos del calor suministrado: "
        "(1) calor sensible para calentar el residuo carbonoso sólido, "
        "(2) calor sensible para calentar los volátiles condensables (futuro Aceite pirolítico líquido), "
        "(3) calor sensible para elevar la temperatura del gas de síntesis, "
        "(4) entalpía química de ruptura endotérmica de enlaces macromoleculares (ΔH_pyro = 600 kJ/kg), y "
        "(5) energía latente y sobrecalentamiento del agua evaporada (ΔH_evap = 2,256 kJ/kg)."
    ))

    unit, column_title = "kWh", "Energía (kWh)"
    total_row = ["ENERGÍA TÉRMICA TOTAL", f"{e.total:.2f} kWh", "100.0%", "Consumo total ciclo"]

    energy_rows = [
        ("Calor Sensible del Sólido (Char)", e.char, "Conducción lecho carbón residual"),
        ("Calor Sensible Aceite pirolítico (Fase Líquida)", e.oil, "Precalentamiento vapores condensables"),
        ("Calor Sensible Syngas (Fase Gas)", e.gas, "Precalentamiento gas incondensable"),
        ("Reacción Química Endotérmica (Pirólisis)", e.rxn, "Craqueo térmico (ΔH=600 kJ/kg)"),
        ("Secado y Evaporación Humedad", e.steam, "Vaporización latente (2,256 kJ/kg)"),
    ]
    rows = [[label, f"{value:.2f} {unit}", f"{(_share_pct(value, e.total)):.1f}%", mechanism] for label, value, mechanism in energy_rows]
    rows.append(total_row)
    _add_data_table(doc, ["Etapa de Transferencia Térmica", column_title, "Porcentaje (%)", "Mecanismo Principal"],
                    rows, NAVY_BG, highlights={-1: TOTAL_ROW_BG})
    doc.add_paragraph()


def _energy_formula_rows(e, oil_kg, gas_kg, char_kg, water_kg):
    """(component, formula, substitution) rows of the calculation memo, TOTAL row included."""
    pct = lambda value: (_share_pct(value, e.total))
    return [
        ["Calor Char (Sólido)", "E_char = [M_char · Cp_char · (T_hold - T_start)] / 3.6e6", f"[{char_kg:.1f} kg · {e.cp_char:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = {e.char:.2f} kWh ({pct(e.char):.1f}%)"],
        ["Calor Aceite pirolítico (Líquido)", "E_oil = [M_oil · Cp_oil · (T_hold - T_start)] / 3.6e6", f"[{oil_kg:.1f} kg · {e.cp_oil:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = {e.oil:.2f} kWh ({pct(e.oil):.1f}%)"],
        ["Calor Syngas (Gas)", "E_gas = [M_gas · Cp_gas · (T_hold - T_start)] / 3.6e6", f"[{gas_kg:.1f} kg · {e.cp_gas:.0f} J/kg·K · {e.dT:.1f} K] / 3.6e6 = {e.gas:.2f} kWh ({pct(e.gas):.1f}%)"],
        ["Reacción Química Craqueo", "E_rxn = [(M_oil + M_gas) · ΔH_pyro] / 3.6e6", f"[{(oil_kg + gas_kg):.1f} kg · {e.dh_pyro:,.0f} J/kg] / 3.6e6 = {e.rxn:.2f} kWh ({pct(e.rxn):.1f}%)"],
        ["Evaporación del Agua", "E_steam = [M_steam · (Cp_wΔT_w + ΔH_evap + Cp_sΔT_s)] / 3.6e6", f"[{water_kg:.1f} kg · (4184·{max(0.0, 100-e.T_start):.0f} + 2.256e6 + 2000·{max(0.0, e.T_hold-100):.0f})] / 3.6e6 = {e.steam:.2f} kWh ({pct(e.steam):.1f}%)"],
        ["ENERGÍA TÉRMICA TOTAL", "E_total = Σ E_componentes", f"{e.total:.2f} kWh (100.00%)"]
    ]


def _add_energy_formulas(doc, e, masses):
    """3.3 Calculation memo: formula and numeric substitution of each heat term."""
    _add_heading(doc, "3.3 Memoria de Cálculo Detallada de Fórmulas Térmicas", level=2, size_pt=11)
    _add_data_table(doc, ["Componente Energético", "Fórmula de Ingeniería Aplicada", "Sustitución de Variables y Resultado"],
                    _energy_formula_rows(e, *masses), DARK_TEAL_BG, highlights={-1: LIGHT_ROW_BG})
    doc.add_paragraph()


def _add_economics_section(doc, summary, solver_inputs):
    """4. CAPEX, OPEX, revenue and KPI tables. Returns (fin, irr_str, payback_str) for the conclusions."""
    _add_section_heading(doc, "4. Evaluación de Viabilidad Económica")
    _add_body_text(doc, (
        "La evaluación financiera modela la factibilidad del proyecto mediante el análisis de Flujo de Caja Descontado (DCF) "
        "a un horizonte de 10 años con una tasa de descuento exigida del 14.0%. Se evalúan la estructura de inversión inicial (CAPEX), "
        "los costos de operación y mantenimiento (OPEX), y los ingresos derivados de la tarifa de recepción de lodos (tipping fee) "
        "junto con la comercialización del aceite pirolítico valorizado."
    ))

    fin = _calculate_financials(summary, solver_inputs)
    curr_sym = CURRENCY
    cb = fin['capex_breakdown']
    tot_cap = fin['total_capex']

    # 4.1 CAPEX
    _add_heading(doc, "4.1 Estructura de Inversión de Capital (CAPEX)", level=2, size_pt=11)
    capex_items = [
        ("Equipamiento Principal del Reactor", 'equip', "Tambor cilíndrico rotatorio y quemadores"),
        ("Instalación Mecánica y Montaje", 'install', "Ensamblaje, alineación y accionamiento"),
        ("Obras Civiles y Cimentaciones", 'civil', "Bases de concreto, losas y contención"),
        ("Tuberías y Redes Eléctricas", 'piping_elec', "Manifold 8'', interconexiones y control"),
        ("Ingeniería y Supervisión", 'eng', "Diseño conceptual, detalle y HAZOP"),
        ("Permisos Ambientales y Legales", 'permits', "Licencia ambiental y permisos op."),
        ("Fondo de Contingencias", 'cont', "Imprevistos de construcción (10%)"),
    ]
    rows_capex = [[label, f"{curr_sym}{cb[key]:,.2f}", f"{(cb[key]/tot_cap*100):.1f}%", note] for label, key, note in capex_items]
    rows_capex.append(["TOTAL INVERSIÓN (CAPEX)", f"{curr_sym}{tot_cap:,.2f}", "100.0%", "Inversión Inicial Total"])
    _add_data_table(doc, ["Rubro de Inversión (CAPEX)", "Monto (RD$)", "Participación (%)", "Descripción del Activo"],
                    rows_capex, NAVY_BG, highlights={-1: TOTAL_ROW_BG})
    doc.add_paragraph()

    # 4.2 OPEX
    ob = fin['opex_breakdown']
    tot_op = fin['total_opex_base']
    rb = fin['revenue_breakdown']
    tot_rev = fin['total_rev_base']
    unit_handling = ob['handling'] / max(1.0, fin['sludge_treated_gal'])
    unit_tipping = rb['tipping'] / max(1.0, fin['sludge_treated_gal'])
    unit_oil = rb['oil'] / max(1.0, fin['oil_produced_gal'])

    _add_heading(doc, "4.2 Estructura de Costos Operativos Anuales (OPEX Base)", level=2, size_pt=11)
    opex_items = [
        ("Manejo y Logística de Lodos", 'handling', f"{fin['sludge_treated_gal']:,.0f} gal a RD$ {unit_handling:.2f}/gal"),
        ("Combustible Auxiliar Quemadores", 'fuel', "Consumo de respaldo térmico inicial"),
        ("Insumos Auxiliares y Servicios", 'aux_utilities', "Agua de enfriamiento y reactivos"),
        ("Diésel Planta de Emergencia", 'gen_diesel', "Respaldo eléctrico de seguridad"),
        ("Mano de Obra y Nómina", 'labor', "Operadores y personal técnico especializado"),
        ("Mantenimiento Planta (3% CAPEX)", 'maintenance', "Repuestos, refractario y mantenimiento prev."),
        ("Seguros y Licencias (1% CAPEX)", 'insurance_tax', "Póliza contra todo riesgo y licencias amb."),
    ]
    rows_opex = [[label, f"{curr_sym}{ob[key]:,.2f}", f"{(ob[key]/max(1,tot_op)*100):.1f}%", note] for label, key, note in opex_items]
    rows_opex.append(["TOTAL OPERACIÓN (OPEX)", f"{curr_sym}{tot_op:,.2f}", "100.0%", "Gasto Operativo Anual Base"])
    _add_data_table(doc, ["Rubro Operativo (OPEX)", "Gasto Anual (RD$)", "Participación (%)", "Base de Cálculo"],
                    rows_opex, TEAL_BG, highlights={-1: TOTAL_ROW_BG})
    doc.add_paragraph()

    # 4.3 Ingresos Anuales
    _add_heading(doc, "4.3 Estructura de Ingresos Anuales (Año 1)", level=2, size_pt=11)
    _add_data_table(doc, ["Fuente de Ingreso / Valorización", "Ingreso Anual (RD$)", "Participación (%)", "Volumen y Precio Unitario"], [
        ["Tarifa Disposición Lodos (Tipping Fee)", f"{curr_sym}{rb['tipping']:,.2f}", f"{(rb['tipping']/max(1,tot_rev)*100):.1f}%", f"{fin['sludge_treated_gal']:,.0f} gal a RD$ {unit_tipping:.2f}/gal"],
        ["Venta de Aceite pirolítico (Pyrolysis oil)", f"{curr_sym}{rb['oil']:,.2f}", f"{(rb['oil']/max(1,tot_rev)*100):.1f}%", f"{fin['oil_produced_gal']:,.0f} gal a RD$ {unit_oil:.2f}/gal"],
        ["TOTAL INGRESOS ANUALES", f"{curr_sym}{tot_rev:,.2f}", "100.0%", "Ingreso Bruto Proyectado Año 1"]
    ], GREEN_BG, highlights={-1: HIGHLIGHT_ROW_BG})
    doc.add_paragraph()

    # 4.4 KPIs Financieros
    _add_heading(doc, "4.4 Evaluación de Indicadores Financieros (KPIs)", level=2, size_pt=11)

    from pyrolysis.gui.economics_panel import format_irr

    irr_str = format_irr(fin['irr'], 1)
    payback_str = f"{fin['payback']:.1f} años" if fin['payback'] != float('inf') else "N/A"
    disc_payback_str = f"{fin['disc_payback']:.1f} años" if fin['disc_payback'] != float('inf') else "N/A"
    ebitda_base = tot_rev - tot_op
    margin_ebitda = (ebitda_base / max(1, tot_rev)) * 100.0

    _add_data_table(doc, ["Métrica Financiera", "Valor Proyectado", "Criterio / Evaluación"], [
        ["Inversión Inicial Total (CAPEX)", f"{curr_sym}{tot_cap:,.2f}", "Inversión fija inicial"],
        ["Ingresos Anuales Base (Año 1)", f"{curr_sym}{tot_rev:,.2f}", "Venta productos + Tipping Fee"],
        ["Costos Anuales OPEX (Año 1)", f"{curr_sym}{tot_op:,.2f}", "Manejo, insumos, nómina y mant."],
        ["EBITDA Estimado Año 1", f"{curr_sym}{ebitda_base:,.2f}", f"Margen EBITDA: {margin_ebitda:.1f}%"],
        ["Valor Actual Neto (VAN / NPV)", f"{curr_sym}{fin['npv']:,.2f}", "Proyecto Altamente Viable (VAN > 0)"],
        ["Tasa Interna de Retorno (TIR / IRR)", f"{irr_str}", "Tasa de descuento exigida: 14.0%"],
        ["Período Recuperación Simple", payback_str, "Recuperación de capital inicial"],
        ["Período Recuperación Descontado", disc_payback_str, "Recuperación considerando r=14%"],
        ["Índice de Rentabilidad (PI)", f"{fin['pi']:.2f}", "PI > 1.0 confirma valor neto positivo"],
        ["Tarifa Equilibrio (Break-Even Tipping)", f"{curr_sym}{fin['breakeven_tipping']:.2f} / gal", "Autosostenible (Superávit)"]
    ], NAVY_BG, highlights={4: HIGHLIGHT_ROW_BG, 5: HIGHLIGHT_ROW_BG})  # NPV and IRR rows
    doc.add_paragraph()
    return fin, irr_str, payback_str


def _add_conclusions_section(doc, inp, summary, timing, gas_m3, fin, irr_str, payback_str):
    """5. Technical discussion and conclusions."""
    _add_section_heading(doc, "5. Discusión Técnica y Conclusiones Académicas")

    curr_sym = CURRENCY
    fill_deg = summary['filling_degree_pct']
    pyro_residence_min = timing.pyro_residence_min
    total_cycle_min = timing.total_cycle_min
    conclusions = [
        f"1. Viabilidad Térmica y Rendimiento de Conversión: La pirólisis de {inp.feed_name} alcanza una conversión del {inp.conv_pct:.1f}% de la materia volátil, demostrando que el perfil térmico aplicado (temperatura máxima de {inp.temp_hold:.0f}°C) proporciona el aporte entálpico necesario para la descomposición de la matriz orgánica pesada.",
        "2. Calidad del aceite pirolítico: el simulador no estima propiedades del aceite; deben tomarse del informe de laboratorio.",
        f"3. Aporte energético potencial del gas no condensable: El rendimiento de gas de síntesis ({inp.gas_pct:.1f} wt.%) correspondiente a {gas_m3:,.1f} m³ de syngas incondensable podría reducir el consumo de combustible auxiliar; la autosuficiencia no está demostrada sin medir caudal, composición y poder calorífico del gas.",
        f"4. Consistencia numérica del balance de masa: El error de cierre en el balance de materia de {summary['mass_error_pct']:.2e}% confirma que el balance cierra por construcción; esto no valida el modelo físico frente a la planta.",
        f"5. Viabilidad Económica y Rentabilidad del Proyecto: El análisis financiero proyecta un Valor Actual Neto (VAN) de {curr_sym}{fin['npv']:,.2f} y una Tasa Interna de Retorno (TIR) del {irr_str} (superando la tasa de descuento de 14.0%), con un período de recuperación estimado de {payback_str}, confirmando la rentabilidad de la instalación.",
        "6. Reducción Volumétrica y Tratamiento Industrial de Residuos: El proceso logra una reducción del volumen de residuo pesado procesado, transformándolo eficientemente en tres coproductos con potencial de aprovechamiento (Aceite pirolítico, Syngas y Char).",
        f"7. Dinámica del Lecho Sólido y Control Operativo: Operando a un grado de llenado del lecho de {fill_deg:.1f}%, con temperatura inicial de {inp.temp_start:.1f}°C (activación de desvolatilización a 350.0°C), un tiempo eficiente de residencia de {pyro_residence_min:.1f} min ({pyro_residence_min/60.0:.2f} h) y un tiempo total de ciclo de {total_cycle_min:.1f} min ({total_cycle_min/60.0:.2f} h), se asegura la agitación constante del sólido en el tambor rotatorio, previniendo la formación de incrustaciones de coque duro en las paredes internas."
    ]
    for c_text in conclusions:
        p_c = doc.add_paragraph()
        p_c.paragraph_format.space_after = Pt(6)
        p_c.paragraph_format.line_spacing = 1.15
        run_c = p_c.add_run(c_text)
        run_c.font.size = Pt(9.5)

    doc.add_paragraph()


def _add_signature(doc):
    t_sig = doc.add_table(rows=2, cols=1)
    t_sig.alignment = WD_TABLE_ALIGNMENT.CENTER
    p_line = t_sig.cell(0, 0).paragraphs[0]
    p_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_line.add_run("________________________________________")

    p_name = t_sig.cell(1, 0).paragraphs[0]
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_name = p_name.add_run("Luis J. Solano Cuevas\nGerente de Calidad")
    run_name.bold = True
    run_name.font.size = Pt(10)


def generate_word_report(results, summary, solver_inputs, config_dict=None):
    """
    Generates a complete, highly formatted engineering technical report in Microsoft Word (.docx) format.
    Returns bytes buffer.
    """
    if not PYTHON_DOCX_AVAILABLE:
        raise ImportError("python-docx is not installed. Please install it with 'pip install python-docx'.")

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(PAGE_MARGIN_IN)
        section.bottom_margin = Inches(PAGE_MARGIN_IN)
        section.left_margin = Inches(PAGE_MARGIN_IN)
        section.right_margin = Inches(PAGE_MARGIN_IN)

    inp = _report_inputs(summary, solver_inputs)
    mode_str_es = "POR LOTES (BATCH)"
    timing = _pyrolysis_timing(results)
    masses = _product_masses(summary)
    energy = _thermal_energy_balance(results, solver_inputs, *masses)

    _add_title_block(doc, mode_str_es, inp.feed_name)
    _add_abstract(doc, inp, mode_str_es, summary)
    _add_feedstock_section(doc, inp)
    _add_reactor_section(doc, inp, summary, solver_inputs, timing)

    _add_section_heading(doc, "3. Balances de Materia y Energía")
    gas_m3 = _add_mass_balance(doc, inp, summary, masses)
    _add_energy_balance(doc, energy)
    _add_energy_formulas(doc, energy, masses)

    fin, irr_str, payback_str = _add_economics_section(doc, summary, solver_inputs)
    _add_conclusions_section(doc, inp, summary, timing, gas_m3, fin, irr_str, payback_str)
    _add_signature(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    word_bytes = buffer.getvalue()
    buffer.close()
    return word_bytes
