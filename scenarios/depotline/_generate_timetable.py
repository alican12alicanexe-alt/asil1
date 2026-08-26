"""Regenerate scenarios/depotline/timetable.yaml - a homogeneous flight.

Every service on this line is now the same train doing the same thing: the same
unit, the same calls, the same roads, the same dwells. That is what makes the
headway a property of the *railway* rather than of the traffic mix. With a fast
unit mixed in among stoppers, the binding constraint is the speed difference and
the answer depends on where the loops happen to be; with one train type it is
the signalling and the station dwell, and nothing else.

Booked times come from running a single unimpeded train and offsetting it by one
headway per service, so the plan is workable by construction. Re-run after
changing a dwell, a chainage, the stock or HEADWAY_S:

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
#: from four minutes down to one and reports what it costs.
HEADWAY_S = 240

STOCK = {"id": "EMU", "name": "Line unit", "length_m": 160,
         "max_speed_kmh": 100, "max_accel": 1.0, "service_brake": 0.8,
         "emergency_brake": 1.2, "etcs_level": "none", "tims": False}

#: (station, platform, dwell). One pattern, one road at each station - a
#: homogeneous flight does not use the loops, which is the point of measuring it.
PATTERN = [("WDEPOT", "WDEPOT_1", DEPOT), ("KINGSFORD", "KINGSFORD_1", DWELL),
           ("MARLOWE", "MARLOWE_1", DWELL), ("ASHDOWN", "ASHDOWN_1", DWELL),
           ("EDEPOT", "EDEPOT_1", DEPOT)]

INFRA = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))


def calls(shift=0):
    """The calling pattern as timetable entries, shifted by ``shift`` seconds."""
    entries = [{"station": s, "platform": p, "dwell_s": d} for s, p, d in PATTERN]
    entries[0]["departure"] = format_clock(BASE + shift)
    return entries


def simulation(timetable, duration_s=7200):
    return Simulation(
        network=INFRA.network, blocks=INFRA.blocks, signals=INFRA.signals,
        block_of_segment=INFRA.block_of_segment,
        signalling=reg.create("fixed_block_3aspect", sighting_distance_m=250),
        dispatcher=TimetableDispatcher(timetable),
        driver=Driver(DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 180, duration_s=duration_s),
        interlocking=Interlocking(network=INFRA.network, blocks=INFRA.blocks,
                                  signals=INFRA.signals, points=INFRA.points,
                                  routes=INFRA.routes))


def probe():
    """Run one train with the road to itself, and time it at every call."""
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "P", "stock": "EMU", "departure": format_clock(BASE),
                       "ready_lead_s": 60, "calls": calls()}]}, INFRA)
    sim = simulation(timetable, duration_s=3600)
    while not sim.finished:
        sim.step()
        if sim.trains.get("P") is not None and sim.trains["P"].state == "finished":
            break
    train = sim.trains["P"]
    return {station: (train.actual_arrivals.get(station),
                      train.actual_departures.get(station))
            for station, _, _ in PATTERN}


def flight_spec(times, headway_s, count=COUNT):
    """The whole flight as a timetable spec: ``count`` trains, one every headway."""
    services = []
    for n in range(count):
        shift = n * headway_s
        entries = []
        for station, platform, dwell in PATTERN:
            arrival, departure = times[station]
            entry = {"station": station, "platform": platform, "dwell_s": dwell}
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
# A homogeneous flight: %d trains of one type, all calling at every station on
# the main road, booked %d seconds apart. Every booked time is what a single
# unimpeded train actually achieves on this railway, so the plan is workable on
# its own and any delay a run reports is the signalling failing to deliver it.
#
# %d seconds is the shortest interval this line will hold. _sweep_headway.py is
# where that number comes from.

'''


def stock_yaml():
    return '''stock:
  - id: EMU
    name: Line unit
    length_m: 160
    max_speed_kmh: 100
    max_accel: 1.0
    service_brake: 0.8
    emergency_brake: 1.2
    # No ETCS fitment: lineside signals, read by drivers, which is what fixes
    # the headway this line can work to.
    etcs_level: none
    tims: false

services:
'''


def render(times, headway_s, count=COUNT):
    out = [HEADER % (count, headway_s, headway_s) + stock_yaml()]
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
    times = probe()
    print("unimpeded run:", {s: (a and round(a - BASE), d and round(d - BASE))
                             for s, (a, d) in times.items()})
    path = os.path.join(HERE, "timetable.yaml")
    with open(path, "w") as handle:
        handle.write(render(times, HEADWAY_S))
    print("wrote %s - %d trains at %d s" % (path, COUNT, HEADWAY_S))
