"""Regenerate scenarios/depotline/timetable.yaml - one flight, every road.

Every service is the same unit making the same calls with the same dwells, so
the headway stays a property of the *railway* rather than of the traffic mix:
with a fast unit mixed in among stoppers the binding constraint is the speed
difference and the answer depends on where the loops happen to be.

What the services no longer share is the concrete. Each station's roads are used
in turn, because a station's roads exist to be used - sending every train to
road 1 held one platform for the dwell plus the approach and left the loops
empty, which put a floor under the headway that had nothing to do with the
signalling.

That makes the flight inhomogeneous in one respect: the loops are slower than
the through road, so a train routed over one takes longer. Each service is
therefore booked from its own unimpeded run rather than from one shared probe,
which keeps the plan workable by construction. Re-run after changing a dwell, a
chainage, the stock or HEADWAY_S:

    python scenarios/depotline/_generate_timetable.py

``_sweep_headway.py`` is what HEADWAY_S below was chosen from.

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
DWELL = 45          # a station call
DEPOT = 60          # preparing to leave the depot / stabling at the far end
COUNT = 8           # trains in the flight

#: The interval the flight is booked at. Measured, not chosen: see the table in
#: scenario.yaml and _sweep_headway.py, which runs the flight at every interval
#: from five minutes down to one and reports what it costs.
#:
#: 165 s while this line still had automatic signals on the plain line. Working
#: it entirely by route costs 45 s of headway, because a route reserves its block
#: from the moment it is set - two signals ahead of the train - while an
#: automatic signal only holds a section that a train is physically standing in.
#:
#: 210 s while every train took road 1 at every station. Using the roads in turn
#: costs another 30 s, because the loops are slower than the through road and
#: this flight has nothing to overtake: half the trains end up in a section worth
#: 169 s to get out of one worth 149 s. It is the loss --check predicted, and it
#: is the price of the platforms being used rather than the price of signalling.
HEADWAY_S = 240

STOCK = {"id": "EMU", "name": "Line unit", "length_m": 160,
         "max_speed_kmh": 100, "max_accel": 1.0, "service_brake": 0.8,
         "emergency_brake": 1.2, "etcs_level": "none", "tims": False}

#: (station, dwell). One calling pattern, every station on the running line.
#: Which *road* each train takes is not fixed here - see :func:`road`.
PATTERN = [("WDEPOT", DEPOT), ("KINGSFORD", DWELL), ("MARLOWE", DWELL),
           ("ASHDOWN", DWELL), ("EDEPOT", DEPOT)]

INFRA = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))

#: Every road at each station, in the order the layout declares them. Read from
#: the infrastructure rather than listed here, so a loop added to the layout is
#: used by the flight without anyone having to remember to say so.
ROADS = {station: [pid for pid, plat in INFRA.network.platforms.items()
                   if plat.station == station]
         for station, _ in PATTERN}


def road(station, index):
    """The road service ``index`` takes at ``station`` - they are used in turn.

    A station's roads exist to be used. Sending every train down road 1 held one
    platform for the dwell plus the approach and left the loops empty, which put
    a floor under the headway that had nothing to do with the signalling: no
    interval is workable if every train needs the same piece of concrete. Using
    them in turn is what a real service pattern does, and it is why the loops
    were built.

    The cost is that the flight is no longer homogeneous - the loops are slower
    than the through road, so a train routed over one takes longer - which is
    why every service is booked from its own unimpeded run rather than from one
    shared probe.
    """
    available = ROADS[station]
    return available[index % len(available)]


def calls(shift=0, index=0):
    """The calling pattern as timetable entries, shifted by ``shift`` seconds."""
    entries = [{"station": s, "platform": road(s, index), "dwell_s": d}
               for s, d in PATTERN]
    entries[0]["departure"] = format_clock(BASE + shift)
    return entries


def simulation(timetable, duration_s=7200, system="fixed_block_3aspect"):
    return Simulation(
        network=INFRA.network, blocks=INFRA.blocks, signals=INFRA.signals,
        block_of_segment=INFRA.block_of_segment,
        signalling=reg.create(system, sighting_distance_m=250),
        # These two must track scenario.yaml, or the timetable is generated
        # against a different railway from the one that runs it. depotline has
        # no automatic signals: every signal waits on a route, so the signaller
        # has to work two ahead for a driver to see a green at all.
        dispatcher=TimetableDispatcher(timetable, route_lookahead=2),
        driver=Driver(DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 180, duration_s=duration_s),
        interlocking=Interlocking(network=INFRA.network, blocks=INFRA.blocks,
                                  signals=INFRA.signals, points=INFRA.points,
                                  routes=INFRA.routes,
                                  automatic_signals=False))


def probe(index=0):
    """Run one train over service ``index``'s roads, alone, and time its calls."""
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "P", "stock": "EMU", "departure": format_clock(BASE),
                       "ready_lead_s": 60, "calls": calls(index=index)}]}, INFRA)
    sim = simulation(timetable, duration_s=5400)
    while not sim.finished:
        sim.step()
        if sim.trains.get("P") is not None and sim.trains["P"].state == "finished":
            break
    train = sim.trains["P"]
    return {station: (train.actual_arrivals.get(station),
                      train.actual_departures.get(station))
            for station, _ in PATTERN}


