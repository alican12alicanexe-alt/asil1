"""The ETCS levels, and the comparison between them.

The claim this milestone makes is that the differences between train control
systems fall out of the model rather than being tuned in. These tests hold that
claim to account:

* the ladder must be *monotonic* - each level at least as good as the one below
  on the same timetable, same trains, same interlocking
* a mixed fleet must make Hybrid Level 3 and moving block **degrade**, not fail
* below capacity the levels must *converge*, because there is nothing to win

The last one matters as much as the first. A model that showed moving block
winning on an empty railway would be flattering the technology, not measuring it.
"""

import unittest

import support
from trainsim.analysis import kpi
from trainsim.core import vss
from trainsim.core.signalling import (ETCSLevel1, ETCSLevel2, HybridLevel3,
                                      LADDER, MovingBlock, REGISTRY, create)
from trainsim.core.units import kmh_to_ms
from trainsim.scenario.loader import build_simulation, load_scenario


def run_under(path, system):
    scenario = load_scenario(path)
    scenario.signalling_spec = {"system": system}
    return kpi.measure(build_simulation(scenario))


class TestRegistry(unittest.TestCase):

    def test_every_ladder_entry_is_buildable(self):
        for name in LADDER:
            self.assertIn(name, REGISTRY)
            system = create(name)
            self.assertEqual(system.name, name)
            self.assertTrue(system.describe())

    def test_unknown_system_is_reported_helpfully(self):
        with self.assertRaises(ValueError) as caught:
            create("etcs_l9")
        self.assertIn("etcs_l2", str(caught.exception))

    def test_lineside_signals_are_declared(self):
        """The view draws lamps or marker boards from this, so it must be right.

        Level 1 is an overlay and keeps its signals; Level 2 and above put the
        authority in the cab and leave nothing lit at the lineside.
        """
        self.assertTrue(create("fixed_block_3aspect").has_lineside_signals)
        self.assertTrue(create("etcs_l1").has_lineside_signals)
        self.assertFalse(create("etcs_l2").has_lineside_signals)
        self.assertFalse(create("etcs_hybrid_l3").has_lineside_signals)
        self.assertFalse(create("etcs_moving_block").has_lineside_signals)

    def test_separation_model_is_declared(self):
        """The kernel picks its safety invariant from this, so it must be right."""
        self.assertEqual(create("fixed_block_3aspect").separates_by, "block")
        self.assertEqual(create("etcs_l1").separates_by, "block")
        self.assertEqual(create("etcs_l2").separates_by, "block")
        self.assertEqual(create("etcs_hybrid_l3").separates_by, "distance")
        self.assertEqual(create("etcs_moving_block").separates_by, "distance")


class TestBrakingEnvelope(unittest.TestCase):
    """The moving block itself: the space a train needs to stop."""

    def _train(self, speed_kmh):
        _, _, timetable = support.build_test_sim()
        train = timetable.services[0].create_train()
        train.speed_ms = kmh_to_ms(speed_kmh)
        return train

    def test_a_stationary_train_needs_nothing(self):
        self.assertEqual(self._train(0).stopping_distance_m(2.0), 0.0)

    def test_it_matches_the_braking_curve(self):
        from trainsim.core.units import braking_distance
        train = self._train(140)
        expected = braking_distance(train.speed_ms, train.stock.service_brake)
        self.assertAlmostEqual(train.stopping_distance_m(0.0), expected, places=6)

    def test_reaction_time_adds_the_distance_run_before_braking(self):
        train = self._train(140)
        extra = train.stopping_distance_m(2.0) - train.stopping_distance_m(0.0)
        self.assertAlmostEqual(extra, train.speed_ms * 2.0, places=6)

    def test_it_shrinks_as_the_train_slows(self):
        """Why moving block is 'moving': the zone is not a fixed length of track."""
        fast = self._train(140).stopping_distance_m(2.0)
        slow = self._train(70).stopping_distance_m(2.0)
        self.assertLess(slow, fast / 2.0)

    def test_it_is_far_shorter_than_a_block(self):
        """The gap fixed block wastes, and what moving block reclaims."""
        _, infra, _ = support.build_test_sim()
        shortest = min(b.length_m for b in support.running_blocks(infra))
        needed = self._train(140).stopping_distance_m(2.0)
        self.assertLess(needed, shortest,
                        "a block must be longer than the braking distance, or the "
                        "layout is unsignalable")


