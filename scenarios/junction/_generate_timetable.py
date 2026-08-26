"""Regenerate scenarios/junction/timetable.yaml.

Like the metro timetables, this is derived data: every service is booked on the
run times a single unimpeded train achieves on this infrastructure, so that the
plan is workable in isolation and any delay the run shows is the junction.

What is *not* derived is the offsets. They are chosen so that a branch service
and a main-line service arrive at Beta wanting the same platform road within
about a minute of each other, which is the whole subject of the scenario. Change
OFFSETS below to move the conflict around.

    python scenarios/junction/_generate_timetable.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from trainsim.scenario.builder import build_infrastructure
from trainsim.scenario.loader import build_timetable, read_data_file
from trainsim.core import signalling as reg
from trainsim.core.dispatcher import TimetableDispatcher
from trainsim.core.driver import Driver, DriverConfig
from trainsim.core.interlocking import Interlocking
from trainsim.core.simulation import SimConfig, Simulation
from trainsim.core.units import format_clock

BASE = 7 * 3600
DWELL = 45
infra = build_infrastructure(read_data_file(os.path.join(HERE, "infrastructure.yaml")))

STOCK = [
    {"id": "EMU_MAIN", "name": "Main line EMU", "length_m": 200,
     "max_speed_kmh": 140, "max_accel": 0.9, "service_brake": 0.7,
     "emergency_brake": 1.2, "etcs_level": "l2", "tims": True},
    {"id": "DMU_BRANCH", "name": "Branch DMU", "length_m": 90,
     "max_speed_kmh": 100, "max_accel": 0.8, "service_brake": 0.7,
     "emergency_brake": 1.1, "etcs_level": "l2", "tims": True},
]

#: name -> (stock, [(station, platform), ...])
PATTERNS = {
    "MU": ("EMU_MAIN", [("ALPHA", "ALPHA_1"), ("BETA", "BETA_1"),
                        ("GAMMA", "GAMMA_1")]),
    "BU": ("DMU_BRANCH", [("HALT", "HALT_1"), ("BETA", "BETA_1"),
                          ("GAMMA", "GAMMA_1")]),
    "MD": ("EMU_MAIN", [("GAMMA", "GAMMA_2"), ("BETA", "BETA_2"),
                        ("ALPHA", "ALPHA_2")]),
    "BD": ("DMU_BRANCH", [("GAMMA", "GAMMA_2"), ("BETA", "BETA_2"),
                          ("HALT", "HALT_2")]),
}

#: pattern -> (first departure offset, interval, how many)
OFFSETS = {
    "MU": (0, 360, 6),
    # Ninety seconds behind each main-line train, arriving at the junction just
    # as it is clearing: close enough that the interlocking has to sequence
    # them, far enough that a well-run railway could still take both.
    "BU": (90, 360, 6),
    "MD": (180, 360, 6),
    "BD": (270, 360, 6),
}


def calls_for(pattern, shift=0, times=None):
    _, stops = PATTERNS[pattern]
    out = []
    for index, (station, platform) in enumerate(stops):
        call = {"station": station, "platform": platform,
                "dwell_s": DWELL if 0 < index < len(stops) - 1 else 30}
        if index == 0:
            call["departure"] = BASE + shift
        elif times is not None:
            arrival, departure = times[station]
            if arrival is not None:
                call["arrival"] = round(arrival) + shift
            if departure is not None:
                call["departure"] = round(departure) + shift
        out.append(call)
    return out


def probe(pattern):
    """Run one train of this pattern alone; return {station: (arrival, departure)}."""
    stock_id, stops = PATTERNS[pattern]
    timetable = build_timetable(
        {"stock": STOCK,
         "services": [{"id": "P", "stock": stock_id, "departure": BASE,
                       "ready_lead_s": 60, "calls": calls_for(pattern)}]},
        infra)
    sim = Simulation(
        network=infra.network, blocks=infra.blocks, signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=reg.create("etcs_l2"),
        dispatcher=TimetableDispatcher(timetable),
        driver=Driver(DriverConfig()),
        config=SimConfig(dt=1.0, start_time_s=BASE - 120, duration_s=3600),
        interlocking=Interlocking(network=infra.network, blocks=infra.blocks,
                                  signals=infra.signals, points=infra.points,
                                  routes=infra.routes))
    while not sim.finished:
        sim.step()
    train = sim.trains["P"]
    assert train.state == "finished", "%s never completed" % (pattern,)
    return {station: (train.actual_arrivals.get(station),
                      train.actual_departures.get(station))
            for station, _ in stops}


TIMES = {pattern: probe(pattern) for pattern in PATTERNS}
for pattern, times in TIMES.items():
    print(pattern, {s: (None if a is None else int(a - BASE))
                    for s, (a, _) in times.items()})


def emit():
    lines = []
    for pattern in ("MU", "BU", "MD", "BD"):
        first, interval, count = OFFSETS[pattern]
        stock_id, _ = PATTERNS[pattern]
        lines.append("# %s" % {
            "MU": "Main line up: Alpha - Beta - Gamma, every 6 minutes.",
            "BU": "Branch up: Halt - Beta - Gamma, joining the up main at Beta.",
            "MD": "Main line down: Gamma - Beta - Alpha.",
            "BD": "Branch down: Gamma - Beta - Halt, leaving the down main at Beta.",
        }[pattern])
        for n in range(count):
            shift = first + n * interval
            service_id = "%s%d" % (pattern, n + 1)
            lines.append("  - id: %s" % service_id)
            lines.append("    stock: %s" % stock_id)
            lines.append('    departure: "%s"' % format_clock(BASE + shift))
            lines.append("    ready_lead_s: 60")
            lines.append("    calls:")
            for call in calls_for(pattern, shift, TIMES[pattern]):
                bits = ["station: %s" % call["station"],
                        "platform: %s" % call["platform"]]
                if "arrival" in call:
                    bits.append('arrival: "%s"' % format_clock(call["arrival"]))
                if "departure" in call:
                    bits.append('departure: "%s"' % format_clock(call["departure"]))
                bits.append("dwell_s: %d" % call["dwell_s"])
                lines.append("      - {%s}" % ", ".join(bits))
    return "\n".join(lines)


HEADER = '''# junction - main line and branch services competing for Beta.
#
# Four patterns, all booked on the run times a single unimpeded train achieves,
# so each is workable on its own. What is not workable on its own is the
# combination: the branch up service is booked to arrive at Beta ninety seconds
# behind a main line service, and both want platform BETA_1.
#
# There is only one road each way at Beta, deliberately. Give the branch its own
# bay platform and the conflict vanishes - which is exactly why bay platforms at
# junction stations are expensive and worth it.
#
# What happens is not a crash and not a violation. The interlocking simply
# refuses the second route request:
#
#     route_refused  BU2  R_BETA_1_from_BR_UP_JN: PT_UP_13400_T locked to
#                         UP_007 by R_BETA_1_from_UP_007, set for MU2
#
# and the branch train stands at its signal on the junction link until the main
# line train has gone. That is correct, safe, and the whole problem: nothing in
# this simulator decided that the main line train should go first. It went first
# because it asked first.
#
#   python run.py scenarios/junction --events | grep route_refused
#   python run.py scenarios/junction --compare

stock:
  - id: EMU_MAIN
    name: Main line EMU
    length_m: 200
    max_speed_kmh: 140
    max_accel: 0.9
    service_brake: 0.7
    emergency_brake: 1.2
    etcs_level: l2
    tims: true

  # Shorter, slower, and it has to cross the junction at 60 km/h - so it occupies
  # the conflicting point for longer than the train it is delaying.
  - id: DMU_BRANCH
    name: Branch DMU
    length_m: 90
    max_speed_kmh: 100
    max_accel: 0.8
    service_brake: 0.7
    emergency_brake: 1.1
    etcs_level: l2
    tims: true

services:
'''

path = os.path.join(HERE, "timetable.yaml")
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(HEADER + emit() + "\n")
print("wrote", path)
