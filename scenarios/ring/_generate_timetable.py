"""Regenerate scenarios/ring/timetable.yaml - the lap.

Every service on this railway is the same lap: away from Akyurt 1 on the up
line, calling at all eleven stations, round HS_EAST, back down the down line
calling at all eleven again, round HS_WEST, and into Akyurt 1 facing the way it
set off. Twenty-two calls, seventy kilometres, no reversal anywhere.

That is the difference from the out-and-back railways here. On those, a service
begins and ends standing on a depot road, and the interval the line can be
booked at turns out to be set by that despatch sequence rather than by the
distance between trains - which is the thing a signalling comparison is trying
to measure. A lap has no such place: every train is running, both lines are
worked at once, and the only reason to wait is that something is in the way.

Booked times come from running one service unimpeded over its own roads, one
probe per distinct set of roads. So every booked time is what that service
achieves with the railway to itself, and any delay in a full run belongs to
trains getting in each other's way rather than to a plan that was never
possible.

    python scenarios/ring/_generate_timetable.py
    python scenarios/ring/_generate_timetable.py 180 timetable-close

Stdlib only, like everything else here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from trainsim.core import signalling as reg
from trainsim.core.dispatcher import TimetableDispatcher
from trainsim.core.driver import Driver, DriverConfig
from trainsim.core.interlocking import Interlocking
from trainsim.core.simulation import SimConfig, Simulation
from trainsim.core.units import format_clock
from trainsim.scenario.builder import build_infrastructure
from trainsim.scenario.loader import build_timetable, read_data_file

BASE = 7 * 3600
#: Thirty seconds at every call, the last one included. A lap ends where it
#: began and the train is not turned round there - it has already turned, twice,
#: on the curves - so the final call is a station stop like the other twenty-one
#: and is booked like one.
DWELL = 30
READY_LEAD = 30
#: Services in the flight. Twelve laps is enough traffic that trains meet each
#: other everywhere on the circuit without the base timetable already fighting
#: itself - what the line actually holds is what _sweep_headway.py measures.
COUNT = 12
HEADWAY_S = 300

STOCK = {"id": "EMU", "name": "Ring unit", "length_m": 120,
         "max_speed_kmh": 90, "max_accel": 1.0, "service_brake": 1.0,
         "emergency_brake": 1.5, "etcs_level": "none", "tims": False}

INFRA = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))

#: The eleven stations in up-line order. A lap calls at every one of them
#: twice, once on each road.
STATIONS = ["AKYURT_1", "MACUNKOY_1", "GOLBASI_1", "TEKNOPARK_1", "AKYURT_2",
            "MACUNKOY_2", "GOLBASI_2", "TEKNOPARK_2", "AKYURT_3", "MACUNKOY_3",
            "GOLBASI_3"]

#: ``(station, line, dwell)`` in the order a lap calls at them. The line moves
#: with the train - up as far as Gölbaşı 3, down all the way back, and up again
#: for the last call, which is the same platform the lap started from.
LAP = ([(station, "UP", DWELL) for station in STATIONS]
       + [(station, "DN", DWELL) for station in reversed(STATIONS)]
       + [(STATIONS[0], "UP", DWELL)])


def roads(station, line):
    """Every road at a station on one line, in the order the layout declares."""
    return [pid for pid, plat in INFRA.network.platforms.items()
            if plat.station == station and plat.track == line]


def road(station, line, index):
    """The road service ``index`` takes - the roads are used in turn."""
    available = roads(station, line)
    return available[index % len(available)]


def calls(shift=0, index=0):
    entries = [{"station": station,
                "platform": road(station, line, index),
                "dwell_s": dwell}
               for station, line, dwell in LAP]
    entries[0]["departure"] = format_clock(BASE + shift)
    return entries


#: Extra settings per signalling system, ``{name: {setting: value}}``. The sweep
#: sets this so a whole sweep can be run under, say, the convoy braking rule
#: without every call site having to know about it. Keyed by system because the
#: probe runs under fixed block whatever is being swept, and a setting meant for
#: virtual coupling is a TypeError anywhere else.
OPTIONS = {}


def signalling_for(system):
    """Build a signalling system, giving it only settings it has.

    Sighting distance is how far off a driver reads a *lineside* signal, so it
    belongs to lineside signalling and to nothing else - the cab systems put the
    authority on the desk and rightly refuse the argument.
    """
    settings = dict(OPTIONS.get(system, {}))
    if system == "fixed_block_3aspect":
        settings.setdefault("sighting_distance_m", 250)
    return reg.create(system, **settings)


def simulation(timetable, duration_s=12000, system="fixed_block_3aspect"):
    return Simulation(
        network=INFRA.network, blocks=INFRA.blocks, signals=INFRA.signals,
        block_of_segment=INFRA.block_of_segment, crossings=INFRA.crossings,
        signalling=signalling_for(system),
        dispatcher=TimetableDispatcher(timetable, route_lookahead=2),
        driver=Driver(reg.fit_driver(
            DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0),
            system)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 180, duration_s=duration_s),
        interlocking=Interlocking(network=INFRA.network, blocks=INFRA.blocks,
                                  signals=INFRA.signals, points=INFRA.points,
                                  routes=INFRA.routes, automatic_signals=False))


def probe(index=0):
    """One lap, alone on the railway, timed at every call.

    Times are read off the train as it goes rather than out of
    ``actual_arrivals``, which is keyed by station: a lap calls at every station
    twice and the dictionary would keep only the second of each. The train's
    ``next_stop_index`` says which call it is working towards, so an arrival is
    the tick that index moves on and a departure is the tick it starts running
    again.
    """
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "P", "stock": "EMU", "departure": format_clock(BASE),
                       "ready_lead_s": READY_LEAD,
                       "calls": calls(index=index)}]}, INFRA)
    sim = simulation(timetable, duration_s=12000)
    arrivals, departures = {}, {}
    was_index, was_state = None, None
    while not sim.finished:
        sim.step()
        train = sim.trains.get("P")
        if train is None:
            continue
        if was_index is not None and train.next_stop_index > was_index:
            arrivals[was_index] = sim.time_s
        if was_state == "dwelling" and train.state == "running":
            departures[train.next_stop_index - 1] = sim.time_s
        was_index, was_state = train.next_stop_index, train.state
        if train.state == "finished":
            break
    if len(arrivals) < len(LAP) - 1:
        raise SystemExit(
            "the probe lap did not finish: %d of %d calls made. Either the "
            "duration is too short or the circuit does not join up."
            % (len(arrivals) + 1, len(LAP)))
    return [(arrivals.get(position), departures.get(position))
            for position in range(len(LAP))]


def probe_all(count=COUNT):
    """An unimpeded lap per service, keyed by service index.

    Two services taking the same roads get the same answer, so the probe is run
    once per distinct set of roads rather than once per service.
    """
    times, seen = {}, {}
    for index in range(count):
        key = tuple(road(station, line, index) for station, line, _ in LAP)
        if key not in seen:
            seen[key] = probe(index)
        times[index] = seen[key]
    return times


#: (id prefix, name) for the flight. One direction of travel: a ring has only
#: the one, and the opposing movements a signalling comparison wants come from
#: the up line and the down line both being worked at the same time.
PREFIX = "R"
FLIGHT_NAME = "Akyurt 1 circuit"


def flight_spec(times, headway_s, count=COUNT, indices=None, stock=None):
    """The flight as a timetable spec: ``count`` laps, ``headway_s`` apart.

    ``indices`` restricts the spec to particular services while leaving them
    booked where they would be in the full flight - which is how the sweep
    prices the flight running alone.

    ``stock`` replaces the unit the flight is booked with, so an experiment can
    change what the train is *fitted* with - which is the variable in a
    signalling comparison - without editing timetable.yaml.
    """
    unit = dict(stock or STOCK)
    services = []
    for n in range(count) if indices is None else indices:
        shift = n * headway_s
        entries = []
        for position, (station, line, dwell) in enumerate(LAP):
            arrival, departure = times[n][position]
            entry = {"station": station, "platform": road(station, line, n),
                     "dwell_s": dwell}
            if arrival is not None:
                entry["arrival"] = format_clock(round(arrival) + shift)
            if departure is not None:
                entry["departure"] = format_clock(round(departure) + shift)
            entries.append(entry)
        services.append({
            "id": "%s%02d" % (PREFIX, n + 1),
            "name": "%s %s" % (format_clock(BASE + shift)[:5], FLIGHT_NAME),
            "stock": unit["id"], "departure": format_clock(BASE + shift),
            "ready_lead_s": READY_LEAD, "calls": entries})
    return {"stock": [unit], "services": services}


HEADER = '''# ring timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_timetable.py
#
# %d laps of the circuit, booked %d seconds apart, all of them the same unit.
# A lap is twenty-two calls: eleven stations out on the up line, round HS_EAST,
# the same eleven back on the down line, round HS_WEST, and into Akyurt 1 again
# facing the way it set off. Thirty seconds at every one. Every booked time is
# what that service achieves with the railway to itself.

'''


def stock_yaml(unit):
    return '''stock:
  - id: %(id)s
    name: %(name)s
    length_m: %(length_m)d
    max_speed_kmh: %(max_speed_kmh)d
    max_accel: %(max_accel)s
    service_brake: %(service_brake)s
    emergency_brake: %(emergency_brake)s
    etcs_level: %(etcs_level)s
    tims: false

services:
''' % unit


def render(times, headway_s, count=COUNT):
    out = [HEADER % (count, headway_s) + stock_yaml(STOCK)]
    for service in flight_spec(times, headway_s, count)["services"]:
        lines = ["  - id: %s" % service["id"],
                 "    name: %s" % service["name"],
                 "    stock: %s" % service["stock"],
                 '    departure: "%s"' % service["departure"],
                 "    ready_lead_s: %d" % READY_LEAD,
                 "    calls:"]
        for entry in service["calls"]:
            bits = ["station: %s" % entry["station"],
                    "platform: %s" % entry["platform"]]
            if "arrival" in entry:
                bits.append('arrival: "%s"' % entry["arrival"])
            if "departure" in entry:
                bits.append('departure: "%s"' % entry["departure"])
            bits.append("dwell_s: %d" % entry["dwell_s"])
            lines.append("      - {%s}" % ", ".join(bits))
        out.append("\n".join(lines))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else HEADWAY_S
    name = sys.argv[2] if len(sys.argv) > 2 else "timetable"
    times = probe_all()
    lap = times[0][-1][0] - times[0][0][1]
    print("a lap, with the railway to itself: %s to %s, %d min %02d s"
          % (format_clock(times[0][0][1]), format_clock(times[0][-1][0]),
             lap // 60, lap % 60))
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway))
    print("wrote %s - %d laps at %d s" % (path, COUNT, headway))
