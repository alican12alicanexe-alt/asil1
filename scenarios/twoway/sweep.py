"""
TWOWAY CAPACITY EXPERIMENT
===========================

Compare how closely trains can be dispatched under:

    1. Fixed-block 3-aspect signalling
    2. ETCS moving block
    3. Virtual coupling

The experiment uses the SAME physical railway and the SAME physical train
performance. The sweep changes the signalling system and the train's
signalling equipment as required.

The first experiment is deliberately simple:

    - UP trains only
    - 6 trains
    - every train stops at every station
    - same infrastructure
    - same train length
    - same acceleration
    - same braking
    - same maximum speed
    - only departure headway changes
    - signalling system changes between experiments

This lets us answer the basic question:

    "How many trains per hour can this railway operate under each
     signalling system?"

Later experiments can add:

    - different train performance
    - random speed limits
    - shorter/longer blocks
    - additional crossovers
    - sidings
    - mixed UP/DN traffic
    - overtaking
    - degraded operation
    - station dwell variation
    - heterogeneous rolling stock

Run:

    python scenarios/twoway/sweep.py

"""


import os
import sys


# ---------------------------------------------------------------------------
# Import project
# ---------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(HERE)),
)

sys.path.insert(0, HERE)


from _generate_timetable import (
    COUNT,
    flight_spec,
    probe_all,
    simulation,
    INFRA,
    STOCK,
)

from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable


# ---------------------------------------------------------------------------
# EXPERIMENT PARAMETERS
# ---------------------------------------------------------------------------

# Departure interval between consecutive trains.
#
# 300 s = 12 trains/hour
# 180 s = 20 trains/hour
# 120 s = 30 trains/hour
# 60 s  = 60 trains/hour
#
# Start relatively wide and gradually tighten the railway.
HEADWAYS = (
    300,
    270,
    240,
    210,
    195,
    180,
    165,
    150,
    135,
    120,
    105,
    90,
    75,
    60,
    # Below a minute a minute is no longer a sensible unit of dispatch, but the
    # cab systems are still not in trouble at 60 s on this railway, and a sweep
    # that stops before the thing it is measuring bends has measured nothing.
    # These rows exist to find where virtual coupling actually gives way.
    50,
    45,
    40,
    35,
    30,
)


# Signalling systems available in the simulator.
#
# IMPORTANT:
# These names must match the signalling registry.
SYSTEMS = (
    "fixed_block_3aspect",
    "etcs_moving_block",
    "virtual_coupling",
)


# First experiment uses only one direction.
#
# This isolates following capacity.
#
# Later we can change this to:
#
#     ("UP", "DN")
#
# to study bidirectional traffic.
DIRECTIONS = ("UP",)


# ---------------------------------------------------------------------------
# TRAIN CONFIGURATION
# ---------------------------------------------------------------------------

def stock_for(system):
    """
    Return the train configuration appropriate for the signalling system.

    Physical train performance stays identical between experiments.
    Only signalling-related equipment changes.
    """

    stock = dict(STOCK)

    if system == "fixed_block_3aspect":

        stock["etcs_level"] = "none"
        stock["tims"] = False
        stock["v2v"] = False

    elif system == "etcs_moving_block":

        # Integrity reporting on: moving block follows the REAR of the train
        # in front, and a train that cannot confirm its own integrity has no
        # trustworthy rear to follow.
        stock["etcs_level"] = "l3"
        stock["tims"] = True
        stock["v2v"] = False

    elif system == "virtual_coupling":

        stock["etcs_level"] = "l3"
        stock["tims"] = True
        stock["v2v"] = True

    else:
        raise ValueError(
            "Unknown experiment system: %s" % system
        )

    return stock


# ---------------------------------------------------------------------------
# ONE CAPACITY TEST
# ---------------------------------------------------------------------------

def run(times, headway_s, system, count=COUNT):
    """
    Run one capacity experiment.

    Parameters
    ----------
    times:
        Unimpeded running times obtained from probe_all().

    headway_s:
        Departure interval between consecutive trains.

    system:
        Signalling system.

    count:
        Number of trains.

    Returns
    -------
    KPI metrics from the simulation.
    """

    # ---------------------------------------------------------------
    # Select train equipment.
    # ---------------------------------------------------------------

    stock = stock_for(system)


    # ---------------------------------------------------------------
    # Generate the timetable directly in memory.
    #
    # No timetable.yaml modification is necessary.
    #
    # Only UP trains are used for the first experiment.
    # ---------------------------------------------------------------

    timetable_data = flight_spec(
        times,
        headway_s,
        count=count,
        directions=DIRECTIONS,
        stock=stock,
    )


    # ---------------------------------------------------------------
    # Convert dictionary to simulator timetable.
    # ---------------------------------------------------------------

    timetable = build_timetable(
        timetable_data,
        INFRA,
    )


    # ---------------------------------------------------------------
    # Run simulation.
    #
    # Give the simulation enough time for the entire flight to finish.
    # ---------------------------------------------------------------

    sim = simulation(
        timetable,
        duration_s=headway_s * count + 3600,
        system=system,
    )


    # measure() runs the simulation and collects the per-tick metrics.
    return measure(sim)


