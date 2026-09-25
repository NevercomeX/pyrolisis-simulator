"""
Feedstock and Characterization Module for Sludge Pyrolysis.

Represents physical, proximate, and kinetic properties of industrial sludges,
including multicomponent kinetic constants and feedstock blending utilities.
"""

from typing import Dict, Optional


class Feedstock:
    """
    Represents the physical, proximate, and kinetic properties of a feedstock sludge.
    All percentage compositions are specified on a WET basis (0.0 to 100.0 wt%).
    """
    def __init__(
        self,
        name: str,
        moisture: float,
        volatile: float,
        fixed_carbon: float,
        ash: float,
        E_a: float,
        A: float,
        yield_oil: float = 0.60,
        yield_gas: float = 0.25,
        yield_char: float = 0.15,
        Ea1: Optional[float] = None,
        A1: Optional[float] = None,
        Ea2: Optional[float] = None,
        A2: Optional[float] = None,
        Ea3: Optional[float] = None,
        A3: Optional[float] = None,
        T_onset_K: Optional[float] = 523.15,
        angle_of_repose: float = 35.0
    ) -> None:
        """
        Initializes and normalizes feedstock proximate analysis and Arrhenius parameters.
        """
        self.name = str(name)
        self.moisture = float(moisture)          # wt% (wet basis)
        self.volatile = float(volatile)          # wt% (wet basis)
        self.fixed_carbon = float(fixed_carbon)  # wt% (wet basis)
        self.ash = float(ash)                    # wt% (wet basis)

        # Normalize proximate components so sum equals 100%
        total = self.moisture + self.volatile + self.fixed_carbon + self.ash
        if total > 0.0 and abs(total - 100.0) > 1e-5:
            self.moisture = (self.moisture / total) * 100.0
            self.volatile = (self.volatile / total) * 100.0
            self.fixed_carbon = (self.fixed_carbon / total) * 100.0
            self.ash = (self.ash / total) * 100.0

        # Global kinetic parameters (Arrhenius)
        self.E_a = float(E_a)  # Activation energy (J/mol)
        self.A = float(A)      # Pre-exponential factor (1/s)

        # Pyrolysis product yields from devolatilized matter (sum = 1.0)
        self.yield_oil = float(yield_oil)
        self.yield_gas = float(yield_gas)
        self.yield_char = float(yield_char)

        y_total = self.yield_oil + self.yield_gas + self.yield_char
        if y_total > 0.0 and abs(y_total - 1.0) > 1e-5:
            self.yield_oil /= y_total
            self.yield_gas /= y_total
            self.yield_char /= y_total

        # Multi-step kinetic parameters (derived from primary kinetics if omitted)
        self.Ea1 = float(Ea1) if Ea1 is not None else self.E_a
        self.A1 = float(A1) if A1 is not None else self.A * self.yield_oil
        self.Ea2 = float(Ea2) if Ea2 is not None else self.E_a
        self.A2 = float(A2) if A2 is not None else self.A * (self.yield_gas + self.yield_char)
        self.Ea3 = float(Ea3) if Ea3 is not None else 100000.0
        self.A3 = float(A3) if A3 is not None else 5e5

        # Physical constants
        self.T_onset_K = float(T_onset_K) if T_onset_K is not None else 523.15
        self.angle_of_repose = float(angle_of_repose)

    @property
    def fractions(self) -> Dict[str, float]:
        """Returns the mass fractions of proximate components on a wet basis (0 to 1)."""
        return {
            'moisture': self.moisture / 100.0,
            'volatile': self.volatile / 100.0,
            'fixed_carbon': self.fixed_carbon / 100.0,
            'ash': self.ash / 100.0
        }

    def get_fractions(self) -> Dict[str, float]:
        """Returns the mass fractions of proximate components on a wet basis (0 to 1)."""
        return self.fractions

    @property
    def dry_matter_fraction(self) -> float:
        """Dimensionless fraction of dry solids (1 - moisture fraction)."""
        return 1.0 - (self.moisture / 100.0)

    def __repr__(self) -> str:
        return (
            f"Feedstock({self.name}: H2O={self.moisture:.1f}%, VM={self.volatile:.1f}%, "
            f"FC={self.fixed_carbon:.1f}%, Ash={self.ash:.1f}%, Ea={self.E_a / 1000.0:.1f} kJ/mol, "
            f"A={self.A:.1e} s^-1)"
        )


