"""Write a runnable scenario directory from a handful of numbers.

Every railway under ``scenarios/`` has a ``_generate_timetable.py`` beside it
that does two things: lay out the drawing, then book it by running one train
over the empty railway and writing down when it got everywhere. Those scripts
are each tied to one geometry - a ring, a branch, a depot road - and none of
them can be pointed at a railway that does not exist yet.

This is the same two steps for the one geometry that needs no drawing: a plain
double-ended corridor, stations at the kilometres you name, one train after
another over it. It is what a person building a line for the first time can
actually fill in, and what :mod:`app` puts a form in front of.

    spec = LineSpec(stations=[("A", "Ankara", 1.0), ("B", "Bala", 12.0)])
    path = write(directory, spec)      # a scenario dir, unbooked
    book(path, spec)                   # run one train alone, write the times in

Booked times come from an unimpeded run, exactly as the hand-written
generators do it, so any delay in a full run belongs to trains getting in each
other's way rather than to a plan that was never possible.
"""

import os
import string
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from ..core.units import format_clock

#: Enough room either side of a platform for the zone not to run off the end of
#: the rails, and for the first train to have somewhere to be ready.
END_MARGIN_KM = 1.0


@dataclass
class LineSpec:
    """Everything a person has to decide. Everything else is derived."""

    #: ``(id, name, km)`` in order along the line.
    stations: List[Tuple[str, str, float]] = field(default_factory=list)
    name: str = "custom"

    # the railway
    line_speed_kmh: float = 100.0
    block_length_m: float = 1200.0
    platform_zone_m: float = 700.0
    platforms_per_station: int = 1

    # the train
    #: What the default unit is called. Services that name no stock get this
    #: one, so renaming it renames what a hand-written timetable refers to.
    stock_id: str = "EMU"
    stock_length_m: float = 120.0
    max_speed_kmh: float = 100.0
    max_accel: float = 1.0
    service_brake: float = 1.0
    emergency_brake: float = 1.5

    # the service
    trains: int = 10
    headway_s: float = 180.0
    dwell_s: float = 30.0
    first_departure_s: int = 7 * 3600
    ready_lead_s: int = 30
    #: Units beyond the one the fields above describe, each a mapping with at
    #: least ``id``; anything left out is taken from that unit. Two of these is
    #: a stopping service and an express sharing a railway.
    extra_stock: List[Dict] = field(default_factory=list)
    #: A timetable written out service by service, or ``None`` for the flight
    #: the fields above imply: ``trains`` of them, ``headway_s`` apart, every
    #: one calling everywhere. Each entry is
    #: ``{"id", "stock", "departure_s", "calls", "dwell_s"}`` and ``calls`` is a
    #: list of station ids or ``None`` for all of them.
    services_spec: Optional[List[Dict]] = None

    # the ground
    #: ``(from_station_id, to_station_id, rise per thousand)``. Written in the
    #: direction of travel, so a climb is positive. Absent stretches are level.
    gradients: List[Tuple[str, str, float]] = field(default_factory=list)
    #: ``(from_km, to_km, max_speed_kmh)`` - a curve, a bridge, an approach.
    #: Part of the railway, not a disruption.
    speed_limits: List[Tuple[float, float, float]] = field(default_factory=list)
    #: Stations with somewhere to stable a train. They get a second face, so a
    #: unit can stand there without blocking the one in service.
    depots: List[str] = field(default_factory=list)
    #: ``{station_id: faces}`` where one station wants a different number from
    #: the rest. What a headway sweep points at: a line that binds on the
    #: approach to one station usually wants another face there rather than a
    #: different signalling system.
    platforms: Dict[str, int] = field(default_factory=dict)

    # the run
    system: str = "fixed_block_3aspect"
    #: Anything else the signalling system takes - the virtual coupling speed
    #: rule, the radio latency, the margin. Written into the scenario as given,
    #: so the loader validates the names rather than this file.
    signalling_options: Dict[str, object] = field(default_factory=dict)
    dt: float = 1.0
    duration_s: float = 9000.0

    @property
    def last_km(self) -> float:
        return max(km for _, _, km in self.stations)

    def platform_id(self, station_id: str, index: int = 1) -> str:
        return "%s_UP_%d" % (station_id, index)

    def roads_at(self, station_id: str) -> int:
        """How many faces this station gets: its own figure, or a depot's extra
        one, or the line's default."""
        if station_id in self.platforms:
            return max(1, int(self.platforms[station_id]))
        base = max(1, self.platforms_per_station)
        return base + 1 if station_id in self.depots else base


