"""ETCS Levels 1 and 2, and full moving block (Level 3).

The three differ along exactly two axes, and nothing else:

===============  ====================  ==============================
system           danger point from     train learns it
===============  ====================  ==============================
Level 1          fixed-block detection at a balise, i.e. at each signal
Level 2          fixed-block detection continuously, by radio
Moving block     rear of the train ahead  continuously, by radio
===============  ====================  ==============================

Everything else - braking curves, the interlocking, the timetable, the driver -
is identical, which is the whole point. Any difference in headway or journey time
between them comes from the information reaching the train, not from a constant
someone chose.

Against conventional lineside signalling, all three also drop the *sighting and
reaction* penalty. A driver reading a yellow lamp must be prepared to stop at the
next signal and starts braking there; an onboard supervising a continuous braking
curve to a known distance brakes at the last safe moment instead. On the corridor
scenario that alone is worth most of the difference.
"""

from ..units import braking_distance
from .base import SEPARATION_BY_DISTANCE, MovementAuthority, SignallingSystem
from .common import block_danger_point, limit_by_route, train_ahead


class ETCSLevel1(SignallingSystem):
    """Spot transmission: the authority is refreshed at balises only.

    A balise sits at each signal. Passing one, the train is told how far it may
    run; between them it knows nothing new, so an authority that lengthens
    because the road ahead has cleared does not reach the train until it reaches
    the next balise. That is Level 1's characteristic cost, and infill loops or
    radio infill exist precisely to reduce it.
    """

    name = "etcs_l1"
    # Level 1 is an overlay: the signals stay up and the driver still reads
    # them. It is the last level on the ladder that has any.
    has_lineside_signals = True

    #: Below this the train could stop short of a balise and never read it.
    MINIMUM_READ_DISTANCE_M = 30.0

    def __init__(self, read_distance_m: float = 250.0):
        super().__init__()
        #: Distance at which the authority ahead becomes known again.
        #:
        #: Level 1 is an *overlay*: the lineside signals stay, and the driver can
        #: still see the one ahead. So information reaches the train at the same
        #: range as under conventional signalling - this defaults to the same
        #: 250 m sighting distance - and what Level 1 adds is the supervised
        #: braking curve and the removal of the driver reaction penalty, not a
        #: faster flow of information.
        #:
        #: Reducing this models Level 1 without lineside signals, where the train
        #: learns nothing between balises. It is markedly worse, which is why
        #: infill loops and radio infill exist. It must always exceed the distance
        #: a driver stands short of a signal, or a train held at a red could never
        #: be released.
        if read_distance_m < self.MINIMUM_READ_DISTANCE_M:
            raise ValueError(
                "read_distance_m must be at least %.0f m: a driver stands short "
                "of a signal, so a shorter range would leave a train held at a "
                "red unable to read the balise that would release it"
                % (self.MINIMUM_READ_DISTANCE_M,)
            )
        self.read_distance_m = float(read_distance_m)

    def observe(self, train, sim) -> None:
        """Read a balise when in range of one, and latch the authority it gives."""
        path = train.path
        upcoming = path.next_signal(train.chainage_m)
        in_range = (upcoming is not None
                    and upcoming[1] - train.chainage_m <= self.read_distance_m)

        passed_one = False
        while train.passed_signal_index + 1 < len(path.signals):
            signal_id, signal_m = path.signals[train.passed_signal_index + 1]
            if signal_m > train.chainage_m:
                break
            train.passed_signal_index += 1
            train.latched_signal_id = signal_id
            passed_one = True

        if passed_one or in_range or train.authority_end_m is None:
            danger, reason = limit_by_route(*block_danger_point(train, sim),
                                            train=train, sim=sim)
            train.authority_end_m = danger
            train.authority_reason_raw = reason

    def movement_authority(self, train, sim) -> MovementAuthority:
        end = getattr(train, "authority_end_m", None)
        if end is None:
            end = train.path.total_m
        reason = getattr(train, "authority_reason_raw", "level 1 authority")
        return MovementAuthority(
            end_distance_m=max(0.0, end - train.chainage_m),
            target_speed_ms=0.0,
            reason="L1: %s" % reason,
        )

    def describe(self) -> str:
        return ("ETCS Level 1 (balise at each signal, lineside overlay, "
                "infill %.0f m)" % (self.read_distance_m,))


