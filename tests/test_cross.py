"""The flat crossing on the ring: that it is there, and that it can be taken away.

The whole of scenarios/ring/_sweep_cross.py rests on two things being true of
the drawing - that the four diamonds really do put the circuit's blocks and the
crossing railway's blocks in conflict, and that ``grade_separated`` really does
remove exactly that and nothing else. Neither is visible in a run: a crossing
that was never declared and a flyover that was never built both look like a
railway with no delays on it.
"""
import os
import unittest

import support

from trainsim.scenario.builder import build_infrastructure
from trainsim.scenario.loader import read_data_file

DRAWING = os.path.join(support.SCENARIOS, "ring", "infrastructure-cross.yaml")


def infrastructure(grade_separated=None):
    spec = read_data_file(DRAWING)
    if grade_separated is not None:
        for crossover in spec["crossovers"]:
            if crossover.get("type") == "diamond":
                crossover["grade_separated"] = grade_separated
    return build_infrastructure(spec)


def crossing_pairs(infra):
    """``{(block, block)}`` for every pair the interlocking holds exclusive."""
    return {tuple(sorted((block, other)))
            for block, others in infra.crossings.items() for other in others}


class TestTheCrossingIsThere(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.flat = infrastructure()
        cls.flyover = infrastructure(grade_separated=True)

    def test_a_circuit_block_conflicts_with_a_crossing_block(self):
        pairs = crossing_pairs(self.flat)
        across = {pair for pair in pairs
                  if any(block.startswith("CROSS_") for block in pair)}
        self.assertTrue(across, "the diamonds put nothing in conflict")

    def test_both_crossing_lines_cross_both_circuit_lines(self):
        """Four diamonds, so four pairs - a double junction, not a single."""
        pairs = crossing_pairs(self.flat)
        across = {pair for pair in pairs
                  if any(block.startswith("CROSS_") for block in pair)}
        self.assertEqual(len(across), 4, sorted(across))
        for pair in across:
            crossing = [b for b in pair if b.startswith("CROSS_")]
            circuit = [b for b in pair if not b.startswith("CROSS_")]
            self.assertEqual(len(crossing), 1, pair)
            self.assertEqual(len(circuit), 1, pair)

    def test_the_two_crossing_lines_do_not_conflict_with_each_other(self):
        """Parallel roads of one railway are not in each other's way."""
        for pair in crossing_pairs(self.flat):
            self.assertFalse(all(block.startswith("CROSS_") for block in pair),
                             "%s and %s are the same railway's two roads" % pair)

    def test_a_flyover_takes_the_conflict_away(self):
        flat = {pair for pair in crossing_pairs(self.flat)
                if any(block.startswith("CROSS_") for block in pair)}
        over = {pair for pair in crossing_pairs(self.flyover)
                if any(block.startswith("CROSS_") for block in pair)}
        self.assertTrue(flat)
        self.assertFalse(over)

    def test_a_flyover_changes_nothing_else(self):
        """Same blocks, same signals, same routes - only the conflict differs.

        This is what makes the two runs a controlled experiment rather than two
        railways that happen to resemble each other.
        """
        self.assertEqual(sorted(self.flat.blocks), sorted(self.flyover.blocks))
        self.assertEqual(sorted(self.flat.signals), sorted(self.flyover.signals))
        self.assertEqual(sorted(self.flat.routes), sorted(self.flyover.routes))

    def test_the_crossing_railway_joins_the_circuit_nowhere(self):
        """A diamond is a conflict, not a connection - no rail runs between them.

        Two railways that share a node share a way from one to the other, and
        this would be a junction rather than a crossing: the experiment would be
        measuring a merge again, which is the thing it exists to stop doing.
        """
        mine, theirs = set(), set()
        for segment in self.flat.network.segments.values():
            ends = {segment.start_node, segment.end_node}
            (mine if segment.track.startswith("CROSS_") else theirs).update(ends)
        self.assertTrue(mine, "there is no crossing railway")
        self.assertEqual(mine & theirs, set(),
                         "the two railways share a node, so a train could get "
                         "from one to the other")


class TestTheCrossingIsClearOfThePlatforms(unittest.TestCase):
    """km 26.60 was chosen to be clear of a platform and clear of the points.

    The gap between Teknopark 2 and Akyurt 3 is the widest on the circuit, and
    if a station were ever moved into it this experiment would quietly go back
    to measuring a platform.
    """

    def test_no_platform_stands_on_a_crossing_block(self):
        infra = infrastructure()
        conflicted = {block for block, others in infra.crossings.items()
                      if block.startswith("CROSS_")
                      or any(other.startswith("CROSS_") for other in others)}
        self.assertTrue(conflicted)
        for block in conflicted:
            for segment_id in infra.blocks[block].segment_ids:
                segment = infra.network.segments[segment_id]
                self.assertFalse(
                    segment.is_platform,
                    "%s is a platform road and is held exclusive by the "
                    "crossing, so this measures a station again" % segment_id)


if __name__ == "__main__":
    unittest.main()
