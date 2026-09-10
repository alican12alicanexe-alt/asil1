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

WHAT CAME BACK - THE STOPPING FLIGHT

``--headway --stopping``. The circuit's own twenty-two-call lap, bisected.

  tightest interval held, nobody more than 1 s late
  -------------------------------------------------
  line speed                69 s     52.2 trains an hour
  capped 70                 68 s     52.9
  incentive + 800           63 s     57.1

  6 s, of which 1 s is the cap and 5 s is the release.   +9.4 % on the hour.

READ THE MIDDLE ROW BEFORE THE BOTTOM ONE. It is the control that says whether
the gain is the rule or just a slower railway, and it very nearly reports the
former: holding the fleet to 70 km/h buys one second by itself. That is small
because most of this circuit is posted below 70 anyway and there are twenty-two
stops a lap, so the cap barely bites - which is NOT true on the non-stop flight,
where it costs 5 % of every journey and buys four seconds.

An earlier version of this file scanned a fixed ladder - 150 120 100 90 80 75 71
65 60 55 - and reported 71 / 71 / 65, which is the same answer at one rung's
resolution: 71 meant "71 held, 65 did not", a bracket of (65, 71]. All three
bisected figures sit inside their brackets, and 69 s for line speed is what
_sweep_timestep.py independently refines the same criterion to. Two searches,
one number.

AND THE GAIN IS STILL SMALL: 69 s to 63 s. What a train is waiting for at 69 s
on this circuit is a platform road; packing trains closer does not shorten a
platform occupancy, and an incentive to pack them cannot either.

WHAT THIS DOES NOT ESTABLISH, AND IT IS THE WHOLE OF IT

The incentive row is booked at 70 km/h and may run at 90, so it carries 20 km/h
of recovery slack that neither control has. Some unknown share of those 5 s is
the slack rather than the rule, and this measurement cannot separate them.

On the NON-STOP flight the equivalent control has been run, on journey time,
which no booking can flatter:

  interval     line speed     capped 70   + the release
      70 s        3457 s        3670 s        3653 s
      50 s        3457 s        3670 s        3520 s
      30 s        3457 s        3670 s        3593 s
      20 s        3474 s        3680 s        3648 s

Plain virtual coupling wins at every interval. The release recovers 150 s of the
213 s the cap costs, and never catches up. Note also that line speed is FLAT
from 70 s down to 30 s: twelve trains half a minute apart, none of them
obstructing another, so there was no congestion there for the rule to relieve.
The same journey-time control has not been run on the stopping flight, and until
it has, the 5 s above is an upper bound rather than a result.

WHAT CAME BACK - THE INTERVAL EACH CAN BE BOOKED AT

``--headway``. Worst arrival in seconds, negative being early; each row booked
against the unimpeded times its OWN fleet achieves, or a capped run would be
late against a plan it was never able to keep.

  interval             60   50   42   36   32   28   24   20   17   14
  ------------------------------------------------------------------
  line speed           -1   -1   -1   -1   -1   -1    2   26   56   88
  capped 70            -1   -1   -1   -1   -1   -1   -1   14   43   76
  incentive + 800      -6   -6   -6   -6   -6   -6   -6   -6   -5   28
  incentive + 1000     -6   -6   -6   -6   -6   -6   -6   -6   -5   28

  tightest interval held        <= 1 s    <= 3 s   <= 30 s
  -------------------------------------------------------
  line speed                      28 s      24 s      20 s
  capped 70                       24 s      24 s      20 s
  incentive + 800                 17 s      17 s      14 s
  incentive + 1000                17 s      17 s      14 s

The incentive holds 17 s where plain virtual coupling breaks at 24 s: 212
trains an hour against 129. That is the capacity case for the rule, and it is
much stronger than the 60 s snapshot below suggests, because at 60 s the trains
are a kilometre apart and the rule is barely firing.

READ IT WITH THE CAVEAT. Every row is booked against its own probe, and a probe
train has nothing in front of it - so under the incentive it is uncoupled for
its whole lap and its plan is a 70 km/h plan, while its coupled trains run at
80. That is why the row sits 6 s early everywhere. Some of the 17 s is real
density and some is recovery margin against a slower plan, and this table does
not separate them.

