"""Financial model of the plant (no Streamlit): yearly cash flows, NPV, IRR, paybacks, break-even fee and
the sludge scenarios. economics_panel.py re-exports every public name, so callers may import from either."""

IRR_SEARCH_MAX = 1000.0   # upper search bound for the IRR as a fraction (= 100,000 %)
GAL_PER_M3 = 264.172      # US gallons per cubic metre


# ----------------------------------------------------------------------------- IRR
def solve_irr(cash_flows):
    """
    Calculates the Internal Rate of Return (IRR) for a given series of cash flows.
    Returns the percentage, float('inf') when a conventional project (investment first, then non-negative
    flows) still has NPV > 0 at IRR_SEARCH_MAX, or None if it cannot be solved.
    """
    if not cash_flows or all(x >= 0 for x in cash_flows) or all(x <= 0 for x in cash_flows):
        return None

    def npv_func(rate):
        return sum(cf / ((1.0 + rate)**yr) for yr, cf in enumerate(cash_flows))

    low = -0.99
    high = 10.0

    val_low = npv_func(low)
    val_high = npv_func(high)
    # Very profitable projects: widen the bracket instead of giving up at 1,000 %
    while val_low * val_high > 0 and high < IRR_SEARCH_MAX:
        high = min(high * 10.0, IRR_SEARCH_MAX)
        val_high = npv_func(high)
    if val_low * val_high > 0 and val_high > 0 and cash_flows[0] < 0 and all(x >= 0 for x in cash_flows[1:]):
        return float('inf')

    if val_low * val_high > 0:
        # No sign change between the ends: look for one in 100 sub-intervals
        steps = 100
        for i in range(steps):
            r1 = low + (high - low) * i / steps
            r2 = low + (high - low) * (i + 1) / steps
            if npv_func(r1) * npv_func(r2) < 0:
                low, high = r1, r2
                break
        else:
            return None

    # Bisection: the end whose NPV has the same sign as `val` moves to `mid`
    for _ in range(100):
        mid = (low + high) / 2.0
        val = npv_func(mid)
        if abs(val) < 1e-3:
            return mid * 100.0
        if (val > 0) == (val_low > 0):
            low = mid
        else:
            high = mid

    return ((low + high) / 2.0) * 100.0


def format_irr(irr, decimals=2):
    """IRR text: 'N/A' when undefined, '> 100,000 %' above the search bound, otherwise the value."""
    if irr is None:
        return "N/A"
    if irr == float('inf'):
        return f"> {IRR_SEARCH_MAX * 100.0:,.0f} %"
    return f"{irr:,.{decimals}f} %"


# ----------------------------------------------------------------------------- sludge scenarios
SLUDGE_SCENARIOS = ('purchase', 'free', 'tipping')
SLUDGE_SCENARIO_LABELS = {
    'purchase': {'es': "Lodo húmedo comprado", 'en': "Wet sludge purchased"},
    'free': {'es': "Lodo sin costo", 'en': "Sludge at no cost"},
    'tipping': {'es': "Lodo con tarifa de disposición", 'en': "Sludge with disposal fee"},
}


def scenario_tipping_fee(scenario, sludge_cost, tipping_fee):
    """Effective tipping fee (RD$/gal) of a sludge scenario: purchase = −X, free = 0, disposal fee = +Y."""
    return {'purchase': 0.0 - float(sludge_cost), 'free': 0.0, 'tipping': float(tipping_fee)}[scenario]  # 0.0 - x avoids "-0.00"


def breakeven_note(breakeven_tipping, lang='es'):
    """Sentence explaining the break-even tipping fee (NPV = 0), shown with two decimals."""
    v = round(breakeven_tipping, 2)
    if v < 0:
        return (f"El proyecto mantiene VAN ≥ 0 mientras el lodo cueste menos de RD$ {-v:,.2f}/gal." if lang == 'es'
                else f"The project keeps NPV ≥ 0 as long as sludge costs less than RD$ {-v:,.2f}/gal.")
    if v > 0:
        return (f"El proyecto necesita cobrar una tarifa de disposición de al menos RD$ {v:,.2f}/gal para tener VAN ≥ 0."
                if lang == 'es' else
                f"The project needs a disposal fee of at least RD$ {v:,.2f}/gal to reach NPV ≥ 0.")
    return ("El proyecto queda en equilibrio exacto sin costo ni tarifa por el lodo." if lang == 'es'
            else "The project breaks even exactly with no sludge cost or fee.")


