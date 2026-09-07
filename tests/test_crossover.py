"""Crossovers: a train leaving the line it started on.

Everything before this kept each train on its own road for the whole journey. A
crossover is the connection that lets it change - a facing point on the line it
leaves, a trailing point on the line it joins, and the train lying across both
while it goes over.

Two things about that are worth pinning down. The block plan has to be drawn
around the connection, because a signal has to be able to stand at each end of
it; and a connection between lines running in *opposite* directions is not a
crossover at all but wrong-line running, which is refused rather than quietly
built.
"""

import unittest

import support
from trainsim.scenario.builder import InfrastructureError, build_infrastructure
from trainsim.scenario.loader import build_simulation, load_scenario


BASE = {
    "name": "xo",
    "defaults": {"platform_zone_m": 800, "block_length_m": 1500},
    "stations": [{"id": "A", "km": 0.0}, {"id": "B", "km": 12.0}],
    "tracks": [
        {"id": "UF", "direction": "up", "y": 0.0, "serves": ["A", "B"]},
        {"id": "US", "direction": "up", "y": 0.75, "serves": ["A", "B"]},
        {"id": "DN", "direction": "down", "y": 1.5, "serves": ["B", "A"]},
    ],
    "platforms": [
        {"id": "A_UF", "station": "A", "track": "UF", "length_m": 200},
        {"id": "A_US", "station": "A", "track": "US", "length_m": 200},
        {"id": "A_DN", "station": "A", "track": "DN", "length_m": 200},
        {"id": "B_UF", "station": "B", "track": "UF", "length_m": 200},
        {"id": "B_US", "station": "B", "track": "US", "length_m": 200},
        {"id": "B_DN", "station": "B", "track": "DN", "length_m": 200},
    ],
}


def build(crossovers):
    spec = {k: (list(v) if isinstance(v, list) else dict(v)
                if isinstance(v, dict) else v)
            for k, v in BASE.items()}
    spec["crossovers"] = crossovers
    return build_infrastructure(spec)


