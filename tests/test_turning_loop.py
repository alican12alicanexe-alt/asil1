"""Horseshoes: a one-way curve that turns a train round at the end of a line.

A train runs to the end of the up line, round a 180-degree curve, and back down
the down line, facing the right way throughout. It never reverses and it never
runs against the way a road is signalled, which is what makes a circuit out of
two lines that would otherwise only meet at a crossover.
"""

import unittest

import support

from trainsim.scenario.builder import InfrastructureError, build_infrastructure

#: A short two-station-plus-middle railway with room beyond each terminus. The
#: rails run 1 km short of West and 2 km past East on purpose: a horseshoe has
#: to attach outside a platform zone, and a line whose terminus is the end of
#: the rails has nowhere to put one.
RING = {
    "name": "ring",
    "defaults": {"platform_zone_m": 400, "stop_margin_m": 40,
                 "block_length_m": 1500, "max_speed_kmh": 120},
    "stations": [
        {"id": "W", "name": "West", "km": 3.0},
        {"id": "M", "name": "Middle", "km": 11.0},
        {"id": "E", "name": "East", "km": 19.0},
    ],
    "tracks": [
        {"id": "UP", "direction": "up", "y": 0.0, "serves": ["W", "M", "E"],
         "runs_from_km": 1.0, "runs_to_km": 21.0},
        {"id": "DN", "direction": "down", "y": 0.4, "serves": ["E", "M", "W"],
         "runs_from_km": 21.0, "runs_to_km": 1.0},
    ],
    "platforms": [
        {"id": "W_UP", "station": "W", "track": "UP", "length_m": 200},
        {"id": "M_UP", "station": "M", "track": "UP", "length_m": 200},
        {"id": "E_UP", "station": "E", "track": "UP", "length_m": 200},
        {"id": "W_DN", "station": "W", "track": "DN", "length_m": 200},
        {"id": "M_DN", "station": "M", "track": "DN", "length_m": 200},
        {"id": "E_DN", "station": "E", "track": "DN", "length_m": 200},
    ],
    "turning_loops": [
        {"id": "HS_EAST", "from": "UP", "to": "DN", "km": 21.0,
         "length_m": 900, "max_speed_kmh": 40},
        {"id": "HS_WEST", "from": "DN", "to": "UP", "km": 1.0,
         "length_m": 900, "max_speed_kmh": 40},
    ],
}


def built(**changes):
    spec = dict(RING)
    spec.update(changes)
    return build_infrastructure(spec)


def variant(key, **changes):
    """``RING`` with the first entry of one of its lists altered."""
    entries = [dict(entry) for entry in RING[key]]
    entries[0].update(changes)
    return {key: entries}

class TestTheCircuit(unittest.TestCase):

    def setUp(self):
        self.network = built().network

    def _path(self, start, end, via=()):
        platforms = self.network.platforms
        return self.network.find_path(
            platforms[start].segment, platforms[end].segment,
            via=[platforms[name].segment for name in via])

    def test_a_train_can_go_up_round_and_back_down(self):
        """The move the horseshoe exists for, and the one that used to fail."""
        self.assertTrue(self._path("W_UP", "W_DN", via=["E_UP"]))

    def test_a_train_can_come_back_to_where_it_started(self):
        """A full lap: up the up line, round, down the down line, round again."""
        lap = self._path("W_UP", "W_UP",
                         via=["M_UP", "E_UP", "M_DN", "W_DN"])
        self.assertIn("HS_EAST", lap)
        self.assertIn("HS_WEST", lap)

    def test_the_curve_is_traversed_between_the_two_lines(self):
        """Not around them: the path leaves the up line and joins the down one."""
        lap = self._path("W_UP", "W_DN", via=["E_UP"])
        turn = lap.index("HS_EAST")
        before = self.network.segments[lap[turn - 1]]
        after = self.network.segments[lap[turn + 1]]
        self.assertEqual(before.track, "UP")
        self.assertEqual(after.track, "DN")
        # And it is the curve that turns the train round, not either line.
        self.assertGreater(before.km_end, before.km_start)
        self.assertLess(after.km_end, after.km_start)

    def test_the_curve_carries_its_own_speed(self):
        """A 180-degree curve is slow, and it is slow only for what takes it."""
        segments = self.network.segments
        curve = [s for s in segments.values() if s.turns]
        self.assertTrue(curve)
        for segment in curve:
            self.assertAlmostEqual(segment.max_speed_ms, 40.0 / 3.6, places=6)

    def test_the_line_either_side_of_it_is_not_slowed(self):
        platforms = self.network.platforms
        main = self.network.segments[platforms["E_UP"].segment]
        self.assertGreater(main.max_speed_ms, 40.0 / 3.6)


