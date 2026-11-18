import unittest
import numpy as np
from pyrolysis import PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, Feedstock, blend_feedstocks, ContinuousReactorSimulation, BatchReactorSimulation

class TestPyrolysisSimulation(unittest.TestCase):
    
    # ==========================================================================
    # CONTINUOUS MODE TESTS
    # ==========================================================================
    
    def test_continuous_mass_conservation(self):
        """Verify that total mass entering equals total mass leaving in Continuous Mode."""
        feed = blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, 0.5)
        feed_rate = 150.0  # kg/h
        
        sim = ContinuousReactorSimulation(
            feedstock=feed,
            feed_rate_kgh=feed_rate,
            length=10.0,
            diameter=0.8,
            slope=0.02,
            rpm=4.0,
            T_inlet_C=20.0,
            h_eff=100.0,
            T_wall_type='uniform',
            T_wall_params={'T_wall': 600.0}
        )
        
        results = sim.simulate(steps=100)
        summary = results['summary']
        
        # Total mass out = Char + Oil + Gas + Steam (at 600°C and 10m, all moisture is steam)
        total_out = (summary['char_yield_kgh'] + 
                     summary['oil_yield_kgh'] + 
                     summary['gas_yield_kgh'] + 
                     summary['water_yield_kgh'])
                      
        self.assertAlmostEqual(total_out, feed_rate, places=4)
        self.assertLess(summary['mass_error_pct'], 1e-4)

    def test_continuous_no_evaporation_at_low_temp(self):
        """Verify water doesn't evaporate and kinetics don't run at low temp in Continuous Mode."""
        feed = PETROLEUM_SLUDGE # 50% moisture
        feed_rate = 100.0
        
        sim = ContinuousReactorSimulation(
            feedstock=feed,
            feed_rate_kgh=feed_rate,
            length=5.0,
            diameter=0.5,
            slope=0.02,
            rpm=3.0,
            T_inlet_C=15.0,
            h_eff=80.0,
            T_wall_type='uniform',
            T_wall_params={'T_wall': 50.0}  # 50°C
        )
        
        results = sim.simulate(steps=50)
        summary = results['summary']
        
        # At 50°C, no steam should be produced
        self.assertAlmostEqual(summary['water_yield_kgh'], 0.0, places=4)
        # Volatiles conversion should be virtually zero
        self.assertLess(summary['conversion_pct'], 0.01)

    def test_continuous_complete_dehydration_and_pyrolysis_at_high_temp(self):
        """Verify complete dehydration and conversion at high temp in Continuous Mode."""
        feed = PETROLEUM_SLUDGE
        feed_rate = 100.0
        
        sim = ContinuousReactorSimulation(
            feedstock=feed,
            feed_rate_kgh=feed_rate,
            length=15.0,
            diameter=0.8,
            slope=0.01,
            rpm=1.0,
            T_inlet_C=25.0,
            h_eff=150.0,
            T_wall_type='uniform',
            T_wall_params={'T_wall': 700.0}
        )
        
        results = sim.simulate(steps=100)
        summary = results['summary']
        
        # Moisture should be completely evaporated
        self.assertAlmostEqual(results['moisture'][-1], 0.0, places=4)
        self.assertAlmostEqual(summary['water_yield_kgh'], feed_rate * (feed.moisture / 100.0), places=4)
        self.assertGreater(summary['conversion_pct'], 99.0)

    # ==========================================================================
    # BATCH MODE TESTS
    # ==========================================================================
    
    def test_batch_mass_conservation(self):
        """Verify mass conservation in Batch Mode."""
        feed = blend_feedstocks(PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, 0.3)
        batch_load = 250.0  # kg
        
        sim = BatchReactorSimulation(
            feedstock=feed,
            batch_load_kg=batch_load,
            length=6.0,
            diameter=0.8,
            rpm=4.0,
            T_start_C=25.0,
            heating_rate_cmin=15.0,
            T_hold_C=600.0,
            hold_time_min=60.0,
            h_eff=120.0
        )
        
        results = sim.simulate(dt_sec=2.0)
        summary = results['summary']
        
        # Total mass balance: Char + Oil + Gas + Steam (all water is evaporated at 600°C)
        total_out = (summary['char_yield_kg'] + 
                     summary['oil_yield_kg'] + 
                     summary['gas_yield_kg'] + 
                     summary['water_yield_kg'])
                      
        self.assertAlmostEqual(total_out, batch_load, places=4)
        self.assertLess(summary['mass_error_pct'], 1e-4)

    def test_batch_no_evaporation_at_low_temp(self):
        """Verify no evaporation and no reactions at low temp in Batch Mode."""
        feed = PETROLEUM_SLUDGE
        batch_load = 80.0  # kg
        
        sim = BatchReactorSimulation(
            feedstock=feed,
            batch_load_kg=batch_load,
            length=5.0,
            diameter=0.6,
            rpm=3.0,
            T_start_C=20.0,
            heating_rate_cmin=5.0,
            T_hold_C=50.0,  # low temp hold
            hold_time_min=30.0,
            h_eff=80.0
        )
        
        results = sim.simulate(dt_sec=2.0)
        summary = results['summary']
        
        # Zero water vapor evaporated (steam)
        self.assertAlmostEqual(summary['water_yield_kg'], 0.0, places=4)
        self.assertLess(summary['conversion_pct'], 0.01)

    def test_batch_complete_dehydration_and_pyrolysis_at_high_temp(self):
        """Verify complete dehydration and conversion at high temp in Batch Mode."""
        feed = PETROLEUM_SLUDGE
        batch_load = 120.0  # kg
        
        sim = BatchReactorSimulation(
            feedstock=feed,
            batch_load_kg=batch_load,
            length=8.0,
            diameter=0.8,
            rpm=2.0,
            T_start_C=25.0,
            heating_rate_cmin=15.0,
            T_hold_C=700.0,
            hold_time_min=120.0,  # long hold time
            h_eff=150.0
        )
        
        results = sim.simulate(dt_sec=2.0)
        summary = results['summary']
        
        # Moisture in solids should be 0.0 at the end (evaporated fully)
        self.assertAlmostEqual(results['moisture'][-1], 0.0, places=4)
        self.assertAlmostEqual(summary['water_yield_kg'], batch_load * (feed.moisture / 100.0), places=4)
        self.assertGreater(summary['conversion_pct'], 99.0)

    def _batch(self, **kw):
        args = dict(feedstock=PETROLEUM_SLUDGE, batch_load_kg=200.0, length=6.0, diameter=0.8, rpm=3.0,
                    T_start_C=25.0, heating_rate_cmin=10.0, T_hold_C=550.0, hold_time_min=60.0, h_eff=100.0)
        args.update(kw)
        return BatchReactorSimulation(**args).simulate(dt_sec=2.0)

    def test_batch_burner_power_series_match_time(self):
        """p_oil / p_syngas must have one sample per time step and respect burner limits."""
        res = self._batch()
        self.assertEqual(len(res['p_oil']), len(res['time']))
        self.assertEqual(len(res['p_syngas']), len(res['time']))
        self.assertGreater(max(res['p_oil']), 0.0)
        self.assertLessEqual(max(res['p_syngas']), 150.0 * 745.7 * 0.85 / 1000.0 + 1e-6)

    def test_batch_api_gravity_not_predicted(self):
        """°API is no longer predicted (must come from ASTM D4052): NaN for any oil density."""
        import math
        for density in (750.0, 900.0):
            self.assertTrue(math.isnan(self._batch(bio_oil_density=density)['summary']['api_gravity']))

    def test_batch_reaction_never_exceeds_heat_input(self):
        """Solid temperature must not drop while heated (no energy created by the endothermic term)."""
        res = self._batch()
        T = res['T_solid']
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(T, T[1:])))

    def test_batch_energy_breakdown_closes(self):
        """Total heat = bed + shell + losses; syngas burned cannot exceed syngas produced."""
        s = self._batch()['summary']
        self.assertAlmostEqual(s['total_energy_kwh'], s['energy_bed_kwh'] + s['energy_shell_kwh'] + s['energy_loss_kwh'], places=6)
        self.assertGreater(s['energy_shell_kwh'], 0.0)
        self.assertLessEqual(s['syngas_burned_kg'], s['gas_yield_kg'] + 1e-9)
        self.assertAlmostEqual(s['syngas_burned_kg'] + s['syngas_flare_kg'], s['gas_yield_kg'], places=6)

    def test_batch_auto_heating_mode_heats_the_wall(self):
        """Auto mode must fire the burner (regression: wall used to stay at T_start) and finish the hold."""
        res = self._batch(auto_heating_rate=True)
        s = res['summary']
        self.assertGreaterEqual(max(res['T_wall']), 549.0)
        self.assertGreater(s['waste_oil_consumed_gal'], 0.0)
        self.assertGreater(s['conversion_pct'], 99.0)

    def test_batch_cycle_time_includes_drying(self):
        """Simulated cycle must be at least the naive ramp + hold estimate."""
        s = self._batch()['summary']
        naive_min = (550.0 - 25.0) / 10.0 + 60.0
        self.assertGreaterEqual(s['cycle_time_min'], naive_min)

    def test_batch_reports_burner_shortfall(self):
        """An undersized burner must be flagged under a manual ramp."""
        s = self._batch(burner_hp=5.0)['summary']
        self.assertGreater(s['burner_shortfall_min'], 0.0)
        s_ok = self._batch(burner_hp=5000.0)['summary']
        self.assertEqual(s_ok['burner_shortfall_min'], 0.0)

    def test_batch_pyrolysis_window_370_to_430(self):
        """No devolatilization below 370 °C; conversion completes by ~430 °C."""
        res = self._batch()
        T = res['T_solid']
        conv = res['conversion']
        below = [c for c, temp in zip(conv, T) if temp < 369.0]
        self.assertLess(max(below), 0.001)
        at_end = [c for c, temp in zip(conv, T) if temp >= 440.0]
        self.assertGreater(min(at_end), 0.99)

    def test_batch_onset_above_430_moves_window_end(self):
        """An onset above the default 430 °C end must be honoured: the window becomes onset → onset + 60."""
        import copy
        feed = copy.copy(HYDROCARBON_SLUDGE)
        feed.T_onset_K = 480.0 + 273.15
        self.assertAlmostEqual(feed.T_end_K - 273.15, 540.0)
        res = self._batch(feedstock=feed)
        below = [c for c, temp in zip(res['conversion'], res['T_solid']) if temp < 479.0]
        self.assertLess(max(below), 0.001)

    def test_batch_air_displacement_unreached_is_nan(self):
        """If headspace air is never displaced, report NaN instead of an arbitrary time."""
        res = self._batch(T_hold_C=50.0, hold_time_min=30.0)
        self.assertTrue(np.isnan(res['summary']['air_disp_complete_min']))

    # ==========================================================================
    # BLENDING TEST
    # ==========================================================================
    
    def test_feedstock_blending(self):
        """Verify feedstock blending values are computed correctly."""
        p_feed = PETROLEUM_SLUDGE
        h_feed = HYDROCARBON_SLUDGE
        
        blend = blend_feedstocks(p_feed, h_feed, 0.5)
        
        expected_moist = 0.5 * p_feed.moisture + 0.5 * h_feed.moisture
        expected_vol = 0.5 * p_feed.volatile + 0.5 * h_feed.volatile
        expected_Ea = 0.5 * p_feed.E_a + 0.5 * h_feed.E_a
        
        self.assertEqual(blend.moisture, expected_moist)
        self.assertEqual(blend.volatile, expected_vol)
        self.assertEqual(blend.E_a, expected_Ea)

    def test_char_yield_sensitivity(self):
        """Verify that increasing feedstock yield_char increases produced char."""
        feed1 = Feedstock("LowChar", moisture=10.0, volatile=60.0, fixed_carbon=10.0, ash=20.0,
                          E_a=1e5, A=1e7, yield_oil=0.60, yield_gas=0.35, yield_char=0.05)
        feed2 = Feedstock("HighChar", moisture=10.0, volatile=60.0, fixed_carbon=10.0, ash=20.0,
                          E_a=1e5, A=1e7, yield_oil=0.60, yield_gas=0.15, yield_char=0.25)
        
        sim1 = BatchReactorSimulation(feed1, batch_load_kg=100.0, length=5.0, diameter=0.5, rpm=3.0,
                                      T_start_C=20.0, heating_rate_cmin=20.0, T_hold_C=600.0, hold_time_min=60.0)
        sim2 = BatchReactorSimulation(feed2, batch_load_kg=100.0, length=5.0, diameter=0.5, rpm=3.0,
                                      T_start_C=20.0, heating_rate_cmin=20.0, T_hold_C=600.0, hold_time_min=60.0)
        
        res1 = sim1.simulate(dt_sec=2.0)['summary']
        res2 = sim2.simulate(dt_sec=2.0)['summary']
        
        self.assertGreater(res2['char_yield_kg'], res1['char_yield_kg'])
        self.assertLess(res2['gas_yield_kg'], res1['gas_yield_kg'])

    # ==========================================================================
    # ENCAPSULATION & BASE REACTOR METHOD TESTS
    # ==========================================================================

    def test_base_geometry_and_fuel_properties(self):
        """Verify encapsulated geometry properties and fuel LHV calculations."""
        from pyrolysis.reactor import BaseReactorSimulation
        
        sim = BaseReactorSimulation(
            feedstock=PETROLEUM_SLUDGE,
            length=10.0,
            diameter=1.0,
            rpm=3.0,
            h_eff=80.0,
            fuel_lhv_mj_kg=40.0,
            fuel_density_kg_l=0.90,
            fuel_moisture_pct=2.0,
            fuel_ash_pct=1.0
        )
        
        self.assertAlmostEqual(sim.radius, 0.5, places=5)
        self.assertAlmostEqual(sim.cross_sectional_area, np.pi * 0.25, places=5)
        self.assertAlmostEqual(sim.inner_surface_area, np.pi * 1.0 * 10.0, places=5)
        self.assertAlmostEqual(sim.reactor_volume, np.pi * 0.25 * 10.0, places=5)
        
        lhv_j_kg, mass_per_gal, lhv_gal = sim.get_fuel_properties()
        self.assertGreater(lhv_j_kg, 1e6)
        self.assertAlmostEqual(mass_per_gal, 0.90 * 3.78541, places=4)
        self.assertAlmostEqual(lhv_gal, lhv_j_kg * mass_per_gal, places=2)

    def test_astm_crude_properties(self):
        """Verify ASTM property correlations return valid physical ranges."""
        from pyrolysis.reactor import BaseReactorSimulation
        
        astm = BaseReactorSimulation.calculate_astm_properties(
            T_operating_C=500.0,
            initial_volatile_pct=60.0,
            moisture_feed_pct=20.0
        )
        
        # Las propiedades del aceite ya no se predicen: deben venir del laboratorio.
        import math
        for key in ('hhv_oil_mj_kg', 'api_gravity', 'viscosity_40c_cst', 'bsw_moisture_pct'):
            self.assertTrue(math.isnan(astm[key]))

    def test_devolatilization_kinetics_onset_threshold(self):
        """Verify reaction rate is zero below onset (370°C) and positive above it."""
        from pyrolysis.reactor import BaseReactorSimulation
        
        sim = BaseReactorSimulation(
            feedstock=PETROLEUM_SLUDGE,
            length=5.0,
            diameter=0.5,
            rpm=3.0,
            h_eff=100.0
        )
        
        # At 200°C (473.15 K), below onset of 370°C
        r_slug_low, k1_low, _, _ = sim.calculate_devolatilization_rate(
            T_s=200.0 + 273.15,
            T_w=250.0 + 273.15,
            m_volatile=50.0,
            m_oil_vap=0.0,
            A_contact=2.0
        )
        self.assertEqual(r_slug_low, 0.0)
        self.assertEqual(k1_low, 0.0)
        
        # At 450°C (723.15 K), above onset
        r_slug_high, k1_high, _, _ = sim.calculate_devolatilization_rate(
            T_s=450.0 + 273.15,
            T_w=500.0 + 273.15,
            m_volatile=50.0,
            m_oil_vap=0.0,
            A_contact=2.0
        )
        self.assertGreater(r_slug_high, 0.0)
        self.assertGreater(k1_high, 0.0)

    def test_resolve_drying_step(self):
        """Verify drying logic clamps solid at boiling point when evaporating."""
        from pyrolysis.reactor import BaseReactorSimulation
        
        sim = BaseReactorSimulation(
            feedstock=PETROLEUM_SLUDGE,
            length=5.0,
            diameter=0.5,
            rpm=3.0,
            h_eff=100.0
        )
        
        # When temperature reaches boiling point (373.15 K) with moisture present
        T_s = 373.15
        T_s_next = 380.0
        T_target_heat = 400.0
        m_moist = 10.0
        thermal_mass = 50000.0
        H_rxn = 0.0
        
        T_res, d_moist = sim.resolve_drying_step(
            T_s=T_s,
            T_s_next=T_s_next,
            T_target_heat=T_target_heat,
            m_moist=m_moist,
            thermal_mass=thermal_mass,
            H_rxn=H_rxn
        )
        
        self.assertGreater(d_moist, 0.0)
        self.assertLessEqual(d_moist, m_moist)
        # Should be clamped near boiling point
        self.assertAlmostEqual(T_res, 373.15, places=1)



