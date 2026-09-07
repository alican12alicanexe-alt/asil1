"""Does paying a train to close up actually assemble a convoy?

    python scenarios/ring/_sweep_convoy.py [headway_s] [uncoupled_kmh]

WHY THIS EXISTS

Everything else on this circuit keeps returning the same finding, and it is a
negative one: virtual coupling lets trains run closer, and nothing in it makes
them GET closer. Closing up is a speed manoeuvre. On a fleet of identical
trains all sitting on line speed there is no speed difference to close with, so
over a 30 km leg with no station not one tick had two trains within 200 m, and
the seven seconds virtual coupling buys at a platform is the whole of it.

The one run that DID assemble a convoy needed a slow leader - a train class
capped below line speed - and there the gap fell to 163 m against moving
block's 301 m, 46 % rather than 9 %. That is where the concept pays, and it
needs a speed difference to exist.

So: manufacture one, with an operating rule instead of a second train class.

THE RULE

  Every train is held to 70 km/h. A train that is within its own braking
  distance plus 50 m of the train in front is COUPLED, and a coupled train is
  released to line speed.

The follower is paid, in line speed, for closing up. Nothing about the physics
changed - this is a rule somebody would write, and it lives in
VirtualCoupling.uncoupled_speed_kmh as a setting rather than as a claim.

WHAT IS ACTUALLY BEING ASKED

Not "is virtual coupling faster" - it cannot be, because a convoy runs at the
speed of the train leading it and the train leading it has nothing to couple
to, so it stays at 70 and sets the pace for everyone behind. What the incentive
can change is DENSITY: whether trains that would have run 700 m apart end up
running 200 m apart, and whether the flight as a whole gains more from packing
than it loses from the cap.

Three runs, same flight, same interval, same trains:

  line speed      plain virtual coupling. Nobody capped, nobody paid. The
                  baseline every other number here is quoted against.
  capped          the fleet held to 70 km/h with no way to earn line speed.
                  What the cap costs on its own, so the incentive is not
                  credited with the cap's effect or charged for it.
  incentive       the rule above.

WHAT CAME BACK

Twelve non-stop laps at 60 s, all under virtual coupling.

  run             journey   released    median gap   when released
  ---------------------------------------------------------------
  line speed      3457.0 s      0.0 %      1053 m         -
  capped 70       3670.0 s      0.0 %       997 m         -
  + 50 m margin   3665.0 s      0.0 %       999 m         -
  + 200 m         3665.0 s      0.0 %       999 m         -
  + 400 m         3665.0 s      0.0 %       999 m         -
  + 600 m         3661.5 s      3.0 %       982 m       694 m
  + 800 m         3637.0 s     49.6 %       954 m       192 m
  + 1000 m        3638.5 s     57.9 %       757 m       188 m
  + 1500 m        3507.7 s    100.0 %       967 m       967 m

THE RULE AS FIRST WRITTEN NEVER FIRES. Braking distance plus 50 m is about
240 m at 70 km/h, and at any interval this railway is actually worked at the
trains are a kilometre apart. An incentive that requires proximity cannot
create proximity - and that is the shape of the idea rather than a bad choice
of number, which is why every radius up to 400 m returns the capped run to
three decimal places.

WIDEN IT FAR ENOUGH AND IT STOPS MEANING ANYTHING. At 1500 m every train is
released every tick and the median gap when released is 967 m: what the rule
has become is "no cap" with extra steps, and the journey time gives it away.

BETWEEN THOSE TWO IS A NARROW BAND WHERE IT WORKS. At 800 m the incentive
fires half the time and the trains it fires for close to 192 m - a real
convoy, five times denser than the 1053 m plain virtual coupling leaves them
at. It costs 180 s a journey, 5 %.

So the mechanism is real and the trade is bad. It assembles convoys, which
nothing else here managed without a slow train class, and charges every train
on the railway 5 % of its journey - including the ones at the front, which can
never earn the release because there is nobody in front of them to earn it
from. A convoy runs at the speed of the train leading it, the train leading it
is uncoupled by definition, so the convoy runs at the cap. The incentive can
pack a queue; it cannot make one go faster.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_express as express     # rebinds ring.LAP  (must come first)
import _generate_timetable as ring

ring.flight_spec = express.express_spec

import _sweep_headway as sweep          # noqa: E402 - after the rebind
from trainsim.analysis.kpi import measure
from trainsim.core.train import nearest_ahead
from trainsim.core.units import braking_distance, ms_to_kmh
from trainsim.scenario.loader import build_timetable

#: The interval to run all three at. One common interval, not each at its own
#: boundary: a denser run charged for its own extra traffic is not a comparison.
#: 60 s is comfortably above the 32 s virtual coupling holds here, so nothing in
#: the table is a queue.
HEADWAY_S = 60

#: The cap, and the clearance beyond a train's own braking distance that still
#: earns line speed.
UNCOUPLED_KMH = 70
COUPLING_MARGIN_M = 50.0

#: The catch-up radii to try. 50 m is the rule as first written - close enough
#: to be following the train in front rather than the line - and the reason the
#: list does not stop there is what that run came back with.
MARGINS = (50.0, 200.0, 400.0, 600.0, 800.0, 1000.0, 1500.0)

SYSTEM = "virtual_coupling"


def gap_of(train, sim):
    """Metres from this train's front to the rear of the one in front."""
    ahead = nearest_ahead(train, sim.trains.values())
    return None if ahead is None else ahead[0] - train.chainage_m


