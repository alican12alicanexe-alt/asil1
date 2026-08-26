"""The interlocking: points, routes, locking and sectional release.

The test that carries the most weight is
:meth:`TestSectionalRelease.test_points_are_released_behind_a_standing_train`.
Hold the points until a whole route clears and a train dwelling in a loop blocks
the road behind it, which would make the overtake the loop exists for impossible.
Sectional release is what prevents that, so it is asserted directly rather than
only through its effect.
"""

import unittest

import support
from trainsim.core.signals import Aspect
from trainsim.scenario.loader import build_simulation, load_scenario


class InterlockingTestCase(unittest.TestCase):

    def setUp(self):
        self.scenario = load_scenario(support.CORRIDOR3)
        self.sim = build_simulation(self.scenario)
        self.infra = self.scenario.infrastructure
        self.interlocking = self.sim.interlocking
        self.facing = "PT_UP_11250_F"
        self.trailing = "PT_UP_12750_T"

    def run_to(self, clock: str):
        from trainsim.core.units import parse_clock
        target = parse_clock(clock)
        while self.sim.time_s < target and not self.sim.finished:
            self.sim.step()


class TestTopology(InterlockingTestCase):

    def test_points_are_derived_not_declared(self):
        """Nothing in the scenario file mentions points; they come from topology."""
        points = self.infra.points
        self.assertEqual(len(points), 2)
        self.assertEqual(points[self.facing].kind, "facing")
        self.assertEqual(points[self.trailing].kind, "trailing")
        for point in points.values():
            self.assertEqual(set(point.legs), {"BETA_1", "BETA_3"})
            self.assertEqual(point.normal, "BETA_1",
                             "the through road should be the normal position")

    def test_converging_roads_get_a_signal_each(self):
        """A trailing point means two trains ask different questions of one block."""
        block = next(b for b in self.infra.blocks.values()
                     if b.entry_node == self.infra.points[self.trailing].node)
        self.assertEqual(len(block.signal_ids), 2)
        legs = {self.infra.signals[s].from_segment for s in block.signal_ids}
        self.assertEqual(legs, {"BETA_1", "BETA_3"})

    def test_only_signals_over_points_are_controlled(self):
        controlled = self.infra.controlled_signals()
        self.assertEqual(len(controlled), 4)
        for signal_id in controlled:
            route_id = self.interlocking.route_for_signal(signal_id)
            self.assertTrue(self.infra.routes[route_id].points,
                            "a controlled signal must read over points")
        # Everything else is plain automatic block and needs no request.
        automatic = [s for s in self.infra.signals.values() if not s.controlled]
        self.assertGreater(len(automatic), 25)

    def test_a_route_does_not_reach_past_its_exit_signal(self):
        """The route into the loop must not hold the points at the far end.

        If it did, a train standing in the loop would keep the exit points, and
        nothing could be routed past it.
        """
        into_loop = self.infra.routes["R_BETA_3"]
        self.assertEqual(set(into_loop.points), {self.facing})
        self.assertNotIn(self.trailing, into_loop.points)