def probe_all(count=COUNT):
    """An unimpeded run per service: index -> station -> (arrival, departure).

    One probe no longer describes the flight. A train routed over a 60 km/h loop
    takes longer than one down the through road, so booking every service from a
    single run would hand half of them times they cannot keep and call the
    difference congestion. Runs sharing a set of roads are measured once.
    """
    by_roads = {}
    times = {}
    for index in range(count):
        key = tuple(road(station, index) for station, _ in PATTERN)
        if key not in by_roads:
            by_roads[key] = probe(index)
        times[index] = by_roads[key]
    return times


def flight_spec(times, headway_s, count=COUNT, indices=None):
    """The whole flight as a timetable spec: ``count`` trains, one every headway.

    ``times`` is what :func:`probe_all` returns. ``indices`` restricts the spec to
    particular services while leaving them booked where they would be in the full
    flight - which is how the sweep prices one train running alone.
    """
    services = []
    for n in range(count) if indices is None else indices:
        shift = n * headway_s
        entries = []
        for station, dwell in PATTERN:
            arrival, departure = times[n][station]
            entry = {"station": station, "platform": road(station, n),
                     "dwell_s": dwell}
            if arrival is not None:
                entry["arrival"] = format_clock(round(arrival) + shift)
            if departure is not None:
                entry["departure"] = format_clock(round(departure) + shift)
            entries.append(entry)
        services.append({"id": "T%02d" % (n + 1),
                         "name": "%s West Depot - East Depot"
                                 % format_clock(BASE + shift)[:5],
                         "stock": "EMU", "departure": format_clock(BASE + shift),
                         "ready_lead_s": 60, "calls": entries})
    return {"stock": [STOCK], "services": services}


HEADER = '''# depotline timetable - generated, do not edit by hand.
#
#   python scenarios/depotline/_generate_timetable.py
#
# A flight of %d trains of one type, all calling at every station, booked %d
# seconds apart, and taking the roads at each station in turn rather than all
# queueing for road 1. Every booked time is what that service actually achieves
# with the railway to itself - over its own roads, since the loops are slower
# than the through road - so the plan is workable on its own and any delay a run
# reports is the signalling failing to deliver it.
#
# %d seconds is the shortest interval this line will hold. _sweep_headway.py is
# where that number comes from.

'''


UNFITTED = """    # No ETCS fitment: lineside signals, read by drivers, which is what fixes
    # the headway this line can work to.
    etcs_level: none
    tims: false
    v2v: false"""

FITTED = """    # Fitted throughout, which is what a distance-separated system needs to be
    # worth anything: a train that cannot confirm its own rear cannot be
    # followed by distance, and one without the link cannot be followed by
    # relative braking distance. Without these three lines moving block falls
    # back to block granularity behind every train and looks exactly like the
    # fixed block it was meant to replace - correctly, and silently.
    etcs_level: l3
    tims: true
    v2v: true"""


def stock_yaml(fitted=False):
    return '''stock:
  - id: EMU
    name: Line unit
    length_m: 160
    max_speed_kmh: 100
    max_accel: 1.0
    service_brake: 0.8
    emergency_brake: 1.2
%s

services:
''' % (FITTED if fitted else UNFITTED,)


def render(times, headway_s, count=COUNT, fitted=False):
    out = [HEADER % (count, headway_s, headway_s) + stock_yaml(fitted)]
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
    # An interval and a file may be given, which is how timetable-close.yaml is
    # made: the same flight booked far tighter than this line can work, so that
    # trains actually close up on each other and there is something for a
    # distance-separated system to do. At the booked interval there is not -
    # eight trains four minutes apart never come within a block of each other,
    # and moving block and fixed block look identical because they are.
    #
    #   python _generate_timetable.py                        -> timetable.yaml
    #   python _generate_timetable.py 90 timetable-l3 fitted -> the L3 one
    #
    # ``fitted`` puts ETCS Level 3, integrity monitoring and the train-to-train
    # link on the stock. It changes nothing under lineside signals and everything
    # under a system that separates by distance.
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else HEADWAY_S
    name = sys.argv[2] if len(sys.argv) > 2 else "timetable"
    fitted = len(sys.argv) > 3 and sys.argv[3] == "fitted"

    times = probe_all()
    for index in sorted(times):
        print("T%02d over %s" % (
            index + 1, ", ".join(road(station, index) for station, _ in PATTERN)))
        print("   unimpeded:", {s: (a and round(a - BASE), d and round(d - BASE))
                                for s, (a, d) in times[index].items()})
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway, fitted=fitted))
    print("wrote %s - %d trains at %d s" % (path, COUNT, headway))
