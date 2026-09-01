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

        stock["etcs_level"] = "l3"
        stock["tims"] = False
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


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