class ETCSLevel2(SignallingSystem):
    """Continuous radio authority over fixed-block train detection.

    The RBC knows where every train is and re-issues the authority every cycle,
    so the moment a block clears the following train's authority extends. No
    lineside signals, no sighting distance, no waiting for the next balise -
    but the granularity of train detection is still the block, so the authority
    can never end closer than the entry to the block the train in front occupies.
    """

    name = "etcs_l2"
    # No lineside signals: the authority arrives in the cab by radio, and the
    # trackside keeps only unlit marker boards at block boundaries.
    has_lineside_signals = False

    def __init__(self, report_interval_s: float = 0.0):
        super().__init__()
        #: Position report interval; 0 means every cycle.
        self.report_interval_s = report_interval_s

    def movement_authority(self, train, sim) -> MovementAuthority:
        danger, reason = limit_by_route(*block_danger_point(train, sim),
                                        train=train, sim=sim)
        return MovementAuthority(
            end_distance_m=max(0.0, danger - train.chainage_m),
            target_speed_ms=0.0,
            reason="L2: %s" % reason,
        )

    def describe(self) -> str:
        return "ETCS Level 2 (continuous radio authority, fixed block detection)"


class MovingBlock(SignallingSystem):
    """Full Level 3: the authority ends just short of the train in front.

    Train detection leaves the trackside entirely - each train reports its own
    position and confirms its own integrity, so the rear of the train ahead is
    known and the following train may run up to it less a safety margin. Block
    sections stop bounding headway; only braking distance and the margin do.

    A train that cannot confirm its integrity cannot be followed this closely,
    because its rear position is not trustworthy. Here such a train falls back to
    being treated as occupying its whole block, which is the honest degraded
    behaviour and the reason Hybrid Level 3 exists.
    """

    name = "etcs_moving_block"
    has_lineside_signals = False
    # Trains are kept apart by measured distance, not by block sections, so
    # two trains sharing a block is correct behaviour rather than a fault.
    separates_by = SEPARATION_BY_DISTANCE

    def __init__(self, safety_margin_m: float = 100.0):
        super().__init__()
        self.safety_margin_m = float(safety_margin_m)

    def movement_authority(self, train, sim) -> MovementAuthority:
        ahead = train_ahead(train, sim)

        if ahead is None:
            # Nothing in front. Block sections do not separate trains here, so
            # the authority runs to the end of the line, bounded only by the
            # interlocking. Capping it at block occupancy would quietly turn
            # moving block back into Level 2.
            danger, reason = train.path.total_m, "clear ahead"
        else:
            rear_m, other_id = ahead
            other = sim.trains.get(other_id)
            if other is not None and not other.stock.tims:
                # The rear of that train is not trustworthy, so it cannot be
                # followed by distance: fall back to block granularity. This is
                # the honest degraded behaviour, and the reason Hybrid Level 3
                # exists at all.
                danger, block_reason = block_danger_point(train, sim)
                reason = "%s has no integrity report (%s)" % (other_id, block_reason)
            else:
                danger = rear_m - self.safety_margin_m
                reason = "rear of %s" % other_id

        danger, reason = limit_by_route(danger, reason, train, sim)
        return MovementAuthority(
            end_distance_m=max(0.0, danger - train.chainage_m),
            target_speed_ms=0.0,
            reason="MB: %s" % reason,
        )

    def describe(self) -> str:
        return ("full moving block / ETCS Level 3 (margin %.0f m)"
                % (self.safety_margin_m,))


def minimum_theoretical_headway(stock, speed_ms: float, block_length_m: float,
                                system: str, margin_m: float = 100.0) -> float:
    """Rough minimum headway at ``speed_ms``, for reporting alongside a run.

    Fixed-block systems must clear two blocks plus the train's length; moving
    block needs only braking distance plus the margin plus the train's length.
    Approximate, and meant for comparison rather than as a design figure.
    """
    if speed_ms <= 0:
        return float("inf")
    if system == "etcs_moving_block":
        distance = braking_distance(speed_ms, stock.service_brake) + margin_m
    else:
        distance = 2.0 * block_length_m
    return (distance + stock.length_m) / speed_ms
