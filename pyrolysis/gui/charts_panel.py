import streamlit as st
import numpy as np
import plotly.graph_objects as go
from pyrolysis import TRANSLATIONS, get_fuel_translation

def get_lang():
    lang_opt = st.session_state.get('lang_option', 'Español')
    return 'en' if lang_opt == 'English' else 'es'

def t(key):
    lang = get_lang()
    return TRANSLATIONS[lang].get(key, key)

def draw_front_view(filling_degree_pct, rpm):
    """Draws the circular cross-section front view showing the bed filling degree and dynamic tilt."""
    lang = get_lang()
    title_front = "Sección Transversal" if lang == 'es' else "Transverse Cross-Section"
    title_filling = "Grado de Llenado" if lang == 'es' else "Filling Degree"
    
    eta = filling_degree_pct / 100.0
    eta = np.clip(eta, 0.001, 0.999)
    
    # Solve for segment half-angle theta such that segment area = eta * pi
    target = eta * np.pi
    low, high = 0.0, np.pi
    for _ in range(12):
        mid = (low + high) / 2.0
        val = mid - np.sin(mid) * np.cos(mid)
        if val < target:
            low = mid
        else:
            high = mid
    theta = (low + high) / 2.0
    
    # Generate bed boundary circular arc (centered at bottom, -pi/2)
    t_arc = np.linspace(-np.pi/2 - theta, -np.pi/2 + theta, 100)
    x_bed = np.cos(t_arc)
    y_bed = np.sin(t_arc)
    
    # Dynamic tilt based on rotation
    tilt_deg = 25.0 if rpm > 0 else 0.0
    tilt_rad = np.radians(tilt_deg)
    
    # Rotate bed clockwise to simulate dynamic angle of repose during counter-clockwise drum rotation
    c, s = np.cos(-tilt_rad), np.sin(-tilt_rad)
    x_bed_rot = x_bed * c - y_bed * s
    y_bed_rot = x_bed * s + y_bed * c
    
    fig = go.Figure()
    
    # Draw solid bed segment
    fig.add_trace(go.Scatter(
        x=x_bed_rot,
        y=y_bed_rot,
        fill='toself',
        fillcolor='rgba(139, 90, 43, 0.85)', # Sludge brown
        line=dict(color='rgb(95, 50, 15)', width=2),
        name="Bed / Cama",
        hoverinfo='skip'
    ))
    
    # Draw outer cylinder wall (circle)
    t_circle = np.linspace(0, 2*np.pi, 200)
    fig.add_trace(go.Scatter(
        x=np.cos(t_circle),
        y=np.sin(t_circle),
        line=dict(color='#8d99ae', width=5), # Metallic grey
        name="Reactor Wall / Pared",
        hoverinfo='skip'
    ))
    
    # Draw rotation direction arrow
    if rpm > 0:
        t_arrow = np.linspace(np.radians(25), np.radians(65), 50)
        fig.add_trace(go.Scatter(
            x=1.15 * np.cos(t_arrow),
            y=1.15 * np.sin(t_arrow),
            line=dict(color='crimson', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=[1.15 * np.cos(np.radians(65))],
            y=[1.15 * np.sin(np.radians(65))],
            marker=dict(symbol='triangle-up', size=10, color='crimson', angle=25),
            showlegend=False,
            hoverinfo='skip'
        ))
        
    fig.update_layout(
        title=dict(
            text=f"<b>{title_front}</b><br>{title_filling}: {filling_degree_pct:.1f}%",
            x=0.5,
            xanchor='center',
            font=dict(size=14)
        ),
        xaxis=dict(visible=False, range=[-1.3, 1.3]),
        yaxis=dict(visible=False, range=[-1.3, 1.3], scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=10, t=60, b=10),
        height=280,
        showlegend=False
    )
    return fig

def draw_side_view(length, diameter, slope_pct, filling_degree_pct, mode_option):
    """Draws a 2D rounded cylinder side view showing reactor tilt and bed filling depth."""
    lang = get_lang()
    title_side = "Perfil Longitudinal" if lang == 'es' else "Longitudinal Profile"
    
    L = length
    D = diameter
    eta = filling_degree_pct / 100.0
    H_bed = D * eta
    y_bed = -D/2 + H_bed
    
    # Dynamic curvature cap radius for the cylinder edges
    r_cap = max(0.15 * D, 0.03 * L)
    
    # Inclination angle
    slope = (slope_pct / 100.0) if mode_option == "Continuous Operation" else 0.0
    alpha = np.arctan(slope)
    
    # Helper to rotate points by -alpha
    def rotate(x, y):
        c, s = np.cos(-alpha), np.sin(-alpha)
        return x * c - y * s, x * s + y * c

    # Cylinder outline coordinates (curved caps at ends)
    theta_left = np.linspace(np.pi/2, 3*np.pi/2, 40)
    left_cap_x = r_cap * np.cos(theta_left)
    left_cap_y = (D/2) * np.sin(theta_left)
    
    theta_right = np.linspace(-np.pi/2, np.pi/2, 40)
    right_cap_x = L + r_cap * np.cos(theta_right)
    right_cap_y = (D/2) * np.sin(theta_right)
    
    shell_x = np.concatenate([left_cap_x, right_cap_x])
    shell_y = np.concatenate([left_cap_y, right_cap_y])
    shell_x_rot, shell_y_rot = rotate(shell_x, shell_y)
    
    # Bed outline coordinates conforming to curved ends
    y_bed_left = np.linspace(y_bed, -D/2, 20)
    x_bed_left = - r_cap * np.sqrt(np.clip(1.0 - (y_bed_left / (D/2))**2, 0.0, 1.0))
    
    y_bed_right = np.linspace(-D/2, y_bed, 20)
    x_bed_right = L + r_cap * np.sqrt(np.clip(1.0 - (y_bed_right / (D/2))**2, 0.0, 1.0))
    
    bed_x = np.concatenate([x_bed_left, x_bed_right])
    bed_y = np.concatenate([y_bed_left, y_bed_right])
    bed_x_rot, bed_y_rot = rotate(bed_x, bed_y)
    
    fig = go.Figure()
    
    # Draw bed of solids inside
    fig.add_trace(go.Scatter(
        x=bed_x_rot,
        y=bed_y_rot,
        fill='toself',
        fillcolor='rgba(139, 90, 43, 0.85)', # Sludge brown
        line=dict(color='rgb(95, 50, 15)', width=1.5),
        name="Bed / Cama",
        hoverinfo='skip'
    ))
    
    # Draw transparent metallic reactor shell on top for see-through depth effect
    fig.add_trace(go.Scatter(
        x=shell_x_rot,
        y=shell_y_rot,
        fill='toself',
        fillcolor='rgba(215, 220, 225, 0.2)', # Shiny metal see-through
        line=dict(color='#8d99ae', width=4), # Outer shell border
        name="Reactor Shell / Cuerpo",
        hoverinfo='skip'
    ))
    
    # Compute shell bounding box to adjust layout zoom dynamically
    x_min, x_max = np.min(shell_x_rot), np.max(shell_x_rot)
    y_min, y_max = np.min(shell_y_rot), np.max(shell_y_rot)

    # Draw feed inlet indicator (green arrow) entering from the left cap center
    inlet_x, inlet_y = rotate(-r_cap - L * 0.05, 0)
    inlet_x_tip, inlet_y_tip = rotate(-r_cap, 0)
    fig.add_annotation(
        x=inlet_x_tip,
        y=inlet_y_tip,
        ax=inlet_x,
        ay=inlet_y,
        xref="x", yref="y",
        axref="x", ayref="y",
        text="",
        showarrow=True,
        arrowhead=3,
        arrowsize=1.2,
        arrowwidth=3,
        arrowcolor="seagreen"
    )
    
    # Draw discharge outlet indicator (red arrow) exiting from the right cap bed height
    x_edge = L + r_cap * np.sqrt(np.clip(1.0 - (y_bed / (D/2))**2, 0.0, 1.0))
    outlet_x, outlet_y = rotate(x_edge, y_bed)
    outlet_x_tip, outlet_y_tip = rotate(x_edge + L * 0.05, y_bed)
    fig.add_annotation(
        x=outlet_x_tip,
        y=outlet_y_tip,
        ax=outlet_x,
        ay=outlet_y,
        xref="x", yref="y",
        axref="x", ayref="y",
        text="",
        showarrow=True,
        arrowhead=3,
        arrowsize=1.2,
        arrowwidth=3,
        arrowcolor="crimson"
    )
    
    # Set tighter, zoomed ranges with dynamic padding
    x_plot_min = inlet_x - L * 0.01
    x_plot_max = outlet_x_tip + L * 0.01
    y_plot_min = y_min - D * 0.05
    y_plot_max = y_max + D * 0.05

    fig.update_layout(
        title=dict(
            text=f"<b>{title_side}</b> ({L:.1f}m x {D:.2f}m)",
            x=0.5,
            xanchor='center',
            font=dict(size=14)
        ),
        xaxis=dict(visible=False, range=[x_plot_min, x_plot_max]),
        yaxis=dict(visible=False, range=[y_plot_min, y_plot_max]),
        margin=dict(l=10, r=10, t=60, b=10),
        height=280,
        showlegend=False
    )
    return fig

def render_reactor_geometry_section(mode_option, summary, solver_inputs):
    """Renders longitudinal and transverse cylinder diagrams showing filling degree."""
    lang = get_lang()
    title_sec = "Visualización Física del Reactor / Visualización del Nivel de Llenado" if lang == 'es' else "Visualización Física del Reactor / Physical Reactor Visualization"
    st.markdown(f"#### {title_sec}")
    
    col1, col2 = st.columns([2, 1])
    
    length = solver_inputs['length']
    diameter = solver_inputs['diameter']
    rpm = solver_inputs['rpm']
    slope_pct = solver_inputs['slope'] * 100.0 if mode_option == "Continuous Operation" else 0.0
    filling_degree_pct = summary['filling_degree_pct']
    
    with col1:
        fig_side = draw_side_view(length, diameter, slope_pct, filling_degree_pct, mode_option)
        st.plotly_chart(fig_side, width='stretch')
        
    with col2:
        fig_front = draw_front_view(filling_degree_pct, rpm)
        st.plotly_chart(fig_front, width='stretch')

def render_charts_panel(mode_option, results):
    """Renders Plotly charts for temperature, solids mass, and vapor accumulation profiles."""
    lang = get_lang()
    fuel_type = st.session_state.get('fuel_type', "Waste Oil / Aceite Residual")
    
    fuel_label = get_fuel_translation(lang, 'waste_oil_consumed_metric', fuel_type)
    fuel_chart_title = get_fuel_translation(lang, 'chart_oil_vs_syngas_title', fuel_type)
    fuel_yaxis_title = get_fuel_translation(lang, 'chart_y_oil_consumed', fuel_type)
    fuel_power_label = get_fuel_translation(lang, 'trace_p_oil', fuel_type)

    col_chart_l, col_chart_r = st.columns(2)
    
    if mode_option == "Continuous Operation":
        x_data = results['z']
        x_label = t("chart_x_len")
        title_temp = t("chart_temp_title")
        title_mass = t("chart_solids_title")
        title_vap = t("chart_vapors_title")
        mass_y_label = t("chart_y_mass")
        
        with col_chart_l:
            fig_temp = go.Figure()
            fig_temp.add_trace(go.Scatter(x=x_data, y=results['T_wall'], name=t("trace_wall_temp"), line=dict(color='crimson', width=2, dash='dash')))
            fig_temp.add_trace(go.Scatter(x=x_data, y=results['T_solid'], name=t("trace_solid_temp"), line=dict(color='royalblue', width=3)))
            fig_temp.add_trace(go.Scatter(x=x_data, y=results['T_gas'], name=t("trace_gas_temp"), line=dict(color='seagreen', width=2, dash='dot')))
            fig_temp.add_trace(go.Scatter(x=x_data, y=[100]*len(x_data), name=t("trace_boiling_pt"), line=dict(color='grey', width=1, dash='dot')))
            fig_temp.update_layout(title=title_temp, xaxis_title=x_label, yaxis_title=t("chart_y_temp"), hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_temp, width='stretch')

        with col_chart_r:
            fig_solids = go.Figure()
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['moisture'], name=t("trace_moisture"), line=dict(color='#3a86c8', width=2)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['volatile'], name=t("trace_volatiles"), line=dict(color='#a233c6', width=2.5)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['char'], name=t("trace_char"), line=dict(color='#2b2d42', width=2)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['ash'], name=t("trace_ash"), line=dict(color='#8d99ae', width=1.5)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['humidity'], name=t("trace_humidity"), line=dict(color='#ff5a5f', width=2, dash='dot'), yaxis="y2"))
            
            fig_solids.update_layout(
                title=title_mass,
                xaxis_title=x_label,
                yaxis_title=mass_y_label,
                yaxis2=dict(
                    title=t("trace_humidity"),
                    overlaying="y",
                    side="right",
                    range=[0, 100],
                    showgrid=False
                ),
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_solids, width='stretch')
            
        fig_vapors = go.Figure()
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['oil'], name=t("trace_bio_oil"), line=dict(color='#ff9f1c', width=3.0)))
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['gas'], name=t("trace_syngas"), line=dict(color='#2ec4b6', width=2.0, dash='dash')))
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['steam'], name=t("trace_steam"), line=dict(color='#e71d36', width=1.5, dash='dot')))
        fig_vapors.update_layout(title=title_vap, xaxis_title=x_label, yaxis_title=t("chart_y_vapors"), hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_vapors, width='stretch')
        
    else:  # Batch Mode
        x_data = results['time']
        x_label = t("chart_x_time")
        title_temp = t("chart_temp_batch_title")
        title_mass = t("chart_solids_batch_title")
        title_vap = t("chart_vapors_batch_title")
        mass_y_label = t("chart_y_mass_batch")
        
        with col_chart_l:
            fig_temp = go.Figure()
            fig_temp.add_trace(go.Scatter(x=x_data, y=results['T_wall'], name=t("trace_wall_temp_prog"), line=dict(color='crimson', width=2, dash='dash')))
            fig_temp.add_trace(go.Scatter(x=x_data, y=results['T_solid'], name=t("trace_solid_temp"), line=dict(color='royalblue', width=3)))
            fig_temp.add_trace(go.Scatter(x=x_data, y=[100]*len(x_data), name=t("trace_boiling_pt"), line=dict(color='grey', width=1, dash='dot')))
            fig_temp.update_layout(title=title_temp, xaxis_title=x_label, yaxis_title=t("chart_y_temp"), hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_temp, width='stretch')

        with col_chart_r:
            fig_solids = go.Figure()
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['moisture'], name=t("trace_moisture"), line=dict(color='#3a86c8', width=2)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['volatile'], name=t("trace_volatiles"), line=dict(color='#a233c6', width=2.5)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['char'], name=t("trace_char"), line=dict(color='#2b2d42', width=2)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['ash'], name=t("trace_ash"), line=dict(color='#8d99ae', width=1.5)))
            fig_solids.add_trace(go.Scatter(x=x_data, y=results['humidity'], name=t("trace_humidity"), line=dict(color='#ff5a5f', width=2, dash='dot'), yaxis="y2"))
            
            fig_solids.update_layout(
                title=title_mass,
                xaxis_title=x_label,
                yaxis_title=mass_y_label,
                yaxis2=dict(
                    title=t("trace_humidity"),
                    overlaying="y",
                    side="right",
                    range=[0, 100],
                    showgrid=False
                ),
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_solids, width='stretch')
            
        fig_vapors = go.Figure()
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['oil'], name=t("trace_bio_oil_batch"), line=dict(color='#ff9f1c', width=3.0)))
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['gas'], name=t("trace_syngas_batch"), line=dict(color='#2ec4b6', width=2.0, dash='dash')))
        fig_vapors.add_trace(go.Scatter(x=x_data, y=results['steam'], name=t("trace_steam_batch"), line=dict(color='#e71d36', width=1.5, dash='dot')))
        fig_vapors.update_layout(title=title_vap, xaxis_title=x_label, yaxis_title=t("chart_y_vapors_batch"), hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_vapors, width='stretch')

        # Gráfica de Consumo de Aceite Residual vs Syngas Producido
        fig_fuel_vs_gas = go.Figure()
        gas_m3_arr = np.array(results['gas']) / 1.15
        
        fig_fuel_vs_gas.add_trace(go.Scatter(
            x=x_data,
            y=gas_m3_arr,
            name=t("trace_syngas_batch") + " (m³)",
            line=dict(color='#2ec4b6', width=3.0)
        ))
        fig_fuel_vs_gas.add_trace(go.Scatter(
            x=x_data,
            y=results.get('waste_oil', np.zeros_like(x_data)),
            name=fuel_label + " (gal)",
            line=dict(color='#e71d36', width=2.5, dash='dash'),
            yaxis="y2"
        ))
        
        fig_fuel_vs_gas.update_layout(
            title=fuel_chart_title,
            xaxis_title=x_label,
            yaxis_title=t("syngas_vol_metric") + " (m³)",
            yaxis2=dict(
                title=fuel_yaxis_title,
                overlaying="y",
                side="right",
                showgrid=False
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_fuel_vs_gas, width='stretch')

        # Gráfica de Potencia de Quemadores vs Temperatura de Cama Sólida
        fig_burner_power = go.Figure()
        
        fig_burner_power.add_trace(go.Scatter(
            x=x_data,
            y=results.get('p_oil', np.zeros_like(x_data)),
            name=fuel_power_label,
            line=dict(color='#e71d36', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(231, 29, 54, 0.15)'
        ))
        fig_burner_power.add_trace(go.Scatter(
            x=x_data,
            y=results.get('p_syngas', np.zeros_like(x_data)),
            name=t("trace_p_syngas"),
            line=dict(color='#2ec4b6', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(46, 196, 182, 0.15)'
        ))
        fig_burner_power.add_trace(go.Scatter(
            x=x_data,
            y=results['T_solid'],
            name=t("trace_solid_temp") + " (°C)",
            line=dict(color='royalblue', width=2.5, dash='dot'),
            yaxis="y2"
        ))
        
        fig_burner_power.update_layout(
            title=t("chart_burner_power_title"),
            xaxis_title=x_label,
            yaxis_title=t("chart_y_burner_power"),
            yaxis2=dict(
                title=t("chart_y_temp") + " (°C)",
                overlaying="y",
                side="right",
                showgrid=False
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_burner_power, width='stretch')


