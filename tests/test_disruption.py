"""Perturbation: that it happens, and that what it costs is attributable.

Two things have to hold for a propagation figure to be worth anything. The
disturbance has to actually reach the train - a declared late start that fails to
delay anything would silently report zero cost - and the *undisturbed* baseline
has to be genuinely undisturbed, or the difference between the two runs is not
the incident. Both are asserted here.
"""

import unittest

import support
from trainsim.analysis import propagation
from trainsim.core.disruption import (
    DisruptedSpeedLimits, DisruptionError, Disruptions, DwellOverrun, LateStart,
    SpeedLimits, SpeedRestriction, build_disruptions,
)
from trainsim.core.units import kmh_to_ms, ms_to_kmh, parse_clock
from trainsim.scenario.loader import build_simulation, load_scenario


class TestParsingADisruptionsBlock(unittest.TestCase):

    def build(self, spec):
        return build_disruptions(spec, parse_clock, kmh_to_ms)

    def test_minutes_and_seconds_are_both_accepted(self):
        both = self.build([
            {"kind": "late_start", "service": "S1", "minutes": 2},
            {"kind": "dwell_overrun", "service": "S2", "station": "BETA",
             "seconds": 45},
        ])
        self.assertEqual(both.late_start_s("S1"), 120.0)
        self.assertEqual(both.dwell_extra_s("S2", "BETA"), 45.0)
        self.assertEqual(both.dwell_extra_s("S2", "GAMMA"), 0.0)

    def test_an_unknown_kind_says_what_is_available(self):
        with self.assertRaises(DisruptionError) as caught:
            self.build([{"kind": "leaves_on_the_line", "service": "S1"}])
        message = str(caught.exception)
        self.assertIn("late_start", message)
        self.assertIn("dwell_overrun", message)

    def test_a_missing_field_names_the_disruption(self):
        with self.assertRaises(DisruptionError) as caught:
            self.build([{"kind": "dwell_overrun", "service": "S1", "minutes": 1}])
        self.assertIn("station", str(caught.exception))

    def test_no_block_at_all_is_the_railway_working_to_plan(self):
        self.assertFalse(self.build(None))
        self.assertFalse(self.build([]))
        self.assertIn("working to plan", self.build([]).describe())


class TestSpeedRestrictionGeometry(unittest.TestCase):
    """A TSR is a stretch of line during a window, not a property of a segment."""

    def setUp(self):
        self.tsr = SpeedRestriction(
            from_km=4.0, to_km=6.0, max_speed_ms=kmh_to_ms(40.0),
            tracks=("UP",), from_s=parse_clock("08:00:00"),
            to_s=parse_clock("09:00:00"),
        )

    def test_it_is_bounded_in_time(self):
        self.assertFalse(self.tsr.active_at(parse_clock("07:59:59")))
        self.assertTrue(self.tsr.active_at(parse_clock("08:30:00")))
        self.assertFalse(self.tsr.active_at(parse_clock("09:00:00")))

    def test_it_is_bounded_in_space_and_by_track(self):
        self.assertTrue(self.tsr.covers("UP", 5.0))
        self.assertFalse(self.tsr.covers("UP", 3.9))
        self.assertFalse(self.tsr.covers("DN", 5.0),
                         "a restriction on the up line must not slow the down line")

    def test_kilometres_may_be_written_in_either_order(self):
        """The down line's chainage runs backwards, so order must not matter."""
        backwards = SpeedRestriction(from_km=6.0, to_km=4.0,
                                     max_speed_ms=kmh_to_ms(40.0))
        self.assertTrue(backwards.covers("DN", 5.0))
        self.assertEqual((backwards.low_km, backwards.high_km), (4.0, 6.0))


