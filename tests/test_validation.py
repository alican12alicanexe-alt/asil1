"""Catching mistakes in scenario files, before they become plausible numbers.

Two classes of mistake used to pass silently, and both produced a believable
answer for a railway nobody had described:

* a **misspelled key** was ignored, so ``max_speed_kph: 80`` left the track at
  its 140 km/h default and nothing said so
* an **unworkable timetable** loaded happily and then reported its trains as
  late, which reads as a railway that cannot cope rather than a plan that was
  never possible

For a tool whose output somebody will quote, silence is worse than a crash.
"""

import glob
import os
import unittest

import support
from trainsim.core.disruption import DisruptionError, build_disruptions
from trainsim.core.units import kmh_to_ms, parse_clock
from trainsim.scenario import checks, schema
from trainsim.scenario.builder import InfrastructureError, build_infrastructure
from trainsim.scenario.loader import ScenarioError, build_timetable, load_scenario


INFRA = {
    "name": "t",
    "defaults": {"platform_zone_m": 400, "block_length_m": 2000},
    "stations": [{"id": "A", "km": 0.0}, {"id": "B", "km": 10.0}],
    "tracks": [{"id": "T", "direction": "up", "y": 0.0, "max_speed_kmh": 140,
                "serves": ["A", "B"]}],
    "platforms": [{"id": "A_1", "station": "A", "track": "T", "length_m": 200},
                  {"id": "B_1", "station": "B", "track": "T", "length_m": 200}],
}
STOCK = {"id": "U", "length_m": 200, "max_speed_kmh": 140, "max_accel": 0.9,
         "service_brake": 0.7, "emergency_brake": 1.2}


def infra(**changes):
    spec = {k: (list(v) if isinstance(v, list) else v) for k, v in INFRA.items()}
    spec.update(changes)
    return build_infrastructure(spec)


class TestUnknownKeysInTheInfrastructure(unittest.TestCase):

    def test_a_misspelled_track_key_is_refused_with_a_suggestion(self):
        with self.assertRaises(InfrastructureError) as caught:
            infra(tracks=[{"id": "T", "direction": "up", "y": 0.0,
                           "max_speed_kph": 80, "serves": ["A", "B"]}])
        message = str(caught.exception)
        self.assertIn("max_speed_kph", message)
        self.assertIn("did you mean 'max_speed_kmh'", message)

    def test_the_error_lists_what_would_have_been_allowed(self):
        with self.assertRaises(InfrastructureError) as caught:
            infra(platforms=[{"id": "A_1", "station": "A", "track": "T",
                              "lenght_m": 200}])
        message = str(caught.exception)
        self.assertIn("platform 'A_1'", message)
        self.assertIn("allowed here", message)
        self.assertIn("length_m", message)

    def test_stations_defaults_junctions_and_stretches_are_all_checked(self):
        cases = [
            dict(stations=[{"id": "A", "km": 0.0, "nam": "Ayton"},
                           {"id": "B", "km": 10.0}]),
            dict(defaults={"platform_zone": 400}),
            dict(tracks=[{"id": "T", "direction": "up", "y": 0.0,
                          "serves": ["A", "B"],
                          "block_lengths": [{"from": "A", "to": "B",
                                             "block_len_m": 900}]}]),
            dict(tracks=[
                {"id": "T", "direction": "up", "y": 0.0, "serves": ["A", "B"]},
                {"id": "BR", "direction": "up", "y": -1.0, "serves": ["A", "B"],
                 "junction": {"track": "T", "at": "B", "lenght_m": 400}},
            ]),
        ]
        for changes in cases:
            with self.assertRaises(InfrastructureError, msg=repr(changes)):
                infra(**changes)


class TestUnknownKeysInTheTimetable(unittest.TestCase):

    def setUp(self):
        self.infra = infra()

    def build(self, spec):
        return build_timetable(spec, self.infra)

    def test_a_misspelled_stock_key_is_refused(self):
        with self.assertRaises(ScenarioError) as caught:
            self.build({"stock": [dict(STOCK, servicebrake=0.4)], "services": []})
        self.assertIn("did you mean 'service_brake'", str(caught.exception))

    def test_a_misspelled_call_key_is_refused_and_says_which_call(self):
        with self.assertRaises(ScenarioError) as caught:
            self.build({"stock": [STOCK], "services": [{
                "id": "S1", "stock": "U", "departure": "08:00:00",
                "calls": [{"station": "A", "platform": "A_1",
                           "depature": "08:00:00"},
                          {"station": "B", "platform": "B_1"}]}]})
        message = str(caught.exception)
        self.assertIn("call at 'A'", message)
        self.assertIn("did you mean 'departure'", message)


class TestUnknownKeysInTheScenario(unittest.TestCase):

    def test_a_misspelled_section_key_is_refused(self):
        path = os.path.join(support.CORRIDOR3, "scenario.yaml")
        scenario = load_scenario(path)      # the real one loads
        self.assertTrue(scenario.name)

        with self.assertRaises(ScenarioError):
            schema.check_keys("simulation", {"duration": 3600},
                              schema.SIMULATION, error=ScenarioError)

    def test_a_misspelled_disruption_key_is_refused(self):
        with self.assertRaises(DisruptionError) as caught:
            build_disruptions(
                [{"kind": "dwell_overrun", "service": "S1", "staton": "BETA",
                  "minutes": 4}], parse_clock, kmh_to_ms)
        self.assertIn("staton", str(caught.exception))
        self.assertIn("station", str(caught.exception))


