"""Three-aspect signalling: aspects, and the rule that trains stop at red.

The red-signal test is the one that matters. It places a standing train in a
block and drives another at it; the follower must come to a stand *before* the
protecting signal, on its own, from the movement authority alone.
"""

import unittest

import support
from trainsim.core.signals import Aspect, compute_aspects
from trainsim.core.units import kmh_to_ms


class TestAspects(unittest.TestCase):

    def setUp(self):
        self.sim, self.infra, self.timetable = support.build_test_sim(
            dispatcher=support.ManualDispatcher()
        )
        self.blocks = support.running_blocks(self.infra)

    def _aspect_of(self, block):
        return compute_aspects(self.infra.blocks, self.infra.signals, self.sim.occupancy)[block.signal_id]

    def test_all_green_when_the_line_is_clear(self):
        aspects = compute_aspects(self.infra.blocks, self.infra.signals, self.sim.occupancy)
        self.assertEqual(set(aspects.values()), {Aspect.GREEN})

    def test_red_protects_an_occupied_block(self):
        self.sim.occupancy.set_train_blocks("X", [self.blocks[2].id])
        self.assertEqual(self._aspect_of(self.blocks[2]), Aspect.RED)

    def test_yellow_precedes_a_red(self):
        self.sim.occupancy.set_train_blocks("X", [self.blocks[2].id])
        self.assertEqual(self._aspect_of(self.blocks[1]), Aspect.YELLOW)
        self.assertEqual(self._aspect_of(self.blocks[0]), Aspect.GREEN)

    def test_divergence_takes_the_least_restrictive_successor(self):
        """At Beta one up road may be blocked while the other is clear."""
        from trainsim.scenario.loader import load_scenario
        scenario = load_scenario(support.CORRIDOR3)
        infra = scenario.infrastructure
        occupancy = type(self.sim.occupancy)(infra.blocks)

        approach = max(
            (b for b in infra.blocks.values()
             if b.track == "UP" and b.platform is None and b.km_end <= 11.81),
            key=lambda b: b.km_end,
        )
        self.assertEqual(set(approach.successors), {"BETA_1", "BETA_3"})

        occupancy.set_train_blocks("X", ["BETA_1"])
        self.assertEqual(
            compute_aspects(infra.blocks, infra.signals, occupancy)[approach.signal_id],
            Aspect.GREEN,
            "the loop road is still clear, so the approach signal may show green",
        )
        occupancy.set_train_blocks("Y", ["BETA_3"])
        self.assertEqual(
            compute_aspects(infra.blocks, infra.signals, occupancy)[approach.signal_id],
            Aspect.YELLOW,
            "both roads blocked: caution, be ready to stop at the next signal",
        )


class TestTrainsObeySignals(unittest.TestCase):

    def test_follower_stops_before_a_signal_at_danger(self):
        sim, infra, timetable = support.build_test_sim(
            dispatcher=support.ManualDispatcher(), duration_s=1200.0,
        )
        service = timetable.services[0]
        blocks = support.running_blocks(infra)
        blocked = blocks[3]

        # A standing train fills block 4, so its protecting signal shows red.
        leader = service.create_train()
        leader.id = "LEADER"
        danger_point = support.block_start_on_path(leader.path, blocked.id)
        leader.chainage_m = danger_point + blocked.length_m * 0.5
        leader.state = "dwelling"
        leader.dwell_until_s = 1e9
        leader.speed_ms = 0.0
        sim.trains["LEADER"] = leader

        follower = service.create_train()
        follower.id = "FOLLOWER"
        follower.state = "running"
        sim.trains["FOLLOWER"] = follower

        sim.refresh_occupancy()
        sim.aspects = compute_aspects(infra.blocks, infra.signals, sim.occupancy)
        self.assertEqual(sim.aspects[blocked.signal_id], Aspect.RED)

        for _ in range(900):
            sim.step()
            self.assertLess(
                follower.chainage_m, danger_point,
                "the follower passed a signal at danger at %s" % sim.clock,
            )
            if follower.speed_ms == 0.0 and follower.chainage_m > 1000.0:
                break

        self.assertEqual(follower.speed_ms, 0.0, "the follower never stopped")
        # Stopped short of the signal, but close to it - not braking absurdly early.
        gap = danger_point - follower.chainage_m
        self.assertGreater(gap, 0.0)
        self.assertLess(gap, 120.0, "stopped %.0f m short of the signal" % gap)
        self.assertEqual(sim.violations, [])

    def test_follower_is_released_when_the_block_clears(self):
        """Once the obstruction goes, the held train must get going again."""
        sim, infra, timetable = support.build_test_sim(
            dispatcher=support.ManualDispatcher(), duration_s=2400.0,
        )
        service = timetable.services[0]
        blocks = support.running_blocks(infra)
        blocked = blocks[3]

        leader = service.create_train()
        leader.id = "LEADER"
        danger_point = support.block_start_on_path(leader.path, blocked.id)
        leader.chainage_m = danger_point + blocked.length_m * 0.5
        leader.state = "dwelling"
        leader.dwell_until_s = 1e9
        sim.trains["LEADER"] = leader

        follower = service.create_train()
        follower.id = "FOLLOWER"
        follower.state = "running"
        sim.trains["FOLLOWER"] = follower
        sim.refresh_occupancy()
        sim.aspects = compute_aspects(infra.blocks, infra.signals, sim.occupancy)

        for _ in range(900):
            sim.step()
            if follower.speed_ms == 0.0 and follower.chainage_m > 1000.0:
                break
        held_at = follower.chainage_m
        self.assertGreater(held_at, 1000.0)

        # Clear the road.
        leader.state = "finished"
        sim.occupancy.remove_train("LEADER")
        for _ in range(120):
            sim.step()

        self.assertGreater(follower.chainage_m, held_at + 100.0,
                           "the follower stayed put after the block cleared")
        self.assertGreater(follower.speed_ms, kmh_to_ms(20))


if __name__ == "__main__":
    unittest.main()