class TestRequests(InterlockingTestCase):

    def test_a_controlled_signal_stays_at_danger_without_a_route(self):
        self.assertEqual(self.sim.aspects["S_BETA_1"], Aspect.RED)
        self.assertEqual(self.sim.aspects["S_BETA_3"], Aspect.RED)

    def test_granting_a_route_moves_and_locks_the_points(self):
        decision = self.interlocking.request("R_BETA_3", "TEST", self.sim)
        self.assertTrue(decision.granted, decision.reason)
        self.assertEqual(self.interlocking.point_position[self.facing], "BETA_3")
        self.assertEqual(self.interlocking.point_locked_by[self.facing], "R_BETA_3")
        self.sim.refresh_aspects()
        self.assertNotEqual(self.sim.aspects["S_BETA_3"], Aspect.RED)

    def test_a_conflicting_route_is_refused_with_a_reason(self):
        self.interlocking.request("R_BETA_3", "FIRST", self.sim)
        decision = self.interlocking.request("R_BETA_1", "SECOND", self.sim)
        self.assertFalse(decision.granted)
        self.assertIn(self.facing, decision.reason)
        self.assertIn("FIRST", decision.reason)
        # ...and the points did not move under the first train.
        self.assertEqual(self.interlocking.point_position[self.facing], "BETA_3")

    def test_a_route_over_an_occupied_block_is_refused(self):
        self.sim.occupancy.set_train_blocks("SQUATTER", ["BETA_1"])
        decision = self.interlocking.request("R_BETA_1", "TEST", self.sim)
        self.assertFalse(decision.granted)
        self.assertIn("SQUATTER", decision.reason)

    def test_an_unknown_route_is_refused_rather_than_raising(self):
        decision = self.interlocking.request("R_NOWHERE", "TEST", self.sim)
        self.assertFalse(decision.granted)
        self.assertIn("no such route", decision.reason)

    def test_the_signal_behind_an_unset_route_shows_caution(self):
        """A driver must be warned about a signal at danger, whatever the cause.

        Aspects are computed from the signal ahead, not from track occupancy, so
        'no route set' propagates back as a yellow exactly as an occupied block
        would. Without that a train would meet a green followed by a red.
        """
        approach = next(
            b for b in self.infra.blocks.values()
            if "BETA_1" in b.successors and b.platform is None
        )
        self.assertEqual(self.sim.aspects[approach.signal_ids[0]], Aspect.YELLOW)

        self.interlocking.request("R_BETA_1", "TEST", self.sim)
        self.sim.refresh_aspects()
        self.assertEqual(self.sim.aspects[approach.signal_ids[0]], Aspect.GREEN)


class TestSectionalRelease(InterlockingTestCase):

    def test_points_are_released_behind_a_standing_train(self):
        """The heart of it: a train dwelling in the loop frees the road behind.

        Asserted from the event log rather than a snapshot, because the whole
        sequence is the claim: S1 takes the loop, releases the points behind it
        while still standing there, and F1 then throws those same points the
        other way and overtakes - all before S1 has moved.
        """
        self.sim.run()

        loop_entry, loop_exit = self._occupation_window("BETA_3", "S1")
        released = self._event_time("points_released", "S1", self.facing)
        relocked = self._event_time("points", "F1", self.facing)

        self.assertIsNotNone(released, "the facing point was never released")
        self.assertIsNotNone(relocked, "F1 never got the points")

        self.assertGreater(released, loop_entry,
                           "released before S1 even reached the loop")
        self.assertLess(released, loop_exit,
                        "the points were only released after S1 left - sectional "
                        "release is not working, and no overtake is possible")
        self.assertGreater(relocked, released)
        self.assertLess(relocked, loop_exit,
                        "F1 took the points only after S1 had gone, so nothing "
                        "was actually overtaken")

    def _occupation_window(self, block_id, train_id):
        """First and last time ``train_id`` occupied ``block_id``, from a fresh run."""
        sim = build_simulation(self.scenario)
        times = []
        while not sim.finished:
            sim.step()
            if train_id in sim.occupancy.trains_in(block_id):
                times.append(sim.time_s)
        self.assertTrue(times, "%s never occupied %s" % (train_id, block_id))
        return min(times), max(times)

    def _event_time(self, kind, train_id, needle):
        for event in self.sim.events:
            if (event.kind == kind and event.train_id == train_id
                    and needle in event.detail):
                return event.time_s
        return None

    def test_a_route_is_given_back_once_the_train_has_gone(self):
        self.run_to("07:07:00")
        self.assertTrue(self.interlocking.is_locked("R_BETA_3"))
        self.run_to("07:12:00")
        self.assertFalse(self.interlocking.is_locked("R_BETA_3"),
                         "the loop should be released after S1 has left it")
        self.assertIsNone(self.interlocking.point_locked_by[self.trailing])

    def test_nothing_stays_locked_at_the_end_of_the_day(self):
        self.sim.run()
        self.assertEqual(self.interlocking.locked_routes(), ())
        for point_id, holder in self.interlocking.point_locked_by.items():
            self.assertIsNone(holder, "%s left locked" % point_id)


