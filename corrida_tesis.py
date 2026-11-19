"""
Corrida de la tesina calibrada con los datos medidos de la corrida documentada.

QUÉ ES MEDIDO, CALIBRADO Y SUPUESTO: ver salidas_tesis/tabla_entradas.csv.
Medido: humedad, cenizas, carga, rampa, inicio de pirólisis (370 °C), máxima del lecho (400 °C),
ventana de aceite (158 min), aceite al apagar (2,431 gal) y total (2,493 gal).
Calibrado con ESA MISMA corrida: carbono fijo, factor A2 y h_eff. No es una validación.
La temperatura de pared no se midió: se evalúan 500, 550 y 600 °C.
El enfriamiento posterior al apagado (62 gal adicionales) no se simula.

Uso:  python corrida_tesis.py   (genera figuras PNG y CSV en ./salidas_tesis)
"""
import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pyrolysis.feedstock import Feedstock, HYDROCARBON_SLUDGE as BASE
from pyrolysis.reactor.batch import BatchReactorSimulation

OUT = "salidas_tesis"
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- datos de la corrida
GAL_L = 3.78541
DENS = 0.9447                         # kg/L, ASTM D4052 (Tabla 1)
DENS_ACEITE = 0.8708                  # kg/L, aceite pirolítico (Tabla 6)
CARGA_KG = 3700 * GAL_L * DENS        # 13,231.49 kg
HUMEDAD, CENIZA = 2.00, 1.61          # % masa, Tabla 1
OBJ_ACEITE_TOTAL, OBJ_CHAR = 62.10, 20.29          # % masa, balance final (incluye 62 gal del enfriamiento)
OBJ_ACEITE_APAGADO = 100 * 2431 * GAL_L * DENS_ACEITE / CARGA_KG   # 60.56 % al apagar
VENTANA_MIN = 158.0                   # aceite visible de 3:43 a 6:21 p. m.
T_INICIO_PIR = 370.0                  # °C, termómetro del lecho al aparecer aceite
T_MAX_LECHO = 400.0                   # °C, máxima del mismo termómetro
T_INI, RAMPA = 50.0, 1.5
DT_SEC = 2.0                          # paso de integración, igual que la GUI y el CLI

CARBONO_FIJO = OBJ_CHAR - CENIZA                      # 18.68 %
VOLATILES = 100.0 - HUMEDAD - CENIZA - CARBONO_FIJO   # 77.71 %


def feed(a2_factor):
    f = Feedstock(
        "Lodo PROENERGÉTICOS (calibrado)", HUMEDAD, VOLATILES, CARBONO_FIJO, CENIZA,
        BASE.E_a, BASE.A, yield_oil=0.80, yield_gas=0.20, yield_char=0.0,
        Ea1=BASE.Ea1, A1=BASE.A1, Ea2=BASE.Ea2, A2=BASE.A2 * a2_factor,
        Ea3=BASE.Ea3, A3=BASE.A3)
    f.T_onset_K = T_INICIO_PIR + 273.15   # inicio observado en planta (el modelo usa 250 °C por defecto)
    return f


def run(h_eff, T_pared, a2):
    sim = BatchReactorSimulation(
        feed(a2), CARGA_KG, length=6.0, diameter=2.75, rpm=1.0,
        T_start_C=T_INI, heating_rate_cmin=RAMPA, T_hold_C=T_pared,
        hold_time_min=900, h_eff=h_eff, burner_eff_pct=85.0)
    return sim.simulate(dt_sec=DT_SEC)


def evaluar(r):
    """Índices de inicio de aceite y de apagado (aceite = 60.56 %)."""
    t = np.array(r["time"]); oil = 100 * np.array(r["oil"]) / CARGA_KG
    i_on = int(np.argmax(oil > 0.05))
    i_st = int(np.argmax(oil >= OBJ_ACEITE_APAGADO)) if oil[-1] >= OBJ_ACEITE_APAGADO else len(t) - 1
    return dict(i_on=i_on, i_st=i_st, ventana=t[i_st] - t[i_on], aceite_final=oil[-1],
                T_lecho_apagado=r["T_solid"][i_st], t_apagado=t[i_st],
                gas=100 * r["gas"][i_st] / CARGA_KG, conv=100 * r["conversion"][i_st],
                comb_gal=r["waste_oil"][i_st])


