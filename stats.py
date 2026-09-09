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
agree by construction: if a derivation changes, this changes with it. The
declared/derived split is read from the timetable file rather than guessed,
because a built RollingStock cannot tell you which of the two a figure was.

What it covers, and it is meant to be everything a train's motion obeys:

    the unit          declared and derived, with the formula beside each -
                      mass, effective mass, starting effort, base speed, power,
                      three Davis coefficients, adhesion, build-up, jerk
    model constants   g, tonnes per metre, the base-speed fraction, the creep
                      speed below which P/v is meaningless, the Davis rates.
                      None of these is in any scenario file and all of them
                      move a result
    traction          effort, resistance, net force and acceleration speed by
                      speed, the time from rest, and the balancing speed said
                      honestly rather than clamped at the train's own limit
    resistance        Davis in kN and in N per tonne, what a coasting train
                      does, and how far it drifts before stopping
    braking           service and emergency, on the level and on the steepest
                      gradients this railway actually has, plus build-up
    gradient          what ten per thousand is worth in m/s2 and in kN, against
                      the drag it is being compared with
    the authority     braking + build-up + reaction + margin, which is the
                      chain that sizes a block and the number a signalling
                      system is really arguing about
    the railway       per track length, speed and gradient weighted by length,
                      the profiles as kilometres at each value, blocks, and on
                      a circuit whether the gradients close
    the plan          services, interval, calls, dwell, booked journey

Stdlib only, like the simulator. ``--check`` reports the layout and whether the
plan is workable; this reports the physics underneath both.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.core import dynamics, signalling             # noqa: E402
from trainsim.core.driver import DriverConfig, stopping_distance  # noqa: E402
from trainsim.core.units import (braking_distance, format_clock,  # noqa: E402
                                 kmh_to_ms, ms_to_kmh)
from trainsim.scenario.loader import (ScenarioError,       # noqa: E402
                                      load_scenario, read_data_file)

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
    spec = scenario.signalling_spec or {}
    lines = [
        rule("SCENARIO"),
        row("name", scenario.name),
        row("directory", os.path.basename(os.path.abspath(scenario.directory))),
        "  description        %s" % (scenario.description or "-"),
        row("window", "%s + %.0f min" % (format_clock(cfg.start_time_s),
                                         cfg.duration_s / 60.0)),
        row("timestep", "%.2f s" % cfg.dt),
        row("signalling", spec.get("system", "-")),
    ]
    for key in sorted(k for k in spec if k != "system"):
        lines.append(row(key.replace("_", " "), "%s" % spec[key]))
    described = describe_signalling(spec)
    if described:
        lines += ["", "  " + described]
    return lines


def describe_system(spec):
    """The signalling system this scenario configures, or None."""
    settings = {k: v for k, v in spec.items() if k != "system"}
    try:
        return signalling.create(spec.get("system", "fixed_block_3aspect"),
                                 **settings)
    except (KeyError, TypeError, ValueError):
        return None


def describe_signalling(spec):
    """What the system says about itself, margins and latencies included."""
    system = describe_system(spec)
    return system.describe() if system is not None else ""


# ------------------------------------------------------------------------ stock

def raw_specs(scenario):
    """The scenario and timetable files as written, not as built.

    Wanted for one thing: knowing which stock figures a scenario DECLARED and
    which the simulator filled in. A built RollingStock cannot say - by the time
    it exists, a derived mass and a declared one look identical - and getting
    that split wrong would make the rest of this report a guess.
    """
    source = scenario.source or os.path.join(scenario.directory, "scenario.yaml")
    spec = read_data_file(source)
    timetable = read_data_file(os.path.join(
        scenario.directory, spec.get("timetable", "timetable.yaml")))
    infra = read_data_file(os.path.join(
        scenario.directory, spec.get("infrastructure", "infrastructure.yaml")))
    return spec, timetable, infra


def declared_keys(timetable_spec, stock_id):
    """Which keys this unit actually carries in the timetable file."""
    for unit in (timetable_spec.get("stock") or []):
        if isinstance(unit, dict) and str(unit.get("id")) == str(stock_id):
            return set(unit)
    return set()


