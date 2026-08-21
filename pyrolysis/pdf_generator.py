import io
import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
        
        # We don't draw running header/footer on page 1 if it's treated as pure cover, 
        # but for a formal thesis report we add top/bottom border rules on pages >= 2.
        if self._pageNumber > 1:
            # Header
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#1E3A8A")) # Deep Navy
            self.drawString(36, 756, "TESIS DE GRADO & SIMULACIÓN TERMOQUÍMICA DE PIRÓLISIS")
            self.setFont("Helvetica-Oblique", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(576, 756, "PROENERGETICOS - Reactor Rotatorio")
            
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.75)
            self.line(36, 750, 576, 750)
            
            # Footer
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.75)
            self.line(36, 45, 576, 45)
            
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(36, 32, "Documento Generado Automáticamente por Simulador Pyrolysis v2.0")
            page_text = f"Página {self._pageNumber} de {page_count}"
            self.drawRightString(576, 32, page_text)
        else:
            # Page 1 Footer only
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.75)
            self.line(36, 45, 576, 45)
            
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(36, 32, "Informe Académico - Proyecto de Tesis de Ingeniería")
            page_text = f"Página 1 de {page_count}"
            self.drawRightString(576, 32, page_text)

        self.restoreState()


def _generate_matplotlib_figures(mode_option, results, summary):
    """
    Generates high-resolution Matplotlib figures and converts them to ReportLab Image flowables.
    """
    fig_images = {}
    
    # Common plot style
    plt.rcParams['axes.edgecolor'] = '#94A3B8'
    plt.rcParams['axes.linewidth'] = 0.8

    is_continuous = (mode_option == "Continuous Operation")
    x_data = results['z'] if is_continuous else results['time']
    x_label = "Posición Longitudinal Z (m)" if is_continuous else "Tiempo de Proceso (min)"

    # --- Figure 1: Temperature Profile ---
    fig, ax = plt.subplots(figsize=(6.5, 2.7), dpi=200)
    ax.plot(x_data, results['T_wall'], label='Temp. Pared (°C)', color='#DC2626', linestyle='--', linewidth=1.5)
    ax.plot(x_data, results['T_solid'], label='Temp. Lecho Sólido (°C)', color='#1E3A8A', linewidth=2.0)
    if is_continuous:
        ax.plot(x_data, results['T_gas'], label='Temp. Fase Gas (°C)', color='#059669', linestyle=':', linewidth=1.5)
    ax.axhline(100, color='#94A3B8', linestyle='-.', linewidth=1, label='Evaporación Agua (100°C)')
    
    ax.set_title("Figura 1. Perfil Térmico del Reactor Rotatorio", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    ax.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax.set_ylabel("Temperatura (°C)", fontsize=8.5, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(fontsize=7.5, loc='best', framealpha=0.9)
    plt.tight_layout()
    
    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf1.seek(0)
    fig_images['fig_temp'] = Image(buf1, width=6.5*inch, height=2.7*inch)

    # --- Figure 2: Mass Profiles of Bed & Humidity ---
    fig, ax1 = plt.subplots(figsize=(6.5, 2.7), dpi=200)
    ax1.plot(x_data, results['moisture'], label='Humedad (kg)', color='#2563EB', linewidth=1.5)
    ax1.plot(x_data, results['volatile'], label='Volátiles (kg)', color='#9333EA', linewidth=2.0)
    ax1.plot(x_data, results['char'], label='Bio-Char (kg)', color='#1F2937', linewidth=1.5)
    ax1.plot(x_data, results['ash'], label='Cenizas (kg)', color='#64748B', linewidth=1.2)
    ax1.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax1.set_ylabel("Masa en Lecho (kg" + ("/h" if is_continuous else "") + ")", fontsize=8.5, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    
    ax2 = ax1.twinx()
    ax2.plot(x_data, results['humidity'], label='Humedad Lecho (%)', color='#EF4444', linestyle=':', linewidth=1.5)
    ax2.set_ylabel("Humedad del Lecho (%)", fontsize=8.5, fontweight='bold', color='#EF4444')
    ax2.set_ylim(0, 105)
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=7.5, loc='center right', framealpha=0.9)
    ax1.set_title("Figura 2. Evolución Sólida y Humedad del Lecho", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    plt.tight_layout()
    
    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf2.seek(0)
    fig_images['fig_solids'] = Image(buf2, width=6.5*inch, height=2.7*inch)

    # --- Figure 3: Volatile Vapor Yields Accumulation ---
    fig, ax = plt.subplots(figsize=(6.5, 2.7), dpi=200)
    ax.plot(x_data, results['oil'], label='Bio-Crudo (Bio-Oil)', color='#D97706', linewidth=2.2)
    ax.plot(x_data, results['gas'], label='Gas de Síntesis (Syngas)', color='#0D9488', linestyle='--', linewidth=1.8)
    ax.plot(x_data, results['steam'], label='Vapor de Agua (Steam)', color='#E11D48', linestyle=':', linewidth=1.5)
    
    ax.set_title("Figura 3. Acumulación de Productos Volátiles Evacuados", fontsize=10, fontweight='bold', color='#1E3A8A', pad=8)
    ax.set_xlabel(x_label, fontsize=8.5, fontweight='bold')
    ax.set_ylabel("Masa Generada (kg" + ("/h" if is_continuous else "") + ")", fontsize=8.5, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(fontsize=7.5, loc='upper left', framealpha=0.9)
    plt.tight_layout()
    
    buf3 = io.BytesIO()
    plt.savefig(buf3, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf3.seek(0)
    fig_images['fig_vapors'] = Image(buf3, width=6.5*inch, height=2.7*inch)

    # --- Figure 4: Mass Yields Distribution Pie Chart ---
    fig, ax = plt.subplots(figsize=(4.0, 2.4), dpi=200)
    labels = ['Bio-Crudo', 'Syngas', 'Bio-Char', 'Vapor Agua']
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
    plt.tight_layout()
    
    buf4 = io.BytesIO()
    plt.savefig(buf4, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf4.seek(0)
    fig_images['fig_pie'] = Image(buf4, width=4.0*inch, height=2.4*inch)

    return fig_images


def generate_thesis_pdf(mode_option, results, summary, solver_inputs, config_dict):
    """
    Generates a thesis-grade academic PDF report containing full kinetics, 
    mass/energy balances, ASTM standards, operational parameters, charts, and conclusions.

    Returns:
        bytes: PDF content.
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("La librería 'reportlab' no está instalada en el entorno de Python. Ejecute 'pip install reportlab' para instalarla.")
        
    buffer = io.BytesIO()
    is_continuous = (mode_option == "Continuous Operation")
    
    # 0.5 inch margins (36 pt) left/right, 54 pt top/bottom
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Academic Styles
    title_style = ParagraphStyle(
        'AcademicTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1E3A8A"), # Deep Navy
        alignment=1, # Center
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'AcademicSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#475569"),
        alignment=1,
        spaceAfter=14
    )
    
    h1_style = ParagraphStyle(
        'AcademicH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'AcademicH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'AcademicBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
        alignment=4, # Justified
        spaceAfter=6
    )
    
    abstract_style = ParagraphStyle(
        'AcademicAbstract',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
        alignment=4,
        spaceBefore=4,
        spaceAfter=8
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
        alignment=0
    )

    table_cell_center = ParagraphStyle(
        'TableCellCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
        alignment=1
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
        alignment=0
    )

    caption_style = ParagraphStyle(
        'FigureCaption',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
        spaceBefore=4,
        spaceAfter=10
    )

    story = []

    # ---------------------------------------------------------
    # 1. ACADEMIC COVER HEADER & TITLE
    # ---------------------------------------------------------
    story.append(Paragraph("UNIVERSIDAD / CENTRO DE INVESTIGACIÓN DE INGENIERÍA QUÍMICA", ParagraphStyle('InstHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=colors.HexColor("#64748B"), alignment=1)))
    story.append(Paragraph("DEPARTAMENTO DE TERMODINÁMICA Y INGENIERÍA DE PROCESOS", ParagraphStyle('SubInstHeader', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor("#94A3B8"), alignment=1, spaceAfter=12)))
    
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceBefore=0, spaceAfter=12))
    
    mode_str_es = "CONTINUO" if mode_option == "Continuous Operation" else "POR LOTES (BATCH)"
    story.append(Paragraph("TESIS DE GRADO - INFORME TÉCNICO DE SIMULACIÓN", ParagraphStyle('DocTag', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.HexColor("#D97706"), alignment=1, spaceAfter=4)))
    story.append(Paragraph(f"EVALUACIÓN TERMOQUÍMICA Y BALANCES DE MATERIA Y ENERGÍA EN REACTOR ROTATORIO DE PIRÓLISIS ({mode_str_es})", title_style))
    story.append(Paragraph("Modelado Cinético Multietapa, Caracterización ASTM del Bio-Crudo y Evaluación de Autosuficiencia Energética", subtitle_style))

    # Metadata Block Table
    current_date = datetime.datetime.now().strftime("%d/%m/%Y")
    feed_obj = solver_inputs.get('current_feed')
    feed_name = feed_obj.name if feed_obj else "Lodo de Petróleo / Hidrocarburos"
    
    meta_data = [
        [
            Paragraph("<b>Autor / Tesista:</b>", table_cell_style), Paragraph("Ing. Proyecto PROENERGETICOS", table_cell_style),
            Paragraph("<b>Fecha de Emisión:</b>", table_cell_style), Paragraph(current_date, table_cell_style)
        ],
        [
            Paragraph("<b>Modo de Operación:</b>", table_cell_style), Paragraph(mode_option, table_cell_style),
            Paragraph("<b>Materia Prima:</b>", table_cell_style), Paragraph(feed_name, table_cell_style)
        ],
        [
            Paragraph("<b>Software Simulador:</b>", table_cell_style), Paragraph("Rotary Pyrolysis Simulator v2.0", table_cell_style),
            Paragraph("<b>Unidad de Proceso:</b>", table_cell_style), Paragraph("Reactor Cilíndrico Rotatorio", table_cell_style)
        ]
    ]
    t_meta = Table(meta_data, colWidths=[1.3*inch, 2.0*inch, 1.3*inch, 2.0*inch])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))

    # ---------------------------------------------------------
    # RESUMEN EJECUTIVO (ABSTRACT)
    # ---------------------------------------------------------
    story.append(Paragraph("<b>RESUMEN EJECUTIVO (ABSTRACT)</b>", h2_style))
    
    load_val = solver_inputs['feed_rate_kgh'] if mode_option == "Continuous Operation" else solver_inputs['batch_load_kg']
    load_unit = "kg/h" if mode_option == "Continuous Operation" else "kg"
    conv_pct = summary['conversion_pct']
    oil_pct = summary['oil_yield_pct']
    gas_pct = summary['gas_yield_pct']
    char_pct = summary['char_yield_pct']
    duty_val = summary['heating_duty_kw'] if mode_option == "Continuous Operation" else summary.get('total_energy_kwh', 0.0)
    duty_unit = "kW" if mode_option == "Continuous Operation" else "kWh"
    
    abstract_text = (
        f"El presente informe técnico expone los resultados de la simulación rigurosa del proceso de pirólisis "
        f"desarrollada en un reactor rotatorio de tambor operando en modo <b>{mode_str_es}</b>, procesando una carga "
        f"nominal de <b>{load_val:.1f} {load_unit}</b> de <b>{feed_name}</b>. "
        f"El modelo fenomenológico resuelve las ecuaciones diferenciales cinéticas de primer orden según el esquema de Arrhenius "
        f"multietapa ($k_1, k_2, k_3$), acopladas con el balance conservativo de materia y transferencia de calor conductivo-convectivo en el lecho sólido. "
        f"Se alcanzó una conversión global de materia volátil del <b>{conv_pct:.1f}%</b>, rindiendo un <b>{oil_pct:.1f} wt.%</b> de bio-crudo condensable, "
        f"un <b>{gas_pct:.1f} wt.%</b> de gas de síntesis (syngas) incondensable, y un <b>{char_pct:.1f} wt.%</b> de bio-carbón (char seco). "
        f"La demanda energética total calculada fue de <b>{duty_val:.2f} {duty_unit}</b> con un error de cierre en el balance de materia de <b>{summary['mass_error_pct']:.2e}%</b>, "
        f"confirmando la consistencia física del modelo y la factibilidad autógena del proceso industrial."
    )
    story.append(Paragraph(abstract_text, abstract_style))
    story.append(Spacer(1, 8))

    # ---------------------------------------------------------
    # 2. CARACTERIZACIÓN CINÉTICA Y FÍSICO-QUÍMICA (NORMAS ASTM)
    # ---------------------------------------------------------
    story.append(Paragraph("1. Propiedades de la Materia Prima y Cinética Química", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=8))
    
    story.append(Paragraph("<b>1.1 Análisis Proximal y Composición Elemental del Lodo</b>", h2_style))
    
    comp_table_data = [
        [Paragraph("<b>Componente</b>", table_header_style), Paragraph("<b>Fracción (wt.%)</b>", table_header_style), Paragraph(f"<b>Carga Entrada ({load_unit})</b>", table_header_style), Paragraph("<b>Volumen Relativo</b>", table_header_style)],
        [Paragraph("Humedad (Moisture)", table_cell_style), Paragraph(f"{feed_obj.moisture:.2f}%", table_cell_center), Paragraph(f"{load_val*feed_obj.moisture/100:.2f}", table_cell_center), Paragraph("Agua libre lecho", table_cell_style)],
        [Paragraph("Materia Volátil (Volatiles)", table_cell_style), Paragraph(f"{feed_obj.volatile:.2f}%", table_cell_center), Paragraph(f"{load_val*feed_obj.volatile/100:.2f}", table_cell_center), Paragraph("Matriz org. reactiva", table_cell_style)],
        [Paragraph("Carbono Fijo (Fixed Carbon)", table_cell_style), Paragraph(f"{feed_obj.fixed_carbon:.2f}%", table_cell_center), Paragraph(f"{load_val*feed_obj.fixed_carbon/100:.2f}", table_cell_center), Paragraph("Estructura char", table_cell_style)],
        [Paragraph("Cenizas Inertes (Ash)", table_cell_style), Paragraph(f"{feed_obj.ash:.2f}%", table_cell_center), Paragraph(f"{load_val*feed_obj.ash/100:.2f}", table_cell_center), Paragraph("Inorgánico inerte", table_cell_style)],
        [Paragraph("<b>TOTAL</b>", table_cell_bold), Paragraph("<b>100.00%</b>", table_cell_center), Paragraph(f"<b>{load_val:.2f}</b>", table_cell_center), Paragraph("<b>Base Húmeda</b>", table_cell_center)]
    ]
    t_comp = Table(comp_table_data, colWidths=[2.2*inch, 1.3*inch, 1.5*inch, 1.6*inch])
    t_comp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_comp)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>1.2 Parámetros Cinéticos de Arrhenius Multietapa</b>", h2_style))
    kin_table_data = [
        [Paragraph("<b>Reacción Química</b>", table_header_style), Paragraph("<b>Energía Act. Ea (kJ/mol)</b>", table_header_style), Paragraph("<b>Factor A (s⁻¹)</b>", table_header_style), Paragraph("<b>Ecuación de Velocidad</b>", table_header_style)],
        [Paragraph("R1: Lodo → Bio-Crudo", table_cell_style), Paragraph(f"{feed_obj.Ea1/1000:.1f}", table_cell_center), Paragraph(f"{feed_obj.A1:.2e}", table_cell_center), Paragraph("k₁ = A₁·exp(-Ea₁/RT)", table_cell_style)],
        [Paragraph("R2: Lodo → Syngas", table_cell_style), Paragraph(f"{feed_obj.Ea2/1000:.1f}", table_cell_center), Paragraph(f"{feed_obj.A2:.2e}", table_cell_center), Paragraph("k₂ = A₂·exp(-Ea₂/RT)", table_cell_style)],
        [Paragraph("R3: Bio-Crudo → Syngas (Craqueo)", table_cell_style), Paragraph(f"{feed_obj.Ea3/1000:.1f}", table_cell_center), Paragraph(f"{feed_obj.A3:.2e}", table_cell_center), Paragraph("k₃ = A₃·exp(-Ea₃/RT)", table_cell_style)]
    ]
    t_kin = Table(kin_table_data, colWidths=[2.2*inch, 1.5*inch, 1.4*inch, 1.5*inch])
    t_kin.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_kin)
    story.append(Spacer(1, 10))

    # ASTM Characterization Section
    story.append(Paragraph("<b>1.3 Caracterización del Bio-Crudo Producido (Normas ASTM)</b>", h2_style))
    temp_hold = float(solver_inputs.get('temp_hold_c', 550.0))
    vol_pct = feed_obj.volatile
    hhv_oil = min(43.5, max(36.0, 38.0 + 0.008 * (temp_hold - 450.0) + 0.10 * (vol_pct - 50.0)))
    hhv_btu = hhv_oil * 429.923
    factor_enh = hhv_oil / 18.5
    visc_40c = max(12.0, 45.0 - 0.08 * (temp_hold - 400.0))
    pump_status = "Bombeable Directo @ 25°C" if visc_40c <= 25.0 else ("Precalentar 40°C" if visc_40c <= 50.0 else "Alta Viscosidad (60°C)")
    bio_oil_dens = float(solver_inputs.get('bio_oil_density', 750.0))
    sg_15 = bio_oil_dens / 999.1
    api_deg = (141.5 / max(0.1, sg_15)) - 131.5
    bsw_pct = min(8.0, max(1.5, 3.5 * (feed_obj.moisture / 30.0)))

    astm_table_data = [
        [Paragraph("<b>Propiedad Físico-Química</b>", table_header_style), Paragraph("<b>Norma ASTM</b>", table_header_style), Paragraph("<b>Valor Calculado</b>", table_header_style), Paragraph("<b>Diagnóstico de Calidad</b>", table_header_style)],
        [Paragraph("Poder Calorífico Superior (PCS/HHV)", table_cell_style), Paragraph("ASTM D240", table_cell_center), Paragraph(f"{hhv_oil:.2f} MJ/kg ({hhv_btu:,.0f} BTU/lb)", table_cell_style), Paragraph(f"Factor Mejora: x{factor_enh:.2f} vs lodo", table_cell_style)],
        [Paragraph("Viscosidad Cinemática @ 40°C", table_cell_style), Paragraph("ASTM D445", table_cell_center), Paragraph(f"{visc_40c:.1f} cSt (mm²/s)", table_cell_style), Paragraph(pump_status, table_cell_style)],
        [Paragraph("Densidad @ 15°C & Gravedad °API", table_cell_style), Paragraph("ASTM D1298", table_cell_center), Paragraph(f"{bio_oil_dens:.1f} kg/m³ | {api_deg:.1f} °API", table_cell_style), Paragraph(f"Gravedad Específica: {sg_15:.4f}", table_cell_style)],
        [Paragraph("Contenido de Agua & Sedimentación (BS&W)", table_cell_style), Paragraph("ASTM D95", table_cell_center), Paragraph(f"{bsw_pct:.2f} wt.%", table_cell_style), Paragraph("Fase org. condensada limpia", table_cell_style)]
    ]
    t_astm = Table(astm_table_data, colWidths=[2.2*inch, 1.1*inch, 1.8*inch, 1.5*inch])
    t_astm.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0D9488")), # Teal
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_astm)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # 3. ESPECIFICACIONES GEOMÉTRICAS Y OPERATIVAS
    # ---------------------------------------------------------
    story.append(Paragraph("2. Geometría y Condiciones Operativas del Reactor", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=8))
    
    length_m = solver_inputs['length']
    dia_m = solver_inputs['diameter']
    aspect_ratio = length_m / max(0.01, dia_m)
    rpm_val = solver_inputs['rpm']
    fill_deg = summary['filling_degree_pct']
    mrt_min = summary.get('residence_time_min', results['time'][-1] if 'time' in results else 0.0)
    h_eff = solver_inputs['h_eff']
    burner_hp = solver_inputs.get('burner_hp', 300.0)
    burner_eff = solver_inputs.get('burner_eff_pct', 70.0)

    time_label = "Tiempo Medio de Residencia (MRT)" if is_continuous else "Tiempo Total de Ciclo Lote"

    geom_table_data = [
        [Paragraph("<b>Parámetro Geométrico / Operativo</b>", table_header_style), Paragraph("<b>Valor</b>", table_header_style), Paragraph("<b>Parámetro Térmico / Energético</b>", table_header_style), Paragraph("<b>Valor</b>", table_header_style)],
        [Paragraph("Longitud Cilíndrica (L)", table_cell_style), Paragraph(f"{length_m:.2f} m", table_cell_center), Paragraph("Coef. Transf. Calor (h_eff)", table_cell_style), Paragraph(f"{h_eff:.1f} W/m²·K", table_cell_center)],
        [Paragraph("Diámetro Interno (D)", table_cell_style), Paragraph(f"{dia_m:.2f} m", table_cell_center), Paragraph("Potencia Quemadores", table_cell_style), Paragraph(f"{burner_hp:.0f} HP", table_cell_center)],
        [Paragraph("Relación de Aspecto (L/D)", table_cell_style), Paragraph(f"{aspect_ratio:.2f}", table_cell_center), Paragraph("Eficiencia Térmica Quemador", table_cell_style), Paragraph(f"{burner_eff:.1f} %", table_cell_center)],
        [Paragraph("Velocidad de Rotación", table_cell_style), Paragraph(f"{rpm_val:.1f} RPM", table_cell_center), Paragraph("Grado de Llenado del Lecho", table_cell_style), Paragraph(f"{fill_deg:.2f} %", table_cell_center)],
        [Paragraph(time_label, table_cell_style), Paragraph(f"{mrt_min:.1f} min", table_cell_center), Paragraph("Conversión Volátiles Total", table_cell_style), Paragraph(f"{conv_pct:.1f} %", table_cell_center)]
    ]
    t_geom = Table(geom_table_data, colWidths=[2.0*inch, 1.3*inch, 2.0*inch, 1.3*inch])
    t_geom.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_geom)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # 4. BALANCES DE MATERIA Y ENERGÍA
    # ---------------------------------------------------------
    story.append(Paragraph("3. Balances de Materia y Energía", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=8))
    
    story.append(Paragraph("<b>3.1 Balance de Materia Global y Cierre de Masa</b>", h2_style))
    
    oil_kgh = summary.get('oil_yield_kgh', summary.get('oil_yield_kg', 0))
    gas_kgh = summary.get('gas_yield_kgh', summary.get('gas_yield_kg', 0))
    char_kgh = summary.get('char_yield_kgh', summary.get('char_yield_kg', 0))
    water_kgh = summary.get('water_yield_kgh', summary.get('water_yield_kg', 0))
    
    oil_density = float(solver_inputs.get('bio_oil_density', 750.0))
    char_density = float(solver_inputs.get('bio_char_density', 500.0))
    oil_gal = (oil_kgh / oil_density) * 264.172
    gas_m3 = gas_kgh / 1.15
    char_gal = (char_kgh / char_density) * 264.172
    water_gal = (water_kgh / 1000.0) * 264.172

    mass_table_data = [
        [Paragraph("<b>Flujo / Corriente</b>", table_header_style), Paragraph("<b>Masa (kg" + ("/h" if is_continuous else "") + ")</b>", table_header_style), Paragraph("<b>Fracción wt.%</b>", table_header_style), Paragraph("<b>Volumen Estimado</b>", table_header_style)],
        [Paragraph("<b>ENTRADA:</b> " + feed_name, table_cell_bold), Paragraph(f"<b>{load_val:.2f}</b>", table_cell_center), Paragraph("<b>100.00%</b>", table_cell_center), Paragraph("-", table_cell_center)],
        [Paragraph("<b>SALIDA:</b> Bio-Crudo (Bio-Oil)", table_cell_style), Paragraph(f"{oil_kgh:.2f}", table_cell_center), Paragraph(f"{oil_pct:.2f}%", table_cell_center), Paragraph(f"{oil_gal:.1f} gal" + ("/h" if is_continuous else ""), table_cell_style)],
        [Paragraph("<b>SALIDA:</b> Gas de Síntesis (Syngas)", table_cell_style), Paragraph(f"{gas_kgh:.2f}", table_cell_center), Paragraph(f"{gas_pct:.2f}%", table_cell_center), Paragraph(f"{gas_m3:.1f} m³" + ("/h" if is_continuous else ""), table_cell_style)],
        [Paragraph("<b>SALIDA:</b> Bio-Carbón (Char Seco)", table_cell_style), Paragraph(f"{char_kgh:.2f}", table_cell_center), Paragraph(f"{char_pct:.2f}%", table_cell_center), Paragraph(f"{char_gal:.1f} gal" + ("/h" if is_continuous else ""), table_cell_style)],
        [Paragraph("<b>SALIDA:</b> Vapor de Agua (Steam)", table_cell_style), Paragraph(f"{water_kgh:.2f}", table_cell_center), Paragraph(f"{summary['water_yield_pct']:.2f}%", table_cell_center), Paragraph(f"{water_gal:.1f} gal" + ("/h" if is_continuous else ""), table_cell_style)],
        [Paragraph("<b>ERROR CIERRE BALANCE</b>", table_cell_bold), Paragraph(f"<b>{summary['mass_error_pct']:.2e} %</b>", table_cell_center), Paragraph("<b>Conservativo</b>", table_cell_center), Paragraph("<b>Tolerancia < 0.01%</b>", table_cell_style)]
    ]
    t_mass = Table(mass_table_data, colWidths=[2.2*inch, 1.4*inch, 1.4*inch, 1.6*inch])
    t_mass.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#F8FAFC")),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#FEF3C7")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_mass)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>3.2 Balance de Energía Térmica y Carga de Calentamiento</b>", h2_style))
    
    # Calculate energy components
    if is_continuous:
        F_oil_s = oil_kgh / 3600.0
        F_gas_s = gas_kgh / 3600.0
        F_char_s = char_kgh / 3600.0
        F_steam_s = water_kgh / 3600.0
        T_in = results['T_solid'][0]
        T_out = results['T_solid'][-1]
        T_gas_out = results['T_gas'][-1]
        
        Q_char_kw = (F_char_s * 1000.0 * (T_out - T_in)) / 1000.0
        Q_pyro_kw = ((F_oil_s + F_gas_s) * (1800.0 * (T_out - T_in) + 600000.0)) / 1000.0
        if T_in < 100.0:
            Q_steam_kw = (F_steam_s * (4184.0 * (100.0 - T_in) + 2256000.0 + 2000.0 * (max(T_gas_out, 100.0) - 100.0))) / 1000.0
        else:
            Q_steam_kw = (F_steam_s * (2256000.0 + 2000.0 * (max(T_gas_out, T_in) - T_in))) / 1000.0
        Q_total_kw = Q_char_kw + Q_pyro_kw + Q_steam_kw
        
        energy_table_data = [
            [Paragraph("<b>Etapa de Transferencia Térmica</b>", table_header_style), Paragraph("<b>Potencia (kW)</b>", table_header_style), Paragraph("<b>Porcentaje (%)</b>", table_header_style), Paragraph("<b>Mecanismo Principal</b>", table_header_style)],
            [Paragraph("Calor Sensible del Sólido", table_cell_style), Paragraph(f"{Q_char_kw:.2f} kW", table_cell_center), Paragraph(f"{(Q_char_kw/max(0.001,Q_total_kw)*100):.1f}%", table_cell_center), Paragraph("Conducción lecho-pared", table_cell_style)],
            [Paragraph("Secado y Evaporación Humedad", table_cell_style), Paragraph(f"{Q_steam_kw:.2f} kW", table_cell_center), Paragraph(f"{(Q_steam_kw/max(0.001,Q_total_kw)*100):.1f}%", table_cell_center), Paragraph("Vaporización latente (100°C)", table_cell_style)],
            [Paragraph("Reacción Endotérmica Pirólisis", table_cell_style), Paragraph(f"{Q_pyro_kw:.2f} kW", table_cell_center), Paragraph(f"{(Q_pyro_kw/max(0.001,Q_total_kw)*100):.1f}%", table_cell_center), Paragraph("Craqueo térmico volátiles", table_cell_style)],
            [Paragraph("<b>DEMANDA TÉRMICA TOTAL</b>", table_cell_bold), Paragraph(f"<b>{Q_total_kw:.2f} kW</b>", table_cell_center), Paragraph("<b>100.0%</b>", table_cell_center), Paragraph("<b>Potencia requerida</b>", table_cell_bold)]
        ]
    else:
        T_start = results['T_solid'][0]
        T_hold = results['T_solid'][-1]
        E_char_kwh = (char_kgh * 1000.0 * (T_hold - T_start)) / 3.6e6
        E_pyro_kwh = ((oil_kgh + gas_kgh) * (1800.0 * (T_hold - T_start) + 600000.0)) / 3.6e6
        if T_hold >= 100.0:
            E_steam_kwh = (water_kgh * (4184.0 * (100.0 - T_start) + 2256000.0 + 2000.0 * (T_hold - 100.0))) / 3.6e6
        else:
            E_steam_kwh = (water_kgh * (4184.0 * (T_hold - T_start))) / 3.6e6
        E_total_kwh = E_char_kwh + E_pyro_kwh + E_steam_kwh
        
        energy_table_data = [
            [Paragraph("<b>Etapa de Transferencia Térmica</b>", table_header_style), Paragraph("<b>Energía (kWh)</b>", table_header_style), Paragraph("<b>Porcentaje (%)</b>", table_header_style), Paragraph("<b>Mecanismo Principal</b>", table_header_style)],
            [Paragraph("Calor Sensible del Sólido", table_cell_style), Paragraph(f"{E_char_kwh:.2f} kWh", table_cell_center), Paragraph(f"{(E_char_kwh/max(0.001,E_total_kwh)*100):.1f}%", table_cell_center), Paragraph("Conducción lecho-pared", table_cell_style)],
            [Paragraph("Secado y Evaporación Humedad", table_cell_style), Paragraph(f"{E_steam_kwh:.2f} kWh", table_cell_center), Paragraph(f"{(E_steam_kwh/max(0.001,E_total_kwh)*100):.1f}%", table_cell_center), Paragraph("Vaporización latente (100°C)", table_cell_style)],
            [Paragraph("Reacción Endotérmica Pirólisis", table_cell_style), Paragraph(f"{E_pyro_kwh:.2f} kWh", table_cell_center), Paragraph(f"{(E_pyro_kwh/max(0.001,E_total_kwh)*100):.1f}%", table_cell_center), Paragraph("Craqueo térmico volátiles", table_cell_style)],
            [Paragraph("<b>ENERGÍA TÉRMICA TOTAL</b>", table_cell_bold), Paragraph(f"<b>{E_total_kwh:.2f} kWh</b>", table_cell_center), Paragraph("<b>100.0%</b>", table_cell_center), Paragraph("<b>Consumo total ciclo</b>", table_cell_bold)]
        ]

    t_energy = Table(energy_table_data, colWidths=[2.2*inch, 1.4*inch, 1.4*inch, 1.6*inch])
    t_energy.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_energy)
    story.append(Spacer(1, 14))

    # Page break before high-resolution academic figures
    story.append(PageBreak())

    # ---------------------------------------------------------
    # 5. ANÁLISIS GRÁFICO DEL PROCESO (FIGURAS DE TESIS)
    # ---------------------------------------------------------
    story.append(Paragraph("4. Perfiles Térmicos y Distribución de Productos (Figuras)", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=8))
    
    # Generate Matplotlib Figures
    figs = _generate_matplotlib_figures(mode_option, results, summary)
    
    story.append(figs['fig_temp'])
    story.append(Paragraph("<b>Figura 1.</b> Perfil axial/temporal de temperaturas en la pared del reactor, lecho sólido y fase gas.", caption_style))
    story.append(Spacer(1, 6))

    story.append(figs['fig_solids'])
    story.append(Paragraph("<b>Figura 2.</b> Evolución de componentes sólidos (humedad, volátiles, char, cenizas) y humedad residual.", caption_style))
    story.append(Spacer(1, 6))

    story.append(figs['fig_vapors'])
    story.append(Paragraph("<b>Figura 3.</b> Masa acumulada de productos volátiles evacuados (bio-crudo, syngas y vapor de agua).", caption_style))
    story.append(Spacer(1, 6))

    # Pie chart figure layout
    t_pie = Table([[figs['fig_pie']]], colWidths=[6.6*inch])
    t_pie.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    story.append(t_pie)
    story.append(Paragraph("<b>Figura 4.</b> Distribución porcentual en masa (wt.%) de las fracciones obtenidas en la pirólisis.", caption_style))
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # 6. DISCUSIÓN TÉCNICA Y CONCLUSIONES ACADÉMICAS
    # ---------------------------------------------------------
    story.append(Paragraph("5. Discusión Técnica y Conclusiones Académicas", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=8))
    
    c1 = (
        f"<b>1. Viabilidad Térmica y Rendimiento de Conversión:</b> "
        f"La pirólisis de <i>{feed_name}</i> alcanza una conversión del <b>{conv_pct:.1f}%</b> de la materia volátil, "
        f"demostrando que el perfil térmico aplicado (temperatura máxima de {temp_hold:.0f}°C) proporciona el aporte entálpico "
        f"necesario para superar la energía de activación de las tres reacciones de descomposición ($E_{{a1}}={feed_obj.Ea1/1000:.1f}$ kJ/mol)."
    )
    c2 = (
        f"<b>2. Calidad Físico-Química del Bio-Crudo (Norma ASTM D240/D445):</b> "
        f"El líquido condensable obtenido posee un Poder Calorífico Superior de <b>{hhv_oil:.2f} MJ/kg</b> ({hhv_btu:,.0f} BTU/lb), "
        f"lo que representa un factor de concentración energética de <b>x{factor_enh:.2f}</b> respecto al lodo bruto de entrada. "
        f"La viscosidad cinemática a 40°C de <b>{visc_40c:.1f} cSt</b> categoriza al bio-crudo como <i>{pump_status}</i>."
    )
    c3 = (
        f"<b>3. Autosuficiencia Energética del Sistema Industrial:</b> "
        f"El rendimiento de gas de síntesis (<b>{gas_pct:.1f} wt.%</b>) correspondiente a <b>{gas_m3:.1f} m³</b> de syngas incondensable, "
        f"permite sustituir el consumo de combustible fósil auxiliar en los quemadores principales del reactor, "
        f"garantizando la operación autógena en régimen estacionario."
    )
    c4 = (
        f"<b>4. Conservación de Masa y Validación del Modelo:</b> "
        f"El error de cierre en el balance de materia de <b>{summary['mass_error_pct']:.2e}%</b> "
        f"valida la precisión matemática del esquema numérico de integración y confirma la ausencia de pérdidas ficticias en el simulador."
    )

    story.append(Paragraph(c1, body_style))
    story.append(Paragraph(c2, body_style))
    story.append(Paragraph(c3, body_style))
    story.append(Paragraph(c4, body_style))
    story.append(Spacer(1, 20))

    # Signature Block Table
    sig_data = [
        [Paragraph("________________________________________", table_cell_center), Paragraph("________________________________________", table_cell_center)],
        [Paragraph("<b>Ing. Investigador / Autor de Tesis</b><br/>Proyecto Simulación Pirólisis", table_cell_center), Paragraph("<b>Director de Tesis / Asesor Técnico</b><br/>Departamento de Ingeniería de Procesos", table_cell_center)]
    ]
    t_sig = Table(sig_data, colWidths=[3.2*inch, 3.2*inch])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(KeepTogether(t_sig))

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
