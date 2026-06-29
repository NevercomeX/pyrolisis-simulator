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
            d_gas_primary = k2_eff * m_volatile * dt_sec
            
            # Craqueo secundario limitado al tiempo de residencia local del vapor
            tau_gas = 2.0  # Tiempo de residencia del vapor caliente (segundos)
            d_oil_cracked = d_oil_primary * (1.0 - np.exp(-k3 * tau_gas))
            
            d_oil_prod = d_oil_primary - d_oil_cracked
            d_gas_prod = d_gas_primary + d_oil_cracked
            
            # Char no se produce directamente a partir de volátiles en esta cinética de 3 especies
            d_char_prod = 0.0
            
            # Calor consumido por la pirólisis endotérmica en este paso (J)
            H_rxn = d_volatile * self.dH_pyro  

            # --- 3. Integración Térmica ---
            # Calor sensible absorbido desde la pared en este paso (J)
            if beta > 0:
                T_target_heat = T_w - (T_w - T_s) * np.exp(-beta * dt_sec)
            else:
                T_target_heat = T_s
                
            H_input = m_solid_total * Cp_s * (T_target_heat - T_s)
            
            # Cambio de temperatura inicial debido a la pirólisis endotérmica
            dT_reaction = - H_rxn / denom_temp if denom_temp > 1e-8 else 0.0
            T_s_next = T_target_heat + dT_reaction
            
            # --- 4. Actualización Dinámica de la Pared y Consumo de Combustible ---
            # LHV de combustible de quemadores (precalculado)
            LHV_syngas = 12e6  # 12 MJ/kg para el syngas
            burner_eff = self.burner_eff_pct / 100.0
            Q_main_capacity = self.burner_hp * 745.7 * burner_eff
            
            # Tasa instantánea de producción de syngas en kg/s
            r_gas_prod = d_gas_prod / dt_sec if dt_sec > 0 else 0.0
            # Calor térmico disponible a partir de la combustión y calor sensible del syngas caliente
            Q_syngas_available_thermal = r_gas_prod * (LHV_syngas + self.Cp_pyro_gas * (T_s - 298.15)) * burner_eff
            
            # Activación del syngas una vez que hay flujo significativo y se supera el umbral de inicio de pirólisis (220 °C)
            syngas_active = (Q_syngas_available_thermal > 100.0) and (T_s >= 493.15)
            
            if self.auto_heating_rate:
                # Pérdidas de calor hacia el ambiente
                Q_loss = self.h_loss * A_outer * max(0.0, T_w - 298.15)
                # Calor transferido al lecho en Watts
                Q_transferred = H_input / dt_sec
                
                if syngas_active:
                    # En la realidad, al usar syngas se deja de utilizar el aceite residual
                    Q_main_used = 0.0
                    Q_syngas_used = Q_syngas_available_thermal
                    Q_in = Q_syngas_used
                    
                    # Termostato limitador modulando el syngas si excede T_hold
                    dT_w_unlimited = ((Q_in - Q_loss - Q_transferred) / C_steel) * dt_sec
                    if T_w + dT_w_unlimited > self.T_hold:
                        Q_in = max(0.0, Q_loss + Q_transferred)
                        Q_syngas_used = Q_in
                else:
                    # Usamos aceite residual únicamente
                    Q_syngas_used = 0.0
                    Q_main_used = Q_main_capacity
                    Q_in = Q_main_used
                    
                    # Termostato limitador modulando el quemador principal si excede T_hold
                    dT_w_unlimited = ((Q_in - Q_loss - Q_transferred) / C_steel) * dt_sec
                    if T_w + dT_w_unlimited > self.T_hold:
                        Q_in = max(0.0, Q_loss + Q_transferred)
                        Q_main_used = min(Q_in, Q_main_capacity)
                
                # Balance de calor en la pared de acero
                dT_w = ((Q_in - Q_loss - Q_transferred) / C_steel) * dt_sec
                T_w_next = min(T_w + dT_w, self.T_hold)
                
                # Acumula la energía total consumida (kWh)
                if Q_in > 0:
                    total_energy_kwh += (Q_in * dt_sec) / 3.6e6
            else:
                T_w_next = self.get_wall_temp_K(t_sec + dt_sec)
                Q_transferred = H_input / dt_sec
                if syngas_active:
                    Q_main_used = 0.0
                    Q_syngas_used = max(0.0, min(Q_transferred, Q_syngas_available_thermal))
                else:
                    Q_syngas_used = 0.0
                    Q_main_used = max(0.0, Q_transferred)
                
                if H_input > 0:
                    total_energy_kwh += (H_input / 3.6e6)
            
            # Calcula el consumo de aceite residual del quemador principal en este paso
            Q_main_combustion = Q_main_used / burner_eff if burner_eff > 0.0 else 0.0
            d_waste_oil = (Q_main_combustion * dt_sec) / LHV_oil_gal
            m_waste_oil_gal += d_waste_oil
            
            p_oil_arr.append(float(Q_main_used) / 1000.0)
            p_syngas_arr.append(float(Q_syngas_used) / 1000.0)
            
            d_moist = 0.0
            
            # --- 4. Balances y Bloqueo de Humedad (Punto de Ebullición a 100 °C) ---
            if m_moist > 1e-8:
                if T_s >= T_boil or T_s_next > T_boil:
                    # Energía sensible consumida para precalentar la humedad hasta 100 °C
                    if T_s < T_boil:
                        H_preheat = m_solid_total * Cp_s * (T_boil - T_s)
                    else:
                        H_preheat = 0.0
                        
                    # Calor neto restante disponible exclusivamente para evaporar agua
                    H_avail_evap = H_input - H_preheat - H_rxn
                    
                    if H_avail_evap > 0:
                        max_d_moist = m_moist
                        d_moist = H_avail_evap / self.dH_evap # Vaporización húmeda (masa en kg)
                        d_moist = min(d_moist, max_d_moist)
                        
                        H_used_evap = d_moist * self.dH_evap
                        H_remain = H_avail_evap - H_used_evap
                        
                        T_s = T_boil # Temperatura fija durante el secado
                        # Si se evapora toda el agua, la energía restante continúa subiendo la temperatura
                        if H_remain > 0 and denom_temp > 1e-8:
                            T_s += H_remain / denom_temp
                    else:
                        T_s = T_s_next
                else:
                    T_s = T_s_next
            else:
                T_s = T_s_next
                
            # --- 5. Actualización de las Masas y Vapores Acumulados ---
            m_moist = max(m_moist - d_moist, 0.0)
            m_volatile = max(m_volatile - d_volatile, 0.0)
            m_char = m_char + d_char_prod
            
            m_steam += d_moist
            m_oil_vap += d_oil_prod
            m_gas_vap += d_gas_prod
            
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
                'final_humidity_pct': humidity_arr[-1]
            }
        }
        return results