class TestVirtualSubSections(unittest.TestCase):

    def _state_with(self, stock_spec):
        timetable = {
            "stock": [stock_spec],
            "services": [{
                "id": "T1", "stock": stock_spec["id"], "departure": "08:00:00",
                "calls": [
                    {"station": "A", "platform": "A_1", "departure": "08:00:00",
                     "dwell_s": 0},
                    {"station": "B", "platform": "B_1", "dwell_s": 30},
                ],
            }],
        }
        sim, infra, _ = support.build_test_sim(timetable_spec=timetable)
        state = vss.VSSState(vss.subdivide(infra.blocks, 4))
        for _ in range(240):          # let the train get well out onto the line
            sim.step()
        vss.update(state, sim)
        return state, sim

    def test_subdivision_covers_each_block_exactly(self):
        _, infra, _ = support.build_test_sim()
        table = vss.subdivide(infra.blocks, 4)
        for block_id, sections in table.items():
            self.assertEqual(len(sections), 4)
            self.assertAlmostEqual(sections[0].from_fraction, 0.0)
            self.assertAlmostEqual(sections[-1].to_fraction, 1.0)
            total = sum(s.length_m for s in sections)
            self.assertAlmostEqual(total, infra.blocks[block_id].length_m, places=6)

    def test_a_fitted_train_resolves_to_sub_sections(self):
        """Position reporting plus integrity: only the sub-sections it covers."""
        state, _ = self._state_with(support.stock("FIT", etcs_level="l2", tims=True))
        counts = state.counts()
        self.assertGreater(counts[vss.OCCUPIED], 0)
        self.assertEqual(counts[vss.UNKNOWN], 0)
        self.assertEqual(counts[vss.AMBIGUOUS], 0)
        # A 200 m train cannot fill a 460 m block: some sub-sections stay free.
        self.assertGreater(counts[vss.FREE], 0)

    def test_no_integrity_leaves_ambiguity_behind_the_train(self):
        """Without TIMS the rear is not trustworthy, so what is behind is unsure."""
        state, _ = self._state_with(support.stock("NOTIMS", etcs_level="l2",
                                                  tims=False))
        counts = state.counts()
        self.assertGreater(counts[vss.OCCUPIED], 0)
        self.assertGreater(counts[vss.AMBIGUOUS], 0,
                           "sub-sections behind an unconfirmed train must be "
                           "ambiguous, not free")

    def test_an_unfitted_train_makes_its_whole_block_unknown(self):
        """No position report: the trackside section is all it knows."""
        state, _ = self._state_with(support.stock("UNFIT", etcs_level="none",
                                                  tims=False))
        counts = state.counts()
        self.assertEqual(counts[vss.OCCUPIED], 0)
        self.assertGreater(counts[vss.UNKNOWN], 0)

    def test_only_free_sub_sections_may_be_given_away(self):
        state, sim = self._state_with(support.stock("FIT"))
        for state_name in (vss.OCCUPIED, vss.AMBIGUOUS, vss.UNKNOWN):
            self.assertGreater(vss.SEVERITY[state_name], vss.SEVERITY[vss.FREE])

    def test_the_worst_claim_on_a_sub_section_wins(self):
        _, infra, _ = support.build_test_sim()
        state = vss.VSSState(vss.subdivide(infra.blocks, 2))
        first = next(iter(state.state))
        state.claim(first, vss.AMBIGUOUS)
        state.claim(first, vss.OCCUPIED)
        state.claim(first, vss.FREE)
        self.assertEqual(state.of(first), vss.OCCUPIED)


