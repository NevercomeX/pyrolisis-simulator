import argparse
import os
import matplotlib.pyplot as plt
import pandas as pd
from pyrolysis import PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, blend_feedstocks, BatchReactorSimulation


def parse_args():
    parser = argparse.ArgumentParser(description="Rotary Pyrolysis Reactor Batch Simulator")

    # Perfil: 'tesis' reproduce la corrida documentada sin introducir datos a mano
    parser.add_argument("--perfil", type=str, choices=["general", "tesis"], default="general",
                        help="Perfil de simulación: 'general' (valores por defecto) o 'tesis' (corrida PROENERGÉTICOS)")

    # Feedstock and reactor
    parser.add_argument("--feed", type=str, choices=["petroleum", "hydrocarbon", "blend"], default="blend",
                        help="Feedstock type: 'petroleum', 'hydrocarbon', or 'blend'")
    parser.add_argument("--blend-ratio", type=float, default=0.5,
                        help="Blend ratio (fraction of Petroleum Sludge in the mixture, 0.0 - 1.0)")
    parser.add_argument("--length", type=float, default=8.0,
                        help="Reactor length (m)")
    parser.add_argument("--diameter", type=float, default=0.6,
                        help="Reactor inner diameter (m)")
    parser.add_argument("--rpm", type=float, default=3.0,
                        help="Rotational speed (RPM)")
    parser.add_argument("--h-eff", type=float, default=80.0,
                        help="Effective wall-to-bed heat transfer coefficient (W/m²·K)")

    # Batch operation
    parser.add_argument("--batch-load", type=float, default=100.0,
                        help="Initial batch loading mass (kg)")
    parser.add_argument("--temp-start", type=float, default=25.0,
                        help="Initial batch start temperature (°C)")
    parser.add_argument("--heating-rate", type=float, default=10.0,
                        help="Heating rate (°C/min)")
    parser.add_argument("--temp-hold", type=float, default=550.0,
                        help="Target holding temperature (°C)")
    parser.add_argument("--hold-time", type=float, default=60.0,
                        help="Holding duration (minutes)")

    # Output file settings
    parser.add_argument("--out-csv", type=str, default="",
                        help="Output path to save the simulated profile CSV")
    parser.add_argument("--out-plot", type=str, default="reactor_profile.png",
                        help="Output path to save the profile plot image")

    return parser.parse_args()


def run_thesis_profile(args):
    """Corrida PROENERGÉTICOS del perfil 'tesis': imprime los rendimientos y, si se pide, guarda el CSV."""
    from pyrolysis.profiles import thesis_batch_kwargs
    results = BatchReactorSimulation(**thesis_batch_kwargs()).simulate(dt_sec=2.0)
    summary = results['summary']
    print("Perfil tesis: corrida PROENERGÉTICOS (calibrada con una sola corrida)")
    for key in ('oil_yield_pct', 'gas_yield_pct', 'char_yield_pct', 'water_yield_pct',
                'conversion_pct', 'waste_oil_consumed_gal'):
        print(f"  {key}: {summary[key]:.2f}")
    if args.out_csv:
        pd.DataFrame({k: v for k, v in results.items() if k != 'summary'}).to_csv(args.out_csv, index=False)


def select_feedstock(args):
    if args.feed == "petroleum":
        return PETROLEUM_SLUDGE
    if args.feed == "hydrocarbon":
        return HYDROCARBON_SLUDGE
    return blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, args.blend_ratio)


def print_run_header(args, feed):
    print("=" * 60)
    print("Starting Rotary Pyrolysis Simulation [Mode: BATCH]")
    print(f"Feedstock: {feed.name}")
    print(f"Reactor dimensions: L = {args.length:.1f} m, D = {args.diameter:.1f} m, RPM = {args.rpm:.1f}")
    print(f"Batch loading: {args.batch_load:.1f} kg, Start Temp = {args.temp_start:.1f} °C")
    print(f"Heating rate:  {args.heating_rate:.1f} °C/min up to {args.temp_hold:.1f} °C, hold {args.hold_time:.1f} min")
    print(f"h_eff = {args.h_eff:.1f} W/m²-K")
    print("=" * 60)