class TestEveryShippedFileStillLoads(unittest.TestCase):
    """The guard that keeps the key lists and the code from drifting apart."""

    def test_every_scenario_loads(self):
        pattern = os.path.join(support.SCENARIOS, "*", "scenario*.yaml")
        paths = sorted(glob.glob(pattern))
        self.assertGreaterEqual(len(paths), 10)
        for path in paths:
            try:
                load_scenario(path)
            except (ScenarioError, InfrastructureError) as exc:
                self.fail("%s no longer loads: %s" % (path, exc))


class TestTheTimetableIsCheckedToo(unittest.TestCase):

    def setUp(self):
        self.infra = infra()

    def timetable(self, calls, **extra):
        service = dict({"id": "S1", "stock": "U", "departure": "08:00:00",
                        "calls": calls}, **extra)
        return build_timetable({"stock": [STOCK], "services": [service]},
                               self.infra)

    def issues(self, calls, **extra):
        return checks.check_timetable(self.infra, self.timetable(calls, **extra))

    def test_a_leg_booked_faster_than_physics_is_reported(self):
        found = self.issues([
            {"station": "A", "platform": "A_1", "departure": "08:00:00"},
            {"station": "B", "platform": "B_1", "arrival": "08:02:00"},
        ])
        self.assertEqual([i.kind for i in found], ["impossible"])
        self.assertIn("fastest the train can physically do it", found[0].detail)

    def test_the_same_leg_with_a_realistic_booking_is_clean(self):
        self.assertEqual(self.issues([
            {"station": "A", "platform": "A_1", "departure": "08:00:00"},
            {"station": "B", "platform": "B_1", "arrival": "08:06:00"},
        ]), [])

    def test_a_call_booked_away_before_it_arrives_is_reported(self):
        found = self.issues([
            {"station": "A", "platform": "A_1", "departure": "08:00:00"},
            {"station": "B", "platform": "B_1", "arrival": "08:06:00",
             "departure": "08:05:00"},
        ])
        self.assertEqual([i.kind for i in found], ["ordering"])

    def test_two_services_booked_into_one_platform_road_are_reported(self):
        timetable = build_timetable({"stock": [STOCK], "services": [
            {"id": "S1", "stock": "U", "departure": "08:00:00",
             "ready_lead_s": 60,
             "calls": [{"station": "A", "platform": "A_1",
                        "departure": "08:00:00"},
                       {"station": "B", "platform": "B_1",
                        "arrival": "08:06:00"}]},
            {"id": "S2", "stock": "U", "departure": "08:00:30",
             "ready_lead_s": 60,
             "calls": [{"station": "A", "platform": "A_1",
                        "departure": "08:00:30"},
                       {"station": "B", "platform": "B_1",
                        "arrival": "08:07:00"}]},
        ]}, self.infra)
        found = checks.check_timetable(self.infra, timetable)
        self.assertTrue(any(i.kind == "clash" for i in found))

    def test_the_bound_is_a_bound(self):
        """No shipped timetable may be called impossible.

        Every one of them is generated from, or checked against, a train that
        actually ran the route - so if the bound ever flags one, the bound is
        wrong rather than the timetable. This is what stops the check from
        becoming a source of false alarms nobody reads.
        """
        pattern = os.path.join(support.SCENARIOS, "*", "scenario*.yaml")
        for path in sorted(glob.glob(pattern)):
            scenario = load_scenario(path)
            found = [i for i in checks.check_timetable(scenario.infrastructure,
                                                       scenario.timetable)
                     if i.kind != "clash"]
            self.assertEqual(found, [], "%s: %s" % (path, found))

    def test_a_platform_clash_is_a_conflict_and_not_a_broken_plan(self):
        """The junction scenario is *built* around a booked platform conflict.

        Reporting that as a fault would cry wolf on every run of a timetable
        that is being worked hard, and the warnings that matter would stop being
        read. It is reported separately, and it does not warn.
        """
        scenario = load_scenario(support.JUNCTION)
        found = checks.check_timetable(scenario.infrastructure, scenario.timetable)
        self.assertTrue(any(i.kind == "clash" for i in found))
        self.assertIsNone(checks.warn_about_timetable(scenario))

        summary = checks.summarise_timetable(found,
                                             len(scenario.timetable.services))
        self.assertIn("workable as booked", summary)
        self.assertIn("booked platform conflicts", summary)

    def test_check_predicts_the_conflict_the_junction_scenario_is_about(self):
        """--check now says what will happen before the run says it did."""
        scenario = load_scenario(support.JUNCTION)
        clashes = [i for i in checks.check_timetable(scenario.infrastructure,
                                                     scenario.timetable)
                   if i.kind == "clash"]
        self.assertTrue(all(i.service.startswith("BU") for i in clashes))
        self.assertTrue(all("BETA_1" in i.detail for i in clashes))


if __name__ == "__main__":
    unittest.main()
