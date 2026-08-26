"""Rolling stock, the path a service runs over, and train state.

A train's position is a single scalar: ``chainage_m``, the distance its *front*
has travelled along its own :class:`Path`. Everything else - which segment it is
on, which blocks it occupies, which signal is next, how far the next stop is -
is derived from that one number, which keeps the state small and the physics
trivially reversible for testing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import dynamics
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
    max_accel: float          # m/s^2, traction, at a stand
    service_brake: float      # m/s^2, normal braking
    emergency_brake: float    # m/s^2, reserved for degraded cases

    #: What the onboard can do: "none" | "l1" | "l2" | "l3".
    etcs_level: str = "none"
    #: Train Integrity Monitoring: can the train confirm its rear is still there?
    tims: bool = False

    # ------------------------------------------------------- dynamics, physical
    #
    # These describe the train as a body being pushed along a rail rather than
    # as a set of performance figures, and they are what
    # :mod:`trainsim.core.dynamics` works in. Every one of them may be left out
    # of a scenario file: what is derived then is a plausible unit of the size
    # and performance already declared, so an existing timetable keeps working
    # and only gains the falling traction curve it should always have had.

    #: Tare + load, tonnes. Derived from length at 1.8 t/m when not given.
    mass_t: float = 0.0
    #: How much heavier the train behaves than it weighs, because wheels, gears
    #: and armatures have to be spun up as well as moved.
    rotating_mass_pct: float = 8.0
    #: Traction power at the wheel, kW. Derived so that the constant-effort
    #: branch of the curve ends at 40% of the train's maximum speed.
    power_kw: float = 0.0
    #: Davis resistance ``A + Bv + Cv^2`` in N, with v in m/s. Derived from
    #: mass and length when not given.
    davis_a_n: Optional[float] = None
    davis_b_n_per_ms: Optional[float] = None
    davis_c_n_per_ms2: Optional[float] = None
    #: Wheel-rail friction coefficient - the ceiling on any brake rate.
    adhesion: float = 0.30
    #: Seconds for a brake demand to become the retardation asked for.
    brake_buildup_s: float = 2.0

    def __post_init__(self):
        """Fill in whatever the scenario left unsaid, consistently.

        Frozen dataclasses do not assign, so this goes through
        ``object.__setattr__``; the values are still fixed for the life of the
        object, which is what being frozen is for.
        """
        set_field = object.__setattr__
        if self.mass_t <= 0.0:
            set_field(self, "mass_t", dynamics.MASS_T_PER_M * self.length_m)
        if self.power_kw <= 0.0:
            # Enough power to hold the starting effort up to base speed, and no
            # more. Below that the train would never reach line speed; far above
            # it, acceleration would stay flat and we would be back where we
            # started.
            base_speed = dynamics.BASE_SPEED_FRACTION * self.max_speed_ms
            set_field(self, "power_kw",
                      self.starting_effort_n * base_speed / 1000.0)
        davis_a, davis_b, davis_c = dynamics.default_davis(
            self.mass_t, self.length_m)
        if self.davis_a_n is None:
            set_field(self, "davis_a_n", davis_a)
        if self.davis_b_n_per_ms is None:
            set_field(self, "davis_b_n_per_ms", davis_b)
        if self.davis_c_n_per_ms2 is None:
            set_field(self, "davis_c_n_per_ms2", davis_c)

    @property
    def reports_position(self) -> bool:
        """Whether the trackside can know where this train is between balises."""
        return self.etcs_level in ("l2", "l3")

    # ------------------------------------------------------------------ physics

    @property
    def mass_kg(self) -> float:
        return self.mass_t * 1000.0

    @property
    def power_w(self) -> float:
        return self.power_kw * 1000.0

    @property
    def starting_effort_n(self) -> float:
        """Tractive effort below base speed.

        Defined *from* ``max_accel`` rather than declared alongside it, so that a
        train still accelerates away from a platform at exactly the rate its
        scenario asks for. What changes is what happens afterwards.
        """
        return self.max_accel * dynamics.effective_mass_kg(self)

    @property
    def base_speed_ms(self) -> float:
        """Where constant effort gives way to constant power."""
        return dynamics.base_speed_ms(self)

    @property
    def balancing_speed_ms(self) -> float:
        """Fastest this train can go on level track, whatever its data sheet says."""
        return dynamics.balancing_speed_ms(self)


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

    def grade_at(self, chainage_m: float) -> float:
        """Rise per thousand where the train's front is, in its own direction."""
        return self.entry_at(chainage_m).segment.grade_permille

    def steepest_fall_ahead(self, chainage_m: float, distance_m: float) -> float:
        """The most adverse gradient between here and ``distance_m`` ahead.

        Adverse for *braking*, so the most negative one: a train that starts
        braking on the level and runs onto a falling gradient halfway down its
        braking distance will not stop where the level-track curve promised. A
        braking curve is computed against the worst gradient it will meet, which
        is what this returns, and never against the one under the train now.
        """
        worst = self.grade_at(chainage_m)
        limit = chainage_m + max(0.0, distance_m)
        for entry in self.entries:
            if entry.end_m <= chainage_m:
                continue
            if entry.start_m > limit:
                break
            worst = min(worst, entry.segment.grade_permille)
        return worst

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
    #: The acceleration the train actually achieved last tick, kept because the
    #: next one may not differ from it by more than the jerk limit - a brake or
    #: a traction demand takes a second or two to become a force.
    applied_accel: float = 0.0
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
    #: Gradient under the train, for the view and the event log.
    grade_permille: float = 0.0
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

        Two things lengthen it beyond the textbook curve, and both are real
        distance the train covers before it is stopped: the brake takes a second
        or two to build up, and a falling gradient over the braking distance robs
        the brake of some of its rate. The gradient is found by solving once on
        the level and then re-solving against the worst gradient inside that
        first answer, which converges immediately for any gradient a railway is
        actually built to.
        """
        rate = dynamics.braking_rate_on_grade(
            self.stock, self.path.grade_at(self.chainage_m))
        first_pass = braking_distance(self.speed_ms, rate)
        worst = self.path.steepest_fall_ahead(self.chainage_m, first_pass)
        rate = dynamics.braking_rate_on_grade(self.stock, worst)
        return (braking_distance(self.speed_ms, rate)
                + dynamics.brake_buildup_distance_m(self.stock, self.speed_ms)
                + self.speed_ms * reaction_s)

    # ---------------------------------------------------------------- diagnostics

    @property
    def resistance_accel(self) -> float:
        """Retardation from running resistance at the speed the train is doing."""
        return dynamics.resistance_accel(self.stock, self.speed_ms)

    @property
    def traction_accel_available(self) -> float:
        """What the traction curve still has to give at this speed."""
        return dynamics.traction_accel(self.stock, self.speed_ms)

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

    def advance(self, demanded_accel: float, dt: float) -> float:
        """Integrate one tick; returns distance moved.

        The driver asks for an acceleration; the train delivers whatever the
        force balance allows. Traction falls away with speed, drag and gravity
        take their share whether or not anyone asked, the brake cannot beat
        adhesion, and neither traction nor brake changes instantly. All of that
        is resolved in :func:`~trainsim.core.dynamics.achievable_accel`; what is
        left here is the integration.

        Trapezoidal, with the special case that matters at a red signal: if the
        train would cross zero speed inside the tick, it stops partway through
        rather than reversing.
        """
        v0 = self.speed_ms
        self.grade_permille = self.path.grade_at(self.chainage_m)

        # The tick that ends at a stand is the one where the brake is already
        # applied and being modulated onto the mark, so the build-up limit does
        # not apply to it. Without this a berthing train would overshoot its
        # stopping point by the metre or so the jerk limit costs.
        stopping = demanded_accel < 0.0 and v0 + demanded_accel * dt <= 1e-9

        accel = dynamics.achievable_accel(
            self.stock, v0, demanded_accel,
            grade_permille=self.grade_permille,
            previous_accel=self.applied_accel,
            dt=dt,
            immediate=stopping,
        )

        v1 = v0 + accel * dt
        if v1 <= 0.0:
            if accel < 0.0:
                time_to_stop = v0 / -accel
                distance = 0.5 * v0 * time_to_stop
            else:
                distance = 0.0
            v1 = 0.0
            # At a stand the brakes are holding and nothing is building up; the
            # next application or notch starts from rest like any other.
            accel = 0.0
        else:
            v1 = min(v1, self.stock.max_speed_ms)
            distance = 0.5 * (v0 + v1) * dt
        self.applied_accel = accel
        self.speed_ms = v1
        self.chainage_m = min(self.chainage_m + distance, self.path.total_m)
        return distance
