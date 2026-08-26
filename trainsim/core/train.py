"""Rolling stock, the path a service runs over, and train state.

A train's position is a single scalar: ``chainage_m``, the distance its *front*
has travelled along its own :class:`Path`. Everything else - which segment it is
on, which blocks it occupies, which signal is next, how far the next stop is -
is derived from that one number, which keeps the state small and the physics
trivially reversible for testing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .network import Network, Segment
from .units import braking_distance


@dataclass(frozen=True)
class RollingStock:
    """Physical and performance characteristics of a train type.

    ``etcs_level`` and ``tims`` describe what the train is *fitted* with, which is
    separate from what the trackside provides. Mixed fitment - some trains able to
    report their position and confirm their integrity, others not - is the normal
    state of a real railway during migration, and it is what Hybrid Level 3 is
    designed to cope with.
    """

    id: str
    name: str
    length_m: float
    max_speed_ms: float
    max_accel: float          # m/s^2, traction
    service_brake: float      # m/s^2, normal braking
    emergency_brake: float    # m/s^2, reserved for degraded cases

    #: What the onboard can do: "none" | "l1" | "l2" | "l3".
    etcs_level: str = "none"
    #: Train Integrity Monitoring: can the train confirm its rear is still there?
    tims: bool = False

    @property
    def reports_position(self) -> bool:
        """Whether the trackside can know where this train is between balises."""
        return self.etcs_level in ("l2", "l3")


@dataclass(frozen=True)
class PathEntry:
    """One segment on a path, with where it sits along that path."""

    segment: Segment
    start_m: float
    end_m: float


@dataclass(frozen=True)
class PathSection:
    """One block along a path, with the signal that guards it for this train."""

    block_id: str
    start_m: float
    end_m: float
    signal_id: Optional[str]
    approach_leg: Optional[str]


def _signal_for_leg(block, signals, leg: Optional[str]) -> Optional[str]:
    """The entry signal of ``block`` that applies to a train arriving via ``leg``.

    Where roads converge, the block has one signal per approach; a train must
    read the one facing it, not whichever happens to be listed first.
    """
    if not block.signal_ids:
        return None
    if signals is None or len(block.signal_ids) == 1:
        return block.signal_ids[0]
    fallback = None
    for signal_id in block.signal_ids:
        signal = signals[signal_id]
        if signal.from_segment == leg:
            return signal_id
        if signal.from_segment is None:
            fallback = signal_id
    return fallback or block.signal_ids[0]


def nearest_ahead(train, others) -> Optional[Tuple[float, str]]:
    """Rear of the nearest train in front, in ``train``'s own chainage.

    ``None`` when the road ahead is clear. Trains on other roads simply do not
    map onto this path, so they are ignored without needing a special case.
    """
    nearest = None
    for other in others:
        if other.id == train.id or not other.is_active:
            continue
        rear_entry = other.path.entry_at(max(0.0, other.rear_m))
        offset = max(0.0, other.rear_m) - rear_entry.start_m
        here = train.path.chainage_of(rear_entry.segment.id, offset,
                                      after_m=train.chainage_m)
        if here is None or here <= train.chainage_m:
            continue
        if nearest is None or here < nearest[0]:
            nearest = (here, other.id)
    return nearest


@dataclass(frozen=True)
class Stop:
    """A scheduled call at a platform."""

    station: str
    platform: str
    segment: str
    stop_chainage_m: float
    arrival_s: Optional[float]
    departure_s: Optional[float]
    min_dwell_s: float


class Path:
    """An ordered chain of segments with chainage, blocks and signals mapped onto it.

    Built once when the service is created. All the lookups the driver and the
    signalling system need are precomputed here, so the per-tick work is a couple
    of binary-search-free linear scans over a short list.
    """

    def __init__(self, network: Network, segment_ids: List[str],
                 block_of_segment: Dict[str, str], blocks: Dict[str, object],
                 signals: Optional[Dict[str, object]] = None):
        self.segment_ids = list(segment_ids)
        self.entries: List[PathEntry] = []
        chainage = 0.0
        for seg_id in self.segment_ids:
            seg = network.segments[seg_id]
            self.entries.append(PathEntry(seg, chainage, chainage + seg.length_m))
            chainage += seg.length_m
        self.total_m = chainage

        # Block ranges along the path, in order. A block may span several segments,
        # so ranges are merged rather than emitted per segment. The road each
        # block is entered from is recorded alongside, because where several
        # roads converge the block has one signal per approach and this train
        # only ever reads the one for the road it is on.
        self.block_ranges: List[Tuple[str, float, float]] = []
        approach_legs: List[Optional[str]] = []
        previous_segment: Optional[str] = None
        for entry in self.entries:
            block_id = block_of_segment.get(entry.segment.id)
            if block_id is None:
                previous_segment = entry.segment.id
                continue
            if self.block_ranges and self.block_ranges[-1][0] == block_id:
                start_m = self.block_ranges[-1][1]
                self.block_ranges[-1] = (block_id, start_m, entry.end_m)
            else:
                self.block_ranges.append((block_id, entry.start_m, entry.end_m))
                approach_legs.append(previous_segment)
            previous_segment = entry.segment.id

        # Sections pair each block with the signal guarding it *for this train*.
        # Kept together rather than in parallel lists so that walking the road
        # ahead - which every signalling system has to do - cannot misalign them.
        self.sections: List[PathSection] = []
        for (block_id, start_m, end_m), leg in zip(self.block_ranges, approach_legs):
            self.sections.append(PathSection(
                block_id=block_id,
                start_m=start_m,
                end_m=end_m,
                signal_id=_signal_for_leg(blocks[block_id], signals, leg),
                approach_leg=leg,
            ))

        # Signals sit at the entry to each block, so they share the block's start.
        self.signals: List[Tuple[str, float]] = [
            (section.signal_id, section.start_m)
            for section in self.sections if section.signal_id is not None
        ]

    # ------------------------------------------------------------------ lookups

    def entry_at(self, chainage_m: float) -> PathEntry:
        """The path entry containing ``chainage_m`` (clamped to the path)."""
        for entry in self.entries:
            if chainage_m < entry.end_m:
                return entry
        return self.entries[-1]

    def km_at(self, chainage_m: float) -> float:
        entry = self.entry_at(chainage_m)
        return entry.segment.km_at(chainage_m - entry.start_m)

    def y_at(self, chainage_m: float) -> float:
        """Schematic y, interpolated across a junction link's ramp."""
        entry = self.entry_at(chainage_m)
        segment = entry.segment
        if segment.y_end is None or segment.length_m <= 0:
            return segment.y
        fraction = max(0.0, min(1.0, (chainage_m - entry.start_m) / segment.length_m))
        return segment.y + (segment.end_y - segment.y) * fraction

    def speed_limit_at(self, chainage_m: float) -> float:
        return self.entry_at(chainage_m).segment.max_speed_ms

    def restrictions_ahead(self, chainage_m: float,
                           lookahead_m: float) -> List[Tuple[float, float]]:
        """``(distance_ahead, speed_limit)`` for segments starting within lookahead.

        Used by the driver to brake *before* reaching a slower stretch - the loop
        road at Beta being the case that matters in the corridor scenario.
        """
        found = []
        for entry in self.entries:
            if entry.start_m <= chainage_m:
                continue
            distance = entry.start_m - chainage_m
            if distance > lookahead_m:
                break
            found.append((distance, entry.segment.max_speed_ms))
        return found

    def blocks_covering(self, rear_m: float, front_m: float) -> List[str]:
        """Blocks occupied by a train spanning ``[rear_m, front_m]``.

        Half-open at the front: a train whose nose is exactly on a block boundary
        has not entered that block yet.
        """
        rear = max(0.0, rear_m)
        covered = []
        for block_id, start_m, end_m in self.block_ranges:
            if start_m < front_m and end_m > rear:
                covered.append(block_id)
        return covered

    def sections_ahead(self, chainage_m: float) -> List["PathSection"]:
        """Sections whose far end is still in front of ``chainage_m``."""
        return [s for s in self.sections if s.end_m > chainage_m]

    def chainage_of(self, segment_id: str, offset_m: float = 0.0,
                    after_m: float = 0.0) -> Optional[float]:
        """Where a point on ``segment_id`` falls along this path, if it does.

        Used to place another train on *this* train's road: the answer is None
        when that segment is not on the path at all, which is how a train on the
        opposite line is correctly ignored.
        """
        for entry in self.entries:
            if entry.segment.id == segment_id and entry.end_m >= after_m:
                return entry.start_m + offset_m
        return None

    def next_signal(self, chainage_m: float) -> Optional[Tuple[str, float, int]]:
        """The first signal strictly ahead: ``(signal_id, chainage, index)``."""
        for index, (signal_id, signal_m) in enumerate(self.signals):
            if signal_m > chainage_m:
                return signal_id, signal_m, index
        return None

    def signal_at_index(self, index: int) -> Optional[Tuple[str, float]]:
        if 0 <= index < len(self.signals):
            return self.signals[index]
        return None