def stock_figures(stock):
    """``(key, label, value, derivation)`` for every figure a train obeys.

    ``key`` is the timetable key that would declare it, or None where nothing
    can - an adhesion ceiling is a consequence, not a setting.
    """
    m_eff = dynamics.effective_mass_kg(stock)
    factor = 1.0 + stock.rotating_mass_pct / 100.0
    return [
        ("length_m", "length", "%.0f m" % stock.length_m, ""),
        ("max_speed_kmh", "max speed", "%.0f km/h" % ms_to_kmh(stock.max_speed_ms),
         "a gearing limit, not a power one - see the traction curve"),
        ("max_accel", "max accel", "%.2f m/s2" % stock.max_accel,
         "what the driver may ask for at a stand"),
        ("service_brake", "service brake", "%.2f m/s2" % stock.service_brake, ""),
        ("emergency_brake", "emergency brake", "%.2f m/s2" % stock.emergency_brake,
         "degraded cases, and what a follower credits its leader with"),
        ("mass_t", "mass", "%.1f t" % stock.mass_t,
         "%.1f t/m x %.0f m" % (dynamics.MASS_T_PER_M, stock.length_m)),
        ("rotating_mass_pct", "rotating mass", "%.0f %%" % stock.rotating_mass_pct,
         "wheels, gears and armatures have to be spun up too"),
        (None, "effective mass", "%.1f t" % (m_eff / 1000.0),
         "%.1f t x %.2f - the mass in every f = ma here" % (stock.mass_t, factor)),
        (None, "starting effort", "%.1f kN" % (stock.starting_effort_n / 1000.0),
         "max_accel x effective mass"),
        (None, "base speed", "%.1f km/h" % ms_to_kmh(dynamics.base_speed_ms(stock)),
         "power / starting effort - where constant effort ends"),
        ("power_kw", "power", "%.1f kW" % stock.power_kw,
         "starting effort x %.0f %% of max speed"
         % (100.0 * dynamics.BASE_SPEED_FRACTION)),
        (None, "", "%.1f kW/t" % (stock.power_kw / stock.mass_t),
         "10-20 is the normal band for a unit of this kind"),
        ("davis_a_n", "davis A", "%.1f N" % stock.davis_a_n,
         "%.1f N/t x %.1f t - journal and rolling, barely varies"
         % (dynamics.DAVIS_A_N_PER_T, stock.mass_t)),
        ("davis_b_n_per_ms", "davis B", "%.2f N/(m/s)" % stock.davis_b_n_per_ms,
         "%.2f x %.1f t - flange and track, linear in speed"
         % (dynamics.DAVIS_B_N_PER_MS_PER_T, stock.mass_t)),
        ("davis_c_n_per_ms2", "davis C", "%.3f N/(m/s)2" % stock.davis_c_n_per_ms2,
         "%.1f + %.3f/m x %.0f m - drag, scales with length not mass"
         % (dynamics.DAVIS_C_N_PER_MS2_BASE,
            dynamics.DAVIS_C_N_PER_MS2_PER_M, stock.length_m)),
        ("adhesion", "adhesion mu", "%.2f" % stock.adhesion,
         "dry rail; the ceiling on any brake rate"),
        (None, "adhesion ceiling", "%.2f m/s2" % dynamics.adhesion_limit(stock),
         "mu x g - service brake uses %.0f %% of it"
         % (100.0 * stock.service_brake / dynamics.adhesion_limit(stock))),
        ("brake_buildup_s", "brake build-up", "%.1f s" % stock.brake_buildup_s,
         "a demand is not an application: air has to move"),
        (None, "jerk limit", "%.2f m/s3" % dynamics.jerk_limit_ms3(stock),
         "service brake / build-up time, applied to traction too"),
        ("etcs_level", "ETCS level", stock.etcs_level,
         "what the onboard can read"),
        ("tims", "integrity report", "yes" if stock.tims else "no",
         "can the train confirm its rear is still there"),
        ("v2v", "radio link", "yes" if stock.v2v else "no",
         "train to train - virtual coupling needs all three"),
    ]