# ----------------------------------------------------------------------------- batch cycle
def batch_thermal_cycle_min(summary, solver_inputs):
    """
    Returns (t_cycle_min, t_heat_min, t_hold_min) of the thermal process of one batch.
    Uses the simulated duration (drying + heating + hold) when available; the naive
    (T_hold - T_start) / heating_rate estimate ignores drying and underestimates the cycle.
    """
    t_hold_min = float(solver_inputs.get('hold_time_min', 60.0))
    sim_cycle = summary.get('cycle_time_min') if summary else None
    if sim_cycle:
        t_cycle_min = float(sim_cycle)
        t_heat_min = max(0.0, t_cycle_min - t_hold_min)
    else:
        rate = max(float(solver_inputs.get('heating_rate_cmin', 1.0)), 1e-6)
        t_heat_min = (float(solver_inputs.get('temp_hold_c', 400.0)) - float(solver_inputs.get('temp_start_c', 25.0))) / rate
        t_cycle_min = t_heat_min + t_hold_min
    return t_cycle_min, t_heat_min, t_hold_min


# ----------------------------------------------------------------------------- cash-flow model
def _payback_years(flows, total_capex, project_lifetime):
    """Years until the running sum of `flows` (starting at -CAPEX) turns non-negative, interpolated
    inside the year it happens; inf if it never does."""
    cum = -total_capex
    for yr in range(1, int(project_lifetime) + 1):
        prev = cum
        cum += flows[yr]
        if cum >= 0:
            return (yr - 1) + (-prev / flows[yr]) if flows[yr] > 0 else (yr - 1)
    return float('inf')


