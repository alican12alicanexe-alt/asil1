"""End-to-end: the corridor3 scenario must run clean and behave as designed."""

import unittest

import support
from trainsim.scenario import checks
from trainsim.scenario.loader import build_simulation, load_scenario


class TestCorridor3(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(support.CORRIDOR3)

    def test_infrastructure_expands_as_expected(self):
        infra = self.scenario.infrastructure
        self.assertEqual(len(infra.network.stations), 3)
        self.assertEqual(len(infra.network.platforms), 7)
        # One signal per block, plus one extra where the two Beta up roads
        # converge - each approaching road needs its own signal.
        self.assertEqual(len(infra.signals), len(infra.blocks) + 1)
        # Beta has three platform roads; two of them share the up line.
        beta = infra.network.stations["BETA"]
        self.assertEqual(len(beta.platforms), 3)
        up_roads = [p for p in infra.network.platforms_at("BETA", track="UP")]
        self.assertEqual({p.id for p in up_roads}, {"BETA_1", "BETA_3"})
        # Parallel roads share both nodes, which is what makes them alternatives.
        first, second = (infra.network.segments["BETA_1"],
                         infra.network.segments["BETA_3"])
        self.assertEqual(first.start_node, second.start_node)
        self.assertEqual(first.end_node, second.end_node)

    def test_block_lengths_are_signalable(self):
        """Every block must be long enough to brake in from line speed."""
        results = checks.check_block_lengths(
            self.scenario.infrastructure, self.scenario.timetable,
            self.scenario.driver_config,
        )
        self.assertTrue(results)
        self.assertEqual(
            checks.failures(results), [],
            "some blocks are shorter than the braking distance from line speed",
        )

    def test_block_lengths_are_not_uniform(self):
        """The busy inner section is signalled more tightly than the open line."""
        infra = self.scenario.infrastructure
        inner = [b.length_m for b in infra.blocks.values()
                 if b.track == "UP" and b.platform is None and b.km_end <= 12]
        outer = [b.length_m for b in infra.blocks.values()
                 if b.track == "UP" and b.platform is None and b.km_start >= 12]
        self.assertTrue(inner and outer)
        self.assertLess(max(inner), min(outer))

    def test_full_run_is_clean(self):
        """Every service completes, and no block ever holds two trains."""
        sim = build_simulation(self.scenario, {"strict": True})
        while not sim.finished:
            sim.step()
            self.assertEqual(sim.occupancy.check_exclusivity(), [])

        self.assertEqual(sim.violations, [])
        self.assertEqual(len(sim.trains), 9, "not every service was introduced")
        self.assertEqual(sim.dispatcher.pending_count, 0)
        for train in sim.trains.values():
            self.assertEqual(train.state, "finished",
                             "%s did not complete: %s" % (train.id, train.state))
            self.assertEqual(train.next_stop_index, len(train.stops),
                             "%s missed a booked call" % (train.id,))

    def test_the_overtake_at_beta_happens(self):
        """The stopper stands in the loop while the fast runs through."""
        sim = build_simulation(self.scenario, {"strict": True})
        loop, through = [], []
        while not sim.finished:
            sim.step()
            if sim.occupancy.trains_in("BETA_3"):
                loop.append((sim.time_s, sorted(sim.occupancy.trains_in("BETA_3"))))
            if sim.occupancy.trains_in("BETA_1"):
                through.append((sim.time_s, sorted(sim.occupancy.trains_in("BETA_1"))))

        self.assertTrue(loop, "nothing ever used the loop road")
        self.assertTrue(through, "nothing ever used the through platform")

        # S1 is in the loop for a window that contains F1's passage of BETA_1.
        s1 = [t for t, trains in loop if trains == ["S1"]]
        f1 = [t for t, trains in through if trains == ["F1"]]
        self.assertTrue(s1 and f1)
        self.assertLess(min(s1), min(f1), "the fast reached Beta before the stopper")
        self.assertGreater(max(s1), max(f1), "the fast did not overtake inside the loop")

    def test_the_fast_is_checked_down_behind_the_stopper(self):
        """Fixed block must visibly cost the fast train time - not run free."""
        sim = build_simulation(self.scenario)
        checked = 0
        while not sim.finished:
            sim.step()
            for train in sim.trains.values():
                if train.state == "running" and "caution" in train.authority_reason:
                    checked += 1
        self.assertGreater(
            checked, 30,
            "no train was ever restrained by signalling; the timetable is too "
            "loose to demonstrate anything about capacity",
        )

    def test_headless_and_view_share_one_simulation_path(self):
        """Two runs of the same scenario must be identical - the kernel is deterministic."""
        first = build_simulation(self.scenario)
        second = build_simulation(self.scenario)
        first.run()
        second.run()
        self.assertEqual(
            [(t.id, round(t.chainage_m, 6), t.state)
             for t in sorted(first.trains.values(), key=lambda x: x.id)],
            [(t.id, round(t.chainage_m, 6), t.state)
             for t in sorted(second.trains.values(), key=lambda x: x.id)],
        )


if __name__ == "__main__":
    unittest.main()
