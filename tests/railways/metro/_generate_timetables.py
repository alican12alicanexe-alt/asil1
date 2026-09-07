"""Regenerate the three metro timetables in this directory.

These timetables are derived data, not hand-written. Every service is booked on
the run times a *single unimpeded train* achieves on this infrastructure -
measured by running one, below - offset by one headway. That is what makes the
plan conflict-free by construction, so any delay the comparison reports is the
signalling failing to deliver a workable plan, rather than a plan that was never
workable in the first place.

Change a dwell, a station chainage or the rolling stock and the booked times are
stale. Re-run this from anywhere:

    python scenarios/metro/_generate_timetables.py

Stdlib only, like everything else here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from trainsim.scenario.builder import build_infrastructure
from trainsim.scenario.loader import read_data_file, build_timetable
from trainsim.core.simulation import SimConfig, Simulation
from trainsim.core.driver import Driver, DriverConfig
from trainsim.core.dispatcher import TimetableDispatcher
from trainsim.core.interlocking import Interlocking
from trainsim.core import signalling as reg
from trainsim.core.units import format_clock

UP = ["HARBOUR", "MARKET", "CENTRAL", "UNIVERSITY", "PARKSIDE", "AIRPORT"]
DN = list(reversed(UP))
BASE = 7 * 3600
DWELL, TERM = 30, 20
COUNT = 12
infra = build_infrastructure(
    read_data_file(os.path.join(HERE, "infrastructure.yaml")))
STOCK = {"id": "METRO", "name": "Metro unit", "length_m": 120, "max_speed_kmh": 90,
         "max_accel": 1.1, "service_brake": 1.1, "emergency_brake": 1.4,
         "etcs_level": "l3", "tims": True}


def probe(order, face):
    calls = [{"station": s, "platform": "%s_%s" % (s, face),
              "dwell_s": TERM if i in (0, len(order) - 1) else DWELL}
             for i, s in enumerate(order)]
    calls[0]["departure"] = "07:00:00"
    tt = build_timetable({"stock": [STOCK],
                          "services": [{"id": "P", "stock": "METRO",
                                        "departure": "07:00:00", "ready_lead_s": 30,
                                        "calls": calls}]}, infra)
    sim = Simulation(
        network=infra.network, blocks=infra.blocks, signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=reg.create("etcs_moving_block"),
        dispatcher=TimetableDispatcher(tt),
        driver=Driver(DriverConfig(reaction_time_s=1.5, safety_margin_m=20.0)),
        config=SimConfig(dt=1.0, start_time_s=BASE - 120, duration_s=2400),
        interlocking=Interlocking(network=infra.network, blocks=infra.blocks,
                                  signals=infra.signals, points=infra.points,
                                  routes=infra.routes))
    while not sim.finished:
        sim.step()
    t = sim.trains["P"]
    return {s: (t.actual_arrivals.get(s), t.actual_departures.get(s)) for s in order}


TIMES = {"1": probe(UP, "1"), "2": probe(DN, "2")}


def service(sid, order, face, shift, stock_id="METRO"):
    lines = ["  - id: %s" % sid,
             "    stock: %s" % stock_id,
             '    departure: "%s"' % format_clock(BASE + shift),
             "    ready_lead_s: 30",
             "    calls:"]
    for i, s in enumerate(order):
        arr, dep = TIMES[face][s]
        bits = ["station: %s" % s, "platform: %s_%s" % (s, face)]
        if arr is not None:
            bits.append('arrival: "%s"' % format_clock(round(arr) + shift))
        if dep is not None:
            bits.append('departure: "%s"' % format_clock(round(dep) + shift))
        bits.append("dwell_s: %d" % (TERM if i in (0, len(order) - 1) else DWELL))
        lines.append("      - {%s}" % ", ".join(bits))
    return "\n".join(lines)


def flight(headway, legacy=()):
    out = ["# Up: Harbour -> Airport, %d trains at a %d-second headway."
           % (COUNT, headway)]
    for n in range(COUNT):
        sid = "U%02d" % (n + 1)
        out.append(service(sid, UP, "1", n * headway,
                           "METRO_LEGACY" if sid in legacy else "METRO"))
    out.append("# Down: Airport -> Harbour, the same flight offset by half a headway.")
    for n in range(COUNT):
        sid = "D%02d" % (n + 1)
        out.append(service(sid, DN, "2", headway // 2 + n * headway,
                           "METRO_LEGACY" if sid in legacy else "METRO"))
    return "\n".join(out)


FITTED_STOCK = """stock:
  - id: METRO
    name: Metro unit
    length_m: 120
    max_speed_kmh: 90
    max_accel: 1.1
    service_brake: 1.1
    emergency_brake: 1.4
    # Full Level 3 fitment. The unit reports its own position and confirms its
    # own integrity, and it is the integrity report that matters: without it the
    # rear of the train is not trustworthy, so nothing may follow it closely.
    etcs_level: l3
    tims: true