def run_financial_model(
    total_capex, sludge_treated_gal, oil_produced_gal, char_produced_kg, gas_produced_m3,
    fuel_consumed_gal, elec_consumed_kwh, generator_fuel_consumed_gal,
    opex_handling, opex_fuel, opex_electricity, opex_aux_utilities, price_generator_fuel,
    opex_labor, opex_maint, opex_insurance_tax,
    opex_tipping, price_oil, price_char, price_gas, price_carbon, rate_carbon_offset,
    discount_rate, project_lifetime, tax_rate, inflation_rate,
    char_carbon_kg=None
):
    """
    Runs the detailed cash flow model over the project lifetime and returns year-by-year cash flows
    and advanced economic indicators (computed in gallons, kg, and m3).

    `char_carbon_kg` is the carbon-bearing char (residue without ash) used for carbon credits;
    defaults to `char_produced_kg` when not given.
    """
    if char_carbon_kg is None:
        char_carbon_kg = char_produced_kg
    disc_frac = discount_rate / 100.0
    infl_frac = inflation_rate / 100.0
    tax_frac = tax_rate / 100.0

    # Year 1 base values (uninflated)
    rev_tipping = sludge_treated_gal * opex_tipping
    rev_oil = oil_produced_gal * price_oil
    rev_char = char_produced_kg * price_char
    rev_gas = gas_produced_m3 * price_gas

    annual_co2_sequestered_ton = (char_carbon_kg * rate_carbon_offset) / 1000.0
    rev_carbon = annual_co2_sequestered_ton * price_carbon

    total_rev_base = rev_tipping + rev_oil + rev_char + rev_gas + rev_carbon

    cost_handling = sludge_treated_gal * opex_handling
    cost_fuel = fuel_consumed_gal * opex_fuel
    cost_electricity = elec_consumed_kwh * opex_electricity
    cost_aux_utilities = opex_aux_utilities
    cost_generator_fuel = generator_fuel_consumed_gal * price_generator_fuel
    cost_labor = opex_labor
    cost_maintenance = total_capex * (opex_maint / 100.0)
    cost_insurance_tax = total_capex * (opex_insurance_tax / 100.0)

    total_opex_base = (
        cost_handling + cost_fuel + cost_electricity + cost_aux_utilities +
        cost_generator_fuel + cost_labor + cost_maintenance + cost_insurance_tax
    )

    depreciation_annual = total_capex / project_lifetime if project_lifetime > 0 else 0.0
    lifetime_years = range(1, int(project_lifetime) + 1)

    def year_flows(rev_base, yr):
        """(revenue, OPEX, taxes, net cash flow, discounted net cash flow) of year `yr` (inflated)."""
        inf_factor = (1.0 + infl_frac) ** (yr - 1)
        rev = rev_base * inf_factor
        opex = total_opex_base * inf_factor
        ebitda = rev - opex
        taxable_income = ebitda - depreciation_annual
        taxes = max(0.0, taxable_income * tax_frac)
        net_cf = ebitda - taxes
        return rev, opex, taxes, net_cf, net_cf / ((1.0 + disc_frac) ** yr)

    years = list(range(0, int(project_lifetime) + 1))
    rev_flows = [0.0] * len(years)
    opex_flows = [0.0] * len(years)
    depr_flows = [0.0] * len(years)
    tax_flows = [0.0] * len(years)
    net_flows = [0.0] * len(years)
    disc_flows = [0.0] * len(years)
    cum_flows = [0.0] * len(years)

    net_flows[0] = -total_capex
    disc_flows[0] = -total_capex
    cum_flows[0] = -total_capex

    for yr in lifetime_years:
        rev_flows[yr], opex_flows[yr], tax_flows[yr], net_flows[yr], disc_flows[yr] = year_flows(total_rev_base, yr)
        depr_flows[yr] = depreciation_annual
        cum_flows[yr] = cum_flows[yr-1] + net_flows[yr]

    npv = sum(disc_flows)
    irr = solve_irr(net_flows)
    payback = _payback_years(net_flows, total_capex, project_lifetime)
    disc_payback = _payback_years(disc_flows, total_capex, project_lifetime)
    pi = 1.0 + (npv / total_capex) if total_capex > 0 else 0.0

    # Break-even tipping fee by bisection: NPV rises with the fee but not in a straight line
    # (taxes only apply to profit), so a two-point secant misses the break-even.
    def npv_for_tipping(fee):
        rev_base = sludge_treated_gal * fee + rev_oil + rev_char + rev_gas + rev_carbon
        return sum([-total_capex] + [year_flows(rev_base, yr)[4] for yr in lifetime_years])

    if sludge_treated_gal > 0:
        lo, hi = -1.0, 1.0
        while npv_for_tipping(lo) > 0 and lo > -1e9:
            lo *= 2.0
        while npv_for_tipping(hi) < 0 and hi < 1e9:
            hi *= 2.0
        for _ in range(100):
            mid = (lo + hi) / 2.0
            if npv_for_tipping(mid) < 0:
                lo = mid
            else:
                hi = mid
        breakeven_tipping = (lo + hi) / 2.0
    else:
        breakeven_tipping = 0.0

    return {
        'npv': npv,
        'irr': irr,
        'payback': payback,
        'disc_payback': disc_payback,
        'pi': pi,
        'breakeven_tipping': breakeven_tipping,
        'annual_co2_sequestered_ton': annual_co2_sequestered_ton,
        'years': years,
        'net_flows': net_flows,
        'disc_flows': disc_flows,
        'cum_flows': cum_flows,
        'rev_flows': rev_flows,
        'opex_flows': opex_flows,
        'depr_flows': depr_flows,
        'tax_flows': tax_flows,
        'revenue_breakdown': {
            'tipping': rev_tipping,
            'oil': rev_oil,
            'char': rev_char,
            'gas': rev_gas,
            'carbon': rev_carbon
        },
        'opex_breakdown': {
            'handling': cost_handling,
            'fuel': cost_fuel,
            'electricity': cost_electricity,
            'aux_utilities': cost_aux_utilities,
            'gen_diesel': cost_generator_fuel,
            'labor': cost_labor,
            'maintenance': cost_maintenance,
            'insurance_tax': cost_insurance_tax
        }
    }