# Predefined feedstocks calibrated with experimental literature data
PETROLEUM_SLUDGE = Feedstock(
    name="Petroleum Sludge",
    moisture=50.0,      # High moisture
    volatile=30.0,      # Volatile hydrocarbons
    fixed_carbon=10.0,  # Organic solid residue
    ash=10.0,           # Soil/inorganic matter
    E_a=120000.0,       # 120 kJ/mol
    A=1e7,              # 10^7 1/s
    yield_oil=0.60,     # High oil potential
    yield_gas=0.25,
    yield_char=0.15,
    Ea1=120000.0, A1=6e6,
    Ea2=125000.0, A2=4e6,
    Ea3=100000.0, A3=5e5,
    T_onset_K=523.15,
    angle_of_repose=35.0
)

HYDROCARBON_SLUDGE = Feedstock(
    name="Hydrocarbon Sludge",
    moisture=15.0,      # Low moisture
    volatile=65.0,      # Very high volatiles
    fixed_carbon=10.0,
    ash=10.0,
    E_a=90000.0,        # 90 kJ/mol
    A=1e6,              # 10^6 1/s
    yield_oil=0.70,     # Extremely high oil yield
    yield_gas=0.22,
    yield_char=0.08,
    Ea1=90000.0, A1=7.5e5,
    Ea2=95000.0, A2=2.5e5,
    Ea3=80000.0, A3=1.0e5,
    T_onset_K=523.15,
    angle_of_repose=35.0
)


def blend_feedstocks(feed1: Feedstock, feed2: Feedstock, ratio: float) -> Feedstock:
    """
    Blends two feedstocks linearly based on a blending ratio.
    ratio = 0.0 means 100% feed2
    ratio = 1.0 means 100% feed1
    ratio = 0.5 means 50% feed1 and 50% feed2
    """
    r1 = float(ratio)
    r2 = 1.0 - r1

    # Linear proximate composition blending
    moisture = r1 * feed1.moisture + r2 * feed2.moisture
    volatile = r1 * feed1.volatile + r2 * feed2.volatile
    fixed_carbon = r1 * feed1.fixed_carbon + r2 * feed2.fixed_carbon
    ash = r1 * feed1.ash + r2 * feed2.ash

    # Linear kinetic parameters blending
    E_a = r1 * feed1.E_a + r2 * feed2.E_a
    A = r1 * feed1.A + r2 * feed2.A

    Ea1 = r1 * feed1.Ea1 + r2 * feed2.Ea1
    A1 = r1 * feed1.A1 + r2 * feed2.A1
    Ea2 = r1 * feed1.Ea2 + r2 * feed2.Ea2
    A2 = r1 * feed1.A2 + r2 * feed2.A2
    Ea3 = r1 * feed1.Ea3 + r2 * feed2.Ea3
    A3 = r1 * feed1.A3 + r2 * feed2.A3

    # Product yields blending
    yield_oil = r1 * feed1.yield_oil + r2 * feed2.yield_oil
    yield_gas = r1 * feed1.yield_gas + r2 * feed2.yield_gas
    yield_char = r1 * feed1.yield_char + r2 * feed2.yield_char

    t_onset = r1 * feed1.T_onset_K + r2 * feed2.T_onset_K
    repose = r1 * feed1.angle_of_repose + r2 * feed2.angle_of_repose
    name = f"Blend ({int(r1 * 100)}% {feed1.name} / {int(r2 * 100)}% {feed2.name})"

    return Feedstock(
        name=name,
        moisture=moisture,
        volatile=volatile,
        fixed_carbon=fixed_carbon,
        ash=ash,
        E_a=E_a,
        A=A,
        yield_oil=yield_oil,
        yield_gas=yield_gas,
        yield_char=yield_char,
        Ea1=Ea1, A1=A1,
        Ea2=Ea2, A2=A2,
        Ea3=Ea3, A3=A3,
        T_onset_K=t_onset,
        angle_of_repose=repose
    )