class TestLadderOnADenseTimetable(unittest.TestCase):
    """The capacity experiment: a 90-second interval, above fixed-block capacity."""

    @classmethod
    def setUpClass(cls):
        cls.results = {name: run_under(support.INTENSIVE, name) for name in LADDER}

    def test_every_system_completes_every_service_safely(self):
        for name, row in self.results.items():
            self.assertEqual(row.violations, 0, "%s: %d violations" % (name, row.violations))
            self.assertEqual(row.completed, row.services,
                             "%s completed only %d of %d"
                             % (name, row.completed, row.services))

    def test_restraint_falls_monotonically_up_the_ladder(self):
        """Each level should hold trains back no more than the one below it."""
        previous = None
        for name in LADDER:
            restrained = self.results[name].total_restrained_s
            if previous is not None:
                self.assertLessEqual(
                    restrained, previous[1] + 1e-6,
                    "%s restrains trains more than %s (%.0fs vs %.0fs)"
                    % (name, previous[0], restrained, previous[1]),
                )
            previous = (name, restrained)

    def test_authority_length_grows_up_the_ladder(self):
        """The mechanism, not just the outcome: better systems grant further."""
        fixed = self.results["fixed_block_3aspect"].mean_authority_m
        moving = self.results["etcs_moving_block"].mean_authority_m
        self.assertGreater(moving, fixed * 1.5)

    def test_journey_times_improve_up_the_ladder(self):
        previous = None
        for name in LADDER:
            journey = self.results[name].mean_journey_s
            if previous is not None:
                self.assertLessEqual(
                    journey, previous[1] + 1.0,
                    "%s is slower than %s" % (name, previous[0]),
                )
            previous = (name, journey)

    def test_moving_block_beats_fixed_block_substantially(self):
        fixed = self.results["fixed_block_3aspect"].mean_journey_s
        moving = self.results["etcs_moving_block"].mean_journey_s
        self.assertGreater(fixed - moving, 120.0,
                           "moving block should save minutes at this density")

    def test_hybrid_l3_captures_most_of_moving_block(self):
        """Its selling point: most of L3's benefit without a fully fitted fleet."""
        fixed = self.results["fixed_block_3aspect"].mean_journey_s
        hybrid = self.results["etcs_hybrid_l3"].mean_journey_s
        moving = self.results["etcs_moving_block"].mean_journey_s
        available = fixed - moving
        captured = fixed - hybrid
        self.assertGreater(captured / available, 0.8)


class TestLadderBelowCapacity(unittest.TestCase):
    """On a railway that is not busy, the levels must converge."""

    @classmethod
    def setUpClass(cls):
        cls.results = {name: run_under(support.CORRIDOR3, name)
                       for name in ("fixed_block_3aspect", "etcs_l2",
                                    "etcs_moving_block")}

    def test_below_capacity_moving_block_wins_almost_nothing(self):
        fixed = self.results["fixed_block_3aspect"].mean_journey_s
        moving = self.results["etcs_moving_block"].mean_journey_s
        self.assertLess(
            fixed - moving, 60.0,
            "below capacity there is nothing for moving block to win; a large "
            "gain here would mean the model is flattering it",
        )

    def test_level_2_already_captures_it(self):
        level2 = self.results["etcs_l2"].mean_journey_s
        moving = self.results["etcs_moving_block"].mean_journey_s
        self.assertAlmostEqual(level2, moving, delta=5.0)


class TestMixedFitmentDegrades(unittest.TestCase):
    """A fleet that cannot all report position must degrade, not break."""

    def _two_service_timetable(self, leader_stock, follower_stock):
        return {
            "stock": [leader_stock, follower_stock],
            "services": [
                {"id": "LEAD", "stock": leader_stock["id"], "departure": "08:00:00",
                 "calls": [
                     {"station": "A", "platform": "A_1", "departure": "08:00:00",
                      "dwell_s": 0},
                     {"station": "B", "platform": "B_1", "dwell_s": 30}]},
                {"id": "FOLLOW", "stock": follower_stock["id"],
                 "departure": "08:01:00", "ready_lead_s": 30,
                 "calls": [
                     {"station": "A", "platform": "A_1", "departure": "08:01:00",
                      "dwell_s": 0},
                     {"station": "B", "platform": "B_1", "dwell_s": 30}]},
            ],
        }

    def _closest_approach(self, leader_stock, system):
        timetable = self._two_service_timetable(
            leader_stock, support.stock("FOLLOWER", etcs_level="l3", tims=True))
        sim, _, _ = support.build_test_sim(
            timetable_spec=timetable, signalling=system, duration_s=2400.0,
        )
        closest = None
        while not sim.finished:
            sim.step()
            lead, follow = sim.trains.get("LEAD"), sim.trains.get("FOLLOW")
            if not (lead and follow and lead.is_active and follow.is_active):
                continue
            # Only while the follower is actually following: standing in the
            # origin platform it is close to nothing but the timetable.
            if follow.state != "running" or follow.chainage_m < 1000.0:
                continue
            gap = lead.rear_m - follow.chainage_m
            if gap > 0 and (closest is None or gap < closest):
                closest = gap
        self.assertEqual(sim.violations, [])
        return closest

    def test_moving_block_follows_a_fitted_train_closely(self):
        gap = self._closest_approach(
            support.stock("FITTED", etcs_level="l3", tims=True),
            MovingBlock(safety_margin_m=100.0),
        )
        self.assertIsNotNone(gap)
        self.assertLess(gap, 400.0, "moving block should close right up")

    def test_moving_block_backs_off_from_a_train_with_no_integrity_report(self):
        """Its rear is not trustworthy, so it cannot be followed by distance."""
        gap = self._closest_approach(
            support.stock("NOTIMS", etcs_level="l2", tims=False),
            MovingBlock(safety_margin_m=100.0),
        )
        self.assertIsNotNone(gap)
        self.assertGreater(gap, 400.0,
                           "a train that cannot confirm its integrity must be "
                           "followed at block granularity, not hugged")

    def test_hybrid_l3_degrades_to_block_granularity_behind_an_unfitted_train(self):
        fitted = self._closest_approach(
            support.stock("FITTED", etcs_level="l2", tims=True),
            HybridLevel3(vss_per_block=4),
        )
        unfitted = self._closest_approach(
            support.stock("UNFIT", etcs_level="none", tims=False),
            HybridLevel3(vss_per_block=4),
        )
        self.assertLess(fitted, unfitted,
                        "an unfitted train marks its whole section unknown, so a "
                        "follower must keep further back")