def bisect(f, lo, hi, n=16):
    flo = f(lo)
    for _ in range(n):
        mid = 0.5 * (lo + hi); fm = f(mid)
        if (fm > 0) == (flo > 0): lo, flo = mid, fm
        else: hi = mid
    return 0.5 * (lo + hi)


def calibrar(T_pared):
    """Ajusta A2 (aceite total 62.10 %) y h_eff (ventana de 158 min) para una temperatura de pared dada."""
    h, a2 = 200.0, 1.2
    for _ in range(3):
        a2 = bisect(lambda x: evaluar(run(h, T_pared, x))["aceite_final"] - OBJ_ACEITE_TOTAL, 0.3, 3.0)
        h = bisect(lambda x: evaluar(run(x, T_pared, a2))["ventana"] - VENTANA_MIN, 30.0, 1500.0)
    return h, a2


# --------------------------------------------- calibración para varias temperaturas de pared (no medida)
rows = []
cal = {}
for Tp in (500.0, 550.0, 600.0):
    h, a2 = calibrar(Tp)
    r = run(h, Tp, a2); e = evaluar(r)
    cal[Tp] = (h, a2, r, e)
    rows.append([f"Pared {Tp:.0f} °C", round(h, 1), round(a2, 3), round(e["ventana"], 1),
                 round(e["T_lecho_apagado"], 1), round(e["t_apagado"], 1), round(e["conv"], 1),
                 round(e["gas"], 2), round(e["comb_gal"], 1)])
    print(rows[-1])
# sensibilidad de la ventana a h_eff en el caso central
h0, a20, _, _ = cal[550.0]
for f_ in (0.75, 1.25):
    e = evaluar(run(h0 * f_, 550.0, a20))
    rows.append([f"Pared 550 °C, h_eff {'-' if f_ < 1 else '+'}25 %", round(h0 * f_, 1), round(a20, 3),
                 round(e["ventana"], 1), round(e["T_lecho_apagado"], 1), round(e["t_apagado"], 1),
                 round(e["conv"], 1), round(e["gas"], 2), round(e["comb_gal"], 1)])
with open(f"{OUT}/calibracion_y_sensibilidad.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["caso", "h_eff_W_m2K", "factor_A2", "ventana_aceite_min", "T_lecho_al_apagar_C",
                "t_apagado_min", "conversion_pct", "gas_pct_al_apagar", "combustible_aux_gal"])
    w.writerows(rows)

