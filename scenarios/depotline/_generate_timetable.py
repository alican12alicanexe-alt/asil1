"""Regenerate scenarios/depotline/timetable.yaml.

Derived data, not hand-written. Every service is booked on the run times a
*single unimpeded train* achieves on this railway - measured by running one,
below - so the plan is workable in isolation and any delay a run reports is the
signalling or the conflict between services rather than a plan that was never
possible. Change a dwell, a chainage or the rolling stock and the booked times
are stale.

    python scenarios/depotline/_generate_timetable.py

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
OVERTAKEN = 180     # the stopper's wait in the loop at Marlowe
DEPOT = 60          # preparing to leave the depot / stabling at the far end

STOCK = [
    {"id": "EMU_STOP", "name": "Stopping unit", "length_m": 160,
     "max_speed_kmh": 100, "max_accel": 1.0, "service_brake": 0.8,
     "emergency_brake": 1.2, "etcs_level": "none", "tims": False},
    {"id": "EMU_FAST", "name": "Fast unit", "length_m": 200,
     "max_speed_kmh": 120, "max_accel": 0.9, "service_brake": 0.7,
     "emergency_brake": 1.2, "etcs_level": "none", "tims": False,
     # Weighed and powered explicitly rather than left to be derived, so the
     # traction curve here is this unit's rather than a plausible one: 360 t on
     # 5.4 MW at the wheel puts base speed at 56 km/h, above which the effort
     # falls away as power over speed like any real train's.
     "mass_t": 360, "power_kw": 5400},
]

#: (station, platform, dwell) - the two calling patterns this line runs.
STOPPER = [("WDEPOT", "WDEPOT_1", DEPOT), ("KINGSFORD", "KINGSFORD_2", DWELL),
           ("MARLOWE", "MARLOWE_3", OVERTAKEN), ("ASHDOWN", "ASHDOWN_2", DWELL),
           ("EDEPOT", "EDEPOT_1", DEPOT)]
FAST = [("WDEPOT", "WDEPOT_1", DEPOT), ("MARLOWE", "MARLOWE_1", DWELL),
        ("EDEPOT", "EDEPOT_1", DEPOT)]

infra = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))


def probe(pattern, stock_id):
    """Run one train over ``pattern`` with the road to itself, and time it."""
    calls = [{"station": s, "platform": p, "dwell_s": d} for s, p, d in pattern]
    calls[0]["departure"] = "07:00:00"
    timetable = build_timetable(
        {"stock": STOCK,
         "services": [{"id": "P", "stock": stock_id, "departure": "07:00:00",
                       "ready_lead_s": 60, "calls": calls}]}, infra)
    sim = Simulation(
        network=infra.network, blocks=infra.blocks, signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=reg.create("fixed_block_3aspect", sighting_distance_m=250),
        dispatcher=TimetableDispatcher(timetable),
        driver=Driver(DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 180, duration_s=3600),
        interlocking=Interlocking(network=infra.network, blocks=infra.blocks,
                                  signals=infra.signals, points=infra.points,
                                  routes=infra.routes))
    while not sim.finished:
        sim.step()
        if sim.trains.get("P") is not None and sim.trains["P"].state == "finished":
            break
    train = sim.trains["P"]
    return {station: (train.actual_arrivals.get(station),
                      train.actual_departures.get(station))
            for station, _, _ in pattern}


TIMES = {"stopper": probe(STOPPER, "EMU_STOP"), "fast": probe(FAST, "EMU_FAST")}
for name, times in TIMES.items():
    print("%-8s %s" % (name, {s: (a and round(a - BASE), d and round(d - BASE))
                              for s, (a, d) in times.items()}))


def service(sid, name, pattern, kind, stock_id, shift):
    lines = ["  - id: %s" % sid,
             "    name: %s" % name,
             "    stock: %s" % stock_id,
             '    departure: "%s"' % format_clock(BASE + shift),
             "    ready_lead_s: 60",
             "    calls:"]
    for station, platform, dwell in pattern:
        arrival, departure = TIMES[kind][station]
        bits = ["station: %s" % station, "platform: %s" % platform]
        if arrival is not None:
            bits.append('arrival: "%s"' % format_clock(round(arrival) + shift))
        if departure is not None:
            bits.append('departure: "%s"' % format_clock(round(departure) + shift))
        bits.append("dwell_s: %d" % dwell)
        lines.append("      - {%s}" % ", ".join(bits))
    return "\n".join(lines)


HEADER = '''# depotline timetable - generated, do not edit by hand.
#
#   python scenarios/depotline/_generate_timetable.py
#
# Four stopping services and two fast ones, all running west depot to east
# depot over the single line. Every booked time is what an unimpeded train of
# that type actually achieves on this railway, so the plan is workable on its
# own; what it is not is conflict-free, and that is the point.
#
# A fast is booked three minutes behind a stopper. On a single line with no
# passing places that would simply mean the fast running at the stopper's speed
# the whole way. Here it means the stopper stands in the loop at Marlowe for
# three minutes while the fast comes through the main road past it, which is the
# cheapest capacity a single-track railway can buy and the reason the station
# has four roads instead of one.

'''

STOCK_YAML = '''stock:
  - id: EMU_STOP
    name: Stopping unit
    length_m: 160
    max_speed_kmh: 100
    max_accel: 1.0
    service_brake: 0.8
    emergency_brake: 1.2
    # No ETCS fitment anywhere on this line: it is signalled by lineside signals
    # and worked by drivers reading them, which is what the scenario is about.
    etcs_level: none
    tims: false

  - id: EMU_FAST
    name: Fast unit
    length_m: 200
    max_speed_kmh: 120
    max_accel: 0.9
    service_brake: 0.7
    emergency_brake: 1.2
    etcs_level: none
    tims: false
    # Weighed and powered explicitly. Everything else about the dynamics - the
    # Davis resistance coefficients, adhesion, brake build-up - is derived from
    # these figures in core/dynamics.py, and can be written here too.
    mass_t: 360
    power_kw: 5400

services:
'''


def build() -> str:
    out = [HEADER + STOCK_YAML]
    out.append("  # ------------------------------------------------- stopping services")
    for n in range(4):
        out.append(service("S%d" % (n + 1),
                           "%s West Depot - East Depot stopping"
                           % format_clock(BASE + n * 600)[:5].replace(":", ""),
                           STOPPER, "stopper", "EMU_STOP", n * 600))
        out.append("")
    out.append("  # ----------------------------------------------------- fast services")
    for n, shift in enumerate((180, 1380)):
        out.append(service("F%d" % (n + 1),
                           "%s West Depot - East Depot fast"
                           % format_clock(BASE + shift)[:5].replace(":", ""),
                           FAST, "fast", "EMU_FAST", shift))
        out.append("")
    return "\n".join(out)


path = os.path.join(HERE, "timetable.yaml")
with open(path, "w") as handle:
    handle.write(build())
print("wrote", path)
