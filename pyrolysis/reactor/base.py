import numpy as np
from ..feedstock import Feedstock

class BaseReactorSimulation:
    def __init__(self, feedstock: Feedstock, length: float, diameter: float, rpm: float, h_eff: float,
                 bulk_density: float = 900.0,
                 Cp_volatile: float = 1800.0,
                 Cp_char: float = 1000.0,
                 Cp_ash: float = 800.0):
        """
        Base simulation class containing shared physical, thermodynamic constants,
        and common math helper methods.
        """
        self.feedstock = feedstock
        self.length = float(length)
        self.diameter = float(diameter)
        self.rpm = float(rpm)
        self.h_eff = float(h_eff)

        # Shared thermodynamics and kinetic constants
        self.R = 8.3144598              # Gas constant (J/mol·K)
        self.Cp_moist = 4184.0      # liquid water (J/kg·K)
        self.Cp_volatile = float(Cp_volatile)   # volatile hydrocarbons (J/kg·K)
        self.Cp_char = float(Cp_char)       # carbon/char (J/kg·K)
        self.Cp_ash = float(Cp_ash)         # inorganic/ash (J/kg·K)
        
        self.Cp_steam = 2000.0      # steam (J/kg·K)
        self.Cp_oil_vap = 2200.0    # oil vapor (J/kg·K)
        self.Cp_pyro_gas = 1500.0   # pyrolysis gas (J/kg·K)
        
        self.dH_evap = 2256000.0    # Water vaporization (endothermic, J/kg)
        self.dH_pyro = 700000.0     # Pyrolysis reaction (endothermic, J/kg)
        self.bulk_density = float(bulk_density)   # Sludge bulk density (kg/m3)

    def calculate_Cp_solid(self, m_moist: float, m_volatile: float, m_char: float, m_ash: float, m_solid_total: float) -> float:
        """Calculates solid bed heat capacity (J/kg·K)."""
        if m_solid_total <= 1e-8:
            return self.Cp_ash
        return (m_moist * self.Cp_moist + 
                m_volatile * self.Cp_volatile + 
                m_char * self.Cp_char + 
                m_ash * self.Cp_ash) / m_solid_total

    def calculate_Cp_gas(self, m_steam: float, m_oil_vap: float, m_gas_vap: float, m_gas_total: float) -> float:
        """Calculates gas phase heat capacity (J/kg·K)."""
        if m_gas_total <= 1e-8:
            return self.Cp_steam
        return (m_steam * self.Cp_steam + 
                m_oil_vap * self.Cp_oil_vap + 
                m_gas_vap * self.Cp_pyro_gas) / m_gas_total

    def calculate_humidity_pct(self, m_moist: float, m_solid_total: float) -> float:
        """Calculates wet-basis bed humidity (wt%)."""
        if m_solid_total <= 0.0:
            return 0.0
        return (m_moist / m_solid_total) * 100.0

    def calculate_pyrolysis_rate(self, T_s: float, m_volatile: float) -> tuple:
        """
        Calculates the pyrolysis kinetics rate constant and mass conversion rate.
        
        Returns:
            (k_pyro, r_pyro): reaction rate constant (1/s) and reaction rate (kg/s).
        """
        k_pyro = self.feedstock.A * np.exp(-self.feedstock.E_a / (self.R * T_s))
        r_pyro = k_pyro * m_volatile
        return k_pyro, r_pyro

    def calculate_first_order_kinetics(self, T_s: float, C_slug: float, C_medios: float) -> tuple:
        """
        Calculates k1, k2, k3 rate constants (1/s) and rates of change (kg/s)
        based on the three-component first-order kinetics model.
        
        Returns:
            (k1, k2, k3, r_slug, r_medios, r_gases)
        """
        # Ensure we don't divide by zero or evaluate log/exp at weird values
        T_s = max(T_s, 200.0)
        
        # Read parameters from feedstock
        A1 = getattr(self.feedstock, 'A1', self.feedstock.A * self.feedstock.yield_oil)
        Ea1 = getattr(self.feedstock, 'Ea1', self.feedstock.E_a)
        
        A2 = getattr(self.feedstock, 'A2', self.feedstock.A * (self.feedstock.yield_gas + self.feedstock.yield_char))
        Ea2 = getattr(self.feedstock, 'Ea2', self.feedstock.E_a)
        
        A3 = getattr(self.feedstock, 'A3', 5e5)
        Ea3 = getattr(self.feedstock, 'Ea3', 100000.0)
        
        # Calculate rate constants
        k1 = A1 * np.exp(-Ea1 / (self.R * T_s))
        k2 = A2 * np.exp(-Ea2 / (self.R * T_s))
        k3 = A3 * np.exp(-Ea3 / (self.R * T_s))
        
        # Calculate rates
        # dC_slug/dt = -(k1 + k2) * C_slug -> rate of consumption of C_slug is (k1 + k2)*C_slug
        r_slug = (k1 + k2) * C_slug
        
        # dC_medios/dt = k1 * C_slug - k3 * C_medios
        r_medios = k1 * C_slug - k3 * C_medios
        
        # dC_gases/dt = k2 * C_slug + k3 * C_medios
        r_gases = k2 * C_slug + k3 * C_medios
        
        return k1, k2, k3, r_slug, r_medios, r_gases

    def calculate_yields(self, d_volatile: float) -> tuple:
        """
        Splits reacted volatiles into Char, Bio-Oil, and Syngas based on feedstock yields.
        
        Returns:
            (d_char, d_oil, d_gas) yields.
        """
        d_char = d_volatile * self.feedstock.yield_char
        d_oil = d_volatile * self.feedstock.yield_oil
        d_gas = d_volatile * self.feedstock.yield_gas
        return d_char, d_oil, d_gas
