"""Is the seven seconds an artefact of the one-second timestep?

Everything this scenario reports is measured at ``dt = 1.0 s``, which at
80 km/h is 22 m of position granularity and one sample per second of the
constraint governing each train. Both of those bound how finely a boundary can
be found, and a boundary found on a knife edge - "nothing was ever checked, and
nobody was more than a second late" - is exactly the kind of number a coarse
clock can flatter.

So this runs the whole thing again at half the timestep. The lap is re-probed at
each one, because the timetable is built from those times; the alone-baseline is
recomputed; and the three boundaries are found by the same descent and bisection
``_sweep_headway`` uses. Only ``dt`` changes.

    python scenarios/ring/_sweep_timestep.py

It takes about a quarter of an hour and it is not run often. It is here because
the answer is quoted, and a number nobody can reproduce is a number nobody
should believe.

WHAT IT FOUND
=============

::

    criterion         dt = 1.0 s              dt = 0.5 s
                    MB    VC   gap          MB    VC   gap
    all-green       78    71     7          80    73     7
    zero-delay      77    69     8          77    69     8
    keeps-time      73    65     8          75    65    10

**The gap is not an artefact.** The all-green difference is seven seconds at
both timesteps, and the zero-delay difference is eight at both. Where a boundary
moves, both systems move together.

**The boundaries themselves are.** All-green costs two seconds more at the finer
timestep under both systems, and keeps-time two seconds more under moving block.
The coarse clock flatters the railway, because a check shorter than a tick is
not sampled and a train's position is only known to 22 m. So 78 s and 71 s are
optimistic by about two seconds each - which is worth saying out loud rather
than being asked.

**Zero-delay is the least robust of the three by construction**, even though it
did not move. At ``dt = 0.5`` an untroubled run reports a worst arrival of 0.5 s
rather than 0.0 - half a tick, from the arrival snapping to the stopping mark -
so ``worst <= 1.0`` admits two ticks of lateness where at ``dt = 1.0`` it admits
one. It landing on the same number at both is partly the threshold's luck.

**And the degradation result gets sharper, not weaker.** Four seconds inside its
own boundary, moving block is 13 s late and virtual coupling is 0.5 s late -
while virtual coupling is the one being *checked* more (1052 s against 742 s).
It absorbs the overload instead of passing it on, at both timesteps.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_timetable as ring                       # noqa: E402
import _sweep_headway as sweep                           # noqa: E402
from trainsim.core.simulation import SimConfig           # noqa: E402

#: The timesteps to compare. Halving is enough: if the answer is stable across a
#: factor of two it is not being decided by the clock, and if it is not stable
#: no further refinement rescues it.
TIMESTEPS = (1.0, 0.5)

SYSTEMS = ("etcs_moving_block", "virtual_coupling")

_real_simulation = ring.simulation
_dt = [TIMESTEPS[0]]


def _at_current_dt(timetable, duration_s=12000, system="fixed_block_3aspect"):
    """The scenario's own simulation, with the timestep overridden."""
    sim = _real_simulation(timetable, duration_s=duration_s, system=system)
    sim.config = SimConfig(dt=_dt[0], start_time_s=sim.config.start_time_s,
                           duration_s=sim.config.duration_s)
    sim.dt = _dt[0]
    return sim


# Both names, because _sweep_headway imported the function rather than the
# module and probe_all() reaches for the one in _generate_timetable.
ring.simulation = sweep.simulation = _at_current_dt

_cache = {}


def run(times, headway, system):
    """A run, remembered: the three criteria overlap almost entirely."""
    key = (_dt[0], system, headway)
    if key not in _cache:
        _cache[key] = sweep.run(times, headway, system)
    return _cache[key]


def worst_of(metrics):
    return max(metrics.delays.values()) if metrics.delays else 0.0


def boundary(times, system, test, start=95, floor=20, step=5):
    """The tightest headway that still passes ``test``, to the second.

    Walk down in fives until it stops passing, then bisect - the same shape as
    :func:`_sweep_headway.refine`, and it makes the same assumption: the railway
    does not un-degrade as the interval tightens.
    """
    headway, best = start, None
    while headway >= floor:
        if test(run(times, headway, system)):
            best = headway
            break
        headway -= step
    if best is None:
        return None

    bad, probe = None, best - step
    while probe >= floor:
        if not test(run(times, probe, system)):
            bad = probe
            break
        best, probe = probe, probe - step
    if bad is None:
        return best

    lo, hi = bad, best
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if test(run(times, mid, system)):
            hi = mid
        else:
            lo = mid
    return hi


def measure(dt):
    """The three boundaries for both systems, at one timestep."""
    _dt[0] = dt
    times = ring.probe_all()
    alone = {
        system: sum(sweep.run(times, sweep.HEADWAYS[0], system, indices=[n]
                              ).total_restrained_s
                    for n in range(sweep.COUNT))
        for system in SYSTEMS
    }
    found = {}
    for system in SYSTEMS:
        for name, test in (
            ("all-green", lambda m, s=system: sweep.is_clean(m, alone[s])),
            ("zero-delay", lambda m: (worst_of(m) <= 1.0
                                      and m.completed == m.services)),
            ("keeps-time", sweep.keeps_time),
        ):
            found[(system, name)] = boundary(times, system, test)
            print("    %-20s %-11s %s"
                  % (system, name, found[(system, name)]), flush=True)
    return found


def main():
    started = time.time()
    print("The ring's headway boundaries, at %s.\n"
          % (" and ".join("dt=%.1f s" % d for d in TIMESTEPS),))
    results = {}
    for dt in TIMESTEPS:
        print("  dt = %.1f s" % dt, flush=True)
        results[dt] = measure(dt)

    print("\n  %-11s%s" % ("", "".join("%22s" % ("dt = %.1f s" % d,)
                                       for d in TIMESTEPS)))
    print("  %-11s%s" % ("criterion",
                         "".join("%8s%8s%6s" % ("MB", "VC", "gap")
                                 for _ in TIMESTEPS)))
    for name in ("all-green", "zero-delay", "keeps-time"):
        row = "  %-11s" % name
        for dt in TIMESTEPS:
            mb = results[dt][("etcs_moving_block", name)]
            vc = results[dt][("virtual_coupling", name)]
            row += "%8s%8s%6s" % (mb, vc, (mb - vc) if mb and vc else "-")
        print(row)
    print("\n  %d runs in %.0f s. The gap is what to read across the table: "
          "where a" % (len(_cache), time.time() - started))
    print("  boundary moves with the timestep, both systems move with it.")


if __name__ == "__main__":
    main()