class TestApproachLocking(InterlockingTestCase):

    def test_a_route_cannot_be_taken_from_an_approaching_train(self):
        self.run_to("07:04:30")
        self.assertTrue(self.interlocking.is_locked("R_BETA_3"))
        s1 = self.sim.trains["S1"]
        self.assertEqual(s1.state, "running")

        decision = self.interlocking.cancel("R_BETA_3", self.sim)
        self.assertFalse(decision.granted)
        self.assertIn("approach locked", decision.reason)

    def test_a_route_no_train_is_near_can_be_given_back(self):
        decision = self.interlocking.request("R_BETA_1", "GHOST", self.sim)
        self.assertTrue(decision.granted)
        cancelled = self.interlocking.cancel("R_BETA_1", self.sim)
        self.assertTrue(cancelled.granted, cancelled.reason)
        self.assertFalse(self.interlocking.is_locked("R_BETA_1"))
        self.assertIsNone(self.interlocking.point_locked_by[self.facing])


class TestOverlaps(InterlockingTestCase):

    def test_overlaps_are_off_by_default_but_available(self):
        for route in self.infra.routes.values():
            self.assertEqual(route.overlap_blocks, ())

    def test_an_overlap_holds_the_block_beyond(self):
        """With overlaps on, the block past the exit signal must also be clear.

        Overlaps are a margin against a signal being passed at danger, and they
        cost capacity - which is why they are a scenario setting rather than
        always-on, so the cost can be measured.
        """
        from trainsim.scenario.builder import build_infrastructure
        from trainsim.scenario.loader import read_data_file
        import os

        spec = read_data_file(os.path.join(support.CORRIDOR3, "infrastructure.yaml"))
        infra = build_infrastructure(spec, overlaps=True)
        with_overlap = [r for r in infra.routes.values() if r.overlap_blocks]
        self.assertTrue(with_overlap, "no route gained an overlap")

        route = infra.routes["R_BETA_1"]
        self.assertEqual(len(route.overlap_blocks), 1)


class TestWholeRunWithInterlocking(InterlockingTestCase):

    def test_the_overtake_still_happens_through_the_interlocking(self):
        loop, through = [], []
        while not self.sim.finished:
            self.sim.step()
            self.assertEqual(self.sim.occupancy.check_exclusivity(), [])
            if self.sim.occupancy.trains_in("BETA_3") == {"S1"}:
                loop.append(self.sim.time_s)
            if self.sim.occupancy.trains_in("BETA_1") == {"F1"}:
                through.append(self.sim.time_s)

        self.assertTrue(loop and through)
        self.assertLess(min(loop), min(through))
        self.assertGreater(max(loop), max(through),
                           "F1 did not pass while S1 was standing in the loop")
        self.assertEqual(self.sim.violations, [])
        for train in self.sim.trains.values():
            self.assertEqual(train.state, "finished", "%s stalled" % train.id)

    def test_the_route_request_lead_decides_whether_the_overtake_works(self):
        """Ask for the departure route too early and the overtake is lost.

        A dispatching decision, not a detail: a train that claims the points at
        the far end of the loop at the moment it arrives holds them for its whole
        dwell, and the train meant to overtake is stopped behind it.
        """
        scenario = load_scenario(support.CORRIDOR3)
        sim = build_simulation(scenario)
        sim.dispatcher.route_request_lead_s = 10000.0  # ask the instant it berths

        refusals = 0
        while not sim.finished:
            sim.step()
            refusals = sum(1 for e in sim.events if e.kind == "route_refused")
        self.assertGreater(
            refusals, 0,
            "with an eager route request the fast should have been refused the "
            "road past the loop",
        )


if __name__ == "__main__":
    unittest.main()
