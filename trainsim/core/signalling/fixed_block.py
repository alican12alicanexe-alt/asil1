"""Conventional three-aspect lineside signalling.

The distinguishing feature of lineside signalling - and the reason ETCS Level 2
will later show a shorter headway on identical infrastructure - is that
information reaches the driver *discretely*. A driver learns the state of the
railway only when a signal is sighted or passed, so braking for an occupied block
starts at the yellow signal one block back, not at the point where braking would
actually need to begin.

That behaviour is modelled explicitly here:

* ``observe`` reads the aspect of the next signal once it is within sighting
  distance, and promotes that reading to the "latched" aspect when the signal is
  passed. Reading the aspect *after* passing would show red - the train's own
  occupation of the block it just entered - which is why the sighted value is
  captured on approach.
* ``movement_authority`` turns the governing aspect into a distance and a target
  speed. Nothing else in the simulator knows what an aspect is.

Block lengths must exceed the service braking distance from line speed, or a
driver who passes a yellow cannot stop at the following red. The corridor scenario
uses 2000 m blocks against a ~1300 m braking distance from 140 km/h.

Two-block working is the same three aspects with the reds spread wider, and it is
:class:`TwoBlockFixedBlock` below.
"""

from ..signals import Aspect
from .base import MovementAuthority, SignallingSystem


class ThreeAspectFixedBlock(SignallingSystem):
    """Conventional red / yellow / green fixed-block signalling."""

    name = "fixed_block_3aspect"

    def __init__(self, sighting_distance_m: float = 250.0):
        super().__init__()
        self.sighting_distance_m = float(sighting_distance_m)

    # ------------------------------------------------------------------ observe

    def observe(self, train, sim) -> None:
        path = train.path

        # Promote the aspect sighted on approach for every signal now behind us.
        while train.passed_signal_index + 1 < len(path.signals):
            signal_id, signal_m = path.signals[train.passed_signal_index + 1]
            if signal_m > train.chainage_m:
                break
            if train.sighted_signal_id == signal_id:
                train.latched_aspect = train.sighted_aspect
            train.latched_signal_id = signal_id
            train.passed_signal_index += 1

        # Read the next signal ahead once it comes into sight.
        upcoming = path.next_signal(train.chainage_m)
        if upcoming is not None:
            signal_id, signal_m, _ = upcoming
            if signal_m - train.chainage_m <= self.sighting_distance_m:
                train.sighted_signal_id = signal_id
                train.sighted_aspect = sim.aspects.get(signal_id, Aspect.GREEN)

    # -------------------------------------------------------- movement authority

    def movement_authority(self, train, sim) -> MovementAuthority:
        path = train.path
        front = train.chainage_m

        upcoming = path.next_signal(front)
        if upcoming is None:
            return MovementAuthority(
                end_distance_m=path.total_m - front,
                target_speed_ms=0.0,
                reason="end of line",
            )

        signal_id, signal_m, index = upcoming
        distance = signal_m - front
        in_sight = distance <= self.sighting_distance_m

        if in_sight:
            aspect = sim.aspects.get(signal_id, Aspect.GREEN)
            if aspect == Aspect.RED:
                # Stop at this signal.
                return MovementAuthority(distance, 0.0, reason="signal at danger")
            if aspect == Aspect.YELLOW:
                # May pass, but the block beyond is occupied: stop at the next one.
                return MovementAuthority(
                    self._distance_to_signal(path, index + 1, front),
                    0.0,
                    reason="approaching caution",
                )
            # Green: two blocks clear, so the limit is the signal after next.
            return MovementAuthority(
                self._distance_to_signal(path, index + 2, front),
                0.0,
                reason="clear",
            )

        # Out of sight of the next signal: act on what the last signal said.
        if train.latched_aspect == Aspect.RED:
            # Should not happen - a train does not pass a signal at danger. Treated
            # as an immediate stop so that a bug fails safe and loudly.
            return MovementAuthority(0.0, 0.0, reason="passed signal at danger")
        if train.latched_aspect == Aspect.YELLOW:
            return MovementAuthority(distance, 0.0, reason="obeying caution")
        return MovementAuthority(
            self._distance_to_signal(path, index + 1, front),
            0.0,
            reason="running on clear",
        )

    @staticmethod
    def _distance_to_signal(path, index: int, front: float) -> float:
        """Distance to the signal at ``index``, or to the end of the path."""
        target = path.signal_at_index(index)
        if target is None:
            return path.total_m - front
        return target[1] - front

    def describe(self) -> str:
        return "conventional 3-aspect fixed block (sighting %.0f m)" % (
            self.sighting_distance_m,
        )


class TwoBlockFixedBlock(ThreeAspectFixedBlock):
    """Three aspects, but a train holds two block sections at danger behind it.

    The aspects and their meanings are exactly those of the class above - red is
    stop, yellow is stop at the next one, green is at least two sections clear -
    and the driver model cannot tell the two systems apart. What changes is
    *where the reds fall*. A signal here answers not only for its own section but
    for the section beyond it, so a single train puts danger on two signals
    rather than one:

        conventional   ... GREEN --- YELLOW --- RED  [train] ...
        two-block      ... GREEN --- YELLOW --- RED --- RED  [train] ...

    **This is not an optimisation.** Four-aspect signalling spends an extra
    indication to *shorten* blocks; two-block working spends a whole extra
    section to buy stopping room, and pays for it in headway. The section behind
    the train is a full-block overlap: it is there so that a train which runs
    past the red - a brake that does not make its book rate, a driver who reads
    the yellow late, a trip-stop applied at the last moment - still comes to a
    stand with a clear section between it and the train ahead.

    That trade is worth making where the overlap is the only thing standing
    between a SPAD and a collision, and blocks are short enough that losing one
    to it is affordable: metros with close signal spacing, no preliminary caution
    aspect to give and an automatic train stop as the backstop. New York's
    two-block and three-block spacing is the canonical example, and
    ``blocks_held`` covers both.

    The cost is arithmetic. A follower may run unchecked only from behind a
    green, which is now one section further back than it was, so the separation
    it must keep goes from two block lengths to three - half as much line again
    for the same train. ``--check`` reports the headway that implies, and
    ``--compare fixed_block_3aspect fixed_block_2block`` measures what it
    actually costs on a given timetable.
    """

    name = "fixed_block_2block"

    #: Fewer than this and there is no overlap to speak of.
    MINIMUM_BLOCKS_HELD = 2

    def __init__(self, sighting_distance_m: float = 250.0, blocks_held: int = 2):
        #: Sections held at danger behind one train, counting the one it is
        #: standing in. Two is two-block working; three is three-block working,
        #: which trades another section for another overlap.
        blocks_held = int(blocks_held)
        if blocks_held < self.MINIMUM_BLOCKS_HELD:
            raise ValueError(
                "blocks_held must be at least %d, got %d - holding one section "
                "behind a train is conventional working, which is "
                "fixed_block_3aspect"
                % (self.MINIMUM_BLOCKS_HELD, blocks_held)
            )
        self.blocks_held = blocks_held
        # One of the held sections is the train's own; the rest are overlap.
        self.overlap_blocks = blocks_held - 1
        super().__init__(sighting_distance_m=sighting_distance_m)

    def describe(self) -> str:
        return ("%d-block fixed block, 3 aspects (%d-section overlap, "
                "sighting %.0f m)"
                % (self.blocks_held, self.overlap_blocks, self.sighting_distance_m))