def run_batch(args, feed):
    sim = BatchReactorSimulation(
        feedstock=feed,
        batch_load_kg=args.batch_load,
        length=args.length,
        diameter=args.diameter,
        rpm=args.rpm,
        T_start_C=args.temp_start,
        heating_rate_cmin=args.heating_rate,
        T_hold_C=args.temp_hold,
        hold_time_min=args.hold_time,
        h_eff=args.h_eff
    )
    return sim.simulate(dt_sec=2.0)


def print_batch_summary(summary):
    print("\n--- SIMULATION RESULTS SUMMARY (BATCH) ---")
    print(f"Static Filling Degree:     {summary['filling_degree_pct']:.2f} %")
    print(f"Total Cumulative Energy:   {summary['total_energy_kwh']:.2f} kWh")
    print(f"Volatiles Conversion:      {summary['conversion_pct']:.1f} %")
    print(f"Mass Conservation Error:   {summary['mass_error_pct']:.2e} %")
    print("\nProduct Yields:")
    print(f"  Pyrolysis oil:   {summary['oil_yield_kg']:.1f} kg ({summary['oil_yield_pct']:.1f} wt.%)")
    print(f"  Syngas:    {summary['gas_yield_kg']:.1f} kg ({summary['gas_yield_pct']:.1f} wt.%)")
    print(f"  Char:  {summary['char_yield_kg']:.1f} kg ({summary['char_yield_pct']:.1f} wt.%)")
    print(f"  Water/Stm: {summary['water_yield_kg']:.1f} kg ({summary['water_yield_pct']:.1f} wt.%)")
    print("-" * 60)


def save_batch_csv(results, path):
    df = pd.DataFrame({
        'time_min': results['time'],
        'moisture_kg': results['moisture'],
        'volatile_kg': results['volatile'],
        'char_kg': results['char'],
        'ash_kg': results['ash'],
        'T_solids_C': results['T_solid'],
        'T_wall_C': results['T_wall'],
        'oil_vapor_kg': results['oil'],
        'gas_vapor_kg': results['gas'],
        'steam_kg': results['steam'],
        'conversion_frac': results['conversion'],
        'humidity_pct': results['humidity']
    })
    df.to_csv(path, index=False)
    print(f"Saved simulation profiles to: {path}")


def plot_batch(results):
    """Temperatures (top) and masses in the reactor (bottom) against time."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(results['time'], results['T_wall'], 'r--', label='Wall Temp')
    ax1.plot(results['time'], results['T_solid'], 'b-', linewidth=2, label='Solid Bed Temp')
    ax1.axhline(100.0, color='gray', linestyle=':', label='Boiling Point (100°C)')
    ax1.set_ylabel("Temperature (°C)")
    ax1.set_title("Batch Pyrolysis Reactor Time Profiles")
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend()

    ax2.plot(results['time'], results['moisture'], 'b:', label='Moisture in Bed')
    ax2.plot(results['time'], results['volatile'], 'm-', label='Volatiles in Bed')
    ax2.plot(results['time'], results['char'], 'k-', label='Char in Bed')
    ax2.plot(results['time'], results['oil'], 'g-', label='Cumulative Oil Vapor')
    ax2.plot(results['time'], results['gas'], 'c--', label='Cumulative Gas Vapor')
    ax2.set_xlabel("Time (minutes)")
    ax2.set_ylabel("Mass in Reactor (kg)")
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend()
    plt.tight_layout()


def main():
    args = parse_args()

    if args.perfil == "tesis":
        run_thesis_profile(args)
        return

    feed = select_feedstock(args)
    print_run_header(args, feed)
    results = run_batch(args, feed)
    print_batch_summary(results['summary'])
    if args.out_csv:
        save_batch_csv(results, args.out_csv)
    plot_batch(results)

    if args.out_plot:
        plt.savefig(args.out_plot, dpi=150)
        print(f"Saved profile chart to: {os.path.abspath(args.out_plot)}")


if __name__ == "__main__":
    main()