# --------------------------------------------- tabla de entradas con su origen
entradas = [
    ("Carga", f"{CARGA_KG:,.2f} kg (3,700 gal)", "Planta + densidad ASTM D4052", "Medido"),
    ("Humedad", "2.00 %", "ASTM D95 (Tabla 1)", "Medido"),
    ("Cenizas", "1.61 %", "ASTM D482 (Tabla 1)", "Medido"),
    ("Inicio de pirólisis", "370 °C", "Termómetro a nivel del líquido al aparecer aceite", "Medido"),
    ("Temperatura máxima del lecho", "400 °C", "Mismo termómetro", "Medido"),
    ("Ventana de aceite", "158 min (3:43 a 6:21 p. m.)", "Observación del visor", "Medido"),
    ("Aceite al apagar", f"2,431 gal ({OBJ_ACEITE_APAGADO:.2f} %)", "Planta", "Medido"),
    ("Aceite total", "2,493 gal (62.10 %)", "Planta, incluye 62 gal del enfriamiento", "Medido"),
    ("Carbono fijo", f"{CARBONO_FIJO:.2f} %", "Residuo carbonoso de la corrida − cenizas", "Calibrado"),
    ("Volátiles", f"{VOLATILES:.2f} %", "Por diferencia", "Calibrado"),
    ("Rampa de pared", "1.5 °C/min", "Operación de planta", "Medido"),
    ("Temperatura de pared", "500 a 600 °C", "No medida; se evalúan tres casos", "Supuesto"),
    ("h_eff", f"{cal[600.0][0]:.0f} a {cal[500.0][0]:.0f} W/m²K", "Ajustado a la ventana de 158 min", "Calibrado"),
    ("Factor A2", f"{a20:.3f}", "Ajustado a 62.10 % de aceite total", "Calibrado"),
    ("Ea1, A1, Ea2, A2 base, Ea3, A3", "90 kJ/mol, 7.5e5 s⁻¹, 95 kJ/mol, 2.5e5 s⁻¹, 80 kJ/mol, 1e5 s⁻¹",
     "Valores por defecto del simulador, sin fuente", "Supuesto"),
    ("ΔH de pirólisis", "700 kJ/kg", "Valor por defecto", "Supuesto"),
    ("PCI syngas", "12 MJ/kg", "Valor por defecto", "Supuesto"),
    ("PCI combustible auxiliar", "41 MJ/kg", "Valor por defecto", "Supuesto"),
    ("Eficiencia del quemador", "85 %", "Supuesto de la tesina", "Supuesto"),
    ("Pérdidas de carcasa h_loss", "5 W/m²K", "Valor por defecto", "Supuesto"),
]
with open(f"{OUT}/tabla_entradas.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["parametro", "valor", "origen", "tipo"]); w.writerows(entradas)

# --------------------------------------------- figuras del caso central (pared 550 °C)
h0, a20, r, e = cal[550.0]
t = np.array(r["time"]); m = t <= e["t_apagado"] + 1e-6
plt.rcParams.update({"font.size": 10})
fig, ax = plt.subplots(figsize=(7.5, 3.6))
ax.plot(t[m], np.array(r["T_wall"])[m], "--", color="#c0392b", label="Pared del reactor (supuesta)")
ax.plot(t[m], np.array(r["T_solid"])[m], color="#1f3a93", lw=2, label="Lecho (simulado)")
ax.axhline(T_INICIO_PIR, color="gray", ls=":", lw=1)
ax.axhline(T_MAX_LECHO, color="gray", ls="-.", lw=1)
ax.text(5, T_INICIO_PIR - 22, "370 °C: inicio de pirólisis (medido)", fontsize=8, color="gray")
ax.text(5, T_MAX_LECHO + 6, "400 °C: máxima del lecho (medida)", fontsize=8, color="gray")
ax.axvspan(t[e["i_on"]], e["t_apagado"], color="#f39c12", alpha=0.12, label="Ventana de aceite (158 min)")
ax.set_xlabel("Tiempo (min)"); ax.set_ylabel("Temperatura (°C)")
ax.set_ylim(0, 600); ax.grid(alpha=.3); ax.legend(loc="upper left", fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/figura4_temperaturas.png", dpi=200)

fig, ax = plt.subplots(figsize=(7.5, 3.6))
ax.plot(t[m], np.array(r["oil"])[m], color="#d35400", lw=2, label="Aceite pirolítico")
ax.plot(t[m], np.array(r["gas"])[m], "--", color="#16a085", lw=2, label="Gas no condensable")
ax.plot(t[m], np.array(r["steam"])[m], ":", color="#8e44ad", lw=2, label="Vapor de agua")
ax.set_xlabel("Tiempo (min)"); ax.set_ylabel("Masa acumulada (kg)")
ax.grid(alpha=.3); ax.legend(loc="upper left")
fig.tight_layout(); fig.savefig(f"{OUT}/figura5_masa_acumulada.png", dpi=200)
print("Listo:", sorted(os.listdir(OUT)))
