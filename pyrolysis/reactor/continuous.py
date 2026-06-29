import numpy as np
import pandas as pd
from ..feedstock import Feedstock
from .base import BaseReactorSimulation

class ContinuousReactorSimulation(BaseReactorSimulation):
    def __init__(self, feedstock: Feedstock, feed_rate_kgh: float, 
                 length: float, diameter: float, slope: float, rpm: float, 
                 T_inlet_C: float, h_eff: float = 80.0, 
                 T_wall_type: str = 'uniform', T_wall_params: dict = None,
                 bulk_density: float = 900.0,
                 Cp_volatile: float = 1800.0,
                 Cp_char: float = 1000.0,
                 Cp_ash: float = 800.0,
                 burner_hp: float = 300.0,
                 burner_eff_pct: float = 70.0,
                 syngas_hp: float = 150.0,
                 fuel_lhv_mj_kg: float = 41.0,
                 fuel_density_kg_l: float = 0.90,
                 fuel_moisture_pct: float = 1.0,
                 fuel_ash_pct: float = 0.5):
        """
        Constructor para el modelo de simulación de reactor rotatorio continuo (1D espacial).
        Hereda de BaseReactorSimulation para reutilizar constantes termodinámicas.
        """
        # Inicializa las variables físicas compartidas en la clase base
        super().__init__(feedstock, length, diameter, rpm, h_eff,
                         bulk_density=bulk_density,
                         Cp_volatile=Cp_volatile,
                         Cp_char=Cp_char,
                         Cp_ash=Cp_ash)
        self.feed_rate_kgh = float(feed_rate_kgh)
        self.burner_hp = float(burner_hp)
        self.burner_eff_pct = float(burner_eff_pct)
        self.syngas_hp = float(syngas_hp)
        self.slope = float(slope)
        self.T_inlet = float(T_inlet_C) + 273.15  # Convierte la temperatura de entrada de sólidos a Kelvin
        self.T_wall_type = T_wall_type             # Tipo de perfil de pared: 'uniform', 'linear', o 'zones'
        self.fuel_lhv_mj_kg = float(fuel_lhv_mj_kg)
        self.fuel_density_kg_l = float(fuel_density_kg_l)
        self.fuel_moisture_pct = float(fuel_moisture_pct)
        self.fuel_ash_pct = float(fuel_ash_pct)
        
        # Define los parámetros de temperatura de pared por defecto si no se especifican
        if T_wall_params is None:
            if T_wall_type == 'uniform':
                self.T_wall_params = {'T_wall': 550.0}
            elif T_wall_type == 'linear':
                self.T_wall_params = {'T_wall_in': 300.0, 'T_wall_out': 600.0}
            else: # zones (3 zonas de calentamiento)
                self.T_wall_params = {'zones': [(0.3, 350.0), (0.7, 550.0), (1.0, 500.0)]}
        else:
            self.T_wall_params = T_wall_params

    def get_residence_time_min(self) -> float:
        """
        Calcula el tiempo medio de residencia de sólidos (MRT) en minutos 
        utilizando la fórmula empírica clásica de Sullivan para tambores rotatorios.
        """
        theta = self.feedstock.angle_of_repose # Ángulo de reposo del lodo
        slope_deg = np.arctan(self.slope) * 180.0 / np.pi # Convierte la pendiente a grados
        
        # Evita división por cero garantizando un valor mínimo para RPM e inclinación
        denom = self.diameter * max(self.rpm, 0.01) * max(slope_deg, 0.01)
        mrt = (1.77 * self.length * np.sqrt(theta)) / denom
        return mrt

    def get_solid_velocity_mps(self) -> float:
        """
        Calcula la velocidad lineal de avance del sólido a lo largo del reactor en m/s.
        Derivado de dividir la longitud total entre el tiempo de residencia en segundos.
        """
        mrt_seconds = self.get_residence_time_min() * 60.0
        return self.length / mrt_seconds

    def get_wall_temp_K(self, z: float) -> float:
        """
        Calcula la temperatura local de la pared del reactor (Kelvin) en la posición axial z (metros).
        Soporta perfiles uniformes, gradientes lineales y perfiles discretos de 3 zonas.
        """
        z_frac = np.clip(z / self.length, 0.0, 1.0) # Fracción de la longitud recorrida (0 a 1)
        
        if self.T_wall_type == 'uniform':
            # Temperatura uniforme a lo largo del reactor
            T_C = self.T_wall_params.get('T_wall', 550.0)
            return T_C + 273.15
        elif self.T_wall_type == 'linear':
            # Gradiente lineal entre la entrada y la salida
            T_in = self.T_wall_params.get('T_wall_in', 300.0)
            T_out = self.T_wall_params.get('T_wall_out', 600.0)
            T_C = T_in + z_frac * (T_out - T_in)
            return T_C + 273.15
        elif self.T_wall_type == 'zones':
            # Interpolación suave entre 3 zonas de calentamiento parametrizadas
            zones = self.T_wall_params.get('zones', [(0.3, 350.0), (0.7, 550.0), (1.0, 500.0)])
            points = [(0.0, zones[0][1])] + list(zones)
            points = sorted(points, key=lambda x: x[0])
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            T_C = np.interp(z_frac, xs, ys)
            return T_C + 273.15
            
        return 550.0 + 273.15

    def simulate(self, steps: int = 500) -> dict:
        """
        Ejecuta la integración numérica espacial 1D a lo largo de la longitud del reactor.
        Resuelve los balances simultáneos de masa (secado y reacción química) y calor.
        """
        dz = self.length / steps                  # Tamaño de paso de discretización espacial (m)
        v_s = self.get_solid_velocity_mps()      # Velocidad de avance de los sólidos (m/s)
        
        # Flujo de alimentación total en la entrada (kg/s)
        F_inlet = (self.feed_rate_kgh) / 3600.0
        fracs = self.feedstock.get_fractions()    # Fracciones de humedad, volátiles, carbón y cenizas
        
        # Inicializa los flujos másicos locales de sólidos en la entrada (kg/s)
        m_moist = F_inlet * fracs['moisture']
        m_volatile = F_inlet * fracs['volatile']
        m_char = F_inlet * fracs['fixed_carbon']
        m_ash = F_inlet * fracs['ash']
        T_s = self.T_inlet                        # Temperatura inicial de sólidos (K)
        
        # Inicializa las corrientes gaseosas en la entrada del reactor (kg/s)
        m_steam = 0.0
        m_oil_vap = 0.0
        m_gas_vap = 0.0
        T_g = self.T_inlet                        # Temperatura inicial de la fase gas (K)
        
        # Listas vacías para almacenar los perfiles axiales
        z_arr, moist_arr, volatile_arr, char_arr, ash_arr = [], [], [], [], []
        temp_s_arr, temp_g_arr, temp_w_arr = [], [], []
        oil_arr, gas_arr, steam_arr, conv_arr = [], [], [], []
        humidity_arr = []
        
        T_boil = 373.15                           # Punto de ebullición del agua en Kelvin (100 °C)
        initial_volatile = max(m_volatile, 1e-10) # Referencia para calcular la conversión
        h_wg = 15.0                               # Coeficiente de transferencia pared-gas (W/m²·K)
        f_bed = 0.1                               # Fracción de volumen ocupada por la cama
        
        # Bucle de integración a lo largo del reactor (paso por paso)
        for i in range(steps + 1):
            z = i * dz
            z_arr.append(z)
            
            # Guarda los flujos másicos actuales (convertidos de kg/s a kg/h)
            moist_arr.append(m_moist * 3600)  
            volatile_arr.append(m_volatile * 3600)  
            char_arr.append(m_char * 3600)  
            ash_arr.append(m_ash * 3600)  
            temp_s_arr.append(T_s - 273.15)       # Convierte sólidos a °C
            temp_g_arr.append(T_g - 273.15)       # Convierte gases a °C
            temp_w_arr.append(self.get_wall_temp_K(z) - 273.15) # Convierte pared a °C
            oil_arr.append(m_oil_vap * 3600)  
            gas_arr.append(m_gas_vap * 3600)  
            steam_arr.append(m_steam * 3600)  
            
            # Calcula la conversión de materia volátil reaccionada (0 a 1)
            conversion = 1.0 - (m_volatile / initial_volatile)
            conv_arr.append(conversion)
            
            # Registra la humedad actual del lecho en base húmeda
            m_sol_tot = m_moist + m_volatile + m_char + m_ash
            humidity_pct = self.calculate_humidity_pct(m_moist, m_sol_tot)
            humidity_arr.append(humidity_pct)
            
            # Termina si se alcanzó el extremo de salida del reactor
            if i == steps:
                break
                
            # --- 1. Propiedades Termodinámicas Locales del Lecho ---
            T_w = self.get_wall_temp_K(z)
            m_solid_total = m_moist + m_volatile + m_char + m_ash
            
            # Capacidad calorífica ponderada del lecho sólido (Cp_s)
            Cp_s = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            
            # Capacidad calorífica ponderada de la corriente de gases (Cp_g)
            m_gas_total = m_steam + m_oil_vap + m_gas_vap
            Cp_g = self.calculate_Cp_gas(m_steam, m_oil_vap, m_gas_vap, m_gas_total)

            # --- 2. Velocidad de Transferencia de Calor por Convección ---
            denom_temp = m_solid_total * Cp_s
            if denom_temp > 1e-8:
                beta = (self.h_eff * np.pi * self.diameter) / denom_temp
            else:
                beta = 0.0
            
            # --- 3. Reacción Química y Cinética de Pirólisis (Primer Orden) ---
            # Calcula las constantes y tasas de reacción locales
            k1, k2, k3, r_slug, r_medios, r_gases = self.calculate_first_order_kinetics(T_s, m_volatile, m_oil_vap)
            
            # Pasos de tiempo locales
            dt_solid = dz / v_s
            tau_gas = 2.0  # Tiempo de residencia de gases en el reactor caliente (segundos)
            dt_gas = (dz / self.length) * tau_gas
            
            # Capa la reacción del lodo para no consumir más de lo disponible en el paso dz (tiempo dt_solid)
            max_r_slug = m_volatile / dt_solid
            if r_slug > max_r_slug:
                scale = max_r_slug / r_slug
                k1_eff = k1 * scale
                k2_eff = k2 * scale
                r_slug = max_r_slug
            else:
                k1_eff = k1
                k2_eff = k2
                
            d_volatile = r_slug * dt_solid
            d_oil_primary = k1_eff * m_volatile * dt_solid
            d_gas_primary = k2_eff * m_volatile * dt_solid
            
            # Craqueo secundario de los vapores de bio-oil acumulados a lo largo del paso espacial
            d_oil_cracked = m_oil_vap * k3 * dt_gas
            max_d_oil_cracked = m_oil_vap + d_oil_primary
            d_oil_cracked = min(d_oil_cracked, max_d_oil_cracked)
            
            d_oil_prod = d_oil_primary - d_oil_cracked
            d_gas_prod = d_gas_primary + d_oil_cracked
            
            # Char no se produce directamente a partir de volátiles en esta cinética de 3 especies
            d_char_prod = 0.0
            
            # Calor absorbido por la reacción endotérmica (J/s)
            q_pyro = r_slug * self.dH_pyro

            # --- 4. Integración del Perfil de Temperaturas de Sólidos ---
            # Calor transferido desde la pared exterior al lecho
            if beta > 0:
                T_target_heat = T_w - (T_w - T_s) * np.exp(-beta * dz)
            else:
                T_target_heat = T_s
                
            q_net_step = m_solid_total * Cp_s * v_s * (T_target_heat - T_s) / dz
            # Pérdida térmica por el efecto endotérmico de la pirólisis
            dT_reaction = - (q_pyro * dz) / (m_solid_total * Cp_s) if denom_temp > 1e-8 else 0.0
            T_s_next = T_target_heat + dT_reaction
            
            d_moist = 0.0
            
            # --- 5. Lógica de Secado y Bloqueo por Ebullición de Agua (100 °C) ---
            if m_moist > 1e-8:
                if T_s >= T_boil or T_s_next > T_boil:
                    # Energía requerida para calentar el lecho hasta la temperatura de ebullición
                    if T_s < T_boil:
                        H_preheat = m_solid_total * Cp_s * (T_boil - T_s)
                    else:
                        H_preheat = 0.0
                        
                    H_input = m_solid_total * Cp_s * (T_target_heat - T_s)
                    H_rxn = q_pyro * (dz / v_s)
                    # Energía neta disponible dedicada a la evaporación del agua
                    H_avail_evap = H_input - H_preheat - H_rxn
                    
                    if H_avail_evap > 0:
                        max_d_moist = m_moist
                        # Cantidad de agua evaporada en este paso
                        d_moist = H_avail_evap / self.dH_evap
                        d_moist = min(d_moist, max_d_moist)
                        
                        H_used_evap = d_moist * self.dH_evap
                        H_remain = H_avail_evap - H_used_evap
                        
                        T_s = T_boil # Forzado a 100 °C
                        # Si toda la humedad se evapora, la energía restante continúa calentando el sólido
                        if H_remain > 0:
                            dT_post_evap = H_remain / (m_solid_total * Cp_s)
                            T_s += dT_post_evap
                    else:
                        T_s = T_s_next
                else:
                    T_s = T_s_next
            else:
                T_s = T_s_next
                
            # --- 6. Actualización de las Corrientes Másicas ---
            m_moist = max(m_moist - d_moist, 0.0)
            m_volatile = max(m_volatile - d_volatile, 0.0)
            m_char = m_char + d_char_prod
            
            # Acumula los gases generados que viajan concurrentemente
            m_steam += d_moist
            m_oil_vap += d_oil_prod
            m_gas_vap += d_gas_prod
            
            # --- 7. Integración de la Temperatura del Gas ---
            # Calor transferido desde la pared al espacio gaseoso
            q_gas_wall = h_wg * np.pi * self.diameter * (1.0 - f_bed) * (T_w - T_g)
            # Calor intercambiado por los vapores calientes que emergen del lecho sólido
            Cp_mix = (d_moist * self.Cp_steam + 
                      d_oil_prod * self.Cp_oil_vap + 
                      d_gas_prod * self.Cp_pyro_gas) / (dz / v_s) if d_moist + d_oil_prod + d_gas_prod > 0 else 0
            q_gas_mix = Cp_mix * (T_s - T_g)
            
            if m_gas_total > 1e-6:
                dT_g = (q_gas_wall + q_gas_mix) * dz / (m_gas_total * Cp_g)
                T_g += dT_g
            else:
                T_g = T_s

        # ==============================================================================
        # CÁLCULOS METRICOS FINALES (Balance de Materia y Energía en la Salida)
        # ==============================================================================
        F_inlet_kgh = self.feed_rate_kgh
        F_dry_inlet_kgh = F_inlet_kgh * (1.0 - fracs['moisture'])
        
        # Rendimientos másicos de salida en kg/h
        final_char_kgh = (m_char + m_ash + m_volatile) * 3600
        final_oil_kgh = m_oil_vap * 3600
        final_gas_kgh = m_gas_vap * 3600
        final_steam_kgh = m_steam * 3600
        
        # Cierre y error porcentual del balance de masa total
        total_out_kgh = (m_char + m_ash + m_volatile + m_oil_vap + m_gas_vap + m_steam + m_moist) * 3600
        mass_error_pct = abs(total_out_kgh - F_inlet_kgh) / F_inlet_kgh * 100.0 if F_inlet_kgh > 0 else 0.0

        # --- Grado de Llenado Dinámico (Filling Degree) ---
        reactor_vol = np.pi * (self.diameter / 2)**2 * self.length
        vol_feed_m3h = (F_inlet) * 3600.0 / self.bulk_density
        v_s_miph = v_s * 3600.0
        cross_area_bed = vol_feed_m3h / v_s_miph
        cross_area_kiln = np.pi * (self.diameter / 2)**2
        filling_degree_pct = (cross_area_bed / cross_area_kiln) * 100.0
        
        # --- Balance de Energía Integrado (kW térmicos) ---
        F_char_s = final_char_kgh / 3600.0
        F_oil_s = final_oil_kgh / 3600.0
        F_gas_s = final_gas_kgh / 3600.0
        F_steam_s = final_steam_kgh / 3600.0
        T_in = temp_s_arr[0]
        T_out = temp_s_arr[-1]
        T_gas_out = temp_g_arr[-1]
        
        # Potencia requerida para calentar los sólidos secos
        Q_char = F_char_s * self.Cp_char * (T_out - T_in)
        # Potencia requerida para calentar los volátiles y sostener la pirólisis endotérmica
        Q_pyro = (F_oil_s + F_gas_s) * (self.Cp_volatile * (T_out - T_in) + self.dH_pyro)
        # Potencia consumida para calentar el agua líquida, vaporizarla y sobrecalentar el vapor
        if T_in < 100.0:
            Q_steam = F_steam_s * (self.Cp_moist * (100.0 - T_in) + self.dH_evap + self.Cp_steam * (max(T_gas_out, 100.0) - 100.0))
        else:
            Q_steam = F_steam_s * (self.dH_evap + self.Cp_steam * (max(T_gas_out, T_in) - T_in))
            
        total_heat_kw = (Q_char + Q_pyro + Q_steam) / 1000.0
        
        # Calcular el poder calorífico y densidad del combustible
        x_comb = max(0.0, 1.0 - (self.fuel_moisture_pct / 100.0) - (self.fuel_ash_pct / 100.0))
        LHV_fuel_j_kg = max(1e6, (self.fuel_lhv_mj_kg * 1e6) * x_comb - 2256000.0 * (self.fuel_moisture_pct / 100.0))
        fuel_mass_per_gal = self.fuel_density_kg_l * 3.78541
        LHV_oil_gal = LHV_fuel_j_kg * fuel_mass_per_gal
        LHV_syngas = 12e6  # 12 MJ/kg para el syngas
        burner_eff = self.burner_eff_pct / 100.0
        Q_transferred = total_heat_kw * 1000.0
        
        Q_main_capacity = self.burner_hp * 745.7 * burner_eff
        
        # Flujo de producción de syngas en kg/s
        r_gas_prod = final_gas_kgh / 3600.0
        T_gas_out_K = (temp_g_arr[-1] if len(temp_g_arr) > 0 else 550.0) + 273.15
        # Calor de combustión más calor sensible del syngas caliente
        Q_syngas_available_thermal = r_gas_prod * (LHV_syngas + self.Cp_pyro_gas * (T_gas_out_K - 298.15)) * burner_eff
        
        # El syngas desplaza el uso de aceite residual en el balance térmico continuo
        Q_main_used = max(0.0, Q_transferred - Q_syngas_available_thermal)
        Q_main_used = min(Q_main_used, Q_main_capacity)
        
        Q_main_combustion = Q_main_used / burner_eff if burner_eff > 0.0 else 0.0
        fuel_consumption_gal_h = (Q_main_combustion * 3600.0) / LHV_oil_gal
        
        # Empaqueta y devuelve la estructura final de resultados
        results = {
            'z': z_arr,
            'moisture': moist_arr,
            'volatile': volatile_arr,
            'char': char_arr,
            'ash': ash_arr,
            'T_solid': temp_s_arr,
            'T_gas': temp_g_arr,
            'T_wall': temp_w_arr,
            'oil': oil_arr,
            'gas': gas_arr,
            'steam': steam_arr,
            'conversion': conv_arr,
            'humidity': humidity_arr,
            'summary': {
                'feed_rate_kgh': F_inlet_kgh,
                'dry_feed_rate_kgh': F_dry_inlet_kgh,
                'oil_yield_kgh': final_oil_kgh,
                'gas_yield_kgh': final_gas_kgh,
                'char_yield_kgh': final_char_kgh,
                'water_yield_kgh': final_steam_kgh,
                'oil_yield_pct': (final_oil_kgh / F_inlet_kgh) * 100.0 if F_inlet_kgh > 0 else 0,
                'gas_yield_pct': (final_gas_kgh / F_inlet_kgh) * 100.0 if F_inlet_kgh > 0 else 0,
                'char_yield_pct': (final_char_kgh / F_inlet_kgh) * 100.0 if F_inlet_kgh > 0 else 0,
                'water_yield_pct': (final_steam_kgh / F_inlet_kgh) * 100.0 if F_inlet_kgh > 0 else 0,
                'oil_yield_pct_dry': (final_oil_kgh / F_dry_inlet_kgh) * 100.0 if F_dry_inlet_kgh > 0 else 0,
                'gas_yield_pct_dry': (final_gas_kgh / F_dry_inlet_kgh) * 100.0 if F_dry_inlet_kgh > 0 else 0,
                'char_yield_pct_dry': ((final_char_kgh - (F_inlet_kgh * fracs['fixed_carbon'] + F_inlet_kgh * fracs['ash'])) / F_dry_inlet_kgh) * 100.0 if F_dry_inlet_kgh > 0 else 0,
                'conversion_pct': conv_arr[-1] * 100.0,
                'residence_time_min': self.get_residence_time_min(),
                'filling_degree_pct': filling_degree_pct,
                'heating_duty_kw': total_heat_kw,
                'waste_oil_consumed_galh': fuel_consumption_gal_h,
                'mass_error_pct': mass_error_pct,
                'inlet_humidity_pct': humidity_arr[0],
                'outlet_humidity_pct': humidity_arr[-1]
            }
        }
        return results