class TestTheReversalGuard(unittest.TestCase):
    """The path finder refuses to invent a reversal. A horseshoe is not one."""

    def test_only_the_curve_is_exempt(self):
        network = built().network
        turning = [s.id for s in network.segments.values() if s.turns]
        self.assertTrue(turning)
        for segment_id in turning:
            self.assertTrue(segment_id.startswith("HS_"), segment_id)

    def test_without_a_loop_there_is_no_way_round(self):
        """The control: the same railway, minus the curves, cannot do it."""
        network = built(turning_loops=[]).network
        platforms = network.platforms
        with self.assertRaises(ValueError):
            network.find_path(platforms["E_UP"].segment,
                              platforms["W_DN"].segment)


class TestWhatIsRefused(unittest.TestCase):

    def test_a_loop_onto_the_same_road_is_refused(self):
        with self.assertRaises(InfrastructureError) as caught:
            built(**variant("turning_loops", to="UP"))
        self.assertIn("onto itself", str(caught.exception))

    def test_a_loop_between_two_roads_worked_the_same_way_is_refused(self):
        """That is a crossover, and it says so."""
        tracks = [dict(t) for t in RING["tracks"]]
        tracks.append({"id": "UP2", "direction": "up", "y": -0.4,
                       "serves": ["W", "M", "E"],
                       "runs_from_km": 1.0, "runs_to_km": 21.0})
        loops = [dict(RING["turning_loops"][0])]
        loops[0]["to"] = "UP2"
        with self.assertRaises(InfrastructureError) as caught:
            built(tracks=tracks, turning_loops=loops,
                  platforms=RING["platforms"] + [
                      {"id": "W_UP2", "station": "W", "track": "UP2",
                       "length_m": 200}])
        self.assertIn("run the same way", str(caught.exception))

    def test_a_loop_onto_an_unknown_track_is_refused(self):
        with self.assertRaises(InfrastructureError):
            built(**variant("turning_loops", to="NOWHERE"))

    def test_a_loop_with_no_room_beyond_the_terminus_is_refused(self):
        """A line that ends at its last platform has nowhere to put one, which
        is the thing that decides whether a railway can have a horseshoe."""
        tracks = [dict(t) for t in RING["tracks"]]
        for track in tracks:
            track.pop("runs_from_km", None)
            track.pop("runs_to_km", None)
        with self.assertRaises(InfrastructureError):
            built(tracks=tracks)


class TestRunningPastTheTerminus(unittest.TestCase):
    """``runs_to_km``/``runs_from_km``: the rails need not stop at the platform."""

    def test_the_extended_line_is_longer_than_its_stations(self):
        plain = build_infrastructure(dict(
            RING, turning_loops=[],
            tracks=[{k: v for k, v in t.items()
                     if k not in ("runs_from_km", "runs_to_km")}
                    for t in RING["tracks"]]))
        extended = built(turning_loops=[])
        self.assertGreater(_length_of(extended, "UP"), _length_of(plain, "UP"))

    def test_a_terminus_with_line_beyond_it_is_not_at_the_buffer_stops(self):
        """Its platform zone is centred on it like any other station's."""
        network = built(turning_loops=[]).network
        platform = network.segments[network.platforms["E_UP"].segment]
        beyond = [s for s in network.segments.values()
                  if s.track == "UP" and s.km_start >= platform.km_end - 1e-9]
        self.assertTrue(beyond, "no line laid past the terminus")


def _length_of(infra, track_id):
    return sum(s.length_m for s in infra.network.segments.values()
               if s.track == track_id)


if __name__ == "__main__":
    unittest.main()
