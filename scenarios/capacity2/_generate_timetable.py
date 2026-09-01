"""Regenerate scenarios/capacity2/timetable.yaml - the mixed-performance flight.

This is sweep 2. It is the capacity base with exactly one thing changed: the
trains are no longer all the same. Two types alternate along each line,

    normal, fast, normal, fast, ...

and the question it exists to answer is whether that changes the *relative*
standing of fixed block, moving block and virtual coupling, or only moves all
three by the same amount. A signalling system that gains its advantage from
putting trains closer together may or may not keep that advantage when the
train behind is quicker than the train in front.

Everything else is held at the capacity base: same layout, same station
spacing, same dwells, same driver, same interlocking, same simulation step, and
the same sweep and refinement method. The line limit is raised from 120 to 150
so the two types actually differ on the road - at a 120 limit a 160 km/h unit
is just a 120 km/h unit with better brakes, and the experiment would be half
missing.

Booked times come from running each service unimpeded with the type that
actually works it. That matters more here than it did on the base: a fast unit
booked on normal timings would be given a run time it beats by minutes and
would spend the whole journey standing at platforms, and a normal unit booked
on fast timings could never keep its plan at all. One probe per (type, set of
roads).

    python scenarios/capacity2/_generate_timetable.py
    python scenarios/capacity2/_generate_timetable.py 240 timetable-close

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
COUNT = 8
HEADWAY_S = 300

#: The two types, in the order they alternate. Index 0 of each direction is a
#: normal unit, index 1 a fast one, and so on down the flight, so every fast
#: train follows a normal one and is followed by a normal one. That is the
#: arrangement that puts the most pressure on the signalling: a quicker train
#: closing on a slower one, every other path, in both directions at once.
NORMAL = {"id": "EMU", "name": "Normal unit", "length_m": 160,
          "max_speed_kmh": 120, "max_accel": 1.0, "service_brake": 0.8,
          "emergency_brake": 1.2, "etcs_level": "none", "tims": False}
FAST = {"id": "EMUF", "name": "Fast unit", "length_m": 160,
        "max_speed_kmh": 160, "max_accel": 1.5, "service_brake": 1.1,
        "emergency_brake": 1.4, "etcs_level": "none", "tims": False}
FLEET = (NORMAL, FAST)

#: Kept for anything that imports the base's name for the unit.
STOCK = NORMAL

INFRA = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))

#: (station, dwell) in the order each direction calls at them.
UP_PATTERN = [("WDEPOT", DEPOT), ("LINFORD", DWELL), ("BRAMLEY", DWELL),
              ("CALDER", DWELL), ("EDEPOT", DEPOT)]
DN_PATTERN = list(reversed(UP_PATTERN))


def fleet_for(index, fleet=None):
    """The unit service ``index`` is worked by - the types alternate."""
    types = tuple(fleet or FLEET)
    return types[index % len(types)]


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
    """Build a signalling system, giving it only settings it has."""
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


def probe(line, pattern, index=0, unit=None):
    """One service, alone on the railway, with its own type, timed at each call."""
    unit = dict(unit or NORMAL)
    timetable = build_timetable(
        {"stock": [unit],
         "services": [{"id": "P", "stock": unit["id"],
                       "departure": format_clock(BASE),
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


def probe_all(count=COUNT, fleet=None):
    """An unimpeded run per service, per direction, keyed (line, index).

    Two services get the same answer only if they take the same roads *and* are
    worked by the same type, so the type is part of the key. On the homogeneous
    base it was not, and reusing that would have booked half this flight on the
    wrong timings.

    ``fleet`` replaces the pair of types, so a control run can put the same unit
    on every path and price the railway without the mix.
    """
    times = {}
    seen = {}
    for line, pattern in (("UP", UP_PATTERN), ("DN", DN_PATTERN)):
        for index in range(count):
            unit = fleet_for(index, fleet)
            key = (line, unit["id"],
                   tuple(road(s, line, index) for s, _ in pattern))
            if key not in seen:
                seen[key] = probe(line, pattern, index, unit)
            times[(line, index)] = seen[key]
    return times


#: (line, pattern, id prefix, name) for each direction, in report order.
DIRECTIONS = (("UP", UP_PATTERN, "U", "West Depot - East Depot"),
              ("DN", DN_PATTERN, "D", "East Depot - West Depot"))


def flight_spec(times, headway_s, count=COUNT, indices=None,
                directions=None, fleet=None):
    """Both flights as a timetable spec: ``count`` trains each way.

    ``indices`` restricts the spec to particular services while leaving them
    booked where they would be in the full flight - which is how the sweep
    prices the flight running alone.

    ``directions`` restricts it to particular lines.

    ``fleet`` replaces the two types the flight is booked with, so the sweep can
    change what the trains are *fitted* with - the variable in a signalling
    comparison - without touching what they can do, which is the variable in
    this one.
    """
    types = tuple(dict(u) for u in (fleet or FLEET))
    wanted = None if directions is None else tuple(directions)
    services = []
    for line, pattern, prefix, name in DIRECTIONS:
        if wanted is not None and line not in wanted:
            continue
        for n in range(count) if indices is None else indices:
            shift = n * headway_s
            unit = fleet_for(n, types)
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
                "name": "%s %s %s" % (format_clock(BASE + shift)[:5], name,
                                      "(fast)" if unit["id"] != types[0]["id"]
                                      else ""),
                "stock": unit["id"], "departure": format_clock(BASE + shift),
                "ready_lead_s": 60, "calls": entries})
    # Deduplicated by id, because a control run puts the same type on every
    # path and a timetable may not declare one unit twice.
    declared = []
    for unit in types:
        if unit["id"] not in [d["id"] for d in declared]:
            declared.append(unit)
    return {"stock": declared, "services": services}


HEADER = '''# capacity2 timetable - generated, do not edit by hand.
#
#   python scenarios/capacity2/_generate_timetable.py
#
# %d trains each way, booked %d seconds apart, taking the roads at each station
# in turn. Two types alternate along each line - normal, fast, normal, fast -
# and every booked time is what that type achieves over those roads with the
# railway to itself.
#
# This is sweep 2: the capacity base with heterogeneous train performance and
# nothing else changed.

'''


def stock_yaml(types=FLEET):
    lines = ["stock:"]
    for unit in types:
        lines += ["  - id: %s" % unit["id"],
                  "    name: %s" % unit["name"],
                  "    length_m: %d" % unit["length_m"],
                  "    max_speed_kmh: %d" % unit["max_speed_kmh"],
                  "    max_accel: %s" % unit["max_accel"],
                  "    service_brake: %s" % unit["service_brake"],
                  "    emergency_brake: %s" % unit["emergency_brake"],
                  "    etcs_level: %s" % unit["etcs_level"],
                  "    tims: %s" % ("true" if unit["tims"] else "false")]
    lines += ["", "services:", ""]
    return "\n".join(lines)


def render(times, headway_s, count=COUNT):
    out = [HEADER % (count, headway_s) + stock_yaml()]
    for service in flight_spec(times, headway_s, count)["services"]:
        lines = ["  - id: %s" % service["id"],
                 "    name: %s" % service["name"].rstrip(),
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
        unit = fleet_for(index)
        print("%s%02d  %-11s over %s" % (
            line[0], index + 1, unit["name"],
            ", ".join(road(s, line, index)
                      for s, _ in (UP_PATTERN if line == "UP" else DN_PATTERN))))
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway))
    print("wrote %s - %d trains each way at %d s" % (path, COUNT, headway))
