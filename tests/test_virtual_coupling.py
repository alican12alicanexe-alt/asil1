"""Virtual coupling's separation terms, and the brake it credits the leader with."""

import unittest

import support  # noqa: F401  - puts the package on the path

from trainsim.core.train import RollingStock
from trainsim.core.signalling import VirtualCoupling
from trainsim.core.units import braking_distance, kmh_to_ms

STOCK = RollingStock(id="UNIT", name="Test unit", length_m=200.0,
                     max_speed_ms=kmh_to_ms(140.0), max_accel=0.9,
                     service_brake=0.7, emergency_brake=1.2)


class Leader:
    """Just enough of a train for :meth:`VirtualCoupling._run_on_m`."""

    def __init__(self, speed_ms):
        self.speed_ms = speed_ms
        self.stock = STOCK


SPEED = 33.3  # m/s, about 120 km/h


class TestLeaderBrake(unittest.TestCase):

    def test_the_default_credits_the_leader_with_its_hardest_brake(self):
        """The follower plans to stop where the leader stops, so by default it
        assumes the leader stops as short as it possibly can."""
        leader = Leader(SPEED)
        run_on = VirtualCoupling()._run_on_m(leader)
        self.assertAlmostEqual(
            run_on, braking_distance(SPEED, leader.stock.emergency_brake))

    def test_the_convoy_rule_credits_the_service_brake_instead(self):
        leader = Leader(SPEED)
        run_on = VirtualCoupling(leader_brake="service")._run_on_m(leader)
        self.assertAlmostEqual(
            run_on, braking_distance(SPEED, leader.stock.service_brake))

    def test_the_convoy_rule_is_the_one_that_buys_separation(self):
        """Crediting the softer brake moves the danger point further away, which
        is the whole of what the rule is worth."""
        leader = Leader(SPEED)
        self.assertGreater(VirtualCoupling(leader_brake="service")._run_on_m(leader),
                           VirtualCoupling()._run_on_m(leader) * 1.2)

    def test_neither_setting_borrows_anything_from_a_standing_train(self):
        """A convoy closing on a stopped train is moving block, correctly:
        there is nothing left to borrow."""
        for choice in VirtualCoupling.LEADER_BRAKE:
            system = VirtualCoupling(leader_brake=choice)
            self.assertEqual(system._run_on_m(Leader(0.0)), 0.0, choice)

    def test_turning_relative_braking_off_beats_either_setting(self):
        """The switch that makes this moving block has to win, or a run made to
        measure the benefit would still be collecting it."""
        for choice in VirtualCoupling.LEADER_BRAKE:
            system = VirtualCoupling(leader_brake=choice,
                                     assume_leader_brakes=False)
            self.assertEqual(system._run_on_m(Leader(SPEED)), 0.0, choice)

    def test_an_unknown_brake_is_refused_at_construction(self):
        """Silently falling back would look like a capacity result."""
        with self.assertRaises(ValueError):
            VirtualCoupling(leader_brake="handbrake")

    def test_the_setting_is_named_in_what_the_system_reports(self):
        """A run's own description has to say which safety case it was made on."""
        for choice in VirtualCoupling.LEADER_BRAKE:
            self.assertIn(choice, VirtualCoupling(leader_brake=choice).describe())


class TestMargins(unittest.TestCase):

    def test_the_margin_grows_with_speed_by_the_radio_delay(self):
        """What the follower covers while the news is in flight."""
        system = VirtualCoupling(safety_margin_m=50.0, v2v_latency_s=0.5)

        class Follower:
            speed_ms = 0.0

        follower = Follower()
        self.assertAlmostEqual(system._margin_m(follower), 50.0)
        follower.speed_ms = SPEED
        self.assertAlmostEqual(system._margin_m(follower), 50.0 + SPEED * 0.5)

    def test_the_degraded_margin_is_not_the_coupled_one(self):
        """The tight margin is justified by the link; without it, moving block's."""
        system = VirtualCoupling()
        self.assertGreater(system.fallback_margin_m, system.safety_margin_m)


if __name__ == "__main__":
    unittest.main()