def stock_section(stock, grades=(0.0,), declared=frozenset()):
    lines = ["", rule("ROLLING STOCK  %s  (%s)" % (stock.id, stock.name)), ""]

    figures = stock_figures(stock)
    given = [f for f in figures if f[0] in declared]
    derived = [f for f in figures if f[0] not in declared]

    lines.append("  DECLARED - what the timetable file actually says")
    for _, label, value, note in given:
        lines.append(row(label, value, note))
    lines.append("")
    lines.append("  DERIVED - filled in by RollingStock.__post_init__ and dynamics")
    for _, label, value, how in derived:
        lines.append(row(label, value, how))

    lines += constants_block(stock)
    lines += traction_table(stock)
    lines += resistance_table(stock)
    lines += braking_table(stock, grades)
    lines += gradient_block(stock, grades)
    return lines


def constants_block(stock):
    """The numbers that are not the train's and not the railway's.

    Every one of them is a modelling choice with a defence in dynamics.py, and
    every one of them moves a result, so they belong in a report that claims to
    say where a figure came from.
    """
    return [
        "",
        "  MODEL CONSTANTS - trainsim/core/dynamics.py, not declared anywhere",
        row("gravity", "%.5f m/s2" % dynamics.G),
        row("mass per metre", "%.1f t/m" % dynamics.MASS_T_PER_M,
            "a 23 m vehicle of 40-50 t is the usual shape"),
        row("base speed", "%.0f %% of v_max" % (100 * dynamics.BASE_SPEED_FRACTION),
            "where a unit given no power rating breaks from effort to power"),
        row("creep speed", "%.1f m/s" % dynamics._CREEP_MS,
            "below it P/v is meaningless, so starting effort applies"),
        row("davis A", "%.1f N/t" % dynamics.DAVIS_A_N_PER_T),
        row("davis B", "%.2f N/(m/s)/t" % dynamics.DAVIS_B_N_PER_MS_PER_T),
        row("davis C", "%.1f + %.3f per m"
            % (dynamics.DAVIS_C_N_PER_MS2_BASE, dynamics.DAVIS_C_N_PER_MS2_PER_M)),
        "",
        "  R(v) = %.1f + %.2f v + %.3f v^2   newtons, v in m/s"
        % (stock.davis_a_n, stock.davis_b_n_per_ms, stock.davis_c_n_per_ms2),
        "  m_eff a = F(v) - R(v) - m g sin(theta)   is the whole force balance",
    ]


def speeds_for(stock):
    """A ladder of speeds worth tabulating, base speed and line speed included."""
    top = ms_to_kmh(stock.max_speed_ms)
    wanted = {0.0, ms_to_kmh(dynamics._CREEP_MS), 20.0,
              ms_to_kmh(dynamics.base_speed_ms(stock)), 40.0,
              60.0, 80.0, 100.0, 120.0, 140.0, top}
    return sorted(v for v in wanted if v <= top + 1e-9)


def traction_table(stock):
    lines = [
        "",
        "  TRACTION - flat to base speed, then power-limited at P/v",
        "",
        "    %8s %10s %11s %10s %10s %11s"
        % ("km/h", "effort kN", "resist kN", "net kN", "accel", "0-v in s"),
        "    " + "-" * 64,
    ]
    for kmh in speeds_for(stock):
        v = kmh_to_ms(kmh)
        effort = dynamics.tractive_effort_n(stock, v)
        resist = dynamics.resistance_n(stock, v)
        accel = (dynamics.traction_accel(stock, v)
                 - dynamics.resistance_accel(stock, v))
        took, _ = run_up_to(stock, v)
        lines.append("    %8.1f %10.1f %11.2f %10.1f %10.3f %11s"
                     % (kmh, effort / 1000.0, resist / 1000.0,
                        (effort - resist) / 1000.0, accel,
                        "-" if took is None else "%.1f" % took))
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


def resistance_table(stock):
    """Davis in the units it is usually quoted in, plus what coasting does."""
    lines = [
        "",
        "  RESISTANCE - and what the train does with no traction and no brake",
        "",
        "    %8s %11s %10s %14s %16s"
        % ("km/h", "resist kN", "N per t", "coasting m/s2", "coasting to stop"),
        "    " + "-" * 62,
    ]
    for kmh in speeds_for(stock):
        if kmh <= 0.0:
            continue
        v = kmh_to_ms(kmh)
        resist = dynamics.resistance_n(stock, v)
        coast = dynamics.coasting_accel(stock, v)
        lines.append("    %8.1f %11.2f %10.1f %14.4f %14.0f m"
                     % (kmh, resist / 1000.0, resist / stock.mass_t, coast,
                        coast_to_stop(stock, v)))
    return lines


