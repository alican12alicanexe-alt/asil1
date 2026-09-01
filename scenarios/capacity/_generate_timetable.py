"""Regenerate scenarios/capacity/timetable.yaml - the homogeneous base flight.

Every train on this railway is the same train, calls everywhere, and dwells the
same time at each call. That is the whole point of the base: with the stock
identical and the layout symmetric, the only thing left that can move a number
between two runs is the signalling system, which is the comparison the scenario
exists to support.

Booked times come from running each service unimpeded over its own roads, one
probe per distinct set of roads. So every booked time is what that service
achieves with the railway to itself, and any delay in a full run belongs to
trains getting in each other's way rather than to a plan that was never
possible.

    python scenarios/capacity/_generate_timetable.py
    python scenarios/capacity/_generate_timetable.py 240 timetable-close

Nothing here is booked over the Mere or Sandon branches. They are laid in and
left alone - see the head of infrastructure.yaml.

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
DWELL = 45
DEPOT = 60
#: Services per direction. Eight each way fills the line without booking it
#: anywhere near the interval it can actually hold - that is what the sweep is
#: for, and a base that is already fighting itself measures nothing.
COUNT = 8
HEADWAY_S = 300

STOCK = {"id": "EMU", "name": "Line unit", "length_m": 160,
         "max_speed_kmh": 120, "max_accel": 1.0, "service_brake": 0.8,
         "emergency_brake": 1.2, "etcs_level": "none", "tims": False}

INFRA = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))

#: (station, dwell) in the order each direction calls at them.
UP_PATTERN = [("WDEPOT", DEPOT), ("LINFORD", DWELL), ("BRAMLEY", DWELL),
              ("CALDER", DWELL), ("EDEPOT", DEPOT)]
DN_PATTERN = list(reversed(UP_PATTERN))


def roads(station, line):
    """Every road at a station on one line, in the order the layout declares."""
    return [pid for pid, plat in INFRA.network.platforms.items()
            if plat.station == station and plat.track == line]


def road(station, line, index):
    """The road service ``index`` takes - the roads are used in turn."""
    available = roads(station, line)
    return available[index % len(available)]


def calls(line, pattern, shift=0, index=0):
    entries = [{"station": s, "platform": road(s, line, index), "dwell_s": d}
               for s, d in pattern]
    entries[0]["departure"] = format_clock(BASE + shift)
    return entries


def signalling_for(system):
    """Build a signalling system, giving it only settings it has.

    Sighting distance is how far off a driver reads a *lineside* signal, so it
    belongs to lineside signalling and to nothing else - the cab systems put the
    authority on the desk and rightly refuse the argument. Passing it to all of
    them turned every sweep of another system into a TypeError. This is what the
    CLI does when ``--compare`` switches systems: the setting goes with the
    system it was written for, and the others use their own defaults.
    """
    if system == "fixed_block_3aspect":
        return reg.create(system, sighting_distance_m=250)
    return reg.create(system)


def simulation(timetable, duration_s=9000, system="fixed_block_3aspect"):
    return Simulation(
        network=INFRA.network, blocks=INFRA.blocks, signals=INFRA.signals,
        block_of_segment=INFRA.block_of_segment, crossings=INFRA.crossings,
        signalling=signalling_for(system),
        dispatcher=TimetableDispatcher(timetable, route_lookahead=2),
        driver=Driver(DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 180, duration_s=duration_s),
        interlocking=Interlocking(network=INFRA.network, blocks=INFRA.blocks,
                                  signals=INFRA.signals, points=INFRA.points,
                                  routes=INFRA.routes, automatic_signals=False))


def probe(line, pattern, index=0):
    """One service, alone on the railway, timed at every call."""
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "P", "stock": "EMU", "departure": format_clock(BASE),
                       "ready_lead_s": 60,
                       "calls": calls(line, pattern, index=index)}]}, INFRA)
    sim = simulation(timetable, duration_s=6000)
    while not sim.finished:
        sim.step()
        if sim.trains.get("P") is not None and sim.trains["P"].state == "finished":
            break
    train = sim.trains["P"]
    return {station: (train.actual_arrivals.get(station),
                      train.actual_departures.get(station))
            for station, _ in pattern}


def probe_all(count=COUNT):
    """An unimpeded run per service, per direction, keyed (line, index).

    Two services taking the same roads get the same answer, so the probe is run
    once per distinct set of roads rather than once per service.
    """
    times = {}
    seen = {}
    for line, pattern in (("UP", UP_PATTERN), ("DN", DN_PATTERN)):
        for index in range(count):
            key = (line, tuple(road(s, line, index) for s, _ in pattern))
            if key not in seen:
                seen[key] = probe(line, pattern, index)
            times[(line, index)] = seen[key]
    return times


#: (line, pattern, id prefix, name) for each direction, in report order.
DIRECTIONS = (("UP", UP_PATTERN, "U", "West Depot - East Depot"),
              ("DN", DN_PATTERN, "D", "East Depot - West Depot"))


def flight_spec(times, headway_s, count=COUNT, indices=None,
                directions=None, stock=None):
    """Both flights as a timetable spec: ``count`` trains each way.

    ``indices`` restricts the spec to particular services while leaving them
    booked where they would be in the full flight - which is how the sweep
    prices the flight running alone.

    ``directions`` restricts it to particular lines - ``("UP",)`` runs an up
    flight on its own, which isolates following capacity from the station
    throats being shared with anything coming the other way.

    ``stock`` replaces the unit the flight is booked with, so an experiment can
    change what the train is *fitted* with - which is the variable in a
    signalling comparison - without editing timetable.yaml.
    """
    unit = dict(stock or STOCK)
    wanted = None if directions is None else tuple(directions)
    services = []
    for line, pattern, prefix, name in DIRECTIONS:
        if wanted is not None and line not in wanted:
            continue
        for n in range(count) if indices is None else indices:
            shift = n * headway_s
            entries = []
            for station, dwell in pattern:
                arrival, departure = times[(line, n)][station]
                entry = {"station": station, "platform": road(station, line, n),
                         "dwell_s": dwell}
                if arrival is not None:
                    entry["arrival"] = format_clock(round(arrival) + shift)
                if departure is not None:
                    entry["departure"] = format_clock(round(departure) + shift)
                entries.append(entry)
            services.append({
                "id": "%s%02d" % (prefix, n + 1),
                "name": "%s %s" % (format_clock(BASE + shift)[:5], name),
                "stock": unit["id"], "departure": format_clock(BASE + shift),
                "ready_lead_s": 60, "calls": entries})
    return {"stock": [unit], "services": services}


HEADER = '''# capacity timetable - generated, do not edit by hand.
#
#   python scenarios/capacity/_generate_timetable.py
#
# %d trains each way, booked %d seconds apart, all of them the same unit calling
# everywhere and taking the roads at each station in turn. Every booked time is
# what that service achieves with the railway to itself, over its own roads.
#
# This is the homogeneous base. Heterogeneous stock, mixed speeds and branch
# services are variations on it, not edits to it.

'''


def stock_yaml():
    return '''stock:
  - id: EMU
    name: Line unit
    length_m: 160
    max_speed_kmh: 120
    max_accel: 1.0
    service_brake: 0.8
    emergency_brake: 1.2
    etcs_level: none
    tims: false

services:
'''


def render(times, headway_s, count=COUNT):
    out = [HEADER % (count, headway_s) + stock_yaml()]
    for service in flight_spec(times, headway_s, count)["services"]:
        lines = ["  - id: %s" % service["id"],
                 "    name: %s" % service["name"],
                 "    stock: %s" % service["stock"],
                 '    departure: "%s"' % service["departure"],
                 "    ready_lead_s: 60",
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
    for (line, index) in sorted(times):
        pattern = UP_PATTERN if line == "UP" else DN_PATTERN
        print("%s%02d over %s" % (line[0], index + 1,
                                  ", ".join(road(s, line, index)
                                            for s, _ in pattern)))
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway))
    print("wrote %s - %d trains each way at %d s" % (path, COUNT, headway))