"""

MAIN = """# metro - twelve trains each way at a 75-second headway.
#
# Every service is booked on the run times a single unimpeded train achieves,
# offset by exactly one headway, so the plan is conflict-free by construction and
# any delay that appears is the signalling refusing to deliver it.
#
# 75 seconds is 48 trains an hour, at the optimistic end of what CBTC metros
# actually work to - Paris Line 14 and the Victoria Line sit nearer 85-100 s -
# and it is chosen because it lands between the two systems rather than outside
# both. The open line can carry it under any of them: `--check` reports an
# implied fixed-block headway of 45-63 s. What cannot carry it is the station.
#
#   fixed block    a following train may not enter the section holding a
#                  standing train, so it waits a whole 500-600 m section back
#                  from a train sitting still with its doors open, and then has
#                  to accelerate from there.
#   moving block   the follower closes to braking distance plus 100 m of that
#                  train's rear. At the 10 m/s it is doing on the approach that
#                  is about 145 m, so it is already on the platform ramp when
#                  the train in front pulls out.
#
# Measured, twenty-four services, mean delay against this plan:
#
#     fixed block  +75 s      ETCS L2  +74 s      moving block  0 s
#
# Level 2 saves one second. That is the point of this scenario and it is the
# opposite of corridor3, where Level 2 captured most of the available benefit.
# On a fast main line the cost being removed is sighting and reaction, and radio
# removes it. Here the cost is *granularity* - the block is the unit of
# separation whether the train is told about it by lamp or by radio - and only
# making the granularity finer (Hybrid L3) or abolishing it (moving block) helps.
#
#   python run.py scenarios/metro --compare
#   python run.py scenarios/metro --system fixed_block_3aspect   (watch it bunch)

"""

SIXTY = """# metro at a 60-second headway - past what moving block can deliver either.
#
# The same twelve-train flight each way, booked 60 seconds apart instead of 75.
# Nothing delivers it:
#
#     fixed block  +163 s     ETCS L2  +162 s     moving block  +51 s
#
# This scenario exists so the project cannot be read as claiming that moving
# block removes the limit. It does not; it moves it. What is left is not
# signalling at all:
#
#     station headway  =  dwell  +  the time the follower needs to close up
#                                   and berth  +  the time the leader needs to
#                                   pull clear of the platform
#
# With a 30-second dwell and 1.1 m/s2 of acceleration those terms come to a
# little under 60 seconds on this line, so 60 is inside the noise and the flight
# slowly loses time station by station. The way out is not better signalling. It
# is shorter dwells - platform-edge doors, wider doors, better passenger flow -
# or higher acceleration. That is a real result, and it is why metro capacity
# programmes spend as much on doors as on train control.
#
#   python run.py scenarios/metro/scenario-60.yaml --compare

"""

MIXED = """# metro at 75 seconds with two units that cannot confirm their integrity.
#
# The flight is the one in timetable.yaml. Two services - U06 up and D06 down -
# run METRO_LEGACY: an older unit that reports its position but has no train
# integrity monitoring, which is the ordinary state of a fleet part-way through
# a migration.
#
# Moving block cannot follow such a train closely. If the rear of a train is not
# confirmed, part of it may have been left behind, and the only safe assumption
# is that it still occupies the whole detection section it entered. It therefore
# imposes Level 2 separation on everything behind it.
#
# What that costs is worth reading per train rather than as a mean. Under moving
# block, restrained seconds and delay at Airport:
#
#   U01 - U05    0 s, on time      the legacy unit is not yet in front of them
#   U06          0 s, on time      this *is* the legacy unit, and it runs fine
#   U07         66 s, +13 s        the train immediately behind it
#   U08 - U12   62, 58, 34, 16, 16 s      +10, +7, +4, +4, +4 s
#
# Two things follow, and neither is a signalling conclusion. The unfitted unit
# pays nothing: the whole cost of not fitting it falls on the services behind.
# And the delay does not wash out - it settles at four seconds rather than
# returning to zero, because a plan booked at the achievable headway has no
# slack anywhere to absorb it.
#
# Hybrid Level 3 is not a free rescue here. With its default four sub-sections
# per section - 150 m on this line - it is coarser than a moving-block authority
# on a platform approach and comes out slightly worse, not better. What fixes
# that is sizing the sub-sections against braking distance rather than counting
# them per block; scenario.yaml has the measured figures.
#
#   python run.py scenarios/metro/scenario-mixed.yaml --compare

"""

LEGACY_STOCK = """
  - id: METRO_LEGACY
    name: Metro unit (no integrity monitoring)
    length_m: 120
    max_speed_kmh: 90
    max_accel: 1.1
    service_brake: 1.1
    emergency_brake: 1.4
    # Reports where its front is, cannot confirm the rest of the train is still
    # attached. Identical in every physical respect to METRO - the only
    # difference is what the trackside is allowed to believe about it.
    etcs_level: l2
    tims: false
"""


def write(path, header, stock_block, body):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(header + stock_block + "\nservices:\n" + body + "\n")
    print("wrote", path)


write(os.path.join(HERE, "timetable.yaml"), MAIN, FITTED_STOCK, flight(75))
write(os.path.join(HERE, "timetable-60.yaml"), SIXTY, FITTED_STOCK, flight(60))
write(os.path.join(HERE, "timetable-mixed.yaml"), MIXED,
      FITTED_STOCK + LEGACY_STOCK, flight(75, legacy=("U06", "D06")))
