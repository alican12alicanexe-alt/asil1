"""The metro scenario: what distance separation buys, and what it does not.

corridor3 shows the ETCS ladder on a main line, where most of the benefit comes
from removing the driver's sighting and reaction penalty - so Level 2 captures
nearly all of it. The metro line is the other case. Its constraint is how fast a
platform can be reoccupied, which is a question of *granularity*: the block is
the unit of separation whether the driver is told about it by a lamp or by radio.

These tests pin down that distinction, because it is the scenario's whole claim
and it would be easy for a later change to quietly erase it. They also pin the
two limits on the other side - the headway nothing delivers, and what one
unfitted unit does to the trains behind it - so the project cannot drift into
overselling moving block.
"""

import unittest

import support
from trainsim.scenario import checks
from trainsim.scenario.loader import build_simulation, load_scenario
from trainsim.analysis.kpi import measure

#: The timetable is booked at this interval; the assertions below are stated in
#: terms of it rather than in bare seconds.
HEADWAY_S = 75.0


def run(path, system, **settings):
    """Measure one run of one scenario under one signalling system."""
    scenario = load_scenario(path)
    scenario.signalling_spec = dict(settings, system=system)
    return measure(build_simulation(scenario))


class TestMetroLayout(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(support.METRO)

    def test_it_expands_into_the_line_described(self):
        infra = self.scenario.infrastructure
        self.assertEqual(len(infra.network.stations), 6)
        self.assertEqual(len(infra.network.platforms), 12)
        # No points anywhere: an island platform each way, nothing to overtake.
        self.assertEqual(infra.points, {})
        self.assertEqual(infra.controlled_signals(), ())
        self.assertEqual(len(infra.signals), len(infra.blocks))

    def test_every_block_is_signalable(self):
        """The line must be buildable under fixed block, or the comparison is void."""
        results = checks.check_block_lengths(
            self.scenario.infrastructure, self.scenario.timetable,
            self.scenario.driver_config,
        )
        self.assertTrue(results)
        self.assertEqual(checks.failures(results), [])

    def test_the_open_line_could_carry_this_headway_under_fixed_block(self):
        """The binding constraint is the station, not signal spacing.

        This is the assertion that makes the rest of the scenario mean anything.
        If the blocks were simply too long for a 75-second headway then fixed
        block failing would prove nothing except that the layout was badly
        signalled. They are not: two blocks plus a train length at line speed is
        comfortably inside the headway everywhere on the open line.
        """
        results = checks.check_block_lengths(
            self.scenario.infrastructure, self.scenario.timetable,
            self.scenario.driver_config,
        )
        open_line = [r for r in results
                     if self.scenario.infrastructure.blocks[r.block_id].platform is None]
        self.assertTrue(open_line)
        self.assertLess(max(r.headway_s for r in open_line), HEADWAY_S)


class TestWhatSeparationBuys(unittest.TestCase):
    """One run per system, shared - each takes a couple of seconds."""

    @classmethod
    def setUpClass(cls):
        cls.fixed = run(support.METRO, "fixed_block_3aspect")
        cls.l2 = run(support.METRO, "etcs_l2")
        cls.hybrid = run(support.METRO, "etcs_hybrid_l3")
        cls.moving = run(support.METRO, "etcs_moving_block")

    def test_every_service_completes_under_every_system(self):
        for metrics in (self.fixed, self.l2, self.hybrid, self.moving):
            self.assertEqual(metrics.completed, metrics.services, metrics.system)
            self.assertEqual(metrics.violations, 0, metrics.system)

    def test_moving_block_all_but_delivers_the_plan(self):
        """Every train runs its booked path to within a few seconds of it.

        Not to the second, and the reason is worth stating. The plan is booked on
        the run times of a *single* unimpeded train, and a real train takes the
        better part of half a minute to get back up to line speed after a call.
        So in a flight at a 75-second headway the following train closes on the
        one in front while that one is braking into the next platform, and its
        authority - the rear of the train ahead, less its own braking distance -
        checks it from 89 to about 80 km/h on each station approach. Four
        stations, about eleven seconds of easing off at each.

        That is the station reoccupation limit showing through, which is this
        scenario's whole subject. It costs three seconds a train here. Fixed
        block, on the same plan and the same physics, costs ninety-seven.
        """
        self.assertLess(self.moving.mean_delay_s, 5.0)
        self.assertLess(max(self.moving.delays.values()), 6.0)
        # Held back on the approaches, not held at a stand: an order of
        # magnitude less restraint than the section-separated systems.
        self.assertLess(self.moving.total_restrained_s,
                        0.35 * self.fixed.total_restrained_s)
        for train_id, seconds in self.moving.restrained_s.items():
            self.assertLess(seconds, 60.0, train_id)

    def test_fixed_block_loses_about_a_headway_per_train(self):
        self.assertGreater(self.fixed.mean_delay_s, 0.6 * HEADWAY_S)
        self.assertGreater(self.fixed.total_restrained_s, 1000.0)

    def test_level_2_barely_helps_on_this_line(self):
        """The point of the scenario, and the opposite of corridor3.

        Continuous radio authority removes the sighting and reaction penalty,
        which is worth minutes on a fast main line. Here it is worth a second,
        because what is actually holding the following train back is that the
        train in front occupies a whole detection section while it stands at the
        platform - and Level 2 still separates by section.
        """
        gain = self.fixed.mean_journey_s - self.l2.mean_journey_s
        self.assertLess(gain, 5.0,
                        "Level 2 gained %.0f s; this scenario is supposed to "
                        "show that it cannot" % gain)
        self.assertGreater(self.l2.mean_delay_s, 0.5 * HEADWAY_S)

    def test_finer_granularity_is_what_helps(self):
        """Hybrid L3 and moving block improve; the fixed-block systems do not.

        Ordered by how finely each one can say where a train is.
        """
        self.assertGreater(self.l2.mean_journey_s - self.hybrid.mean_journey_s, 30.0)
        self.assertLessEqual(self.moving.mean_journey_s, self.hybrid.mean_journey_s)
        self.assertLess(self.moving.total_restrained_s, self.hybrid.total_restrained_s)

    def test_authority_length_grows_with_granularity(self):
        """The mechanism behind the journey times, not just the outcome."""
        lengths = [m.mean_authority_m
                   for m in (self.fixed, self.l2, self.hybrid, self.moving)]
        self.assertEqual(lengths, sorted(lengths))

    def test_sub_sections_want_sizing_against_braking_distance(self):
        """Hybrid L3's default granularity is too coarse for a metro.

        Four sub-sections per section is 150 m here, and a moving-block authority
        on a platform approach leaves about 145 m - so the default cannot match
        it. Twelve can. The conclusion is that sub-sections should be sized
        against braking distance at the local speed rather than counted per
        block, and it is asserted here so that it stays a measured result.
        """
        fine = run(support.METRO, "etcs_hybrid_l3", vss_per_block=12)
        self.assertGreater(self.hybrid.total_restrained_s, 0.0)
        self.assertLess(fine.total_restrained_s,
                        0.5 * self.hybrid.total_restrained_s)
        # Down to the residual every system pays on this plan - the approach
        # check behind a train that is still getting away from the platform in
        # front - and nothing more. The coarse setting loses three times as much.
        self.assertLess(fine.mean_delay_s, 5.0)
        self.assertLess(fine.mean_delay_s, 0.5 * self.hybrid.mean_delay_s)


class TestTheLimitsOnTheOtherSide(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sixty = run(support.METRO_60, "etcs_moving_block")
        cls.sixty_fixed = run(support.METRO_60, "fixed_block_3aspect")
        cls.mixed = run(support.METRO_MIXED, "etcs_moving_block")

    def test_sixty_seconds_defeats_moving_block_too(self):
        """Distance separation moves the limit; it does not remove it.

        What is left is dwell time plus the time a following train needs to close
        up and berth, and no train control system shortens either.
        """
        self.assertGreater(self.sixty.mean_delay_s, 20.0)
        self.assertGreater(self.sixty.total_restrained_s, 0.0)
        # Still much better than fixed block - just not good enough.
        self.assertLess(self.sixty.mean_delay_s, 0.5 * self.sixty_fixed.mean_delay_s)

    def test_an_unfitted_unit_is_paid_for_by_the_trains_behind_it(self):
        """U06 has no integrity monitoring. U06 is not the train that suffers.

        The unit runs its own booked path perfectly; it is the services following
        it that are pushed back to section separation. That the cost falls
        somewhere other than on the decision is the systems point of the variant,
        so it is asserted rather than left to be read off a table.
        """
        self.assertGreater(self.mixed.total_restrained_s, 100.0)

        # Everything in the flight pays the few seconds of approach check that
        # a 75-second headway costs whatever the signalling; what marks the
        # unfitted unit is that it pays nothing *else*, while the train behind
        # it is pushed back to section separation and loses minutes.
        unfitted = self.mixed.restrained_s.get("U06", 0.0)
        self.assertLess(unfitted, 60.0)
        self.assertLess(self.mixed.delays["U06"], 5.0)
        self.assertGreater(self.mixed.restrained_s.get("U07", 0.0),
                           10.0 * unfitted)
        self.assertGreater(self.mixed.delays["U07"],
                           10.0 * self.mixed.delays["U06"])

        # Trains ahead of it are untouched by it: none of them is checked any
        # harder than the train at the head of the flight that has nothing in
        # front of it at all.
        for train_id in ("U01", "U02", "U03", "U04", "U05"):
            self.assertLess(self.mixed.restrained_s.get(train_id, 0.0), 60.0,
                            train_id)
            self.assertLess(self.mixed.delays[train_id], 5.0, train_id)

    def test_the_delay_does_not_wash_out(self):
        """A plan booked at the achievable headway has no slack to recover in."""
        self.assertGreater(self.mixed.delays["U12"], 0.0,
                           "the last train of the flight recovered, so this "
                           "timetable has slack the scenario claims it lacks")


if __name__ == "__main__":
    unittest.main()