def coast_to_stop(stock, speed_ms, dt=0.5):
    """How far a train drifts before Davis alone brings it to rest, on the level."""
    v, x = speed_ms, 0.0
    while v > 0.05 and x < 1e6:
        v += dynamics.coasting_accel(stock, v) * dt
        x += max(v, 0.0) * dt
    return x


def gradient_block(stock, grades):
    """What a gradient is worth, in the units the force balance works in."""
    per = dynamics.grade_accel(stock, 10.0)
    worst = min(grades)
    lines = [
        "",
        "  GRADIENT",
        row("per 10 permille", "%.4f m/s2" % per,
            "g x 0.010 x mass / effective mass"),
        row("", "%.1f kN" % (per * dynamics.effective_mass_kg(stock) / 1000.0),
            "against %.1f kN of drag at line speed"
            % (dynamics.resistance_n(stock, stock.max_speed_ms) / 1000.0)),
    ]
    if worst < 0.0:
        rate = dynamics.braking_rate_on_grade(stock, worst)
        lines.append(row("steepest fall here", "%+g permille" % worst,
                         "service brake worth %.3f m/s2 instead of %.2f"
                         % (rate, stock.service_brake)))
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
    def header(grade):
        return "%+g permille" % grade if grade else "level"

    lines = [
        "",
        "  BRAKING - the driver's curve, which ignores Davis on purpose",
        "",
        "    %8s" % "km/h"
        + "".join("%14s" % header(g) for g in grades)
        + "%13s%12s" % ("emergency", "build-up m"),
        "    " + "-" * (8 + 14 * len(grades) + 25),
    ]
    for kmh in speeds_for(stock):
        if kmh <= 1.0:
            continue
        v = kmh_to_ms(kmh)
        cells = "".join(
            "%14.1f" % braking_distance(
                v, dynamics.braking_rate_on_grade(stock, g)) for g in grades)
        emergency = braking_distance(
            v, dynamics.braking_rate_on_grade(stock, 0.0, emergency=True))
        lines.append("    %8.1f%s%13.1f%12.1f"
                     % (kmh, cells, emergency,
                        dynamics.brake_buildup_distance_m(stock, v)))
    lines.append("")
    lines.append("    the emergency column is level track: it is what a follower "
                 "credits")
    lines.append("    the train in front with under relative-braking separation.")
    return lines


# ---------------------------------------------------------------- the authority

def standoff_block(scenario, stock, config):
    """The two standoffs, and their sum.

    There are two, they mean different things, and they stack - which is not
    obvious from a scenario file where one is under ``signalling:`` and the
    other under ``driver:``. The system decides where the danger point is; the
    driver decides how far short of it to stop.
    """
    system = describe_system(scenario.signalling_spec or {})
    at_the_system = getattr(system, "danger_point_margin_m", 0.0)
    lines = [
        "",
        "  STANDOFF - the two margins, which are different things and add up",
        row("signalling", "%.0f m" % at_the_system,
            "danger point put this far short of what it protects"
            if at_the_system else
            "fixed block protects a boundary the train is already clear of"),
        row("driver", "%.0f m" % config.safety_margin_m,
            "stops this far short of whatever danger point it was given"),
        row("total at rest", "%.0f m" % (at_the_system + config.safety_margin_m),
            "plus %.0f m of reaction distance at line speed"
            % (stock.max_speed_ms * config.reaction_time_s)),
    ]
    latency = getattr(system, "v2v_latency_s", None)
    if latency:
        lines.append(row("radio latency", "%.2f s" % latency,
                         "%.0f m at line speed, added to the signalling margin"
                         % (stock.max_speed_ms * latency)))
    fallback = getattr(system, "fallback_margin_m", None)
    if fallback is not None:
        lines.append(row("if the link fails", "%.0f m" % fallback,
                         "the tight margin is justified BY the link"))
    return lines


