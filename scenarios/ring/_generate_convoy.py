"""Regenerate scenarios/ring/timetable-convoy.yaml - the non-stop flight,
booked at the speed the convoy rule holds a train to.

    python scenarios/ring/_generate_convoy.py [headway_s] [name]
    python scenarios/ring/_generate_convoy.py --stopping

WHICH LAP

Non-stop by default, and ``--stopping`` for the circuit's own twenty-two call
lap - eleven stations out on the up line, the same eleven back on the down
line, thirty seconds at each. Same rule, same fitment, same booking at the cap;
the only difference is whether the trains stop.

Both are worth having, and they answer different halves of the question. The
non-stop flight is the mechanism with nothing in the way: what the incentive
does to trains that are only ever limited by each other. The stopping flight is
the mechanism where this railway actually binds, which is a platform road - and
that is where the incentive is worth six seconds of interval rather than
eleven, because packing trains closer does not shorten a platform occupancy.

A stopping lap also feeds the incentive on its own. A train standing thirty
seconds is a train the one behind closes on for free, so the speed difference
the rule has to manufacture on the open line is handed to it at every station.

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
from trainsim.scenario.loader import read_data_file

import _generate_timetable as ring
from _generate_timetable import COUNT, STOCK, probe_all

#: Twenty-two calls a lap rather than none. Read before the import below,
#: because importing _generate_express rebinds ring.LAP to the non-stop lap and
#: there is no putting it back - probe(), calls() and flight_spec() all read
#: LAP when they are called. Same arrangement _sweep_convoy.py uses.
STOPPING = "--stopping" in sys.argv
if STOPPING:
    sys.argv.remove("--stopping")
    render, LAP_WORDS = ring.render, "twenty-two call"
else:
    import _generate_express as express
    render, LAP_WORDS = express.render, "non-stop"

#: The scenario the flight is written for. Read rather than duplicated: the
#: cap has to be the one the rule actually applies, and when it was a constant
#: here as well the two drifted apart within a day - a flight booked at 65 km/h
#: under a rule that allows 70, which every train then beat by three minutes.
#: The lead train gives it away. Nothing is ever in front of it, so its journey
#: is the same however the flight is booked, and a fixed offset on the FIRST
#: service is a booking that does not match the rule rather than a railway
#: under pressure.
SCENARIO = "scenario-convoy.yaml"


def cap_kmh(scenario=SCENARIO):
    """The speed the rule holds an uncoupled train to, from the scenario."""
    signalling = read_data_file(os.path.join(HERE, scenario))["signalling"]
    cap = signalling.get("uncoupled_speed_kmh")
    if cap is None:
        raise SystemExit(
            "%s sets no uncoupled_speed_kmh, so there is no cap to book at - "
            "this generator writes the flight for the coupling rule, and "
            "without the rule _generate_express.py already writes it" % scenario)
    return float(cap)

#: The system this flight is written for. Only used to fit the stock - the
#: scenario names it again, and has to name the same one.
SYSTEM = "virtual_coupling"


def fitted_stock():
    """STOCK, equipped for SYSTEM. Same unit otherwise: same length, same
    power, same brake, so a convoy run and a plain one differ by the radio."""
    unit = dict(STOCK)
    unit["etcs_level"], unit["tims"], unit["v2v"] = fitment_for(SYSTEM)
    return unit

LAP_TEXT = {
    "non-stop": """# A lap is two calls: away from Akyurt 1 on the up line, round HS_EAST, back
# down the down line and into Akyurt 1 again, running through the twenty-one
# stations in between, with the four faces at Akyurt 1 used in turn.""",
    "twenty-two call": """# A lap is twenty-two calls: eleven stations out on the up line, round HS_EAST,
# the same eleven back on the down line, round HS_WEST, and into Akyurt 1 again
# facing the way it set off. Thirty seconds at every one - and a train standing
# thirty seconds is a train the one behind closes on for free, which is the
# speed difference the rule has to manufacture, handed to it at every station.""",
}

CONVOY_HEADER = '''# ring convoy timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_convoy.py %(headway)d%(flag)s
#
# %(count)d %(lap)s laps of the circuit, booked %(headway)d seconds apart, all of
# them the same unit.
#
%(lap_text)s
#
# BOOKED AT THE CAP, NOT AT LINE SPEED. scenario-convoy.yaml holds every train
# to 70 km/h unless it is closing up on the one in front, and a service alone on
# the railway never closes up on anything - so 70 km/h is the fastest an
# undisturbed lap can be run and these are the times it takes. The stock below
# still says 90: the trains must be able to take the release when they earn it.
#
# The cap is read from %(scenario)s rather than set here, so the plan and the
# rule cannot drift apart. If the first service in this flight finishes with a
# fixed offset - the same delay whatever the interval - the two have drifted
# anyway: nothing is ever in front of the lead train, so its journey does not
# depend on the flight and a constant offset on it is a booking fault.
# Run this timetable under any other scenario and it has 20 km/h of slack in it.

'''


if __name__ == "__main__":
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    name = sys.argv[2] if len(sys.argv) > 2 else (
        "timetable-convoy-stopping" if STOPPING else "timetable-convoy")
    cap = cap_kmh()

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
    print("a %s lap alone: %d min %02d s at %d km/h, %d min %02d s at %d"
          % (LAP_WORDS, capped // 60, capped % 60, cap,
             uncapped // 60, uncapped % 60, line_speed))
    print("the cap is %s's uncoupled_speed_kmh, so the plan matches the rule."
          % SCENARIO)
    print("the flight is booked at the first and may run at the second.")

    unit = fitted_stock()
    assert unit["v2v"] and unit["tims"], (
        "%s does not ask for the train-to-train link - this generator writes a "
        "flight for a system that does" % SYSTEM)

    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway, header=CONVOY_HEADER % {
            "headway": headway, "count": COUNT, "lap": LAP_WORDS,
            "lap_text": LAP_TEXT[LAP_WORDS], "scenario": SCENARIO,
            "flag": " --stopping" if STOPPING else ""}, stock=unit))
    print("wrote %s - %d %s services at %d s"
          % (path, COUNT, LAP_WORDS, headway))