def run(headway_s, max_speed_kmh=None, **options):
    """One run of the flight, with its convoy behaviour traced tick by tick."""
    ring.OPTIONS[SYSTEM] = options
    unit = sweep.stock_for(SYSTEM)
    if max_speed_kmh is not None:
        unit["max_speed_kmh"] = max_speed_kmh
    timetable = build_timetable(
        ring.flight_spec(sweep.probe_all(), headway_s, ring.COUNT, stock=unit),
        ring.INFRA)
    sim = ring.simulation(timetable,
                          duration_s=headway_s * ring.COUNT + sweep.TAIL_S,
                          system=SYSTEM)

    trace = {"ticks": 0, "released": 0, "all_gaps": [], "close_gaps": [],
             "speeds": []}
    step = sim.step

    def stepped():
        # measure() drives the run itself, so the trace hangs off step() rather
        # than off a loop of its own - one run, both sets of numbers.
        step()
        for train in sim.trains.values():
            if train.state != "running":
                continue
            gap = gap_of(train, sim)
            if gap is None:
                continue
            trace["ticks"] += 1
            trace["speeds"].append(train.speed_ms)
            trace["all_gaps"].append(gap)
            reach = braking_distance(train.speed_ms,
                                     train.stock.service_brake)
            if gap <= reach + COUPLING_MARGIN_M:
                trace["released"] += 1
                trace["close_gaps"].append(gap)

    sim.step = stepped
    return measure(sim), trace


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else None


def report(label, metrics, trace):
    """One row.

    No restrained column and no delay column, and both are deliberate. A speed
    ceiling is charged to the signalling every tick it applies, so a capped run
    reports itself restrained for its whole journey and the number stops
    meaning what it means everywhere else here. And every booked time in this
    flight is what a service achieves UNCAPPED, so a capped run is late by
    construction, against a plan it was never able to keep. Journey time is the
    honest measure of what the rule costs, and the gaps of what it buys.
    """
    ticks = trace["ticks"]
    close = median(trace["close_gaps"])
    print("  %-13s %8.1f s %8.1f %%   %7.0f m   %s   %5.1f km/h"
          % (label, metrics.mean_journey_s,
             100.0 * trace["released"] / ticks if ticks else 0.0,
             median(trace["all_gaps"]) or 0.0,
             "%7.0f m" % close if close is not None else "      - ",
             ms_to_kmh(sum(trace["speeds"]) / len(trace["speeds"]))
             if trace["speeds"] else 0.0))


HEAD = ("  run             journey   released    median gap   when released  "
        "mean speed")


def main(headway_s=HEADWAY_S, uncoupled_kmh=UNCOUPLED_KMH):
    print("%d non-stop laps of the circuit at %d s, under %s\n"
          % (ring.COUNT, headway_s, SYSTEM))
    print(HEAD)
    print("  " + "-" * 74)
    report("line speed", *run(headway_s))
    report("capped %d" % uncoupled_kmh,
           *run(headway_s, max_speed_kmh=uncoupled_kmh))
    print()
    print("  the incentive, over the catch-up radius it is given:")
    print("  " + "-" * 74)
    for margin in MARGINS:
        global COUPLING_MARGIN_M
        COUPLING_MARGIN_M = margin
        report("+ %4.0f m" % margin,
               *run(headway_s, uncoupled_speed_kmh=uncoupled_kmh,
                    coupling_margin_m=margin))
    print()
    print("  released       share of train-ticks running at line speed "
          "rather than the cap")
    print("  median gap     metres to the train in front, every tick - "
          "the density")
    print("  when released  the same, over the ticks the incentive paid for")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else HEADWAY_S,
         int(sys.argv[2]) if len(sys.argv) > 2 else UNCOUPLED_KMH)
