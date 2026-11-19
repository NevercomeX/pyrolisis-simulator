"""
Perfiles de simulación.

- "general": valores por defecto de uso público (sin cambios respecto al simulador original).
- "tesis": corrida industrial documentada de PROENERGÉTICOS S.R.L. (reactor rotatorio, una corrida),
  con los datos medidos y los parámetros calibrados en la tesina. Permite que el jurado reproduzca
  el caso sin introducir datos a mano.

Origen de cada valor del perfil "tesis":
  Medido  : carga 3,700 gal, densidad del lodo 944.7 kg/m³ (ASTM D4052), humedad 2.00 % (ASTM D95),
            cenizas 1.61 % (ASTM D482), densidad del aceite 870.8 kg/m³, rampa 1.5 °C/min,
            inicio de pirólisis 370 °C (termómetro a nivel del líquido), velocidad 1 RPM,
            geometría 6.0 m × 2.75 m.
  Calibrado con la misma corrida (no es validación):
            carbono fijo 18.68 % (residuo carbonoso − cenizas), factor de A2 = 0.723 (aceite total 62.10 %),
            h_eff = 262.2 W/m²·K (ventana de aceite de 158 min con pared a 550 °C),
            sostenimiento 96.7 min (el lote termina cuando el aceite llega a 2,431 gal = 60.56 %).
  Supuesto: temperatura de pared 550 °C (no medida; con corrida_tesis.py la calibración da
            h_eff = 390.1 W/m²·K, A2 × 0.723 y 110.8 min a 500 °C, y h_eff = 201.8 W/m²·K, A2 × 0.723
            y 80.5 min a 600 °C; paso de integración 2 s),
            Ea y A base del simulador, eficiencia del quemador 85 %.
Discrepancia conocida: al apagar, el lecho simulado está a ~428.5 °C; el termómetro midió 400 °C como máximo.
El enfriamiento posterior al apagado (62 gal adicionales) no se simula.
"""
from .feedstock import Feedstock

PROFILE_GENERAL = "general"
PROFILE_THESIS = "tesis"
# Súbalo cada vez que cambie THESIS_GUI_OVERRIDES: una configuración guardada con el perfil de tesis y otra
# versión (o sin versión) vuelve a recibir los valores del perfil al cargarse.
THESIS_PROFILE_VERSION = 4
THESIS_OIL_AT_SHUTDOWN_PCT = 60.56   # aceite medido al apagar (2,431 gal), % de la carga

PROFILE_LABELS = {
    PROFILE_GENERAL: {"es": "General (uso público)", "en": "General (public use)"},
    PROFILE_THESIS: {"es": "Caso de estudio: corrida PROENERGÉTICOS (tesis)",
                     "en": "Case study: PROENERGÉTICOS run (thesis)"},
}

THESIS_NOTE = {
    "es": ("Valores medidos y calibrados de la corrida documentada. La temperatura de pared (550 °C) no se midió; "
           "h_eff está calibrado con la ventana de aceite de 158 min. El lote termina al recuperar 2,431 gal "
           "(60.56 %); los 62 gal del enfriamiento no se simulan. Calibración con una sola corrida: no es validación."),
    "en": ("Measured and calibrated values from the documented run. Wall temperature (550 °C) was not measured; "
           "h_eff is calibrated to the 158-min oil window. The batch ends at 2,431 gal recovered (60.56 %); "
           "the 62 gal collected during cool-down are not simulated. Single-run calibration: not a validation."),
}

# Cinética: valores base del simulador; A2 ajustado por calibración.
_EA1, _A1 = 90.0, 7.5e5
_EA2, _A2 = 95.0, 2.5e5 * 0.723
_EA3, _A3 = 80.0, 1.0e5
T_ONSET_THESIS_C = 370.0
H_EFF_THESIS = 262.2      # W/m²·K, pared 550 °C (corrida_tesis.py)
HOLD_MIN_THESIS = 96.7    # min: el lote termina con 60.56 % de aceite