@dataclass
class Train:
    """A running service and everything the kernel tracks about it."""

    id: str
    name: str
    stock: RollingStock
    path: Path
    stops: List[Stop]
    origin_departure_s: float

    chainage_m: float = 0.0
    speed_ms: float = 0.0
    state: str = "waiting"  # waiting | running | dwelling | finished
    next_stop_index: int = 0
    dwell_until_s: Optional[float] = None
    entered_s: Optional[float] = None
    finished_s: Optional[float] = None

    # Conventional lineside signalling: signals carry information only at the
    # moment they are seen, so the driver's knowledge is explicit state. The
    # aspect sighted on approach is promoted to ``latched_aspect`` when the
    # signal is passed - reading it after passing would show the train's own
    # occupation of the block behind it.
    sighted_aspect: str = "green"
    sighted_signal_id: Optional[str] = None
    latched_aspect: str = "green"
    latched_signal_id: Optional[str] = None
    passed_signal_index: int = -1

    # Spot-transmission systems (ETCS Level 1) latch an authority at a balise and
    # supervise towards it until the next one, so the end point is train state
    # rather than something recomputed from the railway each tick.
    authority_end_m: Optional[float] = None
    authority_reason_raw: str = ""

    # Diagnostics, surfaced in the schematic view and the event log.
    authority_reason: str = "not started"
    #: Distance the last movement authority extended to, for metrics and the view.
    last_authority_m: Optional[float] = None
    target_speed_ms: float = 0.0
    delay_s: float = 0.0
    actual_arrivals: Dict[str, float] = field(default_factory=dict)
    actual_departures: Dict[str, float] = field(default_factory=dict)

    # ---------------------------------------------------------------- geometry

    @property
    def rear_m(self) -> float:
        return self.chainage_m - self.stock.length_m

    @property
    def is_active(self) -> bool:
        return self.state in ("running", "dwelling")

    @property
    def km(self) -> float:
        return self.path.km_at(self.chainage_m)

    @property
    def y(self) -> float:
        return self.path.y_at(self.chainage_m)

    def stopping_distance_m(self, reaction_s: float = 0.0) -> float:
        """How much track this train needs in front of it to come to a stand.

        Under fixed block this is invisible - separation is a whole block whether
        the train is doing 40 or 140. Under moving block it *is* the separation,
        which is why it shrinks as the train slows and why the schematic draws it.
        """
        return (braking_distance(self.speed_ms, self.stock.service_brake)
                + self.speed_ms * reaction_s)

    def occupied_blocks(self) -> List[str]:
        if not self.is_active:
            return []
        return self.path.blocks_covering(self.rear_m, self.chainage_m)

    def next_stop(self) -> Optional[Stop]:
        if self.next_stop_index < len(self.stops):
            return self.stops[self.next_stop_index]
        return None

    def distance_to_next_stop(self) -> Optional[float]:
        stop = self.next_stop()
        if stop is None:
            return None
        return stop.stop_chainage_m - self.chainage_m

    # ---------------------------------------------------------------- kinematics

    def advance(self, accel: float, dt: float) -> float:
        """Integrate one tick at constant acceleration; returns distance moved.

        Trapezoidal, with the special case that matters at a red signal: if the
        train would cross zero speed inside the tick, it stops partway through
        rather than reversing.
        """
        v0 = self.speed_ms
        v1 = v0 + accel * dt
        if v1 <= 0.0:
            if accel < 0.0:
                time_to_stop = v0 / -accel
                distance = 0.5 * v0 * time_to_stop
            else:
                distance = 0.0
            v1 = 0.0
        else:
            v1 = min(v1, self.stock.max_speed_ms)
            distance = 0.5 * (v0 + v1) * dt
        self.speed_ms = v1
        self.chainage_m = min(self.chainage_m + distance, self.path.total_m)
        return distance
