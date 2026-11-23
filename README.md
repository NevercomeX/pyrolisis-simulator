# Rotary Pyrolysis Reactor Simulator

A high-fidelity numerical simulator of a rotary pyrolysis reactor (rotary kiln) built in Python. It models **batch** operation, enabling engineers to analyze the thermal dehydration and pyrolysis of **Petroleum Sludge**, **Hydrocarbon Sludge**, and custom blends.

The model is integrated with a beautiful, theme-aware **Streamlit Web Dashboard** and a **Command Line Interface (CLI)** for batch runs and data export.

---

## 🛠️ Installation & Setup

1. Make sure you have Python 3.10+ installed.
2. Navigate to the project directory:
   ```bash
   cd c:\Users\lsola\Documents\Pirolisis
   ```
3. Install the required libraries:
   ```bash
   pip install -r requirements.txt
   ```

### 🔄 Updating the Project
To pull the latest changes from Git and install/update dependencies automatically:

- **Linux / macOS**:
  ```bash
  ./update.sh
  # or: python3 update.py
  ```
- **Windows**:
  ```cmd
  update.bat
  # or: python update.py
  ```

---

## 🚀 Running the Applications

### 1. Interactive Web Dashboard (Streamlit)
To start the web application, run:
```bash
streamlit run app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your web browser (Brave recommended!).

**Dashboard Features:**
- **Feedstock Config**: Blend Petroleum Sludge and Hydrocarbon Sludge using a percentage slider, or input custom values (Moisture, Volatiles, Fixed Carbon, Ash, and Arrhenius kinetics $E_a, A$).
- **Theme-Aware Style**: Supports light and dark browser themes natively.
- **Batch Controls**: Adjust batch size (kg), heating rate (°C/min), holding temperature, and holding duration (minutes).
- **Interactive Visualizations**: Interactive Plotly plots showing temperature, bed mass, and product vapor evolution over time.
- **Data Export**: Download simulation profile CSVs for post-processing.

### 2. Command Line Interface (CLI)
You can run simulations headlessly using `cli.py`:

**Example:**
```bash
python cli.py --feed petroleum --batch-load 200 --heating-rate 12 --temp-hold 600 --hold-time 90 --out-plot batch_profile.png
```

**CLI Arguments:**
- `--feed`: Feedstock type (`petroleum`, `hydrocarbon`, or `blend`, default: `blend`).
- `--blend-ratio`: Ratio of Petroleum Sludge in blend (0.0 to 1.0, default: `0.5`).
- `--length` & `--diameter`: Reactor length and diameter in meters.
- `--rpm`: Rotational speed (RPM).
- `--h-eff`: Effective heat transfer coefficient in W/m²·K (default: `80.0`).
- **Batch Options**: `--batch-load` (kg), `--temp-start` (°C), `--heating-rate` (°C/min), `--temp-hold` (°C), `--hold-time` (minutes).
- `--out-csv` & `--out-plot`: Export CSV data and plot images.

---

## 🔬 Mathematical Modeling Reference

The simulator uses a time-step based solver with analytical heat integration for unconditional numerical stability:

### 1. Volumetric Load
Sludge stays in the drum throughout the cycle. The static filling degree $\eta$ (%) is:
$$\eta = \frac{M_{load} / \rho_{bulk}}{\pi \cdot (D/2)^2 \cdot L} \times 100\%$$
Where sludge bulk density $\rho_{bulk} = 900$ kg/m³.

### 2. Thermal Phase Change (Dehydration)
When moisture is present and solid temperature $T_s$ reaches $100^\circ\text{C}$:
- Bed temperature is locked at $100^\circ\text{C}$ (373.15 K).
- All heat transferred from the wall goes into water vaporization ($\Delta H_{evap} = 2256$ kJ/kg).
- Once fully dry, bed temperature continues heating toward the wall temperature.

### 3. Pyrolysis Kinetics
Thermal decomposition of volatile hydrocarbons is modeled using a first-order rate:
$$r_{pyro} = k_{pyro} \cdot M_{volatile}$$
$$k_{pyro} = A \cdot \exp\left(-\frac{E_a}{R \cdot T_s}\right)$$
Reaction heat consumption is $\Delta H_{pyro} = 600$ kJ/kg of volatiles reacted (endothermic). Pyrolyzed volatiles are split into Pyrolysis oil, Syngas, and solid Char residue.


## Perfiles de simulación

La barra lateral incluye un selector **Perfil**:

- **General (uso público):** valores por defecto del simulador.
- **Caso de estudio: corrida PROENERGÉTICOS (tesis):** carga los datos medidos y calibrados de la corrida
  industrial documentada en la tesina (3,700 gal, inicio de pirólisis a 370 °C, rampa de 1.5 °C/min,
  h_eff calibrado con la ventana de aceite de 158 min). No requiere introducir datos a mano.
  El botón "Restablecer datos de la corrida" vuelve a los valores originales del caso.

Desde la línea de comandos: `python cli.py --perfil tesis`.
El origen de cada valor (medido, calibrado o supuesto) está documentado en `pyrolysis/profiles.py`.
