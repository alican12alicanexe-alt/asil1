"""How much room a train needs behind the one in front, by speed and by system.

    python separation.py                       the ring unit, every system
    python separation.py scenarios/express     another scenario's unit
    python separation.py --grade -25           on a 1-in-40 falling gradient

Every term comes out of the running code rather than being retyped here, so
this table and a run agree by construction. What it composes is the chain the
driver actually applies in Driver.decide:

    authority needed = braking distance          units.braking_distance, at the
                                                 rate dynamics.braking_rate_on_grade
                                                 gives for the gradient
                     + brake build-up            dynamics.brake_buildup_distance_m
                     + driver standing margin    DriverConfig.safety_margin_m
                     + reaction distance         speed x DriverConfig.reaction_time_s
                                                 (zero under ATO - see DRIVING)

That is the distance from the train's front to its danger point. Where the
danger point IS depends on the system, which is the second half of the table:
fixed block and Levels 1-2 put it at the entry of the first occupied block, so
a whole block stands empty on top; the distance-separated systems put it near
the rear of the train in front, less their own margin - except virtual
coupling, which puts it BEYOND that rear by however far the leader would run on
if it braked now.

    python separation.py --selfcheck    the chain, against the driver's own maths
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.core import dynamics, signalling as reg   # noqa: E402
from trainsim.core.driver import DriverConfig, stopping_distance  # noqa: E402
from trainsim.core.units import braking_distance, speed_from_braking_distance  # noqa: E402
from trainsim.scenario.loader import load_scenario      # noqa: E402

DEFAULT_SCENARIO = "scenarios/ring"
SPEEDS_KMH = (120, 100, 80, 60, 50, 40, 30, 20)


def authority_needed(stock, driver, speed_ms, grade_permille=0.0):
    """Authority length that lets a train run at ``speed_ms`` without braking.

    Driver.stopping_distance is the whole of it - the same function the block
    check in --check sizes sections with, so the two reports cannot disagree
    about how much room a train needs.
    """
    return stopping_distance(stock, driver, speed_ms, grade_permille)


def system_offset(system, stock, speed_ms):
    """``(offset, note)``: danger point relative to the rear of the train ahead.

    Negative is short of that rear, which is every system that separates by
    distance. Positive is beyond it, which only virtual coupling may say - it
    is the leader's own run-on, borrowed. ``None`` for the block-based systems,
    where the danger point is a block boundary and there is no rear to measure
    from.
    """
    if system.name == "virtual_coupling":
        # The leader is taken to be running at the same speed as the follower,
        # which is the steady-state convoy case and the one the separation is
        # quoted at. Closing on a slower or standing train is worse, and that
        # is the point of the concept rather than a gap in it.
        decel = (stock.service_brake if system.leader_brake == "service"
                 else max(stock.service_brake, stock.emergency_brake))
        run_on = braking_distance(speed_ms, decel)
        margin = system.safety_margin_m + speed_ms * system.v2v_latency_s
        return run_on - margin, "leader run-on %.0f m less %.0f m" % (run_on, margin)
    if system.name == "etcs_moving_block":
        return -system.safety_margin_m, "%.0f m short of the rear" % system.safety_margin_m
    if system.name == "etcs_hybrid_l3":
        return -system.safety_margin_m, "%.0f m short of the VSS" % system.safety_margin_m
    return None, "block entry, not a rear"


def gap_to_rear(name, stock, driver, speed_ms, grade_permille=0.0):
    """Front of the follower to the rear of the leader, or None if block-based."""
    offset, _ = system_offset(reg.create(name), stock, speed_ms)
    if offset is None:
        return None
    return authority_needed(stock, driver, speed_ms, grade_permille) - offset


def table(stock, base_driver, grade_permille=0.0, speeds=SPEEDS_KMH):
    def driver_for(name):
        return reg.fit_driver(base_driver, name)

    lines = []
    rate = dynamics.braking_rate_on_grade(stock, grade_permille)
    lines.append("%s: %.0f m, %.0f km/h, service brake %.1f, emergency %.1f, "
                 "build-up %.1f s"
                 % (stock.name, stock.length_m, stock.max_speed_ms * 3.6,
                    stock.service_brake, stock.emergency_brake,
                    stock.brake_buildup_s))
    lines.append("driver: %.0f m standing margin, %.1f s reaction (zero where the "
                 "system is ATO)" % (base_driver.safety_margin_m,
                                     base_driver.reaction_time_s))
    lines.append("gradient %+.0f permille, so the braking curve is computed at "
                 "%.2f m/s2" % (grade_permille, rate))
    lines.append("")
    over = [s for s in speeds if s / 3.6 > stock.max_speed_ms + 1e-9]
    if over:
        lines.append("* %s km/h is above this unit's %.0f km/h: those columns are the"
                     % (", ".join(str(s) for s in over), stock.max_speed_ms * 3.6))
        lines.append("  arithmetic carried on past what the train can actually do.")
        lines.append("")
    lines.append("AUTHORITY NEEDED - front of the train to its danger point, metres")
    lines.append("  %-22s %s"
                 % ("km/h", "".join("%7d%s" % (s, "*" if s in over else " ")
                                    for s in speeds)))
    for name in reg.LADDER:
        driver = driver_for(name)
        cells = "".join(
            "%8.0f" % authority_needed(stock, driver, s / 3.6, grade_permille)
            for s in speeds)
        lines.append("  %-22s %s" % (name, cells))
    lines.append("  Rows tie where the driver does: the four with a 2.0 s reaction")
    lines.append("  read alike, the two ATO ones read alike. What separates the")
    lines.append("  systems is WHERE the danger point sits, which is the next table.")

    lines.append("")
    lines.append("GAP TO THE REAR OF THE TRAIN AHEAD, metres - distance separation only")
    lines.append("  %-22s %s" % ("km/h", "".join("%8d" % s for s in speeds)))
    for name in ("etcs_hybrid_l3", "etcs_moving_block", "virtual_coupling"):
        cells = "".join("%8.0f" % gap_to_rear(name, stock, driver_for(name),
                                              s / 3.6, grade_permille)
                        for s in speeds)
        lines.append("  %-22s %s" % (name, cells))
    lines.append("  fixed block, L1 and L2 have no rear to measure from: their")
    lines.append("  danger point is a block boundary, so the gap is a whole block.")

    lines.append("")
    lines.append("what virtual coupling is borrowing, metres")
    for s in speeds:
        vc = reg.create("virtual_coupling")
        offset, note = system_offset(vc, stock, s / 3.6)
        lines.append("  %3d km/h  %+7.0f   %s" % (s, offset, note))
    return "\n".join(lines)


def selfcheck():
    """The chain, checked against the driver's own arithmetic rather than restated."""
    scenario = load_scenario(DEFAULT_SCENARIO)
    stock = scenario.timetable.services[0].stock
    driver = DriverConfig(reaction_time_s=2.0, safety_margin_m=25.0)

    for speed_kmh in (120, 80, 30):
        speed = speed_kmh / 3.6
        needed = authority_needed(stock, driver, speed)
        # Feed that authority back through exactly what Driver.decide does and
        # the permitted speed must come back out as the speed we asked for.
        usable = (needed - driver.safety_margin_m - speed * driver.reaction_time_s
                  - dynamics.brake_buildup_distance_m(stock, speed))
        rate = dynamics.braking_rate_on_grade(stock, 0.0)
        allowed = speed_from_braking_distance(usable, rate)
        assert abs(allowed - speed) < 1e-6, (speed_kmh, allowed * 3.6)

    # A falling gradient lengthens the curve; a rising one shortens it.
    flat = authority_needed(stock, driver, 22.2, 0.0)
    assert authority_needed(stock, driver, 22.2, -25.0) > flat
    assert authority_needed(stock, driver, 22.2, 25.0) < flat

    # Virtual coupling is the only system whose danger point may sit beyond the
    # rear of the train in front, and only while that train is moving.
    vc = reg.create("virtual_coupling")
    assert system_offset(vc, stock, 22.2)[0] > 0.0
    assert system_offset(vc, stock, 0.0)[0] < 0.0
    assert system_offset(reg.create("etcs_moving_block"), stock, 22.2)[0] < 0.0
    print("selfcheck: the table inverts Driver.decide exactly, at 120, 80 and 30 km/h")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
        raise SystemExit(0)
    args = [a for a in sys.argv[1:]]
    grade = 0.0
    if "--grade" in args:
        at = args.index("--grade")
        grade = float(args[at + 1])
        del args[at:at + 2]
    path = args[0] if args else DEFAULT_SCENARIO
    scenario = load_scenario(path)
    print(table(scenario.timetable.services[0].stock,
                scenario.driver_config, grade))
