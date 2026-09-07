"""The one safety invariant that survives block sections being switched off.

Under moving block and virtual coupling the kernel stops asserting one train per
block, because two trains in one block is the whole point. What it asserts
instead is that no two trains are in the same *place* - and for a long time that
assertion could not fail, whatever the trains did.

The reason is worth remembering. It was written on ``nearest_ahead``, which
answers "what is in front of me" and therefore drops every train that is not
strictly in front. A follower that has run into the train ahead is no longer
behind it, so it was dropped too, and the check quietly reported a clear road at
the moment it was most wrong. Nothing was ever detected because nothing could be.

So these tests do not run a railway and hope. They put two trains where they must
not both be and require the kernel to say so.
"""

import os
import unittest

import support


def two_service_timetable():
    spec = support.one_service_timetable()
    second = dict(spec["services"][0])
    second["id"] = "T2"
    second["name"] = "second test service"
    spec["services"] = [spec["services"][0], second]
    return spec


class TestOverlapIsDetected(unittest.TestCase):

    def setUp(self):
        # strict=False: these runs are meant to violate, and a raise would stop
        # the assertion being made about what was reported.
        self.sim, self.infra, self.timetable = support.build_test_sim(
            two_service_timetable(), dispatcher=support.ManualDispatcher(),
            strict=False)
        for service in self.timetable.services:
            train = service.create_train()
            train.state = "running"
            self.sim.trains[train.id] = train
        self.leader = self.sim.trains["T1"]
        self.follower = self.sim.trains["T2"]

    def place(self, leader_front_m, follower_front_m):
        self.leader.chainage_m = leader_front_m
        self.follower.chainage_m = follower_front_m
        # The kernel refreshes occupancy before it checks its invariants, and
        # the check reads occupancy to decide which pairs are worth comparing.
        self.sim.refresh_occupancy()

    def test_a_clear_gap_is_not_a_violation(self):
        self.place(5000.0, 5000.0 - self.leader.stock.length_m - 100.0)
        self.assertEqual(self.sim.check_separation(), [])

    def test_nose_to_tail_is_not_a_violation(self):
        """Touching is the limit case, and the limit case is still legal."""
        self.place(5000.0, 5000.0 - self.leader.stock.length_m)
        self.assertEqual(self.sim.check_separation(), [])

    def test_a_train_inside_the_one_in_front_is_a_violation(self):
        length = self.leader.stock.length_m
        self.place(5000.0, 5000.0 - length + 70.0)
        problems = self.sim.check_separation()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("T1", problems[0])
        self.assertIn("T2", problems[0])
        self.assertIn("70.0 m", problems[0])

    def test_one_collision_is_reported_once(self):
        """Both trains can see it. A pair is a violation, not two."""
        self.place(5000.0, 4900.0)
        self.assertEqual(len(self.sim.check_separation()), 1)

    def test_it_reaches_the_kernel_and_is_logged(self):
        """check_separation is only useful if _check_invariants calls it."""
        self.place(5000.0, 4900.0)
        self.sim._check_invariants()
        overlaps = [v for v in self.sim.violations if "trains overlap" in v]
        self.assertEqual(len(overlaps), 1, self.sim.violations)
        self.assertIn("share 100.0 m", overlaps[0])
        # Under fixed block the block-exclusivity check sees it as well, which
        # is right and is the point: that one goes away under moving block and
        # virtual coupling, and then this is the only thing left.
        self.assertTrue(any("holds T1, T2" in v for v in self.sim.violations))

    def test_a_finished_train_is_not_in_the_way(self):
        self.place(5000.0, 4900.0)
        self.leader.state = "finished"
        self.sim.refresh_occupancy()
        self.assertEqual(self.sim.check_separation(), [])


class TestBlocksTileTheRailway(unittest.TestCase):
    """Every segment belongs to a block, on every railway in the repository.

    :meth:`Simulation.check_separation` only compares trains that share an
    occupied block, which is sound exactly while this holds: a piece of rail
    outside every block is a piece two trains could share unseen. It is cheap to
    assert and it is the assumption that makes the check affordable.
    """

    def test_no_segment_is_outside_every_block(self):
        from trainsim.scenario.loader import load_scenario
        railways = sorted({os.path.dirname(p)
                           for p in support.every_railway("scenario.yaml")})
        self.assertGreaterEqual(len(railways), 6)
        for directory in railways:
            infra = load_scenario(directory).infrastructure
            outside = sorted(s for s in infra.network.segments
                             if s not in infra.block_of_segment)
            self.assertEqual(outside, [], "%s: %s" % (directory, outside))


if __name__ == "__main__":
    unittest.main()