class TestOneCrossover(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.infra = build([{"id": "XO", "from": "US", "to": "UF", "km": 6.0,
                            "length_m": 400, "max_speed_kmh": 60}])

    def test_it_is_a_segment_of_its_own_between_the_two_lines(self):
        segment = self.infra.network.segments["XO"]
        self.assertTrue(segment.start_node.startswith("US@"))
        self.assertTrue(segment.end_node.startswith("UF@"))
        self.assertEqual(segment.length_m, 400.0)
        # It ramps from one alignment to the other, which is what draws it as a
        # diagonal rather than as another parallel line.
        self.assertNotEqual(segment.y, segment.end_y)

    def test_it_makes_a_facing_point_where_it_leaves_and_a_trailing_one_where_it_joins(self):
        by_kind = {p.kind: p for p in self.infra.points.values()}
        self.assertEqual(set(by_kind), {"facing", "trailing"})
        self.assertIn("XO", by_kind["facing"].legs)
        self.assertIn("XO", by_kind["trailing"].legs)
        self.assertTrue(by_kind["facing"].node.startswith("US@"))
        self.assertTrue(by_kind["trailing"].node.startswith("UF@"))

    def test_the_running_line_is_the_normal_position_at_both(self):
        for point in self.infra.points.values():
            self.assertNotEqual(point.normal, "XO",
                                "%s takes the crossover as normal" % (point.id,))

    def test_the_block_plan_is_drawn_around_the_connection(self):
        """A signal has to be able to stand at each end, so both are boundaries.

        Without this the connection would land in the middle of a block and have
        nowhere to start from, whatever block length the track asked for.
        """
        segment = self.infra.network.segments["XO"]
        slow_ends = [b for b in self.infra.blocks.values()
                     if b.track == "US" and b.exit_node == segment.start_node]
        fast_starts = [b for b in self.infra.blocks.values()
                       if b.track == "UF" and b.entry_node == segment.end_node]
        self.assertEqual(len(slow_ends), 1)
        self.assertEqual(len(fast_starts), 1)

    def test_the_two_ways_onto_the_fast_line_are_mutually_exclusive_routes(self):
        segment = self.infra.network.segments["XO"]
        beyond = [b for b in self.infra.blocks.values()
                  if b.entry_node == segment.end_node][0]
        routes = sorted(r.id for r in self.infra.routes.values()
                        if r.block_id == beyond.id)
        self.assertEqual(len(routes), 2, "one route per approach, not %s" % routes)
        sim = build_simulation(load_scenario(support.FOURTRACK))  # any sim
        del sim
        for route_id in routes:
            route = self.infra.routes[route_id]
            self.assertTrue(route.controlled)

    def test_a_path_across_it_is_found_without_being_asked_for(self):
        """Nothing in a timetable names a crossover; the route finder uses it."""
        path = self.infra.network.find_path("A_US", "B_UF")
        self.assertIn("XO", path)


class TestWhatIsRefused(unittest.TestCase):

    def test_connecting_lines_that_run_opposite_ways_is_refused(self):
        """It would be wrong-line running, which needs bidirectional signalling."""
        with self.assertRaises(InfrastructureError) as caught:
            build([{"id": "BAD", "from": "UF", "to": "DN", "km": 6.0}])
        message = str(caught.exception)
        self.assertIn("opposite directions", message)
        self.assertIn("bidirectional", message)
        self.assertIn("not modelled", message)

    def test_a_crossover_to_the_same_track_is_refused(self):
        with self.assertRaises(InfrastructureError):
            build([{"id": "BAD", "from": "UF", "to": "UF", "km": 6.0}])

    def test_an_unknown_track_is_refused(self):
        with self.assertRaises(InfrastructureError) as caught:
            build([{"id": "BAD", "from": "US", "to": "NOPE", "km": 6.0}])
        self.assertIn("NOPE", str(caught.exception))

    def test_a_missing_field_is_refused(self):
        with self.assertRaises(InfrastructureError) as caught:
            build([{"id": "BAD", "from": "US", "to": "UF"}])
        self.assertIn("km", str(caught.exception))

    def test_a_misspelled_field_is_refused(self):
        with self.assertRaises(InfrastructureError) as caught:
            build([{"id": "BAD", "from": "US", "to": "UF", "km": 6.0,
                    "lenght_m": 400}])
        self.assertIn("did you mean 'length_m'", str(caught.exception))


class TestTheFourTrackScenario(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(support.FOURTRACK)
        sim = build_simulation(load_scenario(support.FOURTRACK))
        sim.run()
        cls.sim = sim

    def test_the_layout_is_signalable(self):
        """A fast line needs a longer platform zone than a slow one.

        Left at the default this layout is unsignalable, and --check says so -
        which is the check earning its keep on a layout it was not written for.
        """
        from trainsim.scenario import checks
        results = checks.check_block_lengths(
            self.scenario.infrastructure, self.scenario.timetable,
            self.scenario.driver_config)
        self.assertEqual(checks.failures(results), [])

    def test_four_running_lines_and_a_crossover_between_each_pair(self):
        infra = self.scenario.infrastructure
        self.assertEqual(set(infra.tracks), {"UF", "US", "DS", "DF"})
        self.assertIn("XO_UP", infra.network.segments)
        self.assertIn("XO_DN", infra.network.segments)
        self.assertEqual(len(infra.points), 4)

    def test_beta_has_platforms_on_the_slow_lines_only(self):
        """Which is what makes the crossover necessary rather than decorative."""
        beta = self.scenario.infrastructure.network.stations["BETA"]
        self.assertEqual(set(beta.platforms), {"BETA_US", "BETA_DS"})

    def test_the_semi_fast_actually_changes_lines(self):
        """It starts on the slow line and finishes on the fast one."""
        train = self.sim.trains["X1"]
        self.assertEqual(train.state, "finished")
        self.assertIn("XO_UP", train.path.segment_ids)
        self.assertEqual(train.path.entries[0].segment.track, "US")
        self.assertEqual(train.path.entries[-1].segment.track, "UF")

    def test_the_trains_that_do_not_need_it_never_touch_it(self):
        for train_id in ("F1", "S1", "FD1", "SD1"):
            path = self.sim.trains[train_id].path.segment_ids
            self.assertNotIn("XO_UP", path, train_id)
            self.assertNotIn("XO_DN", path, train_id)

    def test_the_crossover_is_a_flat_junction_in_all_but_name(self):
        """The semi-fast is refused the fast line by the express behind it.

        A crossover puts a train across two running lines at once, so the
        conflict is the same one the junction scenario is about - and again
        nothing decides which train should have it.
        """
        refusals = [e for e in self.sim.events
                    if e.kind == "route_refused" and "XO_UP" in e.detail]
        self.assertTrue(refusals, "the crossover was never contended")
        for event in refusals:
            self.assertTrue(event.train_id.startswith("X"), event.train_id)

    def test_the_semi_fast_is_the_one_that_pays(self):
        delays = {t.id: t.delay_s for t in self.sim.trains.values()}
        semi = max(delays[k] for k in delays if k.startswith("X")
                   and not k.startswith("XD"))
        fasts = [delays[k] for k in delays if k.startswith("F")]
        self.assertGreater(semi, 30.0)
        self.assertGreater(semi, max(fasts))

    def test_the_run_is_clean(self):
        self.assertEqual(self.sim.violations, [])
        self.assertEqual(len(self.sim.trains), 24)
        for train in self.sim.trains.values():
            self.assertEqual(train.state, "finished", train.id)


if __name__ == "__main__":
    unittest.main()
