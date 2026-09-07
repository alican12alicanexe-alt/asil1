"""Regenerate scenarios/ring/timetable-convoy.yaml - the non-stop flight,
booked at the speed the convoy rule holds a train to.

    python scenarios/ring/_generate_convoy.py [headway_s] [name] [cap_kmh]

WHY THIS IS NOT JUST _generate_express.py

It is the same flight - same lap, same faces in turn, same unit - and for a
while scenario-convoy.yaml used a timetable straight out of that generator.
That was wrong, in a way worth spelling out because it decides what the whole
convoy measurement means.

The rule in scenario-convoy.yaml holds every train to 70 km/h and releases it
to line speed only while it is closing up on the train in front. A service with
the railway to itself has nobody in front of it, so it is uncoupled for its
entire lap and 70 km/h IS its unimpeded speed. Book that service against times
achieved at 90 and it is late before it leaves - not because the interval is
tight, not because the signalling held it, but because the plan asks for a lap
its own operating rule forbids. Every delay in the run is then measuring the
cap, and the interval the flight can actually keep is unfindable underneath it.

So: PROBE UNDER THE CAP, RENDER WITHOUT IT.

  - the probe lap is timed with the fleet topped out at ``cap_kmh``, so the
    booked times are times the rule permits;
  - the stock block written out keeps line speed, because the trains must still
    be CAPABLE of the release. The cap is the signalling's to apply, not the
    unit's - take uncoupled_speed_kmh out of the scenario and the same
    timetable runs as plain virtual coupling with slack in it.

AND IT WRITES A FITTED FLEET, which is the other reason this generator has to
exist. Every other timetable on this circuit is written for a system that asks
nothing of the train, so stock_yaml leaves etcs_level none and tims false.
Virtual coupling asks for both, plus the train-to-train link: run this scenario
on an unfitted fleet and every train falls back to block granularity, the run
is fixed block wearing another name, and no convoy can form at all - the loader
says so in a warning that is easy to scroll past. The fitment comes from
signalling.fitment_for, so it is whatever the system declares it needs rather
than three flags copied out by hand.

That slack is real and it is the point. This is the only flight on the circuit
whose booking is easier than what its trains can do, which is what gives a
train held up behind another something to recover with. It is also the one
asymmetry in the convoy comparison, so it is stated here rather than left for
somebody to find in the numbers.

Stdlib only, like everything else here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from trainsim.core.signalling import fitment_for

import _generate_timetable as ring
from _generate_timetable import COUNT, STOCK, probe_all
# Importing this rebinds ring.LAP to the non-stop lap. The convoy flight is the
# express flight; only the booking differs.
import _generate_express as express

#: The speed the rule holds an uncoupled train to. Has to match
#: signalling.uncoupled_speed_kmh in scenario-convoy.yaml - book against one
#: figure and run against another and the flight is late by the difference.
CAP_KMH = 70

#: The system this flight is written for. Only used to fit the stock - the
#: scenario names it again, and has to name the same one.
SYSTEM = "virtual_coupling"


def fitted_stock():
    """STOCK, equipped for SYSTEM. Same unit otherwise: same length, same
    power, same brake, so a convoy run and a plain one differ by the radio."""
    unit = dict(STOCK)
    unit["etcs_level"], unit["tims"], unit["v2v"] = fitment_for(SYSTEM)
    return unit

CONVOY_HEADER = '''# ring convoy timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_convoy.py %d
#
# %d non-stop laps of the circuit, booked %d seconds apart, all of them the same
# unit. A lap is two calls: away from Akyurt 1 on the up line, round HS_EAST,
# back down the down line and into Akyurt 1 again, running through the twenty-one
# stations in between, with the four faces at Akyurt 1 used in turn.
#
# BOOKED AT THE CAP, NOT AT LINE SPEED. scenario-convoy.yaml holds every train
# to 70 km/h unless it is closing up on the one in front, and a service alone on
# the railway never closes up on anything - so 70 km/h is the fastest an
# undisturbed lap can be run and these are the times it takes. The stock below
# still says 90: the trains must be able to take the release when they earn it.
# Run this timetable under any other scenario and it has 20 km/h of slack in it.

'''


if __name__ == "__main__":
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    name = sys.argv[2] if len(sys.argv) > 2 else "timetable-convoy"
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else CAP_KMH

    line_speed = ring.STOCK["max_speed_kmh"]
    free = probe_all()
    ring.STOCK["max_speed_kmh"] = cap
    try:
        times = probe_all()
    finally:
        ring.STOCK["max_speed_kmh"] = line_speed

    def lap_of(probe):
        return probe[0][-1][0] - probe[0][0][1]

    capped, uncapped = lap_of(times), lap_of(free)
    assert capped > uncapped, (
        "a lap at %d km/h came back no slower than one at %d - the cap did not "
        "reach the probe" % (cap, line_speed))
    print("a non-stop lap alone: %d min %02d s at %d km/h, %d min %02d s at %d"
          % (capped // 60, capped % 60, cap,
             uncapped // 60, uncapped % 60, line_speed))
    print("the flight is booked at the first and may run at the second.")

    unit = fitted_stock()
    assert unit["v2v"] and unit["tims"], (
        "%s does not ask for the train-to-train link - this generator writes a "
        "flight for a system that does" % SYSTEM)

    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(express.render(times, headway, header=CONVOY_HEADER,
                                    stock=unit))
    print("wrote %s - %d services at %d s" % (path, COUNT, headway))