def evenly(count: int, spacing_km: float, first_km: float = 1.0,
           names: Optional[List[str]] = None) -> List[Tuple[str, str, float]]:
    """``count`` stations, ``spacing_km`` apart, ready for :class:`LineSpec`.

    Ids are A, B, C ... and then A2, B2 ... past the alphabet, because a line
    long enough to need that is a line nobody is naming by hand anyway.
    """
    if count < 2:
        raise ValueError("a line needs at least two stations")
    stations = []
    for index in range(count):
        letter = string.ascii_uppercase[index % 26]
        suffix = "" if index < 26 else str(index // 26 + 1)
        station_id = letter + suffix
        name = names[index] if names and index < len(names) else station_id
        stations.append((station_id, name, first_km + index * spacing_km))
    return stations


#: One period of a gradient profile that is mostly gentle with a few hard
#: stretches - the shape a real alignment has, because easy country gets an easy
#: line and the banks are where the railway had to cross something. Scaled by
#: the ruling gradient, and levelled so the line comes back to the height it
#: started at.
GRADIENT_SHAPE = (0.55, -0.30, 1.00, -0.45, 0.13, -0.85, 0.35, -0.60, 0.20, -0.03)


def gradient_profile(stations, ruling_permille: float
                     ) -> List[Tuple[str, str, float]]:
    """A stretch-by-stretch profile whose steepest stretch is ``ruling_permille``.

    Levelled: the rises and the falls cancel, so a line does not quietly climb
    into the sky over twenty stations. Edit any single stretch afterwards - this
    is a starting point, not a constraint.
    """
    stretches = len(stations) - 1
    if stretches < 1 or not ruling_permille:
        return []
    shape = [GRADIENT_SHAPE[index % len(GRADIENT_SHAPE)]
             for index in range(stretches)]
    drift = sum(shape) / float(stretches)
    shape = [value - drift for value in shape]
    peak = max(abs(value) for value in shape) or 1.0
    scale = float(ruling_permille) / peak
    return [(stations[index][0], stations[index + 1][0],
             round(shape[index] * scale, 1)) for index in range(stretches)]


# --------------------------------------------------------------------- writing

def write(directory: str, spec: LineSpec, booked=None, services=None) -> str:
    """Write infrastructure, timetable and scenario into ``directory``.

    ``booked`` is what :func:`book` measured - ``[(arrival_s, departure_s), ...]``
    one entry per call - or ``None`` for a plan with no times in it, which is
    what the probe run itself is built from.
    """
    if len(spec.stations) < 2:
        raise ValueError("a line needs at least two stations")
    os.makedirs(directory, exist_ok=True)
    _put(directory, "infrastructure.yaml", _infrastructure(spec))
    _put(directory, "timetable.yaml", _timetable(spec, booked, services))
    _put(directory, "scenario.yaml", _scenario(spec))
    return directory


def _put(directory, filename, text):
    with open(os.path.join(directory, filename), "w", encoding="utf-8") as handle:
        handle.write(text)


def _infrastructure(spec: LineSpec) -> str:
    ids = [sid for sid, _, _ in spec.stations]
    lines = [
        "# Written by trainsim.scenario.generate - edit the form, not this file.",
        "name: %s" % spec.name,
        "defaults:",
        "  platform_zone_m: %g" % spec.platform_zone_m,
        "  block_length_m: %g" % spec.block_length_m,
        "  max_speed_kmh: %g" % spec.line_speed_kmh,
        "  stop_margin_m: 30",
        "stations:",
    ]
    for sid, name, km in spec.stations:
        lines.append('  - {id: %s, name: "%s", km: %.3f}' % (sid, name, km))
    lines += [
        "tracks:",
        "  - id: UP",
        "    direction: up",
        "    y: 0.0",
        "    max_speed_kmh: %g" % spec.line_speed_kmh,
        "    block_length_m: %g" % spec.block_length_m,
        "    runs_from_km: 0.0",
        "    runs_to_km: %.3f" % (spec.last_km + END_MARGIN_KM),
        "    serves: [%s]" % ", ".join(ids),
    ]
    if spec.gradients:
        lines.append("    gradients:")
        for start, end, permille in spec.gradients:
            lines.append("      - {from: %s, to: %s, grade_permille: %g}"
                         % (start, end, permille))
    if spec.speed_limits:
        lines.append("    speed_limits:")
        for from_km, to_km, kmh in spec.speed_limits:
            lines.append("      - {from_km: %.3f, to_km: %.3f, max_speed_kmh: %g}"
                         % (from_km, to_km, kmh))
    lines.append("platforms:")
    for sid, _, _ in spec.stations:
        for index in range(1, spec.roads_at(sid) + 1):
            lines.append(
                "  - {id: %s, station: %s, track: UP, length_m: %g, "
                "max_speed_kmh: %g, y_offset: -%.1f}"
                % (spec.platform_id(sid, index), sid,
                   spec.stock_length_m * 2, spec.line_speed_kmh,
                   0.4 * (index - 1))
            )
    return "\n".join(lines) + "\n"


def units(spec: LineSpec) -> List[Dict]:
    """Every unit on this railway, the default one first."""
    base = {"id": spec.stock_id, "name": "%s unit" % spec.name,
            "length_m": spec.stock_length_m, "max_speed_kmh": spec.max_speed_kmh,
            "max_accel": spec.max_accel, "service_brake": spec.service_brake,
            "emergency_brake": spec.emergency_brake}
    found = [base]
    for extra in spec.extra_stock:
        unit = dict(base)
        unit.update(extra)
        found.append(unit)
    return found


def flight(spec: LineSpec, count=None) -> List[Dict]:
    """The timetable as a list of services, named or derived.

    A form that only ever offers "n trains, every m seconds" cannot say "a
    stopping service every three minutes and an express between every second
    pair", which is the case virtual coupling is actually argued over. So the
    derived flight is one shape this returns rather than the only one it can.
    """
    if spec.services_spec is not None:
        made = [dict(entry) for entry in spec.services_spec]
        return made if count is None else made[:count]
    total = spec.trains if count is None else count
    return [{"id": "S%02d" % (index + 1), "stock": spec.stock_id,
             "departure_s": spec.first_departure_s
                            + int(round(index * spec.headway_s)),
             "calls": None, "dwell_s": spec.dwell_s}
            for index in range(total)]


def booking_key(spec: LineSpec, service: Dict) -> Tuple[str, ...]:
    """What a service's booking is filed under: its unit and its calls.

    The unit is part of it because a 160 unit and a 90 unit over the same stops
    do not run the same times.
    """
    return (service.get("stock", spec.stock_id),) + pattern_of(spec, service)


def pattern_of(spec: LineSpec, service: Dict) -> Tuple[str, ...]:
    """Which stations this service calls at - the key its booking is kept under.

    Two services calling at the same stations run the same times, so they are
    probed once. Two that do not cannot share a booking: an express that misses
    four stops is not merely a stopping train running late.
    """
    calls = service.get("calls")
    if not calls:
        return tuple(sid for sid, _, _ in spec.stations)
    ordered = [sid for sid, _, _ in spec.stations if sid in set(calls)]
    if len(ordered) < 2:
        raise ValueError("service %r calls at fewer than two stations"
                         % (service.get("id"),))
    return tuple(ordered)


def _timetable(spec: LineSpec, booked, services) -> str:
    """``booked`` is ``{pattern: [(arrival_s, departure_s), ...]}`` as
    :func:`book` measured it, a bare list for the everywhere-pattern alone, or
    ``None`` for a plan with no times in it."""
    if isinstance(booked, list):
        booked = {booking_key(spec, {}): booked}
    lines = ["# Written by trainsim.scenario.generate - edit the form, "
             "not this file.", "stock:"]
    for unit in units(spec):
        lines += ["  - id: %s" % unit["id"],
                  '    name: "%s"' % unit.get("name", unit["id"]),
                  "    length_m: %g" % unit["length_m"],
                  "    max_speed_kmh: %g" % unit["max_speed_kmh"],
                  "    max_accel: %g" % unit["max_accel"],
                  "    service_brake: %g" % unit["service_brake"],
                  "    emergency_brake: %g" % unit["emergency_brake"],
                  "    etcs_level: none",
                  "    tims: false"]
    lines.append("services:")

    for service in flight(spec, services):
        pattern = pattern_of(spec, service)
        away = int(service["departure_s"])
        times = (booked or {}).get(booking_key(spec, service))
        # The probe left at first_departure_s; this train leaves when it leaves,
        # so its booking is the probe's shifted by the difference.
        shift = away - spec.first_departure_s
        dwell = service.get("dwell_s", spec.dwell_s)
        lines += [
            "  - id: %s" % service["id"],
            '    name: "%s %s"' % (format_clock(away), spec.stations[-1][1]),
            "    stock: %s" % service.get("stock", spec.stock_id),
            '    departure: "%s"' % format_clock(away),
            "    ready_lead_s: %d" % spec.ready_lead_s,
            "    calls:",
        ]
        for position, sid in enumerate(pattern):
            call = ["station: %s" % sid,
                    "platform: %s" % spec.platform_id(sid)]
            arrival, departure = times[position] if times else (None, None)
            if position == 0:
                call.append('departure: "%s"' % format_clock(away))
            else:
                if arrival is not None:
                    call.append('arrival: "%s"'
                                % format_clock(int(round(arrival)) + shift))
                if departure is not None and position < len(pattern) - 1:
                    call.append('departure: "%s"'
                                % format_clock(int(round(departure)) + shift))
            call.append("dwell_s: %g" % dwell)
            lines.append("      - {%s}" % ", ".join(call))
    return "\n".join(lines) + "\n"


def _scenario(spec: LineSpec) -> str:
    return "\n".join([
        "# Written by trainsim.scenario.generate - edit the form, not this file.",
        "name: %s" % spec.name,
        'description: "%d stations over %.1f km, %d trains %.0f s apart."'
        % (len(spec.stations), spec.last_km, spec.trains, spec.headway_s),
        "infrastructure: infrastructure.yaml",
        "timetable: timetable.yaml",
        "simulation:",
        "  dt: %g" % spec.dt,
        '  start_time: "%s"' % format_clock(spec.first_departure_s - 180),
        "  duration_s: %g" % spec.duration_s,
        "  strict: false",
        "signalling:",
        "  system: %s" % spec.system,
        "  sighting_distance_m: 250",
    ] + ["  %s: %s" % (key, _yaml(value))
         for key, value in sorted(spec.signalling_options.items())] + [
        "interlocking:",
        "  route_request_distance_m: 2000",
        "  route_request_lead_s: 60",
        "  automatic_signals: false",
        "  route_lookahead: 2",
        "driver:",
        "  reaction_time_s: 2.0",
        "  safety_margin_m: 25.0",
        "view:",
        '  title: "%s"' % spec.name,
        "  speed: 20",
    ]) + "\n"


def _yaml(value):
    """A scalar as YAML writes it - booleans lower case, strings bare."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value == int(value):
        return "%d" % int(value)
    return str(value)


# --------------------------------------------------------------------- booking

def book(directory: str, spec: LineSpec) -> Optional[Dict]:
    """Run each kind of train over the empty railway and write the times down.

    One probe per unit-and-calling-pattern, because that is what decides a
    running time; two services that share both share a probe. Returns
    ``{key: [(arrival_s, departure_s), ...]}`` keyed as :func:`booking_key`
    names it, or ``None`` if any probe never finished - which means the
    duration is too short or the plan is not workable, and is worth saying
    rather than booking around.
    """
    bookings = {}
    for service in flight(spec):
        key = booking_key(spec, service)
        if key in bookings:
            continue
        times = _probe(directory, spec, service)
        if times is None:
            write(directory, spec, booked=None)
            return None
        bookings[key] = times
    write(directory, spec, booked=bookings)
    return bookings


def _probe(directory: str, spec: LineSpec, service: Dict) -> Optional[list]:
    """One train of one kind over the empty railway, and when it got everywhere."""
    from .loader import build_simulation, load_scenario

    pattern = pattern_of(spec, service)
    alone = replace(spec, services_spec=[
        {"id": "S01", "stock": service.get("stock", spec.stock_id),
         "departure_s": spec.first_departure_s, "calls": list(pattern),
         "dwell_s": service.get("dwell_s", spec.dwell_s)}])
    write(directory, alone, booked=None)
    sim = build_simulation(load_scenario(directory))

    arrivals, departures = {}, {}
    was_index, was_state = None, None
    while not sim.finished:
        sim.step()
        train = sim.trains.get("S01")
        if train is None:
            continue
        if was_index is not None and train.next_stop_index > was_index:
            arrivals[was_index] = sim.time_s
        if was_state == "dwelling" and train.state == "running":
            departures[train.next_stop_index - 1] = sim.time_s
        was_index, was_state = train.next_stop_index, train.state
        if train.state == "finished":
            break

    if len(arrivals) < len(pattern) - 1:
        return None
    return [(arrivals.get(position), departures.get(position))
            for position in range(len(pattern))]


# --------------------------------------------------------------------- sweeping

#: Wide enough at the top to start clear of anything a new line might hold, and
#: fine enough at the bottom to show it bending rather than simply failing.
HEADWAYS = (300, 240, 195, 165, 135, 120, 105, 90, 75, 60, 50, 45, 40, 35, 30)

#: After the last train is away, long enough for it to finish - and rather
#: longer than the empty-railway journey, because a full railway is slower.
TAIL_FACTOR = 1.6


def journey_s(bookings) -> float:
    """The longest empty-railway run of any kind of train on this line."""
    ends = [times[-1][0] for times in bookings.values() if times[-1][0]]
    starts = [times[0][1] or times[0][0] for times in bookings.values()]
    if not ends:
        return 0.0
    return max(ends) - min(start for start in starts if start is not None)


def measure_at(directory, spec: LineSpec, bookings, headway_s, system,
               services=None):
    """Build this line at ``headway_s`` under ``system`` and run it."""
    from ..analysis.kpi import measure
    from ..core import signalling as reg
    from .loader import build_simulation, load_scenario

    count = spec.trains if services is None else services
    duration = headway_s * count + journey_s(bookings) * TAIL_FACTOR
    write(directory, replace(spec, headway_s=headway_s, system=system,
                             duration_s=duration),
          booked=bookings, services=services)
    scenario = load_scenario(directory)
    # Same fitting the comparison page does: a train measured under moving
    # block has the integrity report, under virtual coupling the radio too.
    reg.fit_timetable(scenario.timetable, system)
    scenario.driver_config = reg.fit_driver(scenario.driver_config, system)
    return measure(build_simulation(scenario))


def sweep_headway(directory, spec: LineSpec, system, headways=HEADWAYS,
                  rule="clean", progress=None):
    """The tightest interval this line works at, and what every interval cost.

    ``rule`` is what "works" means:

    ``clean``    nobody checked by a signal beyond what one train alone pays,
                 and nothing late. The all-green headway - the honest number to
                 compare two signalling systems by, because it is the point at
                 which the signalling itself starts to be the constraint.
    ``ontime``   trains are checked, but every one still makes its booked
                 arrival. What an operator would actually run to.

    Returns ``(rows, limit, binding)``: a row per interval tried, the boundary
    found to the second (``None`` if the range never crossed it), and what was
    holding trains down one second the wrong side of it - the answer to "so
    what do I change to go tighter", which is usually a platform rather than a
    signalling system.
    """
    if spec.services_spec is not None:
        raise ValueError("a headway sweep needs the automatic flight - a "
                         "hand-written timetable already says when trains go")
    bookings = book(directory, spec)
    if bookings is None:
        raise ValueError("the line did not book: one train alone never "
                         "finished, so no interval will work")

    # What the flight pays with the railway to itself. Every service on the
    # automatic flight runs the same pattern, so one probe times the number of
    # them is the whole fleet's bill - and it has to be the whole fleet's,
    # because the column below is a fleet total. Testing eight trains against
    # one train's baseline makes every interval look congested.
    alone = spec.trains * measure_at(directory, spec, bookings, max(headways),
                                     system, services=1).total_restrained_s

    def works(metrics):
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        if metrics.completed != metrics.services:
            return False
        if rule == "ontime":
            return worst < 30.0
        return metrics.total_restrained_s - alone <= 0.0 and worst <= 1.0

    rows, good, bad = [], None, None
    for headway in sorted(headways, reverse=True):
        metrics = measure_at(directory, spec, bookings, headway, system)
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        ok = works(metrics)
        rows.append({"headway_s": headway, "ok": ok,
                     "restrained_s": metrics.total_restrained_s - alone,
                     "mean_delay_s": metrics.mean_delay_s, "worst_s": worst,
                     "completed": metrics.completed,
                     "services": metrics.services})
        if progress is not None:
            progress(rows[-1])
        if ok:
            good, bad = headway, None
        elif good is not None and bad is None:
            bad = headway

    if good is None or bad is None:
        # Never crossed the boundary. The tightest interval tried is still the
        # most informative thing to report on.
        tightest = measure_at(directory, spec, bookings, min(headways), system)
        return rows, None, tightest.binding()

    # The sweep only says the answer is between two rows. Halving that bracket
    # costs four or five runs rather than the seventy a second-by-second sweep
    # would, and assumes the railway does not un-bend as the interval tightens.
    lo, hi = int(bad), int(good)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        ok = works(measure_at(directory, spec, bookings, mid, system))
        rows.append({"headway_s": mid, "ok": ok, "refined": True})
        if progress is not None:
            progress(rows[-1])
        if ok:
            hi = mid
        else:
            lo = mid
    # What binds one second tighter than the answer. At ``hi`` itself nothing
    # is over the baseline by definition, so that run has nothing to say.
    over = measure_at(directory, spec, bookings, lo, system)
    write(directory, replace(spec, headway_s=hi, system=system,
                             duration_s=hi * spec.trains
                                        + journey_s(bookings) * TAIL_FACTOR),
          booked=bookings)
    return rows, hi, over.binding()


def demo():
    """A line books, an express books faster than the stopper, and a sweep bends."""
    import tempfile

    stations = evenly(4, spacing_km=9.0)
    assert [sid for sid, _, _ in stations] == ["A", "B", "C", "D"]
    assert [km for _, _, km in stations] == [1.0, 10.0, 19.0, 28.0]

    profile = gradient_profile(stations, ruling_permille=15)
    assert len(profile) == 3, profile
    assert max(abs(g) for _, _, g in profile) == 15, profile
    assert abs(sum(g for _, _, g in profile)) < 0.11, "profile must not drift"
    assert gradient_profile(stations, 0) == []

    spec = LineSpec(stations=stations, trains=3, headway_s=240, duration_s=4000,
                    gradients=profile, depots=["A"],
                    speed_limits=[(12.0, 13.0, 60.0)])
    assert spec.roads_at("A") == 2 and spec.roads_at("B") == 1
    assert replace(spec, platforms={"B": 3}).roads_at("B") == 3

    with tempfile.TemporaryDirectory() as directory:
        booked = book(directory, spec)
        assert booked is not None, "the probe did not finish"
        stopper = booked[("EMU", "A", "B", "C", "D")]
        arrivals = [a for a, _ in stopper[1:]]
        assert all(a is not None for a in arrivals), arrivals
        assert arrivals == sorted(arrivals), arrivals
        with open(os.path.join(directory, "timetable.yaml")) as handle:
            text = handle.read()
        assert text.count("- id: S") == 3, "three services expected"
        with open(os.path.join(directory, "infrastructure.yaml")) as handle:
            infra = handle.read()
        assert "grade_permille" in infra and "from_km: 12.000" in infra
        assert infra.count("id: A_UP_") == 2, "the depot gets a second face"

    # An express over the same railway: one extra unit, a service that misses
    # the middle, and a booking of its own.
    mixed = replace(spec, extra_stock=[{"id": "EXP", "max_speed_kmh": 140.0}],
                    services_spec=[
        {"id": "S01", "stock": "EMU", "departure_s": 7 * 3600, "calls": None,
         "dwell_s": 30},
        {"id": "S02", "stock": "EXP", "departure_s": 7 * 3600 + 600,
         "calls": ["A", "D"], "dwell_s": 30}])
    with tempfile.TemporaryDirectory() as directory:
        booked = book(directory, mixed)
        assert booked is not None, "the mixed flight did not book"
        assert set(booked) == {("EMU", "A", "B", "C", "D"), ("EXP", "A", "D")}
        stopping = booked[("EMU", "A", "B", "C", "D")][-1][0]
        fast = booked[("EXP", "A", "D")][-1][0]
        assert fast < stopping, (fast, stopping)
        with open(os.path.join(directory, "timetable.yaml")) as handle:
            text = handle.read()
        assert "- id: EXP" in text and "stock: EXP" in text
        assert text.count("station: B") == 1, "only the stopper calls at B"

    # The sweep: wide enough to be clean, tight enough to bend.
    with tempfile.TemporaryDirectory() as directory:
        rows, limit, binding = sweep_headway(
            directory, replace(spec, trains=8), "fixed_block_3aspect",
            headways=(300, 120, 60))
        coarse = [row for row in rows if not row.get("refined")]
        assert coarse[0]["ok"], "the widest interval must run clean"
        assert not coarse[-1]["ok"], "the tightest must not, or nothing bends"
        assert limit is not None and 60 < limit < 300, limit
        assert any(row.get("refined") for row in rows), "no bisection"
        why, where = binding
        assert why and where, "the sweep must say what was binding"
        assert all(seconds > 0 for _, seconds in why), why
    print("generate: ok, booked", [int(a) for a in arrivals], "limit", limit)


if __name__ == "__main__":
    demo()
