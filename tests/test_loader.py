"""Scenario loading, and the no-dependency YAML fallback.

The important test here is that the built-in YAML subset parser agrees with
PyYAML on every file the project ships. That is what makes "runs on a machine
where nothing can be installed" a checked claim rather than a hope.
"""

import glob
import os
import unittest

import support
from trainsim.scenario import minyaml
from trainsim.scenario.builder import InfrastructureError, build_infrastructure
from trainsim.scenario.loader import ScenarioError, load_scenario

try:
    import yaml as pyyaml
except ImportError:
    pyyaml = None


class TestMiniYaml(unittest.TestCase):

    def test_scalars(self):
        self.assertEqual(minyaml.parse("a: 1"), {"a": 1})
        self.assertEqual(minyaml.parse("a: 1.5"), {"a": 1.5})
        self.assertEqual(minyaml.parse("a: true"), {"a": True})
        self.assertEqual(minyaml.parse("a: null"), {"a": None})
        self.assertEqual(minyaml.parse('a: "07:30:00"'), {"a": "07:30:00"})

    def test_comments_are_stripped_but_not_inside_quotes(self):
        self.assertEqual(minyaml.parse("a: 1  # trailing"), {"a": 1})
        self.assertEqual(minyaml.parse('a: "x # y"'), {"a": "x # y"})

    def test_nested_blocks_and_sequences(self):
        text = (
            "root:\n"
            "  items:\n"
            "    - id: one\n"
            "      value: 1\n"
            "    - {id: two, value: 2}\n"
            "  flat: [a, b, c]\n"
        )
        self.assertEqual(minyaml.parse(text), {
            "root": {
                "items": [{"id": "one", "value": 1}, {"id": "two", "value": 2}],
                "flat": ["a", "b", "c"],
            },
        })

    def test_tabs_are_rejected_with_a_clear_message(self):
        with self.assertRaises(minyaml.MiniYamlError) as caught:
            minyaml.parse("a:\n\t- 1\n")
        self.assertIn("tab", str(caught.exception).lower())

    @unittest.skipIf(pyyaml is None, "PyYAML is not installed on this machine")
    def test_agrees_with_pyyaml_on_every_shipped_scenario(self):
        pattern = os.path.join(support.SCENARIOS, "*", "*.yaml")
        files = sorted(glob.glob(pattern))
        self.assertTrue(files, "no scenario files found to compare")
        for path in files:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual(
                minyaml.parse(text), pyyaml.safe_load(text),
                "the built-in parser disagrees with PyYAML on %s" % path,
            )


class TestScenarioLoading(unittest.TestCase):

    def test_corridor3_loads(self):
        scenario = load_scenario(support.CORRIDOR3)
        self.assertEqual(scenario.name, "corridor3")
        self.assertEqual(len(scenario.timetable.services), 9)

    def test_missing_scenario_is_reported_clearly(self):
        with self.assertRaises(ScenarioError):
            load_scenario(os.path.join(support.SCENARIOS, "nope"))

    def test_unknown_platform_is_reported_with_the_service_name(self):
        infra = build_infrastructure(support.TEST_INFRA)
        from trainsim.scenario.loader import build_timetable
        spec = support.one_service_timetable()
        spec["services"][0]["calls"][1]["platform"] = "GHOST"
        with self.assertRaises(ScenarioError) as caught:
            build_timetable(spec, infra)
        self.assertIn("T1", str(caught.exception))
        self.assertIn("GHOST", str(caught.exception))


class TestInfrastructureValidation(unittest.TestCase):

    def _spec(self, **changes):
        spec = {
            "name": "t", "stations": list(support.TEST_INFRA["stations"]),
            "tracks": [dict(support.TEST_INFRA["tracks"][0])],
            "platforms": list(support.TEST_INFRA["platforms"]),
        }
        spec.update(changes)
        return spec

    def test_stations_out_of_travel_order_are_rejected(self):
        spec = self._spec()
        spec["tracks"][0]["serves"] = ["B", "A"]
        with self.assertRaises(InfrastructureError) as caught:
            build_infrastructure(spec)
        self.assertIn("direction of travel", str(caught.exception))

    def test_a_station_with_no_platform_on_a_serving_track_is_rejected(self):
        spec = self._spec()
        spec["platforms"] = [p for p in spec["platforms"] if p["id"] != "B_1"]
        with self.assertRaises(InfrastructureError) as caught:
            build_infrastructure(spec)
        self.assertIn("no platform", str(caught.exception))

    def test_a_line_too_short_for_its_platforms_is_rejected(self):
        spec = self._spec()
        spec["stations"] = [
            {"id": "A", "name": "A", "km": 0.0},
            {"id": "B", "name": "B", "km": 0.3},   # 300 m apart, zones are 400 m
        ]
        spec["defaults"] = {"platform_zone_m": 400}
        with self.assertRaises(InfrastructureError) as caught:
            build_infrastructure(spec)
        self.assertIn("outside the line", str(caught.exception))

    def test_overlapping_platform_zones_are_rejected(self):
        """Stations closer together than a platform zone cannot both be signalled."""
        spec = self._spec()
        spec["defaults"] = {"platform_zone_m": 400}
        spec["stations"] = [
            {"id": "A", "name": "A", "km": 0.0},
            {"id": "B", "name": "B", "km": 0.5},   # B's zone [300, 700] hits A's [0, 400]
            {"id": "C", "name": "C", "km": 2.0},
        ]
        spec["tracks"][0]["serves"] = ["A", "B", "C"]
        spec["platforms"] = spec["platforms"][:1] + [
            {"id": "B_1", "station": "B", "track": "T", "length_m": 200},
            {"id": "C_1", "station": "C", "track": "T", "length_m": 200},
        ]
        with self.assertRaises(InfrastructureError) as caught:
            build_infrastructure(spec)
        self.assertIn("overlap", str(caught.exception))

    def test_per_stretch_block_length_is_applied(self):
        spec = self._spec()
        spec["tracks"][0]["block_lengths"] = [
            {"from": "A", "to": "B", "block_length_m": 1200},
        ]
        infra = build_infrastructure(spec)
        lengths = [b.length_m for b in support.running_blocks(infra)]
        self.assertEqual(len(lengths), 8)          # 9200 m / 1200 -> 8 blocks
        for length in lengths:
            self.assertAlmostEqual(length, 9200.0 / 8, places=6)


if __name__ == "__main__":
    unittest.main()