class TestDisruptionsReachTheTrain(unittest.TestCase):
    """The kernel tests: a declared disturbance must actually change the run."""

    def journey(self, disruptions=None, **kwargs):
        sim, infra, _ = support.build_test_sim(disruptions=disruptions, **kwargs)
        sim.run()
        train = sim.trains["T1"]
        self.assertEqual(train.state, "finished")
        return sim, train

    def test_a_clean_run_is_the_reference(self):
        sim, train = self.journey()
        self.baseline_s = train.finished_s
        self.assertEqual(sim.violations, [])

    def test_a_late_start_delays_the_train_by_what_was_declared(self):
        _, clean = self.journey()
        _, late = self.journey(
            disruptions=Disruptions(late_starts=[LateStart("T1", 300.0)]))
        self.assertAlmostEqual(late.finished_s - clean.finished_s, 300.0, delta=2.0)
        # It must leave late, not merely appear late. A train that is berthed
        # early and then allowed away on time has not been delayed at all, and
        # the ready lead would quietly absorb the whole disturbance.
        self.assertAlmostEqual(
            late.actual_departures["A"] - clean.actual_departures["A"],
            300.0, delta=2.0)
        self.assertGreater(late.entered_s, clean.entered_s)

    def test_a_dwell_overrun_holds_the_train_at_the_named_station_only(self):
        _, clean = self.journey()
        _, held = self.journey(disruptions=Disruptions(
            dwell_overruns=[DwellOverrun("T1", "A", 180.0)]))
        self.assertAlmostEqual(held.finished_s - clean.finished_s, 180.0, delta=2.0)

        _, elsewhere = self.journey(disruptions=Disruptions(
            dwell_overruns=[DwellOverrun("T1", "NOWHERE", 180.0)]))
        self.assertEqual(elsewhere.finished_s, clean.finished_s)

    def test_a_speed_restriction_slows_every_train_that_meets_it(self):
        """And is felt as a slower *run*, not as a signalling restraint."""
        _, clean = self.journey()
        restriction = SpeedRestriction(
            from_km=4.0, to_km=6.0, max_speed_ms=kmh_to_ms(40.0), tracks=("T",))
        sim, slowed = self.journey(
            disruptions=Disruptions(speed_restrictions=[restriction]))
        self.assertGreater(slowed.finished_s, clean.finished_s + 60.0)

    def test_a_restriction_on_another_track_changes_nothing(self):
        _, clean = self.journey()
        _, other = self.journey(disruptions=Disruptions(speed_restrictions=[
            SpeedRestriction(from_km=4.0, to_km=6.0,
                             max_speed_ms=kmh_to_ms(40.0), tracks=("OTHER",))]))
        self.assertEqual(other.finished_s, clean.finished_s)

    def test_a_restriction_outside_its_window_changes_nothing(self):
        _, clean = self.journey()
        _, after = self.journey(disruptions=Disruptions(speed_restrictions=[
            SpeedRestriction(from_km=4.0, to_km=6.0,
                             max_speed_ms=kmh_to_ms(40.0), tracks=("T",),
                             from_s=parse_clock("23:00:00"))]))
        self.assertEqual(after.finished_s, clean.finished_s)

    def test_the_train_is_actually_down_to_the_restricted_speed(self):
        """Not merely slower overall - it must obey the figure, in the stretch."""
        restriction = SpeedRestriction(
            from_km=4.0, to_km=6.0, max_speed_ms=kmh_to_ms(40.0), tracks=("T",))
        sim, _, _ = support.build_test_sim(
            disruptions=Disruptions(speed_restrictions=[restriction]))
        inside = []
        while not sim.finished:
            sim.step()
            train = sim.trains.get("T1")
            if train is not None and train.state == "running" and 4.2 < train.km < 5.8:
                inside.append(ms_to_kmh(train.speed_ms))
        self.assertTrue(inside, "the train never reached the restricted stretch")
        self.assertLessEqual(max(inside), 41.0)


class TestTheSpeedLimitSeam(unittest.TestCase):
    """The driver must not be able to tell a TSR from a permanent restriction."""

    def test_without_disruptions_the_two_agree_everywhere(self):
        sim, infra, _ = support.build_test_sim()
        sim.step()
        train = sim.trains["T1"]
        plain = SpeedLimits()
        overlaid = DisruptedSpeedLimits(Disruptions(), lambda: sim.time_s)
        for chainage in (0.0, 500.0, 4000.0, 9000.0):
            self.assertEqual(plain.at(train, chainage), overlaid.at(train, chainage))
            self.assertEqual(list(plain.ahead(train, chainage, 3000.0)),
                             list(overlaid.ahead(train, chainage, 3000.0)))

    def test_a_restriction_is_seen_ahead_before_it_is_reached(self):
        """Otherwise the driver would brake into it rather than for it."""
        sim, infra, _ = support.build_test_sim()
        sim.step()
        train = sim.trains["T1"]
        limits = DisruptedSpeedLimits(
            Disruptions(speed_restrictions=[SpeedRestriction(
                from_km=4.0, to_km=6.0, max_speed_ms=kmh_to_ms(40.0),
                tracks=("T",))]),
            lambda: sim.time_s)
        ahead = list(limits.ahead(train, 1000.0, 4000.0))
        self.assertTrue(any(abs(limit - kmh_to_ms(40.0)) < 1e-6
                            for _, limit in ahead),
                        "the restriction was not visible from 3 km short of it")


