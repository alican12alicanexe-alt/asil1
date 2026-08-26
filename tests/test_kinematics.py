"""Braking and berthing: does a train stop where the physics says it should?"""

import unittest

import support
from trainsim.core.units import braking_distance, kmh_to_ms, ms_to_kmh


class TestBraking(unittest.TestCase):

    def test_braking_distance_is_its_own_inverse(self):
        from trainsim.core.units import speed_from_braking_distance
        speed = kmh_to_ms(140)
        distance = braking_distance(speed, 0.7)
        self.assertAlmostEqual(
            speed_from_braking_distance(distance, 0.7), speed, places=6
        )

    def test_braking_distance_from_line_speed(self):
        # 140 km/h at 0.7 m/s2 is the figure the corridor scenario is designed
        # around; if this moves, the block lengths need revisiting.
        self.assertAlmostEqual(braking_distance(kmh_to_ms(140), 0.7), 1080.2, places=1)

    def test_train_berths_at_the_platform(self):
        """A train runs A to B and comes to a stand on its stopping point."""
        sim, infra, timetable = support.build_test_sim()
        service = timetable.services[0]
        stop = service.stops[-1]

        top_speed = 0.0
        brake_start = None
        while not sim.finished:
            sim.step()
            train = sim.trains.get("T1")
            if train is None:
                continue
            top_speed = max(top_speed, train.speed_ms)
            if (brake_start is None and top_speed > 1.0
                    and train.speed_ms < top_speed - 1.0):
                brake_start = train.chainage_m
            if train.state == "finished":
                break

        train = sim.trains["T1"]
        self.assertEqual(train.state, "finished")
        self.assertEqual(train.speed_ms, 0.0)
        self.assertIn("B", train.actual_arrivals)

        # Stopped on the mark, not merely near it.
        self.assertLess(abs(train.chainage_m - stop.stop_chainage_m), 1.0)

        # Reached line speed on the way.
        self.assertGreater(ms_to_kmh(top_speed), 139.0)

        # Braking began no earlier than it needed to, and not unreasonably late.
        needed = braking_distance(top_speed, service.stock.service_brake)
        run_in = stop.stop_chainage_m - brake_start
        self.assertGreater(run_in, needed * 0.9)
        self.assertLess(run_in, needed * 1.8)

    def test_advance_does_not_reverse_through_zero(self):
        """Braking harder than the remaining speed stops the train, not reverses it."""
        sim, infra, timetable = support.build_test_sim()
        train = timetable.services[0].create_train()
        train.state = "running"
        train.speed_ms = 2.0
        start = train.chainage_m
        moved = train.advance(-10.0, 1.0)
        self.assertEqual(train.speed_ms, 0.0)
        self.assertGreater(moved, 0.0)
        self.assertAlmostEqual(moved, 0.2, places=6)  # 0.5 * 2.0 * (2.0/10.0)
        self.assertAlmostEqual(train.chainage_m - start, moved, places=6)

    def test_train_never_exceeds_its_speed_limit(self):
        sim, infra, timetable = support.build_test_sim()
        limit = timetable.services[0].stock.max_speed_ms
        while not sim.finished:
            sim.step()
            train = sim.trains.get("T1")
            if train is not None:
                self.assertLessEqual(train.speed_ms, limit + 1e-9)
                if train.state == "finished":
                    break


if __name__ == "__main__":
    unittest.main()
