"""
Continuous Rotary Pyrolysis Reactor Simulation Module.

Implements 1D spatial numerical integration along reactor axis,
modeling continuous feed, drying, Sullivan residence time, and kinetics.
"""

from typing import Dict, Any, Optional
import numpy as np
from ..feedstock import Feedstock
from .base import BaseReactorSimulation


class ContinuousReactorSimulation(BaseReactorSimulation):
    """
    Simulation model for a continuous rotary kiln pyrolysis reactor (1D spatial domain).
    Inherits thermodynamic, kinetic, and combustion models from BaseReactorSimulation.
    """
    def __init__(
        self,
        feedstock: Feedstock,
        feed_rate_kgh: float,
        length: float,
        diameter: float,
        slope: float,
        rpm: float,
        T_inlet_C: float,
        h_eff: float = 80.0,
        T_wall_type: str = 'uniform',
        T_wall_params: Optional[Dict[str, Any]] = None,
        bulk_density: float = 944.7,
        Cp_volatile: float = 1800.0,
        Cp_char: float = 1000.0,
        Cp_ash: float = 800.0,
        burner_hp: float = 300.0,
        burner_eff_pct: float = 70.0,
        syngas_hp: float = 150.0,
        fuel_lhv_mj_kg: float = 41.0,
        fuel_density_kg_l: float = 0.90,
        fuel_moisture_pct: float = 1.0,
        fuel_ash_pct: float = 0.5,
    ) -> None:
        """
        Initializes continuous reactor operating conditions, geometry, and wall temperature profiles.
        """
        super().__init__(
            feedstock=feedstock,
            length=length,
            diameter=diameter,
            rpm=rpm,
            h_eff=h_eff,
            bulk_density=bulk_density,
            Cp_volatile=Cp_volatile,
            Cp_char=Cp_char,
            Cp_ash=Cp_ash,
            burner_hp=burner_hp,
            burner_eff_pct=burner_eff_pct,
            syngas_hp=syngas_hp,
            fuel_lhv_mj_kg=fuel_lhv_mj_kg,
            fuel_density_kg_l=fuel_density_kg_l,
            fuel_moisture_pct=fuel_moisture_pct,
            fuel_ash_pct=fuel_ash_pct,
        )
        self.feed_rate_kgh = float(feed_rate_kgh)
        self.slope = float(slope)
        self.T_inlet = float(T_inlet_C) + 273.15
        self.T_wall_type = T_wall_type

        if T_wall_params is None:
            if T_wall_type == 'uniform':
                self.T_wall_params = {'T_wall': 550.0}
            elif T_wall_type == 'linear':
                self.T_wall_params = {'T_wall_in': 300.0, 'T_wall_out': 600.0}
            else:  # zones
                self.T_wall_params = {'zones': [(0.3, 350.0), (0.7, 550.0), (1.0, 500.0)]}
        else:
            self.T_wall_params = T_wall_params

    def get_residence_time_min(self) -> float:
        """
        Calculates mean residence time (MRT) of solids in minutes
        using Sullivan's classic empirical correlation for rotary drums.
        """
        theta = self.feedstock.angle_of_repose
        slope_deg = np.arctan(self.slope) * 180.0 / np.pi
        denom = self.diameter * max(self.rpm, 0.01) * max(slope_deg, 0.01)
        return (1.77 * self.length * np.sqrt(theta)) / denom

    def get_solid_velocity_mps(self) -> float:
        """
        Calculates axial linear advancement velocity of solid bed in m/s.
        """
        mrt_seconds = self.get_residence_time_min() * 60.0
        return self.length / mrt_seconds

    def get_wall_temp_K(self, z: float) -> float:
        """
        Calculates local reactor wall temperature (K) at axial position z (meters).
        """
        z_frac = np.clip(z / self.length, 0.0, 1.0)

        if self.T_wall_type == 'uniform':
            T_C = self.T_wall_params.get('T_wall', 550.0)
        elif self.T_wall_type == 'linear':
            T_in = self.T_wall_params.get('T_wall_in', 300.0)
            T_out = self.T_wall_params.get('T_wall_out', 600.0)
            T_C = T_in + z_frac * (T_out - T_in)
        elif self.T_wall_type == 'zones':
            zones = self.T_wall_params.get('zones', [(0.3, 350.0), (0.7, 550.0), (1.0, 500.0)])
            points = sorted([(0.0, zones[0][1])] + list(zones), key=lambda x: x[0])
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            T_C = np.interp(z_frac, xs, ys)
        else:
            T_C = 550.0

        return T_C + 273.15

    def simulate(self, steps: int = 500) -> Dict[str, Any]:
        """
        Executes steady-state 1D spatial numerical integration along reactor axis.
        Resolves coupled mass balances (drying and pyrolysis) and heat exchange.
        """
        dz = self.length / steps
        v_s = self.get_solid_velocity_mps()
        dt_solid = dz / v_s
        tau_gas = 2.0
        dt_gas = (dz / self.length) * tau_gas

        F_inlet = self.feed_rate_kgh / 3600.0
        fracs = self.feedstock.get_fractions()

        # Initial inlet solid mass flows (kg/s)
        m_moist = F_inlet * fracs['moisture']
        m_volatile = F_inlet * fracs['volatile']
        m_char = F_inlet * fracs['fixed_carbon']
        m_ash = F_inlet * fracs['ash']
        T_s = self.T_inlet

        # Gas phase streams (kg/s)
        m_steam = 0.0
        m_oil_vap = 0.0
        m_gas_vap = 0.0
        T_g = self.T_inlet

        # Axial profile arrays
        z_arr, moist_arr, volatile_arr, char_arr, ash_arr = [], [], [], [], []
        temp_s_arr, temp_g_arr, temp_w_arr = [], [], []
        oil_arr, gas_arr, steam_arr, conv_arr = [], [], [], []
        humidity_arr = []

        initial_volatile = max(m_volatile, 1e-10)
        h_wg = 15.0      # Wall-to-gas heat transfer coefficient (W/m²·K)
        f_bed = 0.1     # Bed cross-sectional fraction

        for i in range(steps + 1):
            z = i * dz
            z_arr.append(z)

            # Record flows converted to kg/h
            moist_arr.append(m_moist * 3600.0)
            volatile_arr.append(m_volatile * 3600.0)
            char_arr.append(m_char * 3600.0)
            ash_arr.append(m_ash * 3600.0)
            temp_s_arr.append(T_s - 273.15)
            temp_g_arr.append(T_g - 273.15)
            temp_w_arr.append(self.get_wall_temp_K(z) - 273.15)
            oil_arr.append(m_oil_vap * 3600.0)
            gas_arr.append(m_gas_vap * 3600.0)
            steam_arr.append(m_steam * 3600.0)

            conversion = 1.0 - (m_volatile / initial_volatile)
            conv_arr.append(conversion)

            m_sol_tot = m_moist + m_volatile + m_char + m_ash
            humidity_arr.append(self.calculate_humidity_pct(m_moist, m_sol_tot))

            if i == steps:
                break

            # 1. Solid bed thermal properties
            T_w = self.get_wall_temp_K(z)
            m_solid_total = m_moist + m_volatile + m_char + m_ash
            Cp_s = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            m_gas_total = m_steam + m_oil_vap + m_gas_vap
            Cp_g = self.calculate_Cp_gas(m_steam, m_oil_vap, m_gas_vap, m_gas_total)

            denom_temp = m_solid_total * Cp_s
            beta = (self.h_eff * np.pi * self.diameter) / denom_temp if denom_temp > 1e-8 else 0.0

            # 2. Devolatilization and cracking kinetics
            A_step_contact = np.pi * self.diameter * dz * 0.15
            r_slug, k1, k2, k3 = self.calculate_devolatilization_rate(
                T_s=T_s,
                T_w=T_w,
                m_volatile=m_volatile,
                m_oil_vap=m_oil_vap,
                A_contact=A_step_contact
            )
            d_volatile = min(r_slug * dt_solid, m_volatile)
            d_oil_prod, d_gas_prod, d_char_prod, _ = self.split_reaction_products(
                d_volatile=d_volatile,
                k1=k1,
                k2=k2,
                k3=k3,
                tau_gas=tau_gas,
                dt_gas=dt_gas,
                m_oil_vap=m_oil_vap
            )
            q_pyro = r_slug * self.dH_pyro

            # 3. Solid bed temperature integration
            T_target_heat = T_w - (T_w - T_s) * np.exp(-beta * dz) if beta > 0 else T_s
            dT_reaction = - (q_pyro * dz) / denom_temp if denom_temp > 1e-8 else 0.0
            T_s_next = T_target_heat + dT_reaction

            # 4. Drying phase change balance (100°C plateau)
            T_s, d_moist = self.resolve_drying_step(
                T_s=T_s,
                T_s_next=T_s_next,
                T_target_heat=T_target_heat,
                m_moist=m_moist,
                thermal_mass=denom_temp,
                H_rxn=q_pyro * (dz / v_s)
            )

            # 5. Mass stream updates
            m_moist = max(m_moist - d_moist, 0.0)
            m_volatile = max(m_volatile - d_volatile, 0.0)
            m_char += d_char_prod

            m_steam += d_moist
            m_oil_vap += d_oil_prod
            m_gas_vap += d_gas_prod

            # 6. Gas temperature profile integration
            q_gas_wall = h_wg * np.pi * self.diameter * (1.0 - f_bed) * (T_w - T_g)
            Cp_mix = (
                d_moist * self.Cp_steam +
                d_oil_prod * self.Cp_oil_vap +
                d_gas_prod * self.Cp_pyro_gas
            ) / (dz / v_s) if (d_moist + d_oil_prod + d_gas_prod) > 0 else 0.0
            q_gas_mix = Cp_mix * (T_s - T_g)

            if m_gas_total > 1e-6:
                dT_g = (q_gas_wall + q_gas_mix) * dz / (m_gas_total * Cp_g)
                T_g += dT_g
            else:
                T_g = T_s

        # -------------------------------------------------------------------------
        # Final Steady-State Yields and Performance Summary
        # -------------------------------------------------------------------------
        F_inlet_kgh = self.feed_rate_kgh
        F_dry_inlet_kgh = F_inlet_kgh * (1.0 - fracs['moisture'])

        final_char_kgh = (m_char + m_ash + m_volatile) * 3600.0
        final_oil_kgh = m_oil_vap * 3600.0
        final_gas_kgh = m_gas_vap * 3600.0
        final_steam_kgh = m_steam * 3600.0

        total_out_kgh = (m_char + m_ash + m_volatile + m_oil_vap + m_gas_vap + m_steam + m_moist) * 3600.0
        mass_error_pct = self.calculate_mass_balance_error(total_out_kgh, F_inlet_kgh)

        # Dynamic filling degree
        vol_feed_m3h = F_inlet * 3600.0 / self.bulk_density
        v_s_miph = v_s * 3600.0
        cross_area_bed = vol_feed_m3h / v_s_miph
        filling_degree_pct = (cross_area_bed / self.cross_sectional_area) * 100.0

        # Heating duty integration (kW thermal)
        F_char_s = final_char_kgh / 3600.0
        F_oil_s = final_oil_kgh / 3600.0
        F_gas_s = final_gas_kgh / 3600.0
        F_steam_s = final_steam_kgh / 3600.0
        T_in = temp_s_arr[0]
        T_out = temp_s_arr[-1]
        T_gas_out = temp_g_arr[-1]

        Q_char = F_char_s * self.Cp_char * (T_out - T_in)
        Q_pyro = (F_oil_s + F_gas_s) * (self.Cp_volatile * (T_out - T_in) + self.dH_pyro)

        if T_in < 100.0:
            Q_steam = F_steam_s * (
                self.Cp_moist * (100.0 - T_in) +
                self.dH_evap +
                self.Cp_steam * (max(T_gas_out, 100.0) - 100.0)
            )
        else:
            Q_steam = F_steam_s * (self.dH_evap + self.Cp_steam * (max(T_gas_out, T_in) - T_in))

        total_heat_kw = (Q_char + Q_pyro + Q_steam) / 1000.0

        # Fuel and burner consumption
        lhv_fuel_j_kg, fuel_mass_per_gal, lhv_oil_gal = self.get_fuel_properties()
        Q_transferred = total_heat_kw * 1000.0
        Q_main_capacity = self.burner_nominal_power_watts

        r_gas_prod = final_gas_kgh / 3600.0
        T_gas_out_K = (temp_g_arr[-1] if len(temp_g_arr) > 0 else 550.0) + 273.15
        Q_syngas_available = r_gas_prod * (12e6 + self.Cp_pyro_gas * (T_gas_out_K - 298.15)) * self.burner_efficiency

        Q_main_used = min(max(0.0, Q_transferred - Q_syngas_available), Q_main_capacity)
        Q_combustion = Q_main_used / self.burner_efficiency if self.burner_efficiency > 0.0 else 0.0
        fuel_consumption_gal_h = (Q_combustion * 3600.0) / lhv_oil_gal

        return {
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
                'char_yield_pct_dry': (
                    (final_char_kgh - (F_inlet_kgh * fracs['fixed_carbon'] + F_inlet_kgh * fracs['ash'])) / F_dry_inlet_kgh
                ) * 100.0 if F_dry_inlet_kgh > 0 else 0,
                'conversion_pct': conv_arr[-1] * 100.0,
                'residence_time_min': self.get_residence_time_min(),
                'filling_degree_pct': filling_degree_pct,
                'heating_duty_kw': total_heat_kw,
                'waste_oil_consumed_galh': fuel_consumption_gal_h,
                'mass_error_pct': mass_error_pct,
                'inlet_humidity_pct': humidity_arr[0],
                'outlet_humidity_pct': humidity_arr[-1],
            }
        }