# Claves de la interfaz (session_state) que cambia el perfil de tesis.
THESIS_GUI_OVERRIDES = {
    "mode_option": "Batch Operation",
    "feed_option": "Custom Feedstock",
    "c_moist": 2.0,
    "c_vol": 77.71,
    "c_fc": 18.68,
    "c_ash": 1.61,
    "use_advanced_kinetics": True,
    "c_ea1": _EA1, "c_a1": _A1,
    "c_ea2": _EA2, "c_a2": _A2,
    "c_ea3": _EA3, "c_a3": _A3,
    "c_t_onset": T_ONSET_THESIS_C,
    "batch_size": 3700.0,
    "sludge_density": 944.7,
    "bio_oil_density": 870.8,
    "reactor_len": 6.0,
    "reactor_dia": 2.75,
    "rotation_speed": 1.0,
    "heat_transfer_coeff": H_EFF_THESIS,
    "starting_temp": 50.0,
    "heating_rate": 1.5,
    "holding_temp": 550.0,
    "holding_time": HOLD_MIN_THESIS,
    "auto_heating_rate": False,
    "burner_eff_pct": 85.0,
    "cooling_tank_gal": 28000.0,
    # --- Economía (tesina, Tablas 7 a 9). Montos en RD$.
    # CAPEX (Tabla 7), total 20,050,000
    "capex_equip": 12_000_000.0,
    "capex_install": 2_450_000.0,
    "capex_civil": 1_750_000.0,
    "capex_piping_elec": 1_750_000.0,
    "capex_eng": 1_050_000.0,
    "capex_permits": 350_000.0,
    "capex_cont": 700_000.0,
    # OPEX (Tabla 8)
    "opex_handling": 40.0,            # RD$/gal de lodo (manejo, secado y logística)
    "opex_fuel": 0.83795475,          # RD$/gal de combustible auxiliar (106,064.96 ÷ 126,576 gal, Tabla 8)
    "opex_aux_utilities": 500_000.0,  # RD$/año
    "price_generator_fuel": 263.0,    # RD$/gal de diésel; 50 gal/lote × 216 lotes × 263 = 2,840,400/año
    "gen_diesel_batch": 50.0,         # gal/lote
    "opex_labor": 1_000_000.0,        # RD$/año
    "opex_maint": 6.0,                # % del CAPEX/año
    "opex_insurance_tax": 3.0,        # % del CAPEX/año (seguros y licencias)
    # Ingresos: solo aceite; sin tarifa de disposición, char, gas ni créditos de carbono
    "price_oil": 121.0,               # RD$/gal
    "econ_sludge_scenario": "free",   # caso base de la tesina: lodo sin costo (tarifa 0)
    "opex_tipping": 20.0,             # Y, tarifa de disposición (RD$/gal) — supuesto declarado en la tesina
    "econ_sludge_cost": 8.04,         # X, RD$/gal de lodo seco: lodo húmedo (40 % de humedad, 0.96 kg/L) a RD$ 5/gal, 1.61 gal húmedo por gal seco
    "price_char": 0.0,
    "price_gas": 0.0,
    "price_carbon": 0.0,
    # Finanzas
    "discount_rate": 14.0,
    "project_lifetime": 10,
    "tax_rate": 25.0,
    "inflation_rate": 4.0,
    # Datos de planta en lugar de la simulación (el ciclo real no se midió)
    "econ_batches_per_year": 216,           # 216 × 3,700 gal = 799,200 gal de lodo/año
    "econ_oil_gal_per_batch": 2492.8765,    # aceite total medido (8,217.36 kg ÷ 0.8708 ÷ 3.785411784), incluye el enfriamiento
    "econ_fuel_gal_per_batch": 586.0,       # combustible auxiliar medido en planta
}


def thesis_feedstock() -> Feedstock:
    """Lodo de la corrida documentada, con el inicio de pirólisis observado (370 °C)."""
    a = _A1 + _A2
    f = Feedstock(
        name="Lodo PROENERGÉTICOS (tesis)",
        moisture=2.0, volatile=77.71, fixed_carbon=18.68, ash=1.61,
        E_a=_EA1 * 1000.0, A=a,
        yield_oil=_A1 / a, yield_gas=_A2 / a, yield_char=0.0,
        Ea1=_EA1 * 1000.0, A1=_A1,
        Ea2=_EA2 * 1000.0, A2=_A2,
        Ea3=_EA3 * 1000.0, A3=_A3,
    )
    f.T_onset_K = T_ONSET_THESIS_C + 273.15
    return f


def thesis_batch_kwargs() -> dict:
    """Argumentos de BatchReactorSimulation para reproducir la corrida de la tesis."""
    load_kg = 3700.0 * 3.785411784 * 0.9447
    return dict(
        feedstock=thesis_feedstock(), batch_load_kg=load_kg,
        length=6.0, diameter=2.75, rpm=1.0,
        T_start_C=50.0, heating_rate_cmin=1.5, T_hold_C=550.0, hold_time_min=HOLD_MIN_THESIS,
        h_eff=H_EFF_THESIS, burner_eff_pct=85.0, bulk_density=944.7,
    )