Note also that 30 s is worth four to eight seconds of capacity that is not
there. Nothing here should be quoted off it.

WHAT CAME BACK - WHAT IT DOES AT ONE INTERVAL

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

#: Which flight to run this on, decided at import time because that is when the
#: rebinding below has to happen. The default is the NON-STOP flight, where the
#: binding constraint is the distance between two trains and an incentive to
#: close that distance has something to work on. ``--stopping`` runs the
#: circuit's own twenty-two-call lap instead, where virtual coupling holds 69 s
#: and what it is queueing for is a platform road.
STOPPING = "--stopping" in sys.argv
if STOPPING:
    # Taken out of argv, not just read from it. Everything below positions its
    # arguments - headway first, cap second - and a flag left in the list is
    # read as a headway: ``--stopping`` on its own used to die on
    # int('--stopping') rather than run the stopping flight. Same removal
    # _generate_convoy.py does, for the same reason.
    sys.argv.remove("--stopping")

#: What the flight is, for the line every table prints above itself. A sweep
#: that says it is measuring a non-stop lap when it is measuring twenty-two
#: calls is a sweep nobody can read.
FLIGHT = ("laps calling at all eleven stations twice" if STOPPING
          else "non-stop laps")

import _generate_timetable as ring      # noqa: E402

if not STOPPING:
    import _generate_express as express  # rebinds ring.LAP  (must come first)
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
HEADWAY_S = 150 if STOPPING else 60

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


_PROBES = {}


def probe(cap_kmh=None):
    """Unimpeded lap times for a fleet that tops out at ``cap_kmh``.

    The booked times a run is judged against have to be times the fleet in that
    run can actually keep, or every capped train is late by construction and
    the boundary being looked for is the cap rather than the interval. A train
    with the railway to itself has nothing in front of it, so under the
    incentive it is uncoupled for its whole lap and 70 km/h IS its unimpeded
    speed - which is what makes this the right plan to book the incentive
    against too.

    Cached: the probe is a full lap and the boundary search asks for it dozens
    of times.
    """
    if cap_kmh in _PROBES:
        return _PROBES[cap_kmh]
    was = ring.STOCK["max_speed_kmh"]
    if cap_kmh is not None:
        ring.STOCK["max_speed_kmh"] = cap_kmh
    try:
        _PROBES[cap_kmh] = sweep.probe_all()
    finally:
        ring.STOCK["max_speed_kmh"] = was
    return _PROBES[cap_kmh]


