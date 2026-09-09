#!/usr/bin/env python
"""Every number a scenario is actually running on, and where each one came from.

    python stats.py                          the ring
    python stats.py scenarios/express        another railway
    python stats.py scenarios/ring/scenario-grade.yaml
    python stats.py --selfcheck              the derivations, against the code

A scenario file declares surprisingly little. A unit is four performance
figures and a length; a railway is a list of stations and a speed profile.
Everything else - what the train weighs, how much power it has, its Davis
coefficients, where its traction curve breaks, how far it needs to stop, how
many blocks that made, what the mean line speed actually is once it is weighted
by length - is DERIVED, and derived quietly. This prints it, with the formula
beside each figure, so a number in a result can be traced back to the thing it
was computed from rather than taken on trust.

Nothing here is retyped. Every value is read off the built scenario or computed
by calling the same functions the simulator calls, so this report and a run
agree by construction: if a derivation changes, this changes with it.

Stdlib only, like the simulator. ``--check`` reports the layout and whether the
plan is workable; this reports the physics underneath both.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.core import dynamics                        # noqa: E402
from trainsim.core.units import (braking_distance, format_clock,  # noqa: E402
                                 kmh_to_ms, ms_to_kmh)
from trainsim.scenario.loader import ScenarioError, load_scenario  # noqa: E402

WIDTH = 78


def rule(title=""):
    if not title:
        return "-" * WIDTH
    return "%s %s" % (title, "-" * max(0, WIDTH - len(title) - 1))


def row(label, value, how=""):
    """One derived figure: what it is, what it came to, and out of what."""
    return "  %-18s %14s   %s" % (label, value, how)


# --------------------------------------------------------------------- scenario

def scenario_section(scenario):
    cfg = scenario.sim_config
    driver = scenario.driver_config
    return [
        rule("SCENARIO"),
        row("name", scenario.name),
        row("directory", os.path.basename(os.path.abspath(scenario.directory))),
        "  description        %s" % (scenario.description or "-"),
        row("window", "%s + %.0f min" % (format_clock(cfg.start_time_s),
                                         cfg.duration_s / 60.0)),
        row("timestep", "%.2f s" % cfg.dt),
        row("signalling", scenario.signalling_spec.get("system", "-")),
        row("reaction time", "%.1f s" % driver.reaction_time_s,
            "driver; ATO systems override this to 0"),
        row("safety margin", "%.0f m" % driver.safety_margin_m,
            "stood off every danger point"),
        row("stop tolerance", "%.1f m" % driver.stop_tolerance_m),
    ]


# ------------------------------------------------------------------------ stock

def stock_section(stock, grades=(0.0,)):
    """Declared, derived, and the two curves that follow from them."""
    m_eff = dynamics.effective_mass_kg(stock)
    v_max = stock.max_speed_ms
    base = dynamics.base_speed_ms(stock)
    lines = [
        "",
        rule("ROLLING STOCK  %s  (%s)" % (stock.id, stock.name)),
        "",
        "  DECLARED - these are the only stock figures in the timetable file",
        row("length", "%.0f m" % stock.length_m),
        row("max speed", "%.0f km/h" % ms_to_kmh(v_max)),
        row("max accel", "%.2f m/s2" % stock.max_accel, "at a stand"),
        row("service brake", "%.2f m/s2" % stock.service_brake),
        row("emergency brake", "%.2f m/s2" % stock.emergency_brake),
        row("fitment", "ETCS %s" % stock.etcs_level,
            "integrity %s, radio link %s"
            % ("yes" if stock.tims else "no", "yes" if stock.v2v else "no")),
        "",
        "  DERIVED - nothing below was declared; this is where each came from",
        row("mass", "%.1f t" % stock.mass_t,
            "%.1f t/m x %.0f m" % (dynamics.MASS_T_PER_M, stock.length_m)),
        row("effective mass", "%.1f t" % (m_eff / 1000.0),
            "%.1f t x %.2f  (rotating parts %.0f %%)"
            % (stock.mass_t, 1.0 + stock.rotating_mass_pct / 100.0,
               stock.rotating_mass_pct)),
        row("starting effort", "%.1f kN" % (stock.starting_effort_n / 1000.0),
            "max_accel x effective mass"),
        row("base speed", "%.1f km/h" % ms_to_kmh(base),
            "%.0f %% of max speed - where constant effort ends"
            % (100.0 * dynamics.BASE_SPEED_FRACTION)),
        row("power", "%.1f kW" % stock.power_kw,
            "starting effort x base speed"),
        row("", "%.1f kW/t" % (stock.power_kw / stock.mass_t),
            "10-20 is the normal band for this kind of unit"),
        row("davis A", "%.1f N" % stock.davis_a_n,
            "%.1f N/t x %.1f t" % (dynamics.DAVIS_A_N_PER_T, stock.mass_t)),
        row("davis B", "%.2f N/(m/s)" % stock.davis_b_n_per_ms,
            "%.2f x %.1f t" % (dynamics.DAVIS_B_N_PER_MS_PER_T, stock.mass_t)),
        row("davis C", "%.3f N/(m/s)2" % stock.davis_c_n_per_ms2,
            "%.1f + %.3f/m x %.0f m"
            % (dynamics.DAVIS_C_N_PER_MS2_BASE,
               dynamics.DAVIS_C_N_PER_MS2_PER_M, stock.length_m)),
        row("adhesion ceiling", "%.2f m/s2" % dynamics.adhesion_limit(stock),
            "mu %.2f x g - no brake may exceed this" % stock.adhesion),
        row("brake build-up", "%.1f s" % stock.brake_buildup_s,
            "a demand is not an application"),
        row("jerk limit", "%.2f m/s3" % dynamics.jerk_limit_ms3(stock)),
        "",
        "  R(v) = %.1f + %.2f v + %.3f v^2   newtons, v in m/s"
        % (stock.davis_a_n, stock.davis_b_n_per_ms, stock.davis_c_n_per_ms2),
    ]
    lines += traction_table(stock)
    lines += braking_table(stock, grades)
    return lines


def speeds_for(stock):
    """A ladder of speeds worth tabulating, base speed and line speed included."""
    top = ms_to_kmh(stock.max_speed_ms)
    wanted = {0.0, 20.0, ms_to_kmh(dynamics.base_speed_ms(stock)), 40.0,
              60.0, 80.0, 100.0, 120.0, top}
    return sorted(v for v in wanted if v <= top + 1e-9)


def traction_table(stock):
    lines = [
        "",
        "  THE TRACTION CURVE - flat to base speed, then power-limited at P/v",
        "",
        "    %8s %10s %11s %10s %10s %11s"
        % ("km/h", "effort kN", "resist kN", "net kN", "accel", "0-v in s"),
        "    " + "-" * 64,
    ]
    for kmh in speeds_for(stock):
        v = kmh_to_ms(kmh)
        effort = dynamics.tractive_effort_n(stock, v)
        resist = dynamics.resistance_n(stock, v)
        net = effort - resist
        accel = dynamics.traction_accel(stock, v) - dynamics.resistance_accel(
            stock, v)
        took, ran = run_up_to(stock, v)
        lines.append("    %8.0f %10.1f %11.2f %10.1f %10.3f %11s"
                     % (kmh, effort / 1000.0, resist / 1000.0, net / 1000.0,
                        accel, "-" if took is None else "%.1f" % took))
    took, ran = run_up_to(stock, stock.max_speed_ms)
    if took is not None:
        lines.append("")
        lines.append("    rest to line speed: %.1f s and %.0f m, on the level"
                     % (took, ran))
    balance = balancing_unclamped(stock)
    lines.append("    balancing speed   : %s"
                 % ("beyond %.0f km/h - the speed limit is the gearing, not the "
                    "power" % ms_to_kmh(stock.max_speed_ms)
                    if balance is None else
                    "%.0f km/h, so line speed is what limits this train"
                    % ms_to_kmh(balance)))
    if balance is None:
        unclamped = balancing_unclamped(stock, ceiling_ms=200.0)
        if unclamped is not None:
            lines.append("                        (%.0f km/h if the gearing "
                         "allowed it - a model artefact, not a claim)"
                         % ms_to_kmh(unclamped))
    return lines


def run_up_to(stock, target_ms, dt=0.1):
    """Seconds and metres from rest to ``target_ms`` on the level, or None."""
    if target_ms <= 0.0:
        return 0.0, 0.0
    v, t, x, accel = 0.0, 0.0, 0.0, 0.0
    while v < target_ms - 1e-6:
        accel = dynamics.achievable_accel(stock, v, stock.max_accel,
                                          previous_accel=accel, dt=dt)
        if accel <= 1e-6:
            return None, None
        v += accel * dt
        x += v * dt
        t += dt
        if t > 3600.0:
            return None, None
    return t, x


def balancing_unclamped(stock, grade_permille=0.0, ceiling_ms=None):
    """Where traction equals resistance, ignoring the train's own speed limit.

    :func:`dynamics.balancing_speed_ms` returns the speed limit whenever there
    is still surplus at it, which is the right answer for driving and the wrong
    one for reporting: it says the limit is a balance when it is a clamp.
    """
    top = ceiling_ms if ceiling_ms is not None else stock.max_speed_ms
    surplus = (dynamics.traction_accel(stock, top)
               - dynamics.resistance_accel(stock, top)
               - dynamics.grade_accel(stock, grade_permille))
    if surplus >= 0.0:
        return None
    low, high = 0.0, top
    for _ in range(60):
        mid = 0.5 * (low + high)
        if (dynamics.traction_accel(stock, mid)
                - dynamics.resistance_accel(stock, mid)
                - dynamics.grade_accel(stock, grade_permille)) >= 0.0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def braking_table(stock, grades=(0.0,)):
    lines = [
        "",
        "  BRAKING - the driver's curve, which ignores Davis on purpose",
        "",
        "    %8s" % "km/h"
        + "".join("%14s" % ("%+g permille" % g if g else "level") for g in grades)
        + "%12s" % "build-up m",
        "    " + "-" * (8 + 14 * len(grades) + 12),
    ]
    for kmh in speeds_for(stock):
        if kmh <= 0:
            continue
        v = kmh_to_ms(kmh)
        cells = ""
        for grade in grades:
            rate = dynamics.braking_rate_on_grade(stock, grade)
            cells += "%14.1f" % braking_distance(v, rate)
        lines.append("    %8.0f%s%12.1f"
                     % (kmh, cells,
                        dynamics.brake_buildup_distance_m(stock, v)))
    return lines


# --------------------------------------------------------------- infrastructure

def infrastructure_section(scenario):
    infra = scenario.infrastructure
    network = infra.network
    segments = list(network.segments.values())
    lines = [
        "",
        rule("INFRASTRUCTURE"),
        row("stations", "%d" % len(network.stations)),
        row("platforms", "%d" % len(network.platforms)),
        row("tracks", "%d" % len(infra.tracks),
            ", ".join(sorted(infra.tracks)) + "  (_R is the reverse direction)"),
        row("segments", "%d" % len(segments)),
        row("block sections", "%d" % len(infra.blocks)),
        row("signals", "%d" % len(infra.signals)),
        row("points", "%d" % len(infra.points)),
        row("routes", "%d" % len(infra.routes)),
        "",
        "  PER TRACK - speed and gradient weighted by length, not by count",
        "",
        "    %-6s %9s %16s %18s %11s"
        % ("track", "length", "speed km/h", "grade permille", "net rise"),
        "    " + "-" * 64,
    ]
    rises = {}
    for track in sorted(infra.tracks):
        here = [s for s in segments if s.track == track]
        if not here:
            continue
        total_m = sum(s.length_m for s in here)
        speeds = [(ms_to_kmh(s.max_speed_ms), s.length_m) for s in here]
        grades = [(s.grade_permille, s.length_m) for s in here]
        rise = sum(g / 1000.0 * length for g, length in grades)
        rises[track] = rise
        lines.append(
            "    %-6s %7.1f km %5.0f-%3.0f (%3.0f) %6.0f..%+4.0f (%4.1f) %8.1f m"
            % (track, total_m / 1000.0,
               min(v for v, _ in speeds), max(v for v, _ in speeds),
               weighted(speeds),
               min(g for g, _ in grades), max(g for g, _ in grades),
               weighted([(abs(g), length) for g, length in grades]),
               rise))
    lines += closure_note(rises, segments)
    lines += profile_histogram("SPEED PROFILE", segments,
                               lambda s: ms_to_kmh(s.max_speed_ms), "km/h")
    if any(s.grade_permille for s in segments):
        lines += profile_histogram("GRADIENT PROFILE", segments,
                                   lambda s: s.grade_permille, "permille")
    lines += block_note(infra)
    return lines


def weighted(pairs):
    """Mean of ``(value, length)`` weighted by length."""
    total = sum(length for _, length in pairs)
    if not total:
        return 0.0
    return sum(value * length for value, length in pairs) / total


def closure_note(rises, segments):
    """A circuit has to come back to the height it left from.

    Only worth saying on a railway that is one - a turning loop is what makes a
    lap - and only where there is a gradient for it to be wrong about.
    """
    if not any(segment.turns for segment in segments):
        return []
    if not any(segment.grade_permille for segment in segments):
        return []
    forward = {name: rise for name, rise in rises.items()
               if not name.endswith("_R")}
    if len(forward) != 2:
        return []
    net = sum(forward.values())
    verdict = ("closes" if abs(net) < 0.5
               else "DOES NOT CLOSE - a lap would gain %+.1f m of height" % net)
    return ["",
            "    the two running lines rise %s: %s"
            % (" and ".join("%+.1f m" % rise for rise in forward.values()),
               verdict)]


def profile_histogram(title, segments, of, unit):
    counts = {}
    for segment in segments:
        value = round(of(segment), 1)
        counts[value] = counts.get(value, 0.0) + segment.length_m
    total = sum(counts.values())
    lines = ["", "  %s - kilometres of railway at each value" % title, ""]
    for value in sorted(counts):
        share = counts[value] / total
        lines.append("    %+8g %-9s %7.1f km  %5.1f %%  %s"
                     % (value, unit, counts[value] / 1000.0, 100.0 * share,
                        "#" * int(round(share * 40))))
    return lines


def block_note(infra):
    lengths = sorted(block.length_m for block in infra.blocks.values())
    if not lengths:
        return []
    return [
        "",
        "  BLOCK SECTIONS",
        row("shortest", "%.0f m" % lengths[0]),
        row("mean", "%.0f m" % (sum(lengths) / len(lengths))),
        row("longest", "%.0f m" % lengths[-1]),
    ]


# -------------------------------------------------------------------- timetable

def timetable_section(scenario):
    services = scenario.timetable.services
    if not services:
        return ["", rule("TIMETABLE"), "  no services"]
    departures = sorted(service.departure_s for service in services)
    gaps = [b - a for a, b in zip(departures, departures[1:])]
    calls = [len(service.stops) for service in services]
    dwells = sorted({stop.min_dwell_s
                     for service in services for stop in service.stops})
    lines = [
        "",
        rule("TIMETABLE"),
        row("services", "%d" % len(services)),
        row("first away", format_clock(departures[0])),
        row("last away", format_clock(departures[-1])),
        row("booked interval",
            "%.0f s" % (sum(gaps) / len(gaps)) if gaps else "-",
            "%.0f to %.0f s" % (min(gaps), max(gaps)) if gaps else ""),
        row("calls per service", "%d" % calls[0]
            if len(set(calls)) == 1 else "%d-%d" % (min(calls), max(calls))),
        row("dwell", ", ".join("%.0f s" % d for d in dwells)),
    ]
    booked = [service.stops[-1].arrival_s - service.departure_s
              for service in services
              if service.stops and service.stops[-1].arrival_s is not None]
    if booked:
        shortest, longest = min(booked), max(booked)
        lines.append(row("booked journey",
                         "%d:%02d" % (int(shortest) // 60, int(shortest) % 60),
                         "to %d:%02d" % (int(longest) // 60, int(longest) % 60)
                         if longest != shortest else "every service the same"))
    return lines


# ------------------------------------------------------------------------ entry

def notable_grades(scenario):
    """Level, plus the steepest fall and rise this railway actually has.

    A braking table against the level alone says nothing on a graded railway,
    and a table against every gradient says too much.
    """
    grades = [segment.grade_permille
              for segment in scenario.infrastructure.network.segments.values()]
    worst, best = min(grades), max(grades)
    return tuple(g for g in (0.0, worst, best) if g == 0.0 or g)


def report(scenario):
    lines = scenario_section(scenario)
    grades = notable_grades(scenario)
    seen = []
    for service in scenario.timetable.services:
        if service.stock.id not in seen:
            seen.append(service.stock.id)
            lines += stock_section(service.stock, grades)
    lines += infrastructure_section(scenario)
    lines += timetable_section(scenario)
    return "\n".join(line.rstrip() for line in lines)


def selfcheck():
    """The derivations here reproduce what the stock object already holds."""
    scenario = load_scenario(os.path.join("scenarios", "ring"))
    stock = scenario.timetable.services[0].stock

    assert abs(stock.mass_t - dynamics.MASS_T_PER_M * stock.length_m) < 1e-6
    m_eff = dynamics.effective_mass_kg(stock)
    assert abs(m_eff - stock.mass_kg * 1.08) < 1.0, m_eff
    assert abs(stock.starting_effort_n - stock.max_accel * m_eff) < 1.0

    base = dynamics.BASE_SPEED_FRACTION * stock.max_speed_ms
    assert abs(stock.power_kw - stock.starting_effort_n * base / 1000.0) < 1e-6

    # Effort is flat to base speed and P/v above it.
    assert abs(dynamics.tractive_effort_n(stock, base * 0.5)
               - stock.starting_effort_n) < 1.0
    top = stock.max_speed_ms
    assert abs(dynamics.tractive_effort_n(stock, top)
               - stock.power_kw * 1000.0 / top) < 1.0

    # This unit is over-powered for its gearing, so the clamp hides the balance.
    assert balancing_unclamped(stock) is None, "expected surplus at line speed"
    assert balancing_unclamped(stock, ceiling_ms=200.0) > top

    # And the report renders for a railway that has gradients on it.
    graded = load_scenario(os.path.join("scenarios", "ring",
                                        "scenario-grade.yaml"))
    text = report(graded)
    assert "DOES NOT CLOSE" not in text, "the graded circuit should close"
    assert "GRADIENT PROFILE" in text
    print("stats: ok - %d lines, derivations agree with the stock object"
          % text.count("\n"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selfcheck" in argv:
        selfcheck()
        return 0
    path = argv[0] if argv else os.path.join("scenarios", "ring")
    try:
        scenario = load_scenario(path)
    except (ScenarioError, OSError) as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2
    print(report(scenario))
    return 0


if __name__ == "__main__":
    sys.exit(main())
