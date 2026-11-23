"""
Base Simulation Module for Rotary Pyrolysis Reactor.

Encapsulates core physical geometry, thermodynamic constants, combustion
calculations, multicomponent kinetic reaction stepping, and phase-change drying.
"""

from typing import Dict, Tuple
import numpy as np
from ..feedstock import Feedstock

# 1 boiler horsepower (BHP) = 33,475 BTU/h of heat output (not 745.7 W, which is a mechanical hp)
BHP_TO_W = 33475.0 * 0.29307107
SYNGAS_LHV_J_KG = 12e6      # lower heating value assumed for the pyrolysis gas (J/kg)
GAS_RESIDENCE_S = 2.0       # vapour residence time in the hot zone, for secondary cracking (s)


class BaseReactorSimulation:
    """
    Base simulation class containing shared physical, thermodynamic constants,
    combustion parameters, kinetic resolutions, and drying thermodynamics.
    """
    def __init__(
        self,
        feedstock: Feedstock,
        length: float,
        diameter: float,
        rpm: float,
        h_eff: float,
        bulk_density: float = 944.7,
        Cp_volatile: float = 1800.0,
        Cp_char: float = 1000.0,
        Cp_ash: float = 800.0,
        burner_hp: float = 300.0,
        burner_eff_pct: float = 85.0,
        syngas_hp: float = 150.0,
        fuel_lhv_mj_kg: float = 41.0,
        fuel_density_kg_l: float = 0.90,
        fuel_moisture_pct: float = 1.0,
        fuel_ash_pct: float = 0.5,
    ) -> None:
        """
        Initializes common reactor geometry, thermal properties, and auxiliary burner parameters.
        """
        self.feedstock = feedstock
        self.length = float(length)
        self.diameter = float(diameter)
        self.rpm = float(rpm)
        self.h_eff = float(h_eff)
        self.bulk_density = float(bulk_density)

        # Thermal heat capacities (J/kg·K)
        self.Cp_volatile = float(Cp_volatile)
        self.Cp_char = float(Cp_char)
        self.Cp_ash = float(Cp_ash)
        self.Cp_moist = 4184.0          # Liquid water

        # Universal constants and reaction enthalpies
        self.R = 8.3144598              # Ideal gas constant (J/mol·K)
        self.dH_evap = 2256000.0        # Water vaporization enthalpy (J/kg)
        self.dH_pyro = 700000.0         # Pyrolysis reaction enthalpy (J/kg)
        self.T_boil = 373.15            # Water boiling point at 1 atm (K)

        # Auxiliary burner & fuel calibration
        self.burner_hp = float(burner_hp)
        self.burner_eff_pct = float(burner_eff_pct)
        self.syngas_hp = float(syngas_hp)
        self.fuel_lhv_mj_kg = float(fuel_lhv_mj_kg)
        self.fuel_density_kg_l = float(fuel_density_kg_l)
        self.fuel_moisture_pct = float(fuel_moisture_pct)
        self.fuel_ash_pct = float(fuel_ash_pct)

    # -------------------------------------------------------------------------
    # Geometric Properties
    # -------------------------------------------------------------------------
    @property
    def radius(self) -> float:
        """Internal radius of the reactor cylinder (m)."""
        return self.diameter / 2.0

    @property
    def cross_sectional_area(self) -> float:
        """Internal cross-sectional area of the reactor (m²)."""
        return np.pi * (self.radius ** 2)

    @property
    def inner_surface_area(self) -> float:
        """Internal circumferential wall area of the cylinder (m²)."""
        return np.pi * self.diameter * self.length

    @property
    def reactor_volume(self) -> float:
        """Total internal cylinder volume (m³)."""
        return self.cross_sectional_area * self.length

    # -------------------------------------------------------------------------
    # Fuel and Combustion Thermodynamics
    # -------------------------------------------------------------------------
    @property
    def burner_efficiency(self) -> float:
        """Burner thermal efficiency as a dimensionless fraction (0.0 to 1.0)."""
        return self.burner_eff_pct / 100.0

    @property
    def burner_nominal_power_watts(self) -> float:
        """Nominal burner thermal output power delivered (W). `burner_hp` is the nameplate rating in boiler
        horsepower (BHP), which is already a useful-heat output; efficiency only sets the fuel it burns."""
        return self.burner_hp * BHP_TO_W

    def get_fuel_properties(self) -> Tuple[float, float, float]:
        """
        Calculates effective fuel Lower Heating Value (J/kg), fuel mass per
        gallon (kg/gal), and volumetric LHV (J/gal) based on moisture and ash.

        Returns:
            (lhv_fuel_j_kg, fuel_mass_per_gal, lhv_oil_gal)
        """
        x_comb = max(0.0, 1.0 - (self.fuel_moisture_pct / 100.0) - (self.fuel_ash_pct / 100.0))
        lhv_fuel_j_kg = max(
            1e6,
            (self.fuel_lhv_mj_kg * 1e6) * x_comb - self.dH_evap * (self.fuel_moisture_pct / 100.0)
        )
        fuel_mass_per_gal = self.fuel_density_kg_l * 3.78541
        lhv_oil_gal = lhv_fuel_j_kg * fuel_mass_per_gal
        return lhv_fuel_j_kg, fuel_mass_per_gal, lhv_oil_gal

    # -------------------------------------------------------------------------
    # Thermodynamic Mixture Properties
    # -------------------------------------------------------------------------
    def calculate_Cp_solid(
        self,
        m_moist: float,
        m_volatile: float,
        m_char: float,
        m_ash: float,
        m_solid_total: float
    ) -> float:
        """Calculates solid bed heat capacity (J/kg·K)."""
        if m_solid_total <= 1e-8:
            return self.Cp_ash
        return (
            m_moist * self.Cp_moist +
            m_volatile * self.Cp_volatile +
            m_char * self.Cp_char +
            m_ash * self.Cp_ash
        ) / m_solid_total

    @staticmethod
    def calculate_humidity_pct(m_moist: float, m_solid_total: float) -> float:
        """Calculates wet-basis bed humidity (wt%)."""
        if m_solid_total <= 0.0:
            return 0.0
        return (m_moist / m_solid_total) * 100.0

    @staticmethod
    def calculate_mass_balance_error(total_out: float, total_in: float) -> float:
        """Calculates relative mass conservation percentage error (%)."""
        if total_in <= 0.0:
            return 0.0
        return abs(total_out - total_in) / total_in * 100.0

    # -------------------------------------------------------------------------
    # Kinetics & Devolatilization
    # -------------------------------------------------------------------------
    def calculate_first_order_kinetics(
        self,
        T_s: float,
        C_slug: float,
        C_medios: float
    ) -> Tuple[float, float, float, float, float, float]:
        """
        Calculates k1, k2, k3 rate constants (1/s) and rates of change (kg/s)
        based on the three-component first-order kinetics model.

        Returns:
            (k1, k2, k3, r_slug, r_medios, r_gases)
        """
        T_s = max(T_s, 200.0)

        A1 = getattr(self.feedstock, 'A1', self.feedstock.A * self.feedstock.yield_oil)
        Ea1 = getattr(self.feedstock, 'Ea1', self.feedstock.E_a)

        A2 = getattr(self.feedstock, 'A2', self.feedstock.A * (self.feedstock.yield_gas + self.feedstock.yield_char))
        Ea2 = getattr(self.feedstock, 'Ea2', self.feedstock.E_a)

        A3 = getattr(self.feedstock, 'A3', 5e5)
        Ea3 = getattr(self.feedstock, 'Ea3', 100000.0)

        T_onset_K = getattr(self.feedstock, 'T_onset_K', 370.0 + 273.15)
        if T_s < T_onset_K:
            k1 = 0.0
            k2 = 0.0
            k3 = 0.0
        else:
            k1 = A1 * np.exp(-Ea1 / (self.R * T_s))
            k2 = A2 * np.exp(-Ea2 / (self.R * T_s))
            k3 = A3 * np.exp(-Ea3 / (self.R * T_s))

        r_slug = (k1 + k2) * C_slug
        r_medios = k1 * C_slug - k3 * C_medios
        r_gases = k2 * C_slug + k3 * C_medios

        return k1, k2, k3, r_slug, r_medios, r_gases

    def calculate_devolatilization_rate(
        self,
        T_s: float,
        T_w: float,
        m_volatile: float,
        m_oil_vap: float,
        A_contact: float
    ) -> Tuple[float, float, float, float]:
        """
        Calculates the effective devolatilization rate (kg/s) accounting for
        multicomponent kinetics, pyrolysis range (370°C - 430°C), and available
        thermal heat flux.

        Returns:
            (r_slug, k1, k2, k3)
        """
        k1, k2, k3, r_slug, _, _ = self.calculate_first_order_kinetics(T_s, m_volatile, m_oil_vap)

        T_onset_K = getattr(self.feedstock, 'T_onset_K', 370.0 + 273.15)
        T_end_K = getattr(self.feedstock, 'T_end_K', 430.0 + 273.15)

        if T_s >= T_onset_K:
            f_distillable = min(1.0, max(0.05, (T_s - T_onset_K) / max(1.0, T_end_K - T_onset_K)))
            r_slug = r_slug * f_distillable

            Q_avail_heat = max(0.0, T_w - T_s) * self.h_eff * A_contact
            r_thermal_max = Q_avail_heat / self.dH_pyro if self.dH_pyro > 0.0 else r_slug
            r_slug = min(r_slug, r_thermal_max)
        else:
            r_slug = 0.0
            k1 = 0.0
            k2 = 0.0

        return r_slug, k1, k2, k3

    def split_reaction_products(
        self,
        d_volatile: float,
        k1: float,
        k2: float,
        k3: float,
        tau_gas: float = GAS_RESIDENCE_S
    ) ->Tuple[float, float, float, float]:
        """
        Splits reacted volatile mass into pyrolysis oil, non-condensable gas,
        and solid char, including secondary cracking of pyrolysis oil vapors.

        Returns:
            (d_oil_prod, d_gas_prod, d_char_prod, H_rxn)
        """
        k_sum = k1 + k2
        if k_sum > 0.0:
            frac_k1 = k1 / k_sum
            frac_k2 = k2 / k_sum
        else:
            frac_k1 = getattr(self.feedstock, 'yield_oil', 0.60)
            frac_k2 = 1.0 - frac_k1

        d_oil_primary = d_volatile * frac_k1
        d_non_oil = d_volatile * frac_k2

        y_gas = getattr(self.feedstock, 'yield_gas', 0.25)
        y_char = getattr(self.feedstock, 'yield_char', 0.15)
        y_non_oil = y_gas + y_char
        if y_non_oil > 0.0:
            frac_gas = y_gas / y_non_oil
            frac_char = y_char / y_non_oil
        else:
            frac_gas = 1.0
            frac_char = 0.0

        d_gas_primary = d_non_oil * frac_gas
        d_char_prod = d_non_oil * frac_char

        # Secondary cracking of the oil vapour during its residence time in the hot zone
        d_oil_cracked = d_oil_primary * (1.0 - np.exp(-k3 * tau_gas))

        d_oil_prod = d_oil_primary - d_oil_cracked
        d_gas_prod = d_gas_primary + d_oil_cracked
        H_rxn = d_volatile * self.dH_pyro

        return d_oil_prod, d_gas_prod, d_char_prod, H_rxn

    # -------------------------------------------------------------------------
    # Drying and Phase Change Thermodynamics
    # -------------------------------------------------------------------------
    def resolve_drying_step(
        self,
        T_s: float,
        T_s_next: float,
        T_target_heat: float,
        m_moist: float,
        thermal_mass: float,
        H_rxn: float
    ) -> Tuple[float, float]:
        """
        Resolves drying and phase-change temperature buffering around 100°C (373.15 K).

        Returns:
            (T_s_resolved, d_moist): resulting solid temperature and evaporated water mass.
        """
        reaches_boiling = T_s >= self.T_boil or T_s_next > self.T_boil
        if m_moist <= 1e-8 or not reaches_boiling:
            return T_s_next, 0.0

        # Heat left for evaporation after bringing the bed to 100 °C and feeding the reaction (J)
        H_preheat = thermal_mass * (self.T_boil - T_s) if T_s < self.T_boil else 0.0
        H_input = thermal_mass * (T_target_heat - T_s)
        H_avail_evap = H_input - H_preheat - H_rxn
        if H_avail_evap > 0.0:
            d_moist = min(m_moist, H_avail_evap / self.dH_evap)
            H_used_evap = d_moist * self.dH_evap
            H_remain = H_avail_evap - H_used_evap

            # The bed stays at 100 °C; only heat left after evaporating all the water raises it
            T_s_resolved = self.T_boil
            if H_remain > 0.0 and thermal_mass > 1e-8:
                T_s_resolved += H_remain / thermal_mass
            return T_s_resolved, d_moist
        return T_s_next, 0.0

    # -------------------------------------------------------------------------
    # Standard ASTM Fuel Characterization
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_astm_properties(
        T_operating_C: float,
        initial_volatile_pct: float,
        moisture_feed_pct: float,
        bio_oil_density: float = 750.0
    ) -> Dict[str, float]:
        """
        DESHABILITADO: las correlaciones anteriores (PCS, viscosidad, °API, BS&W)
        no tenían fuente bibliográfica ni respaldo experimental. Al compararlas con
        el informe de laboratorio (viscosidad medida 6.903 mm²/s vs 45 cSt
        "predichos") quedaron invalidadas. Estas propiedades deben obtenerse por
        ensayo (ASTM D240, D445, D4052, D95), no por el simulador.

        Returns:
            Diccionario con valores NaN (no disponibles).
        """
        nan = float('nan')
        return {
            'hhv_oil_mj_kg': nan,
            'hhv_oil_btu_lb': nan,
            'energy_enhancement_factor': nan,
            'viscosity_40c_cst': nan,
            'api_gravity': nan,
            'bsw_moisture_pct': nan,
        }
