"""Junctions: converging traffic, and the decision nothing here makes yet.

Every layout before this one was linear. A train was behind or in front of every
other train on its road, the interlocking only ever asked whether the road ahead
was clear, and better signalling meant trains could run closer together.

A junction is a different problem. Two trains want the same *points*, not the
same block, and a point is held far longer than a train is long. The interlocking
refuses one of them - correctly - and which one it refuses is decided by nothing
better than which asked first. These tests pin that down, including the part that
is unsatisfactory, because the unsatisfactory part is the specification for the
traffic management work that follows.
"""

import unittest

import support
from trainsim.scenario.builder import InfrastructureError, build_infrastructure
from trainsim.scenario.loader import build_simulation, load_scenario
from trainsim.analysis import kpi


def run(path, system=None):
    scenario = load_scenario(path)
    if system is not None:
        scenario.signalling_spec = {"system": system}
    sim = build_simulation(scenario)
    sim.run()
    return sim


class TestTheLayout(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(support.JUNCTION)
        cls.infra = cls.scenario.infrastructure

    def test_the_branch_attaches_to_the_main_line(self):
        """One link segment each way, ending on a node of the line it joins."""
        network = self.infra.network
        joining = network.segments["BR_UP_JN"]
        leaving = network.segments["BR_DN_JN"]
        self.assertTrue(joining.end_node.startswith("UP@"),
                        "the up branch does not reach the up main")
        self.assertTrue(leaving.start_node.startswith("DN@"),
                        "the down branch does not leave the down main")
        # It ramps: one alignment at each end, which is what makes it a junction
        # rather than a parallel road.
        self.assertNotEqual(joining.y, joining.end_y)
        self.assertNotEqual(leaving.y, leaving.end_y)

    def test_the_points_fall_out_of_the_topology(self):
        kinds = {p.kind for p in self.infra.points.values()}
        self.assertEqual(kinds, {"facing", "trailing"})
        self.assertEqual(len(self.infra.points), 2)

        trailing = next(p for p in self.infra.points.values()
                        if p.kind == "trailing")
        facing = next(p for p in self.infra.points.values() if p.kind == "facing")
        self.assertEqual(set(trailing.legs), {"UP_007", "BR_UP_JN"})
        self.assertEqual(set(facing.legs), {"DN_009", "BR_DN_JN"})

    def test_the_main_line_is_the_normal_position_at_both(self):
        """The straight road has to be judged at the far end of each leg.

        At the points themselves both roads are on the same alignment - that is
        what a point is - so only where a road *goes* says which is straight.
        Getting this backwards would make the branch the normal position and the
        main line the diverging one.
        """
        for point in self.infra.points.values():
            self.assertFalse(point.normal.endswith("_JN"),
                             "%s takes the branch as its normal position"
                             % (point.id,))

    def test_the_conflicting_routes_exist_and_know_they_conflict(self):
        routes = self.infra.routes
        into_beta = sorted(r.id for r in routes.values()
                           if r.block_id == "BETA_1" and r.controlled)
        self.assertEqual(len(into_beta), 2,
                         "there should be one route into Beta per approach")

        sim = build_simulation(self.scenario)
        for route_id in into_beta:
            others = sim.interlocking.conflicts_for(route_id)
            self.assertTrue(any(other in into_beta for other in others),
                            "%s does not know it conflicts" % (route_id,))

    def test_the_layout_is_signalable(self):
        from trainsim.scenario import checks
        results = checks.check_block_lengths(
            self.infra, self.scenario.timetable, self.scenario.driver_config)
        self.assertEqual(checks.failures(results), [])


class TestBuilderValidation(unittest.TestCase):
    """A junction spec that cannot mean anything must say so, not build oddly."""

    BASE = {
        "name": "t",
        "defaults": {"platform_zone_m": 400, "block_length_m": 2000},
        "stations": [{"id": "A", "km": 0.0}, {"id": "B", "km": 10.0},
                     {"id": "C", "km": 4.0}],
        "tracks": [
            {"id": "M", "direction": "up", "y": 0.0, "serves": ["A", "B"]},
        ],
        "platforms": [
            {"id": "A_1", "station": "A", "track": "M", "length_m": 200},
            {"id": "B_1", "station": "B", "track": "M", "length_m": 200},
            {"id": "C_1", "station": "C", "track": "BR", "length_m": 100},
        ],
    }

    def build(self, junction, serves=("C", "B")):
        spec = {k: (list(v) if isinstance(v, list) else v)
                for k, v in self.BASE.items()}
        spec["tracks"] = list(spec["tracks"]) + [
            {"id": "BR", "direction": "up", "y": -1.0, "serves": list(serves),
             "junction": junction},
        ]
        return build_infrastructure(spec)

    def test_a_valid_branch_builds(self):
        infra = self.build({"track": "M", "at": "B", "length_m": 400})
        self.assertIn("BR_JN", infra.network.segments)

    def test_an_unknown_track_is_reported(self):
        with self.assertRaises(InfrastructureError) as caught:
            self.build({"track": "NOPE", "at": "B"})
        self.assertIn("NOPE", str(caught.exception))

    def test_joining_at_a_station_the_other_track_does_not_serve(self):
        with self.assertRaises(InfrastructureError) as caught:
            self.build({"track": "M", "at": "C"}, serves=("C", "B"))
        self.assertIn("nothing to join", str(caught.exception))

    def test_the_junction_must_be_at_one_end_of_the_branch(self):
        with self.assertRaises(InfrastructureError) as caught:
            self.build({"track": "M", "at": "A"}, serves=("C", "B"))
        self.assertIn("first or last", str(caught.exception))

    def test_a_link_longer_than_the_branch_is_reported(self):
        with self.assertRaises(InfrastructureError) as caught:
            self.build({"track": "M", "at": "B", "length_m": 99000})
        self.assertIn("longer than the branch", str(caught.exception))


class TestTheConflictHappens(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sim = run(support.JUNCTION)
        cls.refusals = [e for e in cls.sim.events if e.kind == "route_refused"]

    def test_the_run_is_clean(self):
        self.assertEqual(self.sim.violations, [])
        self.assertEqual(len(self.sim.trains), 24)
        for train in self.sim.trains.values():
            self.assertEqual(train.state, "finished", train.id)

    def test_the_branch_is_refused_the_junction_every_cycle(self):
        """Not once by accident - every time, which makes it a property."""
        self.assertEqual(len(self.refusals), 6)
        for event in self.refusals:
            self.assertTrue(event.train_id.startswith("BU"), event.train_id)

    def test_the_refusal_names_what_is_holding_the_road(self):
        """A signaller would be told which train has it, and so is the log."""
        detail = self.refusals[0].detail
        self.assertIn("BETA_1", detail)
        self.assertIn("MU", detail, "the refusal does not say who holds it")

    def test_the_branch_train_stops_short_rather_than_running_through(self):
        """Running through a trailing point set against you is a derailment."""
        sim = build_simulation(load_scenario(support.JUNCTION))
        stood = False
        while not sim.finished:
            sim.step()
            for train in sim.trains.values():
                if (train.id.startswith("BU") and train.state == "running"
                        and train.speed_ms == 0.0
                        and "danger" in train.authority_reason):
                    stood = True
                    # It must be standing on its own side of the points.
                    self.assertLess(train.km, 13.45)
        self.assertTrue(stood, "no branch train was ever held at the junction")

    def test_the_main_line_wins_and_the_branch_pays(self):
        delays = {t.id: t.delay_s for t in self.sim.trains.values()}
        branch = [delays[k] for k in delays if k.startswith("BU")]
        main = [delays[k] for k in delays if k.startswith("MU")]
        self.assertGreater(min(branch), max(main),
                           "the branch was not the one held back")
        self.assertGreater(min(branch), 60.0)

    def test_nothing_decided_that_the_main_line_should_win(self):
        """It wins because it asks first, and that is the gap this scenario marks.

        Asserted rather than merely written down: if a later dispatcher starts
        making an actual decision here, this test should fail and be rewritten
        to say what the decision is.
        """
        self.assertEqual(self.sim.dispatcher.name, "timetable")
        # Every cycle costs the branch the same, because nothing is adapting.
        branch = sorted((t.id, t.delay_s) for t in self.sim.trains.values()
                        if t.id.startswith("BU"))
        losses = [delay for _, delay in branch]
        self.assertAlmostEqual(min(losses), max(losses), delta=2.0)

    def test_the_junction_delay_turns_into_a_speed_mismatch_delay(self):
        """The branch DMU, pushed later, ends up in front of a faster train.

        The second effect of a junction, and the one that makes it expensive: the
        delay does not stay at the junction. It follows the trains up the line.
        """
        sim = build_simulation(load_scenario(support.JUNCTION))
        far_out = set()
        while not sim.finished:
            sim.step()
            for train in sim.trains.values():
                if (train.id.startswith("MU") and train.state == "running"
                        and "caution" in train.authority_reason
                        and train.km > 20.0):
                    far_out.add(train.id)
        self.assertTrue(far_out,
                        "no main line train was checked down beyond the junction")

    def test_both_roads_through_the_facing_point_are_used(self):
        """The down branch must actually diverge, or the point is decoration."""
        blocks = set()
        sim = build_simulation(load_scenario(support.JUNCTION))
        while not sim.finished:
            sim.step()
            for block_id in ("BR_DN_JN", "DN_009"):
                if sim.occupancy.trains_in(block_id):
                    blocks.add(block_id)
        self.assertEqual(blocks, {"BR_DN_JN", "DN_009"})


class TestBetterSignallingBarelyHelps(unittest.TestCase):
    """The point of the scenario, and the reason Phase 5 comes next."""

    @classmethod
    def setUpClass(cls):
        cls.results = {
            name: kpi.measure(build_simulation(_with(support.JUNCTION, name)))
            for name in ("fixed_block_3aspect", "etcs_moving_block")
        }

    def test_every_level_runs_the_junction_safely(self):
        for name, metrics in self.results.items():
            self.assertEqual(metrics.violations, 0, name)
            self.assertEqual(metrics.completed, metrics.services, name)

    def test_moving_block_gains_far_less_here_than_on_a_linear_line(self):
        """It shortens the gap between trains going the same way.

        That is not this problem. Two trains wanting the same points is a
        question of order, and no train control system answers it.
        """
        fixed = self.results["fixed_block_3aspect"].mean_journey_s
        moving = self.results["etcs_moving_block"].mean_journey_s
        gain = (fixed - moving) / fixed
        self.assertLess(gain, 0.05,
                        "moving block gained %.1f%% at a junction; on the metro "
                        "it gains around 10%% and on the intensive corridor 23%%"
                        % (100.0 * gain,))

    def test_the_branch_is_still_held_under_moving_block(self):
        delays = self.results["etcs_moving_block"].delays
        branch = [v for k, v in delays.items() if k.startswith("BU")]
        self.assertGreater(min(branch), 60.0)


class TestTheFlatJunction(unittest.TestCase):
    """A diamond: two lines crossing on the level, and what it costs.

    The flat layout and the flyover layout are the same railway, the same
    timetable and the same trains. One line of the infrastructure file differs.
    Everything below is that difference.
    """

    @classmethod
    def setUpClass(cls):
        cls.flat = load_scenario(support.JUNCTION_FLAT)
        cls.flyover = load_scenario(support.JUNCTION_FLYOVER)
        cls.flat_run = kpi.measure(build_simulation(load_scenario(
            support.JUNCTION_FLAT)))
        cls.flyover_run = kpi.measure(build_simulation(load_scenario(
            support.JUNCTION_FLYOVER)))

    def test_the_crossings_are_derived_from_the_drawing(self):
        """Nothing declares them - a ramp crosses what lies between its ends."""
        crossings = self.flat.infrastructure.crossings
        self.assertIn("DN_009", crossings.get("BR_UP_JN", ()),
                      "the up branch does not cross the down main")
        self.assertIn("BR_UP_JN", crossings.get("DN_009", ()),
                      "the crossing is not symmetric")

    def test_grade_separation_removes_only_the_crossing_it_is_built_for(self):
        flyover = self.flyover.infrastructure.crossings
        self.assertNotIn("DN_009", flyover.get("BR_UP_JN", ()),
                         "the flyover still fouls the down main")
        # The down branch still crosses the up branch: a flyover is built for the
        # move that fouls the main line, not for every move at the junction.
        self.assertIn("BR_UP_JN", flyover.get("BR_DN_JN", ()))

    def test_the_two_layouts_differ_only_in_the_crossing(self):
        """Otherwise the comparison would be measuring something else."""
        def geometry(scenario):
            return sorted(
                (s.id, round(s.length_m, 3), round(s.km_start, 6),
                 round(s.max_speed_ms, 6))
                for s in scenario.infrastructure.network.segments.values())

        self.assertEqual(geometry(self.flat), geometry(self.flyover))
        self.assertEqual(len(self.flat.timetable.services),
                         len(self.flyover.timetable.services))

    def test_a_route_over_a_diamond_needs_asking_for(self):
        """Even with no points on it: granting it takes the crossing away."""
        route = self.flat.infrastructure.routes["R_BR_UP_JN"]
        self.assertEqual(route.points, {})
        self.assertTrue(route.crossings)
        self.assertTrue(route.controlled)
        self.assertIn("crosses", route.describe())

    def test_the_down_main_is_refused_its_own_plain_line_by_a_branch_train(self):
        """The mechanism: a branch train going over stops the line it crosses."""
        sim = build_simulation(load_scenario(support.JUNCTION_FLAT))
        sim.run()
        refusals = [e for e in sim.events
                    if e.kind == "route_refused" and e.train_id.startswith("MD")]
        self.assertTrue(refusals,
                        "no down main train was ever refused by the junction")
        self.assertIn("DN_009", refusals[0].detail)
        self.assertIn("BU", refusals[0].detail,
                      "the down main was not refused on account of a branch train")

    def test_the_cost_falls_on_the_line_being_crossed_not_on_the_branch(self):
        """The result that is worth the whole scenario, and it is counterintuitive.

        The branch train crosses, so one expects the branch train to pay. It does
        not: it asks first and gets the road. What pays is the down main express
        that had nothing to do with the branch at all.
        """
        def mean_extra(prefix):
            extras = [self.flat_run.journey_times[k]
                      - self.flyover_run.journey_times[k]
                      for k in self.flat_run.journey_times if k.startswith(prefix)]
            return sum(extras) / len(extras)

        self.assertGreater(mean_extra("MD"), 60.0, "the down main did not pay")
        self.assertGreater(mean_extra("BD"), 10.0)
        self.assertAlmostEqual(mean_extra("BU"), 0.0, delta=5.0,
                               msg="the crossing train paid for the crossing")
        self.assertAlmostEqual(mean_extra("MU"), 0.0, delta=5.0)

    def test_the_flat_layout_costs_measurably_more_on_this_timetable(self):
        """On *this* timetable. The next test says why that qualifier matters."""
        self.assertGreater(
            self.flat_run.mean_journey_s - self.flyover_run.mean_journey_s, 30.0)
        self.assertGreater(self.flat_run.total_restrained_s,
                           1.5 * self.flyover_run.total_restrained_s)

    def test_what_it_costs_depends_entirely_on_the_phasing(self):
        """Move the branch service and the conflict can vanish completely.

        This is the honesty check on the test above. A flat junction is not a
        fixed tax: it costs nothing when the conflicting moves miss each other,
        and a great deal when they coincide. Quoting the single-run figure as
        *the* cost of a flat junction would be picking the number that suited
        the argument, so the model is made to demonstrate the opposite case too.
        """
        shifted = self._shift_branch(120)
        flat = kpi.measure(build_simulation(shifted[0]))
        flyover = kpi.measure(build_simulation(shifted[1]))
        self.assertAlmostEqual(flat.mean_journey_s, flyover.mean_journey_s,
                               delta=2.0,
                               msg="at this phasing the diamond should be free")

    @staticmethod
    def _shift_branch(seconds):
        """The flat and flyover scenarios with the branch service moved later."""
        from dataclasses import replace
        out = []
        for path in (support.JUNCTION_FLAT, support.JUNCTION_FLYOVER):
            scenario = load_scenario(path)
            services = []
            for service in scenario.timetable.services:
                if not service.id.startswith("BU"):
                    services.append(service)
                    continue
                stops = [replace(
                    stop,
                    arrival_s=(None if stop.arrival_s is None
                               else stop.arrival_s + seconds),
                    departure_s=(None if stop.departure_s is None
                                 else stop.departure_s + seconds),
                ) for stop in service.stops]
                services.append(replace(service, stops=stops,
                                        departure_s=service.departure_s + seconds))
            scenario.timetable = replace(scenario.timetable, services=services)
            out.append(scenario)
        return out

    def test_both_layouts_run_safely(self):
        for label, metrics in (("flat", self.flat_run),
                               ("flyover", self.flyover_run)):
            self.assertEqual(metrics.violations, 0, label)
            self.assertEqual(metrics.completed, metrics.services, label)


def _with(path, system):
    scenario = load_scenario(path)
    scenario.signalling_spec = {"system": system}
    return scenario


if __name__ == "__main__":
    unittest.main()