# ---------------------------------------------------------------------------
# FINDING THE EXACT BOUNDARY
# ---------------------------------------------------------------------------

def is_clean(metrics):
    """
    Whether this interval ran all-green.

    All-green means no train was ever held down by the signalling, nobody
    arrived late, and every train finished. It is a stricter test than "no
    violations": a railway can run a timetable safely and still be fighting
    itself the whole way.
    """

    worst = max(metrics.delays.values()) if metrics.delays else 0.0

    return (metrics.total_restrained_s <= 0.0
            and worst <= 1.0
            and metrics.completed == metrics.services)


def refine(times, system, clean_s, degraded_s):
    """
    Narrow the boundary between a clean interval and a degraded one to 1 s.

    The coarse sweep only says the answer is somewhere between two of its
    rows. Clean at 120 s and degraded at 105 s says nothing about 112 s.

    So halve the bracket and try the middle:

        clean 120, degraded 105  ->  try 112
        112 clean                ->  try 108
        108 degraded             ->  try 110
        ...until one second separates the two ends

    Four or five runs instead of the fifteen a second-by-second sweep would
    take.

    This assumes the railway does not become clean again as the interval
    tightens. That holds in every case seen here, but it is an assumption:
    where the restraint column is not monotonic this finds *a* boundary in
    the bracket rather than the only one.

    Returns the tightest interval that still ran clean, and every interval
    tried on the way.
    """

    lo = int(degraded_s)     # known degraded
    hi = int(clean_s)        # known clean

    tried = []

    while hi - lo > 1:

        mid = (lo + hi) // 2

        ok = is_clean(run(times, mid, system))

        tried.append((mid, ok))

        if ok:
            hi = mid
        else:
            lo = mid

    return hi, tried


# ---------------------------------------------------------------------------
# PRINT HEADER
# ---------------------------------------------------------------------------

def print_header(system):
    """Print the heading for one signalling system."""

    print()
    print("=" * 78)
    print("SIGNALLING: %s" % system)
    print("=" * 78)

    print(
        "headway   tph    restraint   mean delay   "
        "worst delay   completed   violations"
    )

    print("-" * 78)


# ---------------------------------------------------------------------------
# MAIN EXPERIMENT
# ---------------------------------------------------------------------------

def main():

    print()
    print("TWOWAY CAPACITY EXPERIMENT")
    print("---------------------------")
    print("traffic     : %s" % " + ".join(DIRECTIONS))
    print("trains      : %d" % COUNT)
    print("infrastructure: twoway")
    print()


    # ---------------------------------------------------------------
    # Calculate the unimpeded running times once.
    #
    # probe_all() runs each service alone on the railway.
    #
    # Therefore the booked timetable is physically achievable when
    # there is no traffic interaction.
    # ---------------------------------------------------------------

    print("Calculating unimpeded running times...")

    times = probe_all()

    print("Done.")


    # ---------------------------------------------------------------
    # Run every signalling system.
    # ---------------------------------------------------------------

    for system in SYSTEMS:

        print_header(system)


        # The tightest interval that ran clean, and the widest that did not
        # once it had. Together they bracket the boundary.
        all_green = None
        first_degraded = None


        for headway in HEADWAYS:

            # -------------------------------------------------------
            # Run the actual experiment.
            # -------------------------------------------------------

            metrics = run(
                times,
                headway,
                system,
            )


            # -------------------------------------------------------
            # Calculate useful values.
            # -------------------------------------------------------

            tph = 3600.0 / headway


            if metrics.delays:
                worst = max(metrics.delays.values())
            else:
                worst = 0.0


            # -------------------------------------------------------
            # Print result.
            # -------------------------------------------------------

            print(
                "%6d   %5.1f   %9.0f   %10.1f   "
                "%11.1f   %d/%d       %d"
                % (
                    headway,
                    tph,
                    metrics.total_restrained_s,
                    metrics.mean_delay_s,
                    worst,
                    metrics.completed,
                    metrics.services,
                    metrics.violations,
                )
            )


            # -------------------------------------------------------
            # Track the bracket.
            # -------------------------------------------------------

            if is_clean(metrics):
                all_green = headway
                first_degraded = None

            elif all_green is not None and first_degraded is None:
                first_degraded = headway


        # -----------------------------------------------------------
        # Close in on the exact interval.
        # -----------------------------------------------------------

        print()

        if all_green is None:
            print("  no interval in the range ran all-green - widen HEADWAYS")
            continue

        if first_degraded is None:
            print("  all-green all the way down to %d s: this railway has not "
                  "bent yet, so" % (all_green,))
            print("  that is the end of HEADWAYS rather than a limit. Tighten "
                  "the list.")
            continue

        print("  clean at %d s, degraded at %d s. Closing in:"
              % (all_green, first_degraded))

        exact, tried = refine(times, system, all_green, first_degraded)

        for headway, ok in tried:
            print("    %4d s   %s" % (headway, "clean" if ok else "degraded"))

        print("  all-green headway: %d s (%.1f tph). At %d s one train is "
              "checked." % (exact, 3600.0 / exact, exact - 1))


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
