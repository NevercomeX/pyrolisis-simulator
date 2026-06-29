import unittest
import numpy as np
from pyrolysis import PETROLEUM_SLUDGE, HYDROCARBON_SLUDGE, blend_feedstocks, ContinuousReactorSimulation, BatchReactorSimulation

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

if __name__ == "__main__":
    unittest.main()