class TestThesisProfile(unittest.TestCase):
    def test_thesis_profile_reproduces_run(self):
        from pyrolysis.profiles import thesis_batch_kwargs
        from pyrolysis.reactor.batch import BatchReactorSimulation
        s = BatchReactorSimulation(**thesis_batch_kwargs()).simulate(dt_sec=2.0)['summary']
        # aceite al apagar: 2,431 gal = 60.56 % de la carga (h_eff 266.0, A2 × 0.703, sostenimiento 96.5 min)
        self.assertAlmostEqual(s['oil_yield_pct'], 60.56, delta=0.1)
        # rampa 50 → 550 °C a 1.5 °C/min (333.3 min) + 96.5 min de sostenimiento
        self.assertAlmostEqual(s['cycle_time_min'], 429.8, delta=1.0)
        self.assertAlmostEqual(s['water_yield_pct'], 2.0, delta=0.05)


class TestFinancialModel(unittest.TestCase):
    # Loses money with no tipping fee (no tax) and pays tax above ~6 RD$/gal: NPV is not a straight line.
    BASE = dict(
        total_capex=1e6, sludge_treated_gal=1e5, oil_produced_gal=0, char_produced_kg=0, gas_produced_m3=0,
        fuel_consumed_gal=0, elec_consumed_kwh=0, generator_fuel_consumed_gal=0,
        opex_handling=0, opex_fuel=0, opex_electricity=0, opex_aux_utilities=5e5, price_generator_fuel=0,
        opex_labor=0, opex_maint=0, opex_insurance_tax=0, opex_tipping=9.0,
        price_oil=0, price_char=0, price_gas=0, price_carbon=0, rate_carbon_offset=0,
        discount_rate=14.0, project_lifetime=10, tax_rate=25.0, inflation_rate=4.0,
    )

    def _model(self, **kw):
        from pyrolysis.gui.economics_panel import run_financial_model
        return run_financial_model(**dict(self.BASE, **kw))

    def test_npv_is_zero_at_breakeven_tipping_fee(self):
        breakeven = self._model()['breakeven_tipping']
        self.assertAlmostEqual(self._model(opex_tipping=breakeven)['npv'], 0.0, delta=1.0)

    def test_npv_is_zero_at_irr(self):
        irr = self._model()['irr']
        self.assertIsNotNone(irr)
        self.assertAlmostEqual(self._model(discount_rate=irr)['npv'], 0.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()