def run(headway_s, max_speed_kmh=None, times=None, **options):
    """One run of the flight, with its convoy behaviour traced tick by tick."""
    ring.OPTIONS[SYSTEM] = options
    if times is None:
        times = probe()
    unit = sweep.stock_for(SYSTEM)
    if max_speed_kmh is not None:
        unit["max_speed_kmh"] = max_speed_kmh
    timetable = build_timetable(
        ring.flight_spec(times, headway_s, ring.COUNT, stock=unit),
        ring.INFRA)
    # Long enough for the last train away to finish, and no longer. The sweeps
    # here carry a flat 7200 s tail, which is over an hour of empty railway on
    # a flight whose lap is under an hour - and every second of it is stepped.
    # The probe already knows the lap, so the tail can be the lap plus slack
    # for the queue, which takes about a third off every run in this file.
    tail_s = (times[0][-1][0] - times[0][0][1]) * 1.25 + 600
    sim = ring.simulation(timetable,
                          duration_s=headway_s * ring.COUNT + tail_s,
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
    print("%d %s of the circuit at %d s, under %s\n"
          % (ring.COUNT, FLIGHT, headway_s, SYSTEM))
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


#: How late the worst arrival may be and the flight still counts as workable.
#: 1 s rather than the 30 s _sweep_headway.keeps_time allows: 30 s of lateness
#: on a 20 s interval is more than a headway, which is not a railway keeping
#: time but one about to stop doing so, and it was worth four to eight seconds
#: of capacity that is not there when both were measured.
#:
#: NO ZERO-DELAY THRESHOLD, deliberately. Nothing here is entitled to assume a
#: flight arrives dead on its booked time, and this railway could not
#: demonstrate it if it were: probe() in _generate_timetable.py reads the clock
#: after Simulation.step() has already advanced it, so on some flights an
#: undisturbed service reports -1 s. A 0 s threshold would be measuring that
#: artefact. 1 s is the tightest figure this model can honestly carry, and it
#: answered the same as 0 s in every cell where both were tried.
TOLERANCE_S = 1.0

#: Where the search starts looking. Only a starting guess - it brackets itself
#: from here - so being wrong costs one or two runs, not an answer.
SEED_S = 100

#: Bounds on the bracket, so a configuration that holds everything or nothing
#: stops rather than doubling forever.
FLOOR_S, CEILING_S = 8, 600


def boundary(label, cap_kmh, seed=SEED_S, **run_kwargs):
    """The tightest interval this configuration still keeps time at.

    Brackets itself and then bisects, rather than scanning a list somebody had
    to guess right in advance. From a seed it halves while the interval still
    holds and doubles while it does not, which finds a bracket in one or two
    runs, and then bisects to the second. About nine runs against a ten-rung
    scan's ten - and the answer is exact rather than the nearest rung.

    Lateness rather than all-green, and that is forced. All-green asks whether
    any train was held down by the signalling, and a speed ceiling IS the
    signalling holding a train down: a capped run reports itself restrained for
    its whole journey whether or not another train is within a kilometre.
    Lateness stays clean, PROVIDED each configuration is booked against its own
    unimpeded probe, which is what ``cap_kmh`` is for.
    """
    times = probe(cap_kmh)
    seen = {}

    def holds(headway_s):
        if headway_s not in seen:
            metrics = run(headway_s, times=times, **run_kwargs)[0]
            worst = max(metrics.delays.values()) if metrics.delays else 0.0
            seen[headway_s] = (metrics.completed == metrics.services
                               and worst <= TOLERANCE_S)
        return seen[headway_s]

    if holds(seed):
        hi, lo = seed, max(FLOOR_S, seed // 2)
        while lo > FLOOR_S and holds(lo):
            hi, lo = lo, max(FLOOR_S, lo // 2)
        if lo == FLOOR_S and holds(lo):
            print("  %-16s holds %d s, the floor of the search" % (label, lo))
            return lo
    else:
        lo, hi = seed, min(CEILING_S, seed * 2)
        while hi < CEILING_S and not holds(hi):
            lo, hi = hi, min(CEILING_S, hi * 2)
        if not holds(hi):
            print("  %-16s does not keep time even at %d s" % (label, hi))
            return None

    while hi - lo > 1:
        mid = (lo + hi) // 2
        if holds(mid):
            hi = mid
        else:
            lo = mid
    print("  %-16s %4d s   (%5.1f trains an hour)   %2d runs"
          % (label, hi, 3600.0 / hi, len(seen)))
    return hi


def headways(uncoupled_kmh=UNCOUPLED_KMH):
    """What each configuration can be booked at, not what it does at one
    interval. Each answer seeds the next, because the configurations are
    neighbours and a good seed is one or two runs saved."""
    print("tightest interval held with nobody more than %.0f s late" % TOLERANCE_S)
    print("%d %s, all under %s, each booked at times its own fleet achieves "
          "alone.\n" % (ring.COUNT, FLIGHT, SYSTEM))
    seed = boundary("line speed", None) or SEED_S
    seed = boundary("capped %d" % uncoupled_kmh, uncoupled_kmh, seed=seed,
                    max_speed_kmh=uncoupled_kmh) or seed
    # 800 m only. On the non-stop flight 1000 m answered identically in every
    # cell, so a second radius is another search for a repeated row.
    global COUPLING_MARGIN_M
    COUPLING_MARGIN_M = 800.0
    boundary("incentive + 800", uncoupled_kmh, seed=seed,
             uncoupled_speed_kmh=uncoupled_kmh, coupling_margin_m=800.0)


if __name__ == "__main__":
    if "--headway" in sys.argv:
        sys.argv.remove("--headway")
        headways(int(sys.argv[1]) if len(sys.argv) > 1 else UNCOUPLED_KMH)
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else HEADWAY_S,
             int(sys.argv[2]) if len(sys.argv) > 2 else UNCOUPLED_KMH)