def driven_by_ato(system):
    """Whether this system drives the train rather than showing a driver a signal.

    Asked of the system rather than of the scenario's own reaction time: a
    scenario may declare 0.0 for its own reasons, and that would not make
    lineside signalling automatic.
    """
    reference = DriverConfig(reaction_time_s=2.0)
    return signalling.fit_driver(reference, system).reaction_time_s == 0.0


def authority_section(scenario, stock, grades):
    """The four terms that turn a speed into the room a train needs.

    This is the chain Driver.decide applies and the one scenario.checks sizes
    blocks against, so it is the number a signalling system is really arguing
    about. Two of the four belong to the driver rather than to the train, and
    one of those two - reaction time - is nil under ATO, which is where a good
    deal of what the cab systems are worth actually comes from.
    """
    config = scenario.driver_config
    system = scenario.signalling_spec.get("system", "fixed_block_3aspect")
    ato = signalling.fit_driver(config, system)
    worst = min(grades)
    columns = [("level m", 0.0, config)]
    if worst:
        columns.append(("on %+g m" % worst, worst, config))
    if ato.reaction_time_s != config.reaction_time_s:
        columns.append(("as driven m", worst, ato))
    lines = [
        "",
        "  MOVEMENT AUTHORITY NEEDED - braking + build-up + reaction + margin",
        "",
        "    %8s" % "km/h" + "".join("%14s" % head for head, _, _ in columns),
        "    " + "-" * (8 + 14 * len(columns)),
    ]
    for kmh in speeds_for(stock):
        if kmh <= 1.0:
            continue
        v = kmh_to_ms(kmh)
        lines.append("    %8.1f%s"
                     % (kmh, "".join("%14.1f" % stopping_distance(
                         stock, cfg, v, grade) for _, grade, cfg in columns)))
    lines += standoff_block(scenario, stock, config)
    lines += [
        "",
        row("driver reaction", "%.1f s" % config.reaction_time_s,
            "as the scenario declares it"),
        row("as driven", "%.1f s" % ato.reaction_time_s,
            "%s puts the authority on the desk - no signal to read"
            % system if driven_by_ato(system)
            else "%s is read from the lineside" % system),
        row("safety margin", "%.0f m" % config.safety_margin_m,
            "stood off every danger point"),
        row("stop tolerance", "%.1f m" % config.stop_tolerance_m,
            "how near the mark counts as berthed"),
        row("speed deadband", "%.2f m/s" % config.speed_deadband_ms,
            "avoids hunting around the target"),
    ]
    interlocking = scenario.interlocking_spec or {}
    if interlocking:
        lines.append("")
        lines.append("  INTERLOCKING")
        for key in sorted(interlocking):
            label = key
            for suffix in ("_m", "_s"):          # a unit, not part of the name
                if label.endswith(suffix):
                    label = label[:-len(suffix)]
            lines.append(row(label.replace("_", " ")[:18],
                             "%s" % interlocking[key]))
    return lines


# --------------------------------------------------------------- infrastructure

def infrastructure_section(scenario, infra_spec=None):
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
    ]
    defaults = (infra_spec or {}).get("defaults") or {}
    if defaults:
        lines.append("")
        lines.append("  DEFAULTS - what the drawing applies where a track says nothing")
        for key in sorted(defaults):
            label = key
            for suffix in ("_m", "_kmh", "_permille"):
                if label.endswith(suffix):
                    label = label[:-len(suffix)]
            lines.append(row(label.replace("_", " "), "%s" % defaults[key]))
    lines += [
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
    wanted = []
    for grade in (0.0, min(grades), max(grades)):
        if grade not in wanted:          # a level railway wants one column
            wanted.append(grade)
    return tuple(wanted)


def report(scenario):
    _, timetable_spec, infra_spec = raw_specs(scenario)
    lines = scenario_section(scenario)
    grades = notable_grades(scenario)
    seen = []
    for service in scenario.timetable.services:
        stock = service.stock
        if stock.id in seen:
            continue
        seen.append(stock.id)
        lines += stock_section(stock, grades,
                               declared_keys(timetable_spec, stock.id))
        lines += authority_section(scenario, stock, grades)
    lines += infrastructure_section(scenario, infra_spec)
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
