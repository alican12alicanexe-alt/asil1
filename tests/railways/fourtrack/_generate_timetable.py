"""Regenerate scenarios/fourtrack/timetable.yaml.

Derived data, like the other generated timetables: every service is booked on the
run times a single unimpeded train achieves, so each pattern is workable on its
own and any delay a run shows belongs to the interaction between them.

The interaction being studied is the semi-fast crossing from the slow line to the
fast line at XO_UP. OFFSETS below decide how close it is booked to the fast train
it has to fit in front of; that is the whole experiment, so it is chosen rather
than derived.

    python scenarios/fourtrack/_generate_timetable.py
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
DWELL = 60
infra = build_infrastructure(read_data_file(os.path.join(HERE, "infrastructure.yaml")))

STOCK = [
    {"id": "EXPRESS", "name": "Express", "length_m": 240, "max_speed_kmh": 160,
     "max_accel": 0.8, "service_brake": 0.7, "emergency_brake": 1.2,
     "etcs_level": "l2", "tims": True},
    {"id": "STOPPER", "name": "Suburban EMU", "length_m": 160,
     "max_speed_kmh": 120, "max_accel": 1.0, "service_brake": 0.8,
     "emergency_brake": 1.2, "etcs_level": "l2", "tims": True},
]

#: pattern -> (stock, calls, what it is)
PATTERNS = {
    "F": ("EXPRESS", [("ALPHA", "ALPHA_UF"), ("GAMMA", "GAMMA_UF")],
          "Up fast: Alpha to Gamma non-stop, never leaves the fast line."),
    "S": ("STOPPER", [("ALPHA", "ALPHA_US"), ("BETA", "BETA_US"),
                      ("GAMMA", "GAMMA_US")],
          "Up slow: all stations, never leaves the slow line."),
    "X": ("EXPRESS", [("ALPHA", "ALPHA_US"), ("BETA", "BETA_US"),
                      ("GAMMA", "GAMMA_UF")],
          "Up semi-fast: calls at Beta on the slow line, then crosses to the "
          "fast line at XO_UP and runs through. This is the train the crossover "
          "exists for, and the one that has to be fitted in."),
    "FD": ("EXPRESS", [("GAMMA", "GAMMA_DF"), ("ALPHA", "ALPHA_DF")],
           "Down fast: Gamma to Alpha non-stop."),
    "SD": ("STOPPER", [("GAMMA", "GAMMA_DS"), ("BETA", "BETA_DS"),
                       ("ALPHA", "ALPHA_DS")],
           "Down slow: all stations."),
    "XD": ("EXPRESS", [("GAMMA", "GAMMA_DF"), ("BETA", "BETA_DS"),
                       ("ALPHA", "ALPHA_DS")],
           "Down semi-fast: leaves the fast line at XO_DN to call at Beta."),
}

#: pattern -> (first departure offset, interval, how many)
#:
#: The semi-fast is booked to reach the crossover shortly after a fast has
#: passed. Move X's offset and the conflict moves with it - that is the knob.
OFFSETS = {
    "F": (0, 480, 4),
    "S": (120, 480, 4),
    "X": (300, 480, 4),
    "FD": (240, 480, 4),
    "SD": (360, 480, 4),
    "XD": (60, 480, 4),
}


def calls_for(pattern, shift=0, times=None):
    _, stops, _ = PATTERNS[pattern]
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
    stock_id, stops, _ = PATTERNS[pattern]
    timetable = build_timetable(
        {"stock": STOCK,
         "services": [{"id": "P", "stock": stock_id, "departure": BASE,
                       "ready_lead_s": 60, "calls": calls_for(pattern)}]},
        infra)
    sim = Simulation(
        network=infra.network, blocks=infra.blocks, signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=reg.create("etcs_l2"),
        dispatcher=TimetableDispatcher(timetable), driver=Driver(DriverConfig()),
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
    print("%-3s %s" % (pattern, {s: (None if a is None else int(a - BASE))
                                 for s, (a, _) in times.items()}))


def emit():
    lines = []
    for pattern in ("F", "S", "X", "FD", "SD", "XD"):
        first, interval, count = OFFSETS[pattern]
        stock_id, _, description = PATTERNS[pattern]
        lines.append("# %s" % description)
        for n in range(count):
            shift = first + n * interval
            lines.append("  - id: %s%d" % (pattern, n + 1))
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


HEADER = '''# fourtrack - fasts, stoppers, and the semi-fast that has to cross between them.
#
# Six patterns on a four-track railway, four of each an hour. Five of them never
# leave the line they start on. The sixth is the interesting one:
#
#   X1-X4   Alpha (slow) - Beta (slow) - cross to the fast line - Gamma (fast)
#
# It calls at Beta, which has platforms on the slow lines only, and then has to
# get onto the fast line to be any use. It does that at XO_UP, a crossover at
# km 17, and to do it it needs the fast line to be free at that moment.
#
# So the up fast has a flat junction in the middle of it, in everything but name.
# A crossover is exactly that: a facing point on one line, a trailing point on
# the other, and a train sitting across both while it goes over. The express
# behind it gets checked, and the semi-fast waits if it is refused - the same
# argument as the junction scenario, on plain line, which is why four-track
# railways with heavy semi-fast traffic end up with burrowing junctions.
#
#   python run.py scenarios/fourtrack --check
#   python run.py scenarios/fourtrack --headless --events | grep -E "XO_UP|route_refused"

stock:
  - id: EXPRESS
    name: Express
    length_m: 240
    max_speed_kmh: 160
    max_accel: 0.8
    service_brake: 0.7
    emergency_brake: 1.2
    etcs_level: l2
    tims: true

  - id: STOPPER
    name: Suburban EMU
    length_m: 160
    max_speed_kmh: 120
    max_accel: 1.0
    service_brake: 0.8
    emergency_brake: 1.2
    etcs_level: l2
    tims: true

services:
'''

path = os.path.join(HERE, "timetable.yaml")
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(HEADER + emit() + "\n")
print("wrote", path)
