import argparse
import os
import matplotlib.pyplot as plt
import pandas as pd
from pyrolysis import PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, blend_feedstocks, ContinuousReactorSimulation, BatchReactorSimulation

def main():
    parser = argparse.ArgumentParser(description="Rotary Pyrolysis Reactor Dual-Mode Simulator (Continuous & Batch)")
    
    # Mode selector
    parser.add_argument("--mode", type=str, choices=["continuous", "batch"], default="continuous",
                        help="Operation mode: 'continuous' or 'batch'")
    
    # Shared arguments
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
    
    # Continuous mode specific arguments
    parser.add_argument("--feed-rate", type=float, default=100.0,
                        help="Feedstock mass flow rate (kg/h) - Continuous mode only")
    parser.add_argument("--slope", type=float, default=0.02,
                        help="Reactor slope (inclination, m/m) - Continuous mode only")
    parser.add_argument("--temp-inlet", type=float, default=25.0,
                        help="Inlet solid feedstock temperature (°C) - Continuous mode only")
    parser.add_argument("--temp-wall", type=float, default=500.0,
                        help="Uniform wall temperature setting (°C) - Continuous mode only")
    
    # Batch mode specific arguments
    parser.add_argument("--batch-load", type=float, default=100.0,
                        help="Initial batch loading mass (kg) - Batch mode only")
    parser.add_argument("--temp-start", type=float, default=25.0,
                        help="Initial batch start temperature (°C) - Batch mode only")
    parser.add_argument("--heating-rate", type=float, default=10.0,
                        help="Heating rate (°C/min) - Batch mode only")
    parser.add_argument("--temp-hold", type=float, default=550.0,
                        help="Target holding temperature (°C) - Batch mode only")
    parser.add_argument("--hold-time", type=float, default=60.0,
                        help="Holding duration (minutes) - Batch mode only")
    
    # Output file settings
    parser.add_argument("--out-csv", type=str, default="",
                        help="Output path to save the simulated profile CSV")
    parser.add_argument("--out-plot", type=str, default="reactor_profile.png",
                        help="Output path to save the profile plot image")
    
    args = parser.parse_args()
    
    # Define feedstock
    if args.feed == "petroleum":
        feed = PETROLEUM_SLUDGE
    elif args.feed == "hydrocarbon":
        feed = HYDROCARBON_SLUDGE
    else:
        feed = blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, args.blend_ratio)
        
    print("=" * 60)
    print(f"Starting Rotary Pyrolysis Simulation [Mode: {args.mode.upper()}]")
    print(f"Feedstock: {feed.name}")
    print(f"Reactor dimensions: L = {args.length:.1f} m, D = {args.diameter:.1f} m, RPM = {args.rpm:.1f}")
    
    if args.mode == "continuous":
        print(f"Continuous feed: {args.feed_rate:.1f} kg/h, Slope = {args.slope * 100:.1f}%, Inlet Temp = {args.temp_inlet:.1f} °C")
        print(f"Wall Temp setting: {args.temp_wall:.1f} °C, h_eff = {args.h_eff:.1f} W/m²-K")
        print("=" * 60)
        
        sim = ContinuousReactorSimulation(
            feedstock=feed,
            feed_rate_kgh=args.feed_rate,
            length=args.length,
            diameter=args.diameter,
            slope=args.slope,
            rpm=args.rpm,
            T_inlet_C=args.temp_inlet,
            h_eff=args.h_eff,
            T_wall_type='uniform',
            T_wall_params={'T_wall': args.temp_wall}
        )
        results = sim.simulate(steps=200)
        summary = results['summary']
        
        print("\n--- SIMULATION RESULTS SUMMARY (CONTINUOUS) ---")
        print(f"Mean Residence Time (MRT): {summary['residence_time_min']:.1f} minutes")
        print(f"Filling Degree:            {summary['filling_degree_pct']:.2f} %")
        print(f"Total Heating Duty:        {summary['heating_duty_kw']:.2f} kW")
        print(f"Volatiles Conversion:      {summary['conversion_pct']:.1f} %")
        print(f"Mass Conservation Error:   {summary['mass_error_pct']:.2e} %")
        print("\nProduct Yields:")
        print(f"  Bio-Oil:   {summary['oil_yield_kgh']:.1f} kg/h ({summary['oil_yield_pct']:.1f} wt.%)")
        print(f"  Syngas:    {summary['gas_yield_kgh']:.1f} kg/h ({summary['gas_yield_pct']:.1f} wt.%)")
        print(f"  Bio-Char:  {summary['char_yield_kgh']:.1f} kg/h ({summary['char_yield_pct']:.1f} wt.%)")
        print(f"  Water/Stm: {summary['water_yield_kgh']:.1f} kg/h ({summary['water_yield_pct']:.1f} wt.%)")
        print("-" * 60)
        
        df = pd.DataFrame({
            'z_m': results['z'],
            'moisture_kgh': results['moisture'],
            'volatile_kgh': results['volatile'],
            'char_kgh': results['char'],
            'ash_kgh': results['ash'],
            'T_solids_C': results['T_solid'],
            'T_gas_C': results['T_gas'],
            'T_wall_C': results['T_wall'],
            'oil_vapor_kgh': results['oil'],
            'gas_vapor_kgh': results['gas'],
            'steam_kgh': results['steam'],
            'conversion_frac': results['conversion'],
            'humidity_pct': results['humidity']
        })
        
        if args.out_csv:
            df.to_csv(args.out_csv, index=False)
            print(f"Saved simulation profiles to: {args.out_csv}")
            
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        ax1.plot(results['z'], results['T_wall'], 'r--', label='Wall Temp')
        ax1.plot(results['z'], results['T_solid'], 'b-', linewidth=2, label='Solid Bed Temp')
        ax1.plot(results['z'], results['T_gas'], 'g-.', label='Gas Phase Temp')
        ax1.axhline(100.0, color='gray', linestyle=':', label='Boiling Point (100°C)')
        ax1.set_ylabel("Temperature (°C)")
        ax1.set_title("Continuous Pyrolysis Reactor 1D Spatial Profiles")
        ax1.grid(True, linestyle=':', alpha=0.6)
        ax1.legend()
        
        ax2.plot(results['z'], results['moisture'], 'b:', label='Moisture in Bed')
        ax2.plot(results['z'], results['volatile'], 'm-', label='Volatiles in Bed')
        ax2.plot(results['z'], results['char'], 'k-', label='Char in Bed')
        ax2.plot(results['z'], results['oil'], 'g-', label='Cumulative Oil Vapor')
        ax2.plot(results['z'], results['gas'], 'c--', label='Cumulative Gas Vapor')
        ax2.set_xlabel("Reactor Length (z, m)")
        ax2.set_ylabel("Mass Flow Rate (kg/h)")
        ax2.grid(True, linestyle=':', alpha=0.6)
        ax2.legend()
        plt.tight_layout()
        
    else:  # Batch mode
        print(f"Batch loading: {args.batch_load:.1f} kg, Start Temp = {args.temp_start:.1f} °C")
        print(f"Heating rate:  {args.heating_rate:.1f} °C/min up to {args.temp_hold:.1f} °C, hold {args.hold_time:.1f} min")
        print(f"h_eff = {args.h_eff:.1f} W/m²-K")
        print("=" * 60)
        
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
        results = sim.simulate(dt_sec=2.0)
        summary = results['summary']
        
        print("\n--- SIMULATION RESULTS SUMMARY (BATCH) ---")
        print(f"Static Filling Degree:     {summary['filling_degree_pct']:.2f} %")
        print(f"Total Cumulative Energy:   {summary['total_energy_kwh']:.2f} kWh")
        print(f"Volatiles Conversion:      {summary['conversion_pct']:.1f} %")
        print(f"Mass Conservation Error:   {summary['mass_error_pct']:.2e} %")
        print("\nProduct Yields:")
        print(f"  Bio-Oil:   {summary['oil_yield_kg']:.1f} kg ({summary['oil_yield_pct']:.1f} wt.%)")
        print(f"  Syngas:    {summary['gas_yield_kg']:.1f} kg ({summary['gas_yield_pct']:.1f} wt.%)")
        print(f"  Bio-Char:  {summary['char_yield_kg']:.1f} kg ({summary['char_yield_pct']:.1f} wt.%)")
        print(f"  Water/Stm: {summary['water_yield_kg']:.1f} kg ({summary['water_yield_pct']:.1f} wt.%)")
        print("-" * 60)
        
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
        
        if args.out_csv:
            df.to_csv(args.out_csv, index=False)
            print(f"Saved simulation profiles to: {args.out_csv}")
            
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

    if args.out_plot:
        plt.savefig(args.out_plot, dpi=150)
        print(f"Saved profile chart to: {os.path.abspath(args.out_plot)}")
        
if __name__ == "__main__":
    main()