class TestPropagationOnCorridor3(unittest.TestCase):
    """A four-minute stand at Beta, on a line with a loop and some slack."""

    @classmethod
    def setUpClass(cls):
        cls.path = support.CORRIDOR3_DISRUPTED
        cls.result = propagation.measure_propagation(
            load_scenario(cls.path), build_simulation)

    def test_the_baseline_run_really_is_undisturbed(self):
        """The difference is only the incident if the other run has none.

        Asserted against the *undisrupted* scenario file rather than against the
        override, so a bug that let a disruption leak into the baseline could not
        hide behind both sides being equally wrong.
        """
        plain = load_scenario(support.CORRIDOR3)
        plain_sim = build_simulation(plain)
        plain_sim.run()
        baseline = {t.id: t.finished_s - t.origin_departure_s
                    for t in plain_sim.trains.values() if t.finished_s is not None}
        for impact in self.result.impacts:
            self.assertAlmostEqual(impact.clean_journey_s,
                                   baseline[impact.service], delta=0.001,
                                   msg=impact.service)

    def test_the_primary_delay_is_the_incident_and_nothing_else(self):
        primary = [i for i in self.result.impacts if i.directly_hit]
        self.assertEqual([i.service for i in primary], ["S1"])
        self.assertAlmostEqual(self.result.primary_s, 240.0, delta=2.0)

    def test_the_incident_reaches_a_train_it_was_not_applied_to(self):
        """If nothing propagated there would be nothing to study."""
        self.assertGreater(self.result.knock_on_s, 0.0)
        self.assertIsNotNone(self.result.multiplier)

    def test_a_scenario_with_no_disruptions_refuses_rather_than_reporting_zero(self):
        with self.assertRaises(ValueError) as caught:
            propagation.measure_propagation(
                load_scenario(support.CORRIDOR3), build_simulation)
        self.assertIn("no disruptions", str(caught.exception))


class TestPropagationOnTheMetro(unittest.TestCase):
    """The same idea on a railway with no slack anywhere - the interesting case."""

    @classmethod
    def setUpClass(cls):
        cls.fixed = propagation.measure_propagation(
            load_scenario(support.METRO_DISRUPTED), build_simulation,
            system="fixed_block_3aspect")
        cls.moving = propagation.measure_propagation(
            load_scenario(support.METRO_DISRUPTED), build_simulation,
            system="etcs_moving_block")

    def test_a_line_with_no_slack_amplifies_its_incidents(self):
        """Ninety seconds of held door buys several times that in knock-on."""
        self.assertGreater(self.fixed.multiplier, 3.0)
        self.assertGreater(self.moving.multiplier, 3.0)

    def test_under_fixed_block_the_delay_transfers_whole(self):
        """Every following train loses the same amount: nothing absorbs it."""
        behind = {i.service: i.extra_s for i in self.fixed.impacts
                  if i.service.startswith("U") and i.service > "U05"}
        self.assertEqual(len(behind), 7)
        self.assertAlmostEqual(min(behind.values()), max(behind.values()),
                               delta=2.0)

    def test_under_moving_block_it_decays_instead(self):
        """Trains close up behind the incident and take some of it back.

        This is the clearest thing distance separation buys under disruption, and
        it is not a journey time claim at all.
        """
        behind = [(i.service, i.extra_s) for i in self.moving.impacts
                  if i.service.startswith("U") and i.service > "U05"]
        behind.sort()
        losses = [extra for _, extra in behind]
        self.assertEqual(len(losses), 7)
        self.assertEqual(losses, sorted(losses, reverse=True),
                         "the delay did not decay down the flight")
        self.assertLess(losses[-1], losses[0] - 30.0)

    def test_the_better_system_is_better_on_the_day_as_well(self):
        """Knock-on is measured against each system's own plan, so it can mislead.

        Here both readings agree - but the absolute one is the one that decides
        it, and the report prints both for that reason.
        """
        self.assertLess(self.moving.knock_on_s, self.fixed.knock_on_s)
        self.assertLess(self.moving.mean_disrupted_journey_s,
                        self.fixed.mean_disrupted_journey_s)


if __name__ == "__main__":
    unittest.main()
