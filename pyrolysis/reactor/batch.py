import numpy as np
from ..feedstock import Feedstock
from .base import BaseReactorSimulation

class BatchReactorSimulation(BaseReactorSimulation):
    def __init__(self, feedstock: Feedstock, batch_load_kg: float,
                 length: float, diameter: float, rpm: float,
                 T_start_C: float, heating_rate_cmin: float,
                 T_hold_C: float, hold_time_min: float,
                 h_eff: float = 80.0,
                 auto_heating_rate: bool = False,
                 burner_hp: float = 300.0,
                 burner_eff_pct: float = 70.0,
                 syngas_hp: float = 150.0,
                 shell_material_dict: dict = None,
                 shell_thickness_mm: float = 15.0,
                 h_loss: float = 5.0,
                 bulk_density: float = 900.0,
                 Cp_volatile: float = 1800.0,
                 Cp_char: float = 1000.0,
                 Cp_ash: float = 800.0,
                 fuel_lhv_mj_kg: float = 41.0,
                 fuel_density_kg_l: float = 0.90,
                 fuel_moisture_pct: float = 1.0,
                 fuel_ash_pct: float = 0.5):
        """
        Constructor para el modelo de simulación por lotes (Batch, dependiente del tiempo).
        Hereda de BaseReactorSimulation para reutilizar constantes termodinámicas.
        """
        # Inicializa las variables físicas compartidas en la clase base
        super().__init__(feedstock, length, diameter, rpm, h_eff,
                         bulk_density=bulk_density,
                         Cp_volatile=Cp_volatile,
                         Cp_char=Cp_char,
                         Cp_ash=Cp_ash)
        self.batch_load_kg = float(batch_load_kg)     # Carga inicial de masa seca/húmeda (kg)
        self.T_start = float(T_start_C) + 273.15       # Temperatura inicial de la cama (Kelvin)
        self.heating_rate_cmin = float(heating_rate_cmin)
        # Convierte la tasa de calentamiento de °C/min a °C/s
        self.heating_rate_csec = float(heating_rate_cmin) / 60.0
        self.T_hold = float(T_hold_C) + 273.15         # Temperatura final de sostenimiento (Kelvin)
        self.hold_time_min = float(hold_time_min)       # Tiempo de remojo o sostenimiento (minutos)

        # Calibración del quemador y tambor
        self.auto_heating_rate = bool(auto_heating_rate)
        self.burner_hp = float(burner_hp)
        self.burner_eff_pct = float(burner_eff_pct)
        self.syngas_hp = float(syngas_hp)
        
        if shell_material_dict is None:
            self.shell_material_dict = {'density': 7850.0, 'Cp': 480.0, 'k': 50.0}
        else:
            self.shell_material_dict = shell_material_dict
            
        self.shell_thickness_mm = float(shell_thickness_mm)
        self.h_loss = float(h_loss)
        self.fuel_lhv_mj_kg = float(fuel_lhv_mj_kg)
        self.fuel_density_kg_l = float(fuel_density_kg_l)
        self.fuel_moisture_pct = float(fuel_moisture_pct)
        self.fuel_ash_pct = float(fuel_ash_pct)

    def get_filling_degree_pct(self) -> float:
        """
        Calcula el grado de llenado volumétrico estático inicial (%).
        Representa la porción del cilindro del reactor ocupada por el lecho sólido de lodo.
        """
        vol_sludge = self.batch_load_kg / self.bulk_density
        vol_kiln = np.pi * (self.diameter / 2)**2 * self.length
        return (vol_sludge / max(vol_kiln, 1e-6)) * 100.0

    def get_wall_temp_K(self, t_sec: float) -> float:
        """
        Calcula la temperatura instantánea programada de la pared del reactor en el tiempo t_sec.
        Sigue un perfil clásico de calentamiento por rampa (lineal) y posterior sostenimiento (placa).
        (Nota: Solo se usa en el modo de rampa manual predefinida).
        """
        dT = self.T_hold - self.T_start
        t_ramp = dT / self.heating_rate_csec if self.heating_rate_csec > 0 else 0.0
        
        if t_sec <= t_ramp:
            # Fase de calentamiento lineal (Rampa)
            return self.T_start + self.heating_rate_csec * t_sec
        else:
            # Fase de mantenimiento a temperatura constante (Holding)
            return self.T_hold

    def simulate(self, dt_sec: float = 2.0) -> dict:
        """
        Ejecuta la integración numérica en el tiempo (solución dinámica transitoria).
        Simula las variaciones de masa y temperatura del lote sólido dentro del reactor.
        """
        # 1. Configuración de parámetros físicos del tambor para balance transitorio
        t_steel = self.shell_thickness_mm / 1000.0
        rho_steel = self.shell_material_dict.get('density', 7850.0)
        Cp_steel = self.shell_material_dict.get('Cp', 480.0)
        
        M_steel = np.pi * self.diameter * self.length * t_steel * rho_steel
        C_steel = M_steel * Cp_steel
        
        D_outer = self.diameter + 2.0 * t_steel
        A_outer = np.pi * D_outer * self.length
        
        # Poder calorífico efectivo del combustible e inercia volumétrica
        x_comb = max(0.0, 1.0 - (self.fuel_moisture_pct / 100.0) - (self.fuel_ash_pct / 100.0))
        LHV_fuel_j_kg = max(1e6, (self.fuel_lhv_mj_kg * 1e6) * x_comb - 2256000.0 * (self.fuel_moisture_pct / 100.0))
        fuel_mass_per_gal = self.fuel_density_kg_l * 3.78541
        LHV_oil_gal = LHV_fuel_j_kg * fuel_mass_per_gal
        
        # 2. Inicialización de masas
        fracs = self.feedstock.get_fractions()
        m_moist = self.batch_load_kg * fracs['moisture']
        m_volatile = self.batch_load_kg * fracs['volatile']
        m_char = self.batch_load_kg * fracs['fixed_carbon']
        m_ash = self.batch_load_kg * fracs['ash']
        m_solid_total = m_moist + m_volatile + m_char + m_ash
        
        # Estima el tiempo nominal de rampa para definir la duración del ensayo
        dT = self.T_hold - self.T_start
        if self.auto_heating_rate:
            Q_main_nominal = self.burner_hp * 745.7 * (self.burner_eff_pct / 100.0)
            Cp_s_init = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            C_total_init = C_steel + (m_solid_total * Cp_s_init)
            nominal_rate_csec = Q_main_nominal / C_total_init if C_total_init > 0 else 0.1
            t_ramp_sec = dT / nominal_rate_csec if nominal_rate_csec > 0 else 1000.0
        else:
            t_ramp_sec = dT / self.heating_rate_csec if self.heating_rate_csec > 0 else 0.0
            
        t_total_sec = t_ramp_sec + self.hold_time_min * 60.0 # Tiempo total de simulación en segundos
        steps = int(t_total_sec / dt_sec)
        
        T_s = self.T_start
        T_w = self.T_start
        
        # Inicializa las corrientes gaseosas acumuladas que se liberan del lote (kg)
        m_steam = 0.0
        m_oil_vap = 0.0
        m_gas_vap = 0.0
        
        # Listas vacías para almacenar los perfiles temporales
        time_arr, moist_arr, volatile_arr, char_arr, ash_arr = [], [], [], [], []
        temp_s_arr, temp_w_arr = [], []
        oil_arr, gas_arr, steam_arr, conv_arr = [], [], [], []
        humidity_arr = []
        waste_oil_arr = []
        m_waste_oil_gal = 0.0
        p_oil_arr = []
        p_syngas_arr = []
        
        # PROENERGETICOS Manifold & Autogenous Pressure Kinetics
        pressure_kpa_arr = []
        pressure_psig_arr = []
        v_main_arr = []
        v_branch_arr = []
        air_disp_arr = []
        
        v_reactor_m3 = np.pi * (self.diameter / 2.0)**2 * self.length
        v_sludge_m3 = self.batch_load_kg / max(self.bulk_density, 100.0)
        v_headspace_init_m3 = max(0.1, v_reactor_m3 - v_sludge_m3)
        
        d_main_m = 8.0 * 0.0254      # 8 pulgadas = 0.2032 m
        d_branch_m = 4.0 * 0.0254    # 4 pulgadas = 0.1016 m
        a_main = np.pi * (d_main_m / 2.0)**2
        a_branches = 4.0 * np.pi * (d_branch_m / 2.0)**2
        
        T_boil = 373.15                           # Punto de ebullición del agua en Kelvin (100 °C)
        initial_volatile = max(m_volatile, 1e-10) # Referencia para calcular la conversión
        
        # Área de contacto térmico basada en la fracción superficial correspondiente al grado de llenado
        eta = self.get_filling_degree_pct() / 100.0
        A_heat = np.pi * self.diameter * self.length * max(0.05, eta)
        
        total_energy_kwh = 0.0                    # Consumo acumulado de energía térmica suministrada (kWh)
        
        # Bucle de integración a lo largo del tiempo (paso por paso)
        for step in range(steps + 1):
            t_sec = step * dt_sec
            t_min = t_sec / 60.0
            
            # Guarda los estados másicos y térmicos en el minuto actual
            time_arr.append(t_min)
            moist_arr.append(m_moist)
            volatile_arr.append(m_volatile)
            char_arr.append(m_char)
            ash_arr.append(m_ash)
            temp_s_arr.append(T_s - 273.15)       # Temperatura del lecho en °C
            temp_w_arr.append(T_w - 273.15)       # Temperatura de pared en °C
            oil_arr.append(m_oil_vap)
            gas_arr.append(m_gas_vap)
            steam_arr.append(m_steam)
            waste_oil_arr.append(m_waste_oil_gal)
            
            # Conversión instantánea de materia volátil (0 a 1)
            conversion = 1.0 - (m_volatile / initial_volatile)
            conv_arr.append(conversion)
            
            # Humedad instantánea del lecho sólido en base húmeda
            m_sol_tot = m_moist + m_volatile + m_char + m_ash
            humidity_pct = self.calculate_humidity_pct(m_moist, m_sol_tot)
            humidity_arr.append(humidity_pct)
            
            # Termina si se alcanzó el tiempo límite programado
            if t_sec >= t_total_sec:
                p_oil_arr.append(p_oil_arr[-1] if p_oil_arr else 0.0)
                p_syngas_arr.append(p_syngas_arr[-1] if p_syngas_arr else 0.0)
                pressure_kpa_arr.append(pressure_kpa_arr[-1] if pressure_kpa_arr else 101.325)
                pressure_psig_arr.append(pressure_psig_arr[-1] if pressure_psig_arr else 0.0)
                v_main_arr.append(v_main_arr[-1] if v_main_arr else 0.0)
                v_branch_arr.append(v_branch_arr[-1] if v_branch_arr else 0.0)
                air_disp_arr.append(air_disp_arr[-1] if air_disp_arr else 0.0)
                break
                
            # --- 1. Propiedades Termodinámicas y Coeficientes ---
            m_solid_total = m_moist + m_volatile + m_char + m_ash
            
            # Capacidad calorífica ponderada del lecho sólido Cp_s (J/kg·K)
            Cp_s = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            
            # Coeficiente dinámico térmico beta (1/s)
            denom_temp = m_solid_total * Cp_s
            if denom_temp > 1e-8:
                beta = (self.h_eff * A_heat) / denom_temp
            else:
                beta = 0.0
                
            # --- 2. Cinética y Reacción de Pirólisis (Primer Orden) ---
            # Constantes y tasas de reacción locales
            k1, k2, k3, r_slug, r_medios, r_gases = self.calculate_first_order_kinetics(T_s, m_volatile, m_oil_vap)
            
            # Capa la reacción del lodo para no consumir más de lo disponible en el paso dt_sec
            max_r_slug = m_volatile / dt_sec if dt_sec > 0.0 else 0.0
            if r_slug > max_r_slug:
                scale = max_r_slug / r_slug
                k1_eff = k1 * scale
                k2_eff = k2 * scale
                r_slug = max_r_slug
            else:
                k1_eff = k1
                k2_eff = k2
                
            d_volatile = r_slug * dt_sec
            d_oil_primary = k1_eff * m_volatile * dt_sec
            d_non_oil = k2_eff * m_volatile * dt_sec
            
            y_gas = getattr(self.feedstock, 'yield_gas', 0.25)
            y_char = getattr(self.feedstock, 'yield_char', 0.15)
            y_non_oil = y_gas + y_char
            if y_non_oil > 0:
                frac_gas = y_gas / y_non_oil
                frac_char = y_char / y_non_oil
            else:
                frac_gas = 1.0
                frac_char = 0.0
                
            d_gas_primary = d_non_oil * frac_gas
            d_char_prod = d_non_oil * frac_char
            
            # Craqueo secundario limitado al tiempo de residencia local del vapor
            tau_gas = 2.0  # Tiempo de residencia del vapor caliente (segundos)
            d_oil_cracked = d_oil_primary * (1.0 - np.exp(-k3 * tau_gas))
            
            d_oil_prod = d_oil_primary - d_oil_cracked
            d_gas_prod = d_gas_primary + d_oil_cracked
            
            # Calor consumido por la pirólisis endotérmica en este paso (J)
            H_rxn = d_volatile * self.dH_pyro  

            # --- 3. Integración Térmica ---
            # Calor sensible absorbido desde la pared en este paso (J)
            if beta > 0:
                T_target_heat = T_w - (T_w - T_s) * np.exp(-beta * dt_sec)
            else:
                T_target_heat = T_s
                
            # Pérdida de temperatura por el efecto endotérmico de la pirólisis
            dT_reaction = - (H_rxn / denom_temp) if denom_temp > 1e-8 else 0.0
            T_s_next = T_target_heat + dT_reaction
            
            # --- 4. Balance Térmico de la Pared del Reactor y Quemador ---
            Q_main_nominal = self.burner_hp * 745.7 * (self.burner_eff_pct / 100.0) # W
            r_syngas_prod = d_gas_prod / dt_sec if dt_sec > 0.0 else 0.0 # kg/s
            LHV_syngas = 12e6 # J/kg
            Q_syngas_thermal = r_syngas_prod * LHV_syngas * (self.burner_eff_pct / 100.0)
            
            Q_needed_wall = (T_w - T_s) * self.h_eff * A_heat if T_w > T_s else 0.0
            Q_main_used = max(0.0, Q_needed_wall - Q_syngas_thermal)
            Q_main_used = min(Q_main_used, Q_main_nominal)
            
            if self.auto_heating_rate:
                D_outer = self.diameter + 2.0 * (self.shell_thickness_mm / 1000.0)
                A_outer = np.pi * D_outer * self.length
                Q_loss = self.h_loss * A_outer * (T_w - self.T_start)
                
                Q_net_wall = (Q_main_used + Q_syngas_thermal) - Q_needed_wall - Q_loss
                M_steel = np.pi * self.diameter * self.length * (self.shell_thickness_mm / 1000.0) * self.shell_material_dict.get('density', 7850.0)
                C_steel = M_steel * self.shell_material_dict.get('Cp', 480.0)
                
                dT_w = (Q_net_wall * dt_sec) / C_steel if C_steel > 0 else 0.0
                T_w_next = min(T_w + dT_w, self.T_hold)
            else:
                T_w_next = self.get_wall_temp_K(t_sec + dt_sec)
            
            # Acumula combustible auxiliar consumido en galones
            Q_main_combustion = Q_main_used / (self.burner_eff_pct / 100.0) if self.burner_eff_pct > 0 else 0.0
            dm_waste_oil_kg = (Q_main_combustion * dt_sec) / LHV_fuel_j_kg
            m_waste_oil_gal += dm_waste_oil_kg / fuel_mass_per_gal
            
            # Acumula energía total suministrada al lecho sólido en kWh
            total_energy_kwh += (Q_needed_wall * dt_sec) / 3.6e6
            
            d_moist = 0.0
            
            # --- 5. Lógica de Secado y Bloqueo por Ebullición de Agua (100 °C) ---
            if m_moist > 1e-8:
                if T_s >= T_boil or T_s_next > T_boil:
                    if T_s < T_boil:
                        H_preheat = denom_temp * (T_boil - T_s)
                    else:
                        H_preheat = 0.0
                        
                    H_input = denom_temp * (T_target_heat - T_s)
                    H_avail_evap = H_input - H_preheat - H_rxn
                    
                    if H_avail_evap > 0:
                        max_d_moist = m_moist
                        d_moist = H_avail_evap / self.dH_evap
                        d_moist = min(d_moist, max_d_moist)
                        
                        H_used_evap = d_moist * self.dH_evap
                        H_remain = H_avail_evap - H_used_evap
                        
                        T_s = T_boil
                        if H_remain > 0 and denom_temp > 1e-8:
                            T_s += H_remain / denom_temp
                    else:
                        T_s = T_s_next
                else:
                    T_s = T_s_next
            else:
                T_s = T_s_next
                
            # --- 6. Actualización de las Masas y Vapores Acumulados ---
            m_moist = max(m_moist - d_moist, 0.0)
            m_volatile = max(m_volatile - d_volatile, 0.0)
            m_char = m_char + d_char_prod
            
            m_steam += d_moist
            m_oil_vap += d_oil_prod
            m_gas_vap += d_gas_prod
            
            # --- 7. Cálculo de Purga Autógena y Dinámica de Presión ---
            w_vap_gen = (d_moist + d_oil_prod + d_gas_prod) / dt_sec if dt_sec > 0 else 0.0
            T_gas_k = max(T_s, 298.15)
            
            w_h2o_f = d_moist / max(1e-8, d_moist + d_oil_prod + d_gas_prod) if w_vap_gen > 0 else 0.5
            w_oil_f = d_oil_prod / max(1e-8, d_moist + d_oil_prod + d_gas_prod) if w_vap_gen > 0 else 0.3
            w_gas_f = max(0.0, 1.0 - w_h2o_f - w_oil_f)
            
            mw_mix = w_h2o_f * 18.0 + w_oil_f * 120.0 + w_gas_f * 28.0
            mw_mix = max(18.0, min(120.0, mw_mix))
            
            rho_gas_t = (101325.0 * (mw_mix / 1000.0)) / (8.314 * T_gas_k)
            q_gas_gen_m3s = w_vap_gen / max(1e-4, rho_gas_t)
            
            v_main_ms = q_gas_gen_m3s / a_main if a_main > 0 else 0.0
            v_branch_ms = q_gas_gen_m3s / a_branches if a_branches > 0 else 0.0
            
            air_disp_m3 = min(v_headspace_init_m3, (m_steam + m_oil_vap + m_gas_vap) / max(1e-4, rho_gas_t))
            
            # Contrapresión de tubería por pérdidas por fricción y accesorios (8" manifold / 4x4" ramas)
            delta_p_pa = 0.025 * (10.0 / d_main_m) * (0.5 * rho_gas_t * v_main_ms**2) + (1.5 * 0.5 * rho_gas_t * v_main_ms**2)
            p_abs_kpa = (101325.0 + delta_p_pa) / 1000.0
            p_gauge_psig = delta_p_pa / 6894.76
            
            v_main_arr.append(v_main_ms)
            v_branch_arr.append(v_branch_ms)
            air_disp_arr.append(air_disp_m3)
            pressure_kpa_arr.append(p_abs_kpa)
            pressure_psig_arr.append(p_gauge_psig)
            
            # Actualiza T_w para el paso siguiente
            T_w = T_w_next

        # ==============================================================================
        # CÁLCULOS Y BALANCE DE MATERIA FINAL DE LA OPERACIÓN POR LOTES
        # ==============================================================================
        final_char_kg = m_char + m_ash + m_volatile
        final_oil_kg = m_oil_vap
        final_gas_kg = m_gas_vap
        final_steam_kg = m_steam
        
        # Cierre y error porcentual del balance de masa acumulado
        total_out_kg = final_char_kg + final_oil_kg + final_gas_kg + final_steam_kg + m_moist
        mass_error_pct = abs(total_out_kg - self.batch_load_kg) / self.batch_load_kg * 100.0 if self.batch_load_kg > 0 else 0.0
        
        # ASTM Correlaciones y Métricas de Calidad de Bio-Crudo
        hhv_sludge_mj_kg = 18.5
        hhv_oil_mj_kg = min(43.5, max(36.0, 38.0 + 0.008 * (self.T_hold - 273.15 - 450.0) + 0.10 * (initial_volatile / self.batch_load_kg * 100.0 - 50.0)))
        hhv_oil_btu_lb = hhv_oil_mj_kg * 429.923
        energy_enhancement_factor = hhv_oil_mj_kg / hhv_sludge_mj_kg
        
        viscosity_40c_cst = max(12.0, 45.0 - 0.08 * (self.T_hold - 273.15 - 400.0))
        density_15c_kg_m3 = float(getattr(self, 'bio_oil_density', 750.0))
        sg_15c = density_15c_kg_m3 / 999.1
        api_gravity = (141.5 / max(0.1, sg_15c)) - 131.5
        
        moisture_feed_pct = (humidity_arr[0] if humidity_arr else 30.0)
        bsw_moisture_pct = min(8.0, max(1.5, 3.5 * (moisture_feed_pct / 30.0)))
        
        # Autosuficiencia de Syngas y Excedente a Antorcha / Flare
        lhv_syngas_mj_kg = 12.0
        total_syngas_energy_mj = final_gas_kg * lhv_syngas_mj_kg
        total_thermal_demand_mj = (total_energy_kwh * 3.6) / max(0.1, self.burner_eff_pct / 100.0)
        
        syngas_recirc_pct = min(100.0, (total_syngas_energy_mj / max(1e-4, total_thermal_demand_mj)) * 100.0) if total_thermal_demand_mj > 0 else 100.0
        syngas_flare_kg = final_gas_kg * (1.0 - (syngas_recirc_pct / 100.0))
        syngas_flare_m3 = syngas_flare_kg / 1.15
        
        # Tiempo de desplazamiento completo de aire inicial
        air_disp_complete_min = 0.0
        for idx_t, v_d in enumerate(air_disp_arr):
            if v_d >= v_headspace_init_m3 * 0.90:
                air_disp_complete_min = time_arr[idx_t]
                break
        if air_disp_complete_min == 0.0 and time_arr:
            air_disp_complete_min = time_arr[min(len(time_arr)-1, 15)]
        
        # Devuelve el resumen temporal completo y los indicadores agregados del lote
        results = {
            'time': time_arr,
            'moisture': moist_arr,
            'volatile': volatile_arr,
            'char': char_arr,
            'ash': ash_arr,
            'T_solid': temp_s_arr,
            'T_wall': temp_w_arr,
            'oil': oil_arr,
            'gas': gas_arr,
            'steam': steam_arr,
            'waste_oil': waste_oil_arr,
            'p_oil': p_oil_arr,
            'p_syngas': p_syngas_arr,
            'conversion': conv_arr,
            'humidity': humidity_arr,
            'pressure_kpa': pressure_kpa_arr,
            'pressure_psig': pressure_psig_arr,
            'v_main_ms': v_main_arr,
            'v_branch_ms': v_branch_arr,
            'air_disp_m3': air_disp_arr,
            'summary': {
                'batch_load_kg': self.batch_load_kg,
                'oil_yield_kg': final_oil_kg,
                'gas_yield_kg': final_gas_kg,
                'char_yield_kg': final_char_kg,
                'water_yield_kg': final_steam_kg,
                'oil_yield_pct': (final_oil_kg / self.batch_load_kg) * 100.0 if self.batch_load_kg > 0 else 0,
                'gas_yield_pct': (final_gas_kg / self.batch_load_kg) * 100.0 if self.batch_load_kg > 0 else 0,
                'char_yield_pct': (final_char_kg / self.batch_load_kg) * 100.0 if self.batch_load_kg > 0 else 0,
                'water_yield_pct': (final_steam_kg / self.batch_load_kg) * 100.0 if self.batch_load_kg > 0 else 0,
                'conversion_pct': conv_arr[-1] * 100.0,
                'filling_degree_pct': self.get_filling_degree_pct(),
                'total_energy_kwh': total_energy_kwh,
                'waste_oil_consumed_gal': m_waste_oil_gal,
                'mass_error_pct': mass_error_pct,
                'initial_humidity_pct': humidity_arr[0],
                'final_humidity_pct': humidity_arr[-1],
                'peak_pressure_kpa': max(pressure_kpa_arr) if pressure_kpa_arr else 101.325,
                'peak_pressure_psig': max(pressure_psig_arr) if pressure_psig_arr else 0.0,
                'max_v_main_ms': max(v_main_arr) if v_main_arr else 0.0,
                'max_v_branch_ms': max(v_branch_arr) if v_branch_arr else 0.0,
                'air_disp_complete_min': air_disp_complete_min,
                'headspace_volume_m3': v_headspace_init_m3,
                'hhv_oil_mj_kg': hhv_oil_mj_kg,
                'hhv_oil_btu_lb': hhv_oil_btu_lb,
                'energy_enhancement_factor': energy_enhancement_factor,
                'viscosity_40c_cst': viscosity_40c_cst,
                'api_gravity': api_gravity,
                'bsw_moisture_pct': bsw_moisture_pct,
                'syngas_recirc_pct': syngas_recirc_pct,
                'syngas_flare_kg': syngas_flare_kg,
                'syngas_flare_m3': syngas_flare_m3
            }
        }
        return results
