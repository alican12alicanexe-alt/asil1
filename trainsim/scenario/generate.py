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
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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

    # the run
    system: str = "fixed_block_3aspect"
    dt: float = 1.0
    duration_s: float = 9000.0

    @property
    def last_km(self) -> float:
        return max(km for _, _, km in self.stations)

    def platform_id(self, station_id: str, index: int = 1) -> str:
        return "%s_UP_%d" % (station_id, index)


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
        "platforms:",
    ]
    for sid, _, _ in spec.stations:
        for index in range(1, max(1, spec.platforms_per_station) + 1):
            lines.append(
                "  - {id: %s, station: %s, track: UP, length_m: %g, "
                "max_speed_kmh: %g, y_offset: -%.1f}"
                % (spec.platform_id(sid, index), sid,
                   spec.stock_length_m * 2, spec.line_speed_kmh,
                   0.4 * (index - 1))
            )
    return "\n".join(lines) + "\n"


def _timetable(spec: LineSpec, booked, services) -> str:
    count = spec.trains if services is None else services
    lines = [
        "# Written by trainsim.scenario.generate - edit the form, not this file.",
        "stock:",
        "  - id: EMU",
        '    name: "%s unit"' % spec.name,
        "    length_m: %g" % spec.stock_length_m,
        "    max_speed_kmh: %g" % spec.max_speed_kmh,
        "    max_accel: %g" % spec.max_accel,
        "    service_brake: %g" % spec.service_brake,
        "    emergency_brake: %g" % spec.emergency_brake,
        "    etcs_level: none",
        "    tims: false",
        "services:",
    ]
    for index in range(count):
        shift = int(round(index * spec.headway_s))
        away = spec.first_departure_s + shift
        lines += [
            "  - id: S%02d" % (index + 1),
            '    name: "%s %s"' % (format_clock(away), spec.stations[-1][1]),
            "    stock: EMU",
            '    departure: "%s"' % format_clock(away),
            "    ready_lead_s: %d" % spec.ready_lead_s,
            "    calls:",
        ]
        for position, (sid, _, _) in enumerate(spec.stations):
            call = ["station: %s" % sid,
                    "platform: %s" % spec.platform_id(sid)]
            times = booked[position] if booked else (None, None)
            arrival, departure = times
            if position == 0:
                call.append('departure: "%s"' % format_clock(away))
            else:
                if arrival is not None:
                    call.append('arrival: "%s"'
                                % format_clock(int(round(arrival)) + shift))
                if departure is not None and position < len(spec.stations) - 1:
                    call.append('departure: "%s"'
                                % format_clock(int(round(departure)) + shift))
            call.append("dwell_s: %g" % spec.dwell_s)
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


# --------------------------------------------------------------------- booking

def book(directory: str, spec: LineSpec) -> Optional[list]:
    """Run one train over the empty railway and write the times it achieved.

    Returns the ``[(arrival_s, departure_s), ...]`` it measured, or ``None`` if
    the probe never finished - which means the duration is too short or the
    plan is not workable, and is worth saying rather than booking around.
    """
    from .loader import build_simulation, load_scenario

    write(directory, spec, booked=None, services=1)
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

    if len(arrivals) < len(spec.stations) - 1:
        write(directory, spec, booked=None)
        return None

    booked = [(arrivals.get(position), departures.get(position))
              for position in range(len(spec.stations))]
    write(directory, spec, booked=booked)
    return booked


def demo():
    """A four-station line books, and the booking is monotonic."""
    import tempfile

    spec = LineSpec(stations=[("A", "Aydin", 1.0), ("B", "Bolu", 9.0),
                              ("C", "Ceyhan", 18.0), ("D", "Demirci", 27.0)],
                    trains=3, headway_s=240, duration_s=4000)
    with tempfile.TemporaryDirectory() as directory:
        booked = book(directory, spec)
        assert booked is not None, "the probe did not finish"
        arrivals = [a for a, _ in booked[1:]]
        assert all(a is not None for a in arrivals), arrivals
        assert arrivals == sorted(arrivals), arrivals
        with open(os.path.join(directory, "timetable.yaml")) as handle:
            text = handle.read()
        assert text.count("- id: S") == 3, "three services expected"
    print("generate: ok, booked", [int(a) for a in arrivals])


if __name__ == "__main__":
    demo()
