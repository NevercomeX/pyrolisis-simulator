"""
Batch Rotary Pyrolysis Reactor Simulation Module.

Implements transient time-dependent integration of mass and energy balances,
kiln wall thermal inertia, manifold autogenous pressure dynamics, and drying.
"""

from typing import Dict, Any, Optional
import numpy as np
from ..feedstock import Feedstock
from .base import BaseReactorSimulation


class BatchReactorSimulation(BaseReactorSimulation):
    """
    Simulation model for a batch rotary pyrolysis reactor (transient time-domain).
    Inherits thermodynamic, kinetic, and combustion models from BaseReactorSimulation.
    """
    def __init__(
        self,
        feedstock: Feedstock,
        batch_load_kg: float,
        length: float,
        diameter: float,
        rpm: float,
        T_start_C: float,
        heating_rate_cmin: float,
        T_hold_C: float,
        hold_time_min: float,
        h_eff: float = 80.0,
        auto_heating_rate: bool = False,
        burner_hp: float = 300.0,
        burner_eff_pct: float = 70.0,
        syngas_hp: float = 150.0,
        shell_material_dict: Optional[Dict[str, float]] = None,
        shell_thickness_mm: float = 15.0,
        h_loss: float = 5.0,
        bulk_density: float = 944.7,
        Cp_volatile: float = 1800.0,
        Cp_char: float = 1000.0,
        Cp_ash: float = 800.0,
        fuel_lhv_mj_kg: float = 41.0,
        fuel_density_kg_l: float = 0.90,
        fuel_moisture_pct: float = 1.0,
        fuel_ash_pct: float = 0.5,
    ) -> None:
        """
        Initializes batch reactor configuration, thermal program, and shell geometry.
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
        self.batch_load_kg = float(batch_load_kg)
        self.T_start = float(T_start_C) + 273.15
        self.heating_rate_cmin = float(heating_rate_cmin)
        self.heating_rate_csec = float(heating_rate_cmin) / 60.0
        self.T_hold = float(T_hold_C) + 273.15
        self.hold_time_min = float(hold_time_min)
        self.auto_heating_rate = bool(auto_heating_rate)

        self.shell_material_dict = shell_material_dict or {'density': 7850.0, 'Cp': 480.0, 'k': 50.0}
        self.shell_thickness_mm = float(shell_thickness_mm)
        self.h_loss = float(h_loss)

    def get_filling_degree_pct(self) -> float:
        """
        Calculates initial static volumetric filling degree (%).
        Fraction of reactor cylinder occupied by solid sludge bed.
        """
        vol_sludge = self.batch_load_kg / self.bulk_density
        return (vol_sludge / max(self.reactor_volume, 1e-6)) * 100.0

    def get_wall_temp_K(self, t_sec: float) -> float:
        """
        Calculates programmed wall temperature (K) at time t_sec under manual ramp mode.
        """
        dT = self.T_hold - self.T_start
        t_ramp = dT / self.heating_rate_csec if self.heating_rate_csec > 0 else 0.0

        if t_sec <= t_ramp:
            return self.T_start + self.heating_rate_csec * t_sec
        return self.T_hold

    def _get_shell_properties(self) -> tuple[float, float]:
        """Calculates shell outer area (m²) and steel thermal capacitance (J/K)."""
        t_steel = self.shell_thickness_mm / 1000.0
        rho_steel = self.shell_material_dict.get('density', 7850.0)
        cp_steel = self.shell_material_dict.get('Cp', 480.0)

        m_steel = np.pi * self.diameter * self.length * t_steel * rho_steel
        c_steel = m_steel * cp_steel

        d_outer = self.diameter + 2.0 * t_steel
        a_outer = np.pi * d_outer * self.length
        return a_outer, c_steel

    def simulate(self, dt_sec: float = 2.0) -> Dict[str, Any]:
        """
        Executes dynamic transient numerical integration in time.
        Simulates solid bed mass loss, devolatilization, and thermal trajectories.
        """
        # 1. Shell thermal inertia and fuel calibration
        a_outer, c_steel = self._get_shell_properties()
        lhv_fuel_j_kg, fuel_mass_per_gal, _ = self.get_fuel_properties()

        # 2. Initial mass inventory
        fracs = self.feedstock.get_fractions()
        m_moist = self.batch_load_kg * fracs['moisture']
        m_volatile = self.batch_load_kg * fracs['volatile']
        m_char = self.batch_load_kg * fracs['fixed_carbon']
        m_ash = self.batch_load_kg * fracs['ash']
        m_solid_total = m_moist + m_volatile + m_char + m_ash

        # Nominal duration estimation
        dT = self.T_hold - self.T_start
        if self.auto_heating_rate:
            q_main_nominal = self.burner_nominal_power_watts
            cp_s_init = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            c_total_init = c_steel + (m_solid_total * cp_s_init)
            nominal_rate_csec = q_main_nominal / c_total_init if c_total_init > 0 else 0.1
            t_ramp_sec = dT / nominal_rate_csec if nominal_rate_csec > 0 else 1000.0
        else:
            t_ramp_sec = dT / self.heating_rate_csec if self.heating_rate_csec > 0 else 0.0

        eta_fill = self.get_filling_degree_pct() / 100.0
        a_heat_est = np.pi * self.diameter * self.length * max(0.05, eta_fill)
        q_dry_est = self.h_eff * a_heat_est * 150.0
        t_dry_est_sec = (m_moist * self.dH_evap) / max(q_dry_est, 1.0) if m_moist > 0 else 0.0

        q_pyro_est = self.h_eff * a_heat_est * 100.0
        t_pyro_est_sec = (m_volatile * self.dH_pyro) / max(q_pyro_est, 1.0) if m_volatile > 0 else 0.0

        t_total_sec = max(
            t_ramp_sec + self.hold_time_min * 60.0,
            t_dry_est_sec + t_pyro_est_sec + self.hold_time_min * 60.0
        )
        steps = int(t_total_sec / dt_sec)

        T_s = self.T_start
        T_w = self.T_start

        # Cumulative gas release streams (kg)
        m_steam = 0.0
        m_oil_vap = 0.0
        m_gas_vap = 0.0
        m_waste_oil_gal = 0.0

        # Output time series
        time_arr, moist_arr, volatile_arr, char_arr, ash_arr = [], [], [], [], []
        temp_s_arr, temp_w_arr = [], []
        oil_arr, gas_arr, steam_arr, conv_arr = [], [], [], []
        humidity_arr = []
        waste_oil_arr = []
        p_oil_arr, p_syngas_arr = [], []

        # Manifold and autogenous pressure dynamics
        pressure_kpa_arr, pressure_psig_arr = [], []
        v_main_arr, v_branch_arr, air_disp_arr = [], [], []

        v_sludge_m3 = self.batch_load_kg / max(self.bulk_density, 100.0)
        v_headspace_init_m3 = max(0.1, self.reactor_volume - v_sludge_m3)

        d_main_m = 8.0 * 0.0254       # 8-inch main exhaust duct (m)
        d_branch_m = 4.0 * 0.0254     # 4-inch manifold branch (m)
        a_main = np.pi * (d_main_m / 2.0)**2
        a_branches = 4.0 * np.pi * (d_branch_m / 2.0)**2

        initial_volatile = max(m_volatile, 1e-10)
        A_heat = np.pi * self.diameter * self.length * max(0.05, eta_fill)
        total_energy_kwh = 0.0

        for step in range(steps + 1):
            t_sec = step * dt_sec
            t_min = t_sec / 60.0

            time_arr.append(t_min)
            moist_arr.append(m_moist)
            volatile_arr.append(m_volatile)
            char_arr.append(m_char)
            ash_arr.append(m_ash)
            temp_s_arr.append(T_s - 273.15)
            temp_w_arr.append(T_w - 273.15)
            oil_arr.append(m_oil_vap)
            gas_arr.append(m_gas_vap)
            steam_arr.append(m_steam)
            waste_oil_arr.append(m_waste_oil_gal)

            conversion = 1.0 - (m_volatile / initial_volatile)
            conv_arr.append(conversion)

            m_sol_tot = m_moist + m_volatile + m_char + m_ash
            humidity_arr.append(self.calculate_humidity_pct(m_moist, m_sol_tot))

            if t_sec >= t_total_sec:
                p_oil_arr.append(p_oil_arr[-1] if p_oil_arr else 0.0)
                p_syngas_arr.append(p_syngas_arr[-1] if p_syngas_arr else 0.0)
                pressure_kpa_arr.append(pressure_kpa_arr[-1] if pressure_kpa_arr else 101.325)
                pressure_psig_arr.append(pressure_psig_arr[-1] if pressure_psig_arr else 0.0)
                v_main_arr.append(v_main_arr[-1] if v_main_arr else 0.0)
                v_branch_arr.append(v_branch_arr[-1] if v_branch_arr else 0.0)
                air_disp_arr.append(air_disp_arr[-1] if air_disp_arr else 0.0)
                break

            # 1. Solid bed thermal mass
            m_solid_total = m_moist + m_volatile + m_char + m_ash
            Cp_s = self.calculate_Cp_solid(m_moist, m_volatile, m_char, m_ash, m_solid_total)
            denom_temp = m_solid_total * Cp_s
            beta = (self.h_eff * A_heat) / denom_temp if denom_temp > 1e-8 else 0.0

            # 2. Chemical reaction step (multicomponent devolatilization & cracking)
            r_slug, k1, k2, k3 = self.calculate_devolatilization_rate(
                T_s=T_s,
                T_w=T_w,
                m_volatile=m_volatile,
                m_oil_vap=m_oil_vap,
                A_contact=A_heat
            )
            d_volatile = min(r_slug * dt_sec, m_volatile)
            d_oil_prod, d_gas_prod, d_char_prod, H_rxn = self.split_reaction_products(
                d_volatile=d_volatile,
                k1=k1,
                k2=k2,
                k3=k3,
                tau_gas=2.0
            )

            # 3. Solid sensible heat integration
            T_target_heat = T_w - (T_w - T_s) * np.exp(-beta * dt_sec) if beta > 0 else T_s
            dT_input = T_target_heat - T_s
            dT_endothermic = (H_rxn / denom_temp) if denom_temp > 1e-8 else 0.0
            dT_net = max(0.02 * dT_input, dT_input - dT_endothermic)
            T_s_next = T_s + dT_net

            # 4. Reactor shell & burner heat balance
            q_main_nominal = self.burner_nominal_power_watts
            r_syngas_prod = d_gas_prod / dt_sec if dt_sec > 0.0 else 0.0
            q_syngas_thermal = r_syngas_prod * 12e6 * self.burner_efficiency

            q_needed_wall = max(0.0, (T_w - T_s) * self.h_eff * A_heat)
            q_main_used = min(max(0.0, q_needed_wall - q_syngas_thermal), q_main_nominal)

            if self.auto_heating_rate:
                q_loss = self.h_loss * a_outer * (T_w - self.T_start)
                q_net_wall = (q_main_used + q_syngas_thermal) - q_needed_wall - q_loss
                dT_w = (q_net_wall * dt_sec) / c_steel if c_steel > 0 else 0.0
                T_w_next = min(T_w + dT_w, self.T_hold)
            else:
                T_w_nominal = self.get_wall_temp_K(t_sec + dt_sec)
                T_w_next = min(T_w_nominal, T_s + 250.0) if m_moist > 1.0 else T_w_nominal

            q_combustion = q_main_used / self.burner_efficiency if self.burner_efficiency > 0 else 0.0
            dm_waste_oil_kg = (q_combustion * dt_sec) / lhv_fuel_j_kg
            m_waste_oil_gal += dm_waste_oil_kg / fuel_mass_per_gal
            total_energy_kwh += (q_needed_wall * dt_sec) / 3.6e6

            # 5. Drying and water evaporation resolution
            T_s, d_moist = self.resolve_drying_step(
                T_s=T_s,
                T_s_next=T_s_next,
                T_target_heat=T_target_heat,
                m_moist=m_moist,
                thermal_mass=denom_temp,
                H_rxn=H_rxn
            )

            # 6. Mass balance updates
            m_moist = max(m_moist - d_moist, 0.0)
            m_volatile = max(m_volatile - d_volatile, 0.0)
            m_char += d_char_prod

            m_steam += d_moist
            m_oil_vap += d_oil_prod
            m_gas_vap += d_gas_prod

            # 7. Autogenous venting and piping backpressure dynamics
            w_vap_gen = (d_moist + d_oil_prod + d_gas_prod) / dt_sec if dt_sec > 0 else 0.0
            T_gas_k = max(T_s, 298.15)
            w_total = max(1e-8, d_moist + d_oil_prod + d_gas_prod)
            w_h2o_f = d_moist / w_total if w_vap_gen > 0 else 0.5
            w_oil_f = d_oil_prod / w_total if w_vap_gen > 0 else 0.3
            w_gas_f = max(0.0, 1.0 - w_h2o_f - w_oil_f)

            mw_mix = max(18.0, min(120.0, w_h2o_f * 18.0 + w_oil_f * 120.0 + w_gas_f * 28.0))
            rho_gas_t = (101325.0 * (mw_mix / 1000.0)) / (self.R * T_gas_k)
            q_gas_gen_m3s = w_vap_gen / max(1e-4, rho_gas_t)

            v_main_ms = q_gas_gen_m3s / a_main if a_main > 0 else 0.0
            v_branch_ms = q_gas_gen_m3s / a_branches if a_branches > 0 else 0.0
            air_disp_m3 = min(v_headspace_init_m3, (m_steam + m_oil_vap + m_gas_vap) / max(1e-4, rho_gas_t))

            delta_p_pa = 0.025 * (10.0 / d_main_m) * (0.5 * rho_gas_t * v_main_ms**2) + (1.5 * 0.5 * rho_gas_t * v_main_ms**2)
            p_abs_kpa = (101325.0 + delta_p_pa) / 1000.0
            p_gauge_psig = delta_p_pa / 6894.76

            v_main_arr.append(v_main_ms)
            v_branch_arr.append(v_branch_ms)
            air_disp_arr.append(air_disp_m3)
            pressure_kpa_arr.append(p_abs_kpa)
            pressure_psig_arr.append(p_gauge_psig)

            T_w = T_w_next

        # -------------------------------------------------------------------------
        # Final Operation Yields and Quality Balances
        # -------------------------------------------------------------------------
        final_char_kg = m_char + m_ash + m_volatile
        final_oil_kg = m_oil_vap
        final_gas_kg = m_gas_vap
        final_steam_kg = m_steam

        total_out_kg = final_char_kg + final_oil_kg + final_gas_kg + final_steam_kg + m_moist
        mass_error_pct = self.calculate_mass_balance_error(total_out_kg, self.batch_load_kg)

        initial_vol_pct = (initial_volatile / self.batch_load_kg * 100.0) if self.batch_load_kg > 0 else 50.0
        feed_moist_pct = humidity_arr[0] if humidity_arr else 30.0
        astm = self.calculate_astm_properties(
            T_operating_C=self.T_hold - 273.15,
            initial_volatile_pct=initial_vol_pct,
            moisture_feed_pct=feed_moist_pct,
            bio_oil_density=getattr(self, 'bio_oil_density', 750.0)
        )

        syngas_recirc_pct, syngas_flare_kg, syngas_flare_m3 = self.calculate_syngas_balance(
            final_gas_kg=final_gas_kg,
            total_energy_kwh=total_energy_kwh
        )

        air_disp_complete_min = 0.0
        for idx_t, v_d in enumerate(air_disp_arr):
            if v_d >= v_headspace_init_m3 * 0.90:
                air_disp_complete_min = time_arr[idx_t]
                break
        if air_disp_complete_min == 0.0 and time_arr:
            air_disp_complete_min = time_arr[min(len(time_arr) - 1, 15)]

        return {
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
                'hhv_oil_mj_kg': astm['hhv_oil_mj_kg'],
                'hhv_oil_btu_lb': astm['hhv_oil_btu_lb'],
                'energy_enhancement_factor': astm['energy_enhancement_factor'],
                'viscosity_40c_cst': astm['viscosity_40c_cst'],
                'api_gravity': astm['api_gravity'],
                'bsw_moisture_pct': astm['bsw_moisture_pct'],
                'syngas_recirc_pct': syngas_recirc_pct,
                'syngas_flare_kg': syngas_flare_kg,
                'syngas_flare_m3': syngas_flare_m3,
            }
        }
