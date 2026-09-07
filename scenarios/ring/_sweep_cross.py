"""What does a flat crossing cost, and can a signalling system get it back?

    python scenarios/ring/_sweep_cross.py                 all four systems
    python scenarios/ring/_sweep_cross.py virtual_coupling

Every other measurement on this circuit is made where the constraint is a
platform, and the answer is always the same: a platform is not a following
distance, so the signalling has almost nothing to work on. This asks the other
question. Two railways cross at km 26.60 and share nothing else, nothing calls
anywhere on the circuit, and the diamond is the only thing in the way.

HOW IT IS MEASURED

Each system is run at ITS OWN all-green headway on the non-stop circuit - 139,
49, 39 and 32 seconds, the figures scenarios/ring/_sweep_express.py produced on
the same flight with no crossing at all. At that interval the circuit is exactly
as full as that system can hold and not one second fuller, so what appears when
the crossing railway is laid over it is the crossing and nothing else.

Then the same run twice: once with the crossing flat, once with
grade_separated on all four diamonds, which is the same two railways with the
conflict taken away. The difference between the two is what the diamond costs,
measured rather than argued.

WHAT TO EXPECT, SAID BEFORE THE RUN

The cost should barely move between systems. A diamond is held for as long as
a train is on it, and that is train length plus block over speed - nothing on
this ladder shortens any of those three. What virtual coupling can shorten is
the APPROACH, because the next train is nearer the crossing when the slot
opens, and how fast a queue clears once one has built. Those are following
distances, which is the one thing it does shorten.

If the cost does not move, that is the finding and it generalises the study:
virtual coupling shortens following distances, it does not shorten occupancies,
and this railway is limited by occupancies.

WHAT IT ANSWERED

Every flyover run came back at 0 s restrained, mean -1.0 s, 28 of 28 completed,
which is the check on the plan: the timetable is workable with the conflict
taken away, so everything below belongs to the crossing.

Each system at its own all-green headway - so each is carrying all the traffic
it can hold, and a denser railway puts proportionally more over the diamond:

                          headway   restrained   mean delay    worst
    fixed block 3-aspect    139 s      + 781 s     +25.1 s     +103 s
    ETCS hybrid L3 (VSS)     49 s      +2376 s     +74.6 s     +516 s
    ETCS moving block        39 s      +1636 s     +50.6 s     +411 s
    virtual coupling         32 s      +1136 s     +36.7 s     +337 s

That is not a comparison, because the interval is different in every row: a
system that holds a tighter headway sends more trains over the crossing and is
charged for the extra traffic. Hold the interval still and the comparison
appears (``--at 39``, moving block's own boundary, so both are inside it):

                          restrained   mean delay    worst
    ETCS moving block        1636 s      49.6 s      410 s
    virtual coupling         1519 s      49.0 s      410 s

VIRTUAL COUPLING IS CHECKED 7 % LESS AND ARRIVES EXACTLY AS LATE. Not
approximately: 410 s against 410 s, to the second, and 49.0 s of mean delay
against 49.6 s. What relative braking buys is the queue standing closer to the
crossing, which is a following distance and is the one thing it shortens. What
it cannot buy is a turn over the diamond, because a diamond is held for as long
as a train is on it and that is length plus block over speed - three quantities
no signalling system on this ladder touches.

So the seven seconds is worth nothing at a junction, and the study has its
general statement: virtual coupling shortens following distances, it does not
shorten occupancies, and a railway with platforms and junctions in it is
limited by occupancies.

It also separates two things the rest of this repository reports together.
Restraint is the direct cost of the signalling and it fell by 117 s; delay is
what a passenger notices and it did not move at all. A system can be checked
much less and still be exactly as late.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_cross as cross
import _generate_timetable as ring
from _generate_timetable import COUNT, STOCK, probe_all, simulation
from trainsim.analysis.kpi import measure
from trainsim.core import signalling as reg
from trainsim.scenario.builder import build_infrastructure
from trainsim.scenario.loader import build_timetable, read_data_file

#: The all-green headway each system holds on this same non-stop flight with no
#: crossing on the railway at all, from _sweep_express.py. Running each system
#: at its own boundary is what makes the comparison fair: a system is not
#: penalised here for holding a wider interval on the plain circuit.
EXPRESS_BOUNDARY = {
    "fixed_block_3aspect": 139,
    "etcs_hybrid_l3": 49,
    "etcs_moving_block": 39,
    "virtual_coupling": 32,
}

#: How often a train goes over the crossing, each way. Four minutes: often
#: enough to be in the circuit's way at every interval tested, wide enough that
#: the crossing railway never queues on its own account and what is measured
#: stays the circuit's delay rather than its own.
CROSS_HEADWAY = 240

TAIL_S = 7200


def infrastructure(grade_separated):
    """The crossing drawing, flat or as a flyover.

    Patched in memory rather than kept as a second file. The two railways, the
    blocks, the signals and the timetable are identical either way - the only
    difference is whether the four diamonds are declared as conflicts, which is
    exactly the difference the experiment is about, and a duplicate drawing
    would be one more thing that could quietly stop being identical.
    """
    spec = read_data_file(os.path.join(HERE, cross.INFRA_FILE))
    for crossover in spec["crossovers"]:
        if crossover.get("type") == "diamond":
            crossover["grade_separated"] = grade_separated
    return build_infrastructure(spec)


def stock_for(system):
    level, tims, v2v = reg.fitment_for(system)
    return dict(STOCK, etcs_level=level, tims=tims, v2v=v2v)


def run(system, headway_s, grade_separated, ring_only=False, cross_only=False,
        indices=None):
    ring.INFRA = infrastructure(grade_separated)
    unit = stock_for(system)
    times_up, times_dn = cross.probe_cross(cross.CROSS_UP_RUN), \
        cross.probe_cross(cross.CROSS_DN_RUN)
    spec = cross.combined_spec(probe_all(), headway_s, times_up, times_dn,
                               CROSS_HEADWAY, offset_s=headway_s // 2,
                               stock=unit)
    if ring_only:
        spec["services"] = [s for s in spec["services"]
                            if not s["id"].startswith("X")]
    if cross_only:
        spec["services"] = [s for s in spec["services"]
                            if s["id"].startswith("X")]
    if indices is not None:
        spec["services"] = [spec["services"][n] for n in indices]
    timetable = build_timetable(spec, ring.INFRA)
    sim = simulation(timetable,
                     duration_s=headway_s * COUNT + TAIL_S, system=system)
    return measure(sim)


def worst_of(metrics):
    return max(metrics.delays.values()) if metrics.delays else 0.0


def report(system, headway=None):
    headway = headway or EXPRESS_BOUNDARY[system]
    print("\n%s - the circuit at %d s%s"
          % (system, headway,
             " (its own all-green headway)"
             if headway == EXPRESS_BOUNDARY.get(system) else ""))
    print("  " + "-" * 66)
    rows = {}
    for label, separated in (("flyover", True), ("flat", False)):
        metrics = run(system, headway, separated)
        rows[label] = metrics
        print("  %-9s restrained %7.0f s   mean %6.1f s   worst %6.0f s   "
              "%d/%d" % (label, metrics.total_restrained_s,
                         metrics.mean_delay_s, worst_of(metrics),
                         metrics.completed, metrics.services))
    flat, over = rows["flat"], rows["flyover"]
    print("  " + "-" * 66)
    print("  the diamond costs %+.0f s of restraint, %+.1f s of mean delay, "
          "%+.0f s at worst" % (flat.total_restrained_s - over.total_restrained_s,
                                flat.mean_delay_s - over.mean_delay_s,
                                worst_of(flat) - worst_of(over)))
    return flat, over


if __name__ == "__main__":
    # ``--at N`` runs every system named at ONE interval instead of at its own
    # boundary. The two questions are different and both worth asking: at its
    # own boundary a system is carrying all the traffic it can, so the answer
    # includes how much traffic that is; at a common interval the traffic is
    # held still and what is left is how the system handles the crossing.
    argv = sys.argv[1:]
    common = None
    if "--at" in argv:
        where = argv.index("--at")
        common = int(argv[where + 1])
        argv = argv[:where] + argv[where + 2:]
    wanted = argv or list(EXPRESS_BOUNDARY)
    print("A flat crossing at km 26.60, %d circuit services calling nowhere, "
          "%d crossing" % (COUNT, cross.CROSS_COUNT))
    print("services each way every %d s, %s."
          % (CROSS_HEADWAY,
             "all at %d s" % common if common
             else "each system at its own all-green headway"))
    for system in wanted:
        report(system, common)