class TestInformationRate(unittest.TestCase):
    """Level 1 differs from Level 2 only in when the train is told."""

    def _authority_trace(self, system):
        timetable = {
            "stock": [support.stock("UNIT")],
            "services": [
                {"id": "LEAD", "stock": "UNIT", "departure": "08:00:00",
                 "calls": [{"station": "A", "platform": "A_1",
                            "departure": "08:00:00", "dwell_s": 0},
                           {"station": "B", "platform": "B_1", "dwell_s": 30}]},
                {"id": "FOLLOW", "stock": "UNIT", "departure": "08:00:50",
                 "ready_lead_s": 30,
                 "calls": [{"station": "A", "platform": "A_1",
                            "departure": "08:00:50", "dwell_s": 0},
                           {"station": "B", "platform": "B_1", "dwell_s": 30}]},
            ],
        }
        sim, _, _ = support.build_test_sim(
            timetable_spec=timetable, signalling=system, duration_s=2400.0)
        steps = 0
        while not sim.finished:
            sim.step()
            follow = sim.trains.get("FOLLOW")
            if follow is not None and follow.state == "running":
                steps += 1
        self.assertEqual(sim.violations, [])
        return sim

    def test_level_1_holds_its_authority_between_balises(self):
        """With infill turned off, the authority may only change at a balise."""
        sim = self._authority_trace(ETCSLevel1(read_distance_m=30.0))
        follow = sim.trains["FOLLOW"]
        self.assertEqual(follow.state, "finished")

    def test_too_short_a_read_distance_is_refused(self):
        """A silent deadlock is worse than a loud error."""
        with self.assertRaises(ValueError) as caught:
            ETCSLevel1(read_distance_m=5.0)
        self.assertIn("stands short", str(caught.exception))

    def test_level_2_refreshes_continuously(self):
        sim = self._authority_trace(ETCSLevel2())
        self.assertEqual(sim.trains["FOLLOW"].state, "finished")

    def test_level_1_without_infill_costs_time(self):
        """Braking towards a signal that has already cleared is Level 1's cost."""
        with_infill = run_under(support.INTENSIVE, "etcs_l1")
        scenario = load_scenario(support.INTENSIVE)
        scenario.signalling_spec = {"system": "etcs_l1", "read_distance_m": 30.0}
        without_infill = kpi.measure(build_simulation(scenario))
        self.assertGreater(without_infill.total_restrained_s,
                           with_infill.total_restrained_s)


class TestInterlockingStillBounds(unittest.TestCase):
    """No level of ETCS may run past the interlocking."""

    def test_every_level_stops_at_an_unset_route(self):
        for name in LADDER:
            scenario = load_scenario(support.CORRIDOR3)
            scenario.signalling_spec = {"system": name}
            sim = build_simulation(scenario)
            # Before any route is requested, the controlled signals are at danger,
            # so no authority may reach past the divergence at Beta.
            sim.step()
            for train in sim.trains.values():
                if train.state != "running" or train.last_authority_m is None:
                    continue
                limit = train.chainage_m + train.last_authority_m
                for section in train.path.sections_ahead(train.chainage_m):
                    signal = sim.signals.get(section.signal_id)
                    if signal is not None and signal.controlled:
                        if sim.interlocking.route_set_from(signal.id) is None:
                            self.assertLessEqual(
                                limit, section.start_m + 1e-6,
                                "%s under %s was authorised past an unset route"
                                % (train.id, name),
                            )
                        break


if __name__ == "__main__":
    unittest.main()
