"""Design checks on a scenario, run by ``--check`` and before every run.

The check that matters for a fixed-block railway is **signal spacing against
braking distance**. Under three-aspect signalling a driver gets exactly one
block of warning: they pass a yellow, and must stop at the next signal. So

    block length  >=  braking distance from line speed
                      + distance run during the driver's reaction
                      + the standing margin short of the signal

If that fails, the layout is not signalable as drawn - trains would pass signals
at danger - and the simulation would be modelling a railway that could not be
built. Rather than let that pass silently, it is reported.

The opposite constraint is capacity, and it is not a safety rule so it is not
enforced here. It is reported as the **all-green headway**: the closest two
trains may follow each other with the second one never seeing anything but a
green signal.

That is the figure a timetable is actually written to. Braking for a yellow is a
degraded state - it means the plan has already failed - so a railway is not
planned to the point where trains can just about stop in time, it is planned to
the point where they never have to slow down at all. What that costs is a whole
train's worth of railway standing empty ahead of every train:

    all-green headway  =  ( two block sections
                            + the train's own length
                            + the distance at which a driver reads a signal )
                          / line speed

Two sections, because the follower may only run unchecked from behind a green,
and a signal shows green only when the section beyond the one it protects is
also clear. So a train "uses up" two sections of railway rather than the one it
is standing in - which is exactly why halving block length nearly halves the
headway, and why real block lengths are not uniform. They are short on station
approaches, where speeds are low and capacity is wanted, and long on fast open
line. Scenario files can set ``block_length_m`` per stretch to reflect that.

This is the *theoretical* figure: it is what the signal spacing allows, and it
assumes the only thing in a train's way is the train in front. Anywhere trains
stand - a platform, a depot road, a terminal - reoccupation binds first and the
line will not hold it. The measured figure, which is the one to believe, comes
from running the flight: see ``scenarios/depotline/_sweep_headway.py``.

Four-aspect signalling, which gives two blocks of warning and so permits blocks
*shorter* than braking distance, is a Phase 3 addition alongside the ETCS levels.
"""

from dataclasses import dataclass
from typing import List, Optional

from ..core import dynamics
from ..core.units import braking_distance, format_clock, ms_to_kmh


@dataclass
class BlockCheck:
    """The outcome of checking one block section."""

    block_id: str
    track: str
    length_m: float
    line_speed_ms: float
    required_m: float
    worst_stock: str
    #: All-green headway this section implies: the closest two trains may
    #: follow one another through it with the second never checked by a signal.
    headway_s: float
    #: Steepest fall in the section, per thousand. Zero on a level railway, and
    #: the reason ``required_m`` is longer than the level-track curve when not.
    grade_permille: float = 0.0

    @property
    def ok(self) -> bool:
        return self.length_m >= self.required_m

    @property
    def margin_m(self) -> float:
        return self.length_m - self.required_m


def check_block_lengths(infrastructure, timetable, driver_config,
                        aspects: int = 3,
                        sighting_distance_m: float = 0.0) -> List[BlockCheck]:
    """Check every running block against the braking distance rule.

    ``aspects`` is how many indications the signalling shows: three gives one
    block of warning, four gives two, so a four-aspect layout may use blocks
    roughly half as long.

    ``sighting_distance_m`` is how far off a driver reads a signal, and it is
    part of the all-green headway rather than of the safety rule: a follower has
    not run unchecked if it *sighted* a yellow, even one that cleared before it
    got there. Left at zero the headway is the bare block-and-train figure.
    """
    warning_blocks = max(1, aspects - 2)
    results = []

    for block in infrastructure.blocks.values():
        # Platform roads are checked too. It is tempting to skip them on the
        # grounds that a train stopping there brakes anyway - but a train running
        # *through* a platform does not, and its exit signal can be at danger,
        # so the section still has to be long enough to brake in.
        # The fastest a train may be going anywhere in this block, because that
        # is what it has to be able to stop from. Taking the first segment was
        # right while a block held exactly one; a block split by a speed limit
        # holds several, and the tightest of them is not the one that binds.
        line_speed = max(infrastructure.network.segments[seg_id].max_speed_ms
                         for seg_id in block.segment_ids)
        # The gradient a train braking in this section is on. The steepest fall
        # decides, because that is the one that takes rate away from the brake
        # and so asks for the longest section.
        grade = min(infrastructure.network.segments[seg_id].grade_permille
                    for seg_id in block.segment_ids)

        required = 0.0
        worst = "-"
        for service in timetable.services:
            stock = service.stock
            speed = min(stock.max_speed_ms, line_speed)
            needed = (
                braking_distance(
                    speed, dynamics.braking_rate_on_grade(stock, grade))
                + dynamics.brake_buildup_distance_m(stock, speed)
                + speed * driver_config.reaction_time_s
                + driver_config.safety_margin_m
            ) / float(warning_blocks)
            if needed > required:
                required, worst = needed, stock.id

        top_speed = max(
            (min(s.stock.max_speed_ms, line_speed) for s in timetable.services),
            default=line_speed,
        )
        longest_train = max((s.stock.length_m for s in timetable.services), default=0.0)
        # Two sections, because a green means the section beyond the one the
        # signal protects is clear too; plus the train's own length, which has
        # to leave the second section before the signal behind it clears; plus
        # the sighting distance, because a follower that read a yellow was
        # checked whether or not it had to brake.
        headway = ((2.0 * block.length_m + longest_train + sighting_distance_m)
                   / top_speed if top_speed > 0 else float("inf"))

        results.append(BlockCheck(
            block_id=block.id,
            track=block.track,
            length_m=block.length_m,
            line_speed_ms=line_speed,
            required_m=required,
            worst_stock=worst,
            headway_s=headway,
            grade_permille=grade,
        ))
    return results


def failures(results: List[BlockCheck]) -> List[BlockCheck]:
    return [r for r in results if not r.ok]


def summarise(results: List[BlockCheck], aspects: int = 3) -> str:
    """A short report, grouped by track."""
    if not results:
        return "no running blocks to check"

    lines = [
        "signal spacing (%d-aspect, %d block%s of warning)"
        % (aspects, max(1, aspects - 2), "" if aspects == 3 else "s"),
    ]
    tracks = sorted({r.track for r in results})
    for track in tracks:
        rows = [r for r in results if r.track == track]
        tightest = min(rows, key=lambda r: r.margin_m)
        lines.append(
            "  %-4s %2d blocks  %.0f-%.0f m   needs >= %.0f m (%s)   "
            "tightest margin %+.0f m"
            % (track, len(rows), min(r.length_m for r in rows),
               max(r.length_m for r in rows), tightest.required_m,
               tightest.worst_stock, tightest.margin_m)
        )
        binding = max(rows, key=lambda r: r.headway_s)
        lines.append(
            "       all-green headway %.0f-%.0f s at %.0f km/h; %s sets it at "
            "%.0f s (%.1f trains/hour)"
            % (min(r.headway_s for r in rows), max(r.headway_s for r in rows),
               ms_to_kmh(max(r.line_speed_ms for r in rows)),
               binding.block_id, binding.headway_s, 3600.0 / binding.headway_s)
        )
        # Only worth saying on a railway that has gradients, and worth saying
        # loudly there: a falling gradient is why a section that looks long
        # enough on the level is not.
        steepest = min(r.grade_permille for r in rows)
        if steepest < 0.0:
            lines.append(
                "       steepest fall %.0f per thousand, allowed for above"
                % (steepest,)
            )

    bad = failures(results)
    lines.append(
        "  all-green headway is what the signal spacing allows with nothing in "
        "the way but the train in front."
    )
    lines.append(
        "  Anywhere a train stands - a platform, a depot road - reoccupation "
        "binds first and the line will not hold it."
    )
    if bad:
        lines.append("  UNSIGNALABLE: %d block(s) shorter than braking distance" % len(bad))
        for row in bad[:5]:
            lines.append(
                "    %-10s %.0f m < %.0f m required (worst stock %s)"
                % (row.block_id, row.length_m, row.required_m, row.worst_stock)
            )
    return "\n".join(lines)


def warn_if_unsignalable(scenario, driver_config=None) -> Optional[str]:
    """Return a warning message if any block is too short, else ``None``."""
    results = check_block_lengths(
        scenario.infrastructure, scenario.timetable,
        driver_config or scenario.driver_config,
    )
    bad = failures(results)
    if not bad:
        return None
    return (
        "warning: %d block section(s) are shorter than the braking distance from "
        "line speed, so a train passing a yellow could not stop at the next "
        "signal. Run with --check for detail." % (len(bad),)
    )


def fitment_note(scenario, signalling) -> Optional[str]:
    """What this fleet can actually be worked by, under this signalling system.

    A distance-separated system follows the *rear* of the train in front, so a
    train that cannot confirm its own integrity cannot be followed by one: the
    system falls back to block granularity behind it and behaves exactly like the
    fixed-block railway it was meant to replace. Virtual coupling needs the
    train-to-train link on top of that.

    Both degrades are correct, and both are silent. Silent is the problem - on
    screen it looks identical to moving block simply not working, which is what
    this line exists to say out loud.
    """
    if getattr(signalling, "separates_by", "block") != "distance":
        return None

    services = scenario.timetable.services
    if not services:
        return None
    total = len(services)
    no_tims = sum(1 for s in services if not s.stock.tims)
    no_v2v = sum(1 for s in services if not getattr(s.stock, "v2v", False))
    wants_v2v = bool(getattr(signalling, "permits_relative_braking", False))

    if no_tims == 0 and not (wants_v2v and no_v2v):
        return "fleet          : fitted throughout - separation is by distance"

    bits = []
    if no_tims:
        bits.append("%d of %d cannot confirm their own integrity (tims)" % (no_tims, total))
    if wants_v2v and no_v2v:
        bits.append("%d of %d have no train-to-train link (v2v)"
                    % (no_v2v, total))
    worst = "block granularity" if no_tims else "absolute braking distance"
    return ("fleet          : %s - a train following one of those falls back to "
            "%s" % ("; ".join(bits), worst))


def warn_about_fitment(scenario, signalling) -> Optional[str]:
    """The same thing as a warning, for a run that is about to look wrong."""
    note = fitment_note(scenario, signalling)
    if note is None or "fitted throughout" in note:
        return None
    return ("warning: %s separates trains by distance, but this fleet is not "
            "fitted for it - %s. Trains will keep a block apart and the run will "
            "look like fixed block, correctly. Set tims%s on the stock in the "
            "timetable to see the system work."
            % (getattr(signalling, "name", "this system"),
               note.split(" : ", 1)[-1].strip(),
               " and v2v" if getattr(signalling, "permits_relative_braking", False)
               else ""))


# --------------------------------------------------------------- the timetable

@dataclass
class TimetableIssue:
    """Something wrong with the plan, as opposed to with the railway."""

    kind: str            # "impossible" | "clash" | "ordering" | "too long"
    service: str
    detail: str

    def __str__(self) -> str:
        return "%-10s %-6s %s" % (self.kind, self.service, self.detail)


def minimum_leg_time_s(service, from_stop, to_stop) -> float:
    """A *lower bound* on the time between two calls. Not a prediction.

    Two things bound it, and the larger wins:

    **speed limits** - the train cannot exceed the limit on any piece of track it
    covers, so the leg takes at least the sum of each piece's length over its own
    limit.
    **starting and stopping** - it begins at rest and ends at rest, so even with
    no speed limit at all it cannot beat the triangular acceleration profile.

    Deliberately optimistic: no signalling, no reaction time, no margin, full
    power throughout. Anything it flags is therefore impossible for reasons of
    physics rather than merely difficult, which is the only kind of claim worth
    making from a bound.
    """
    start = from_stop.stop_chainage_m
    end = to_stop.stop_chainage_m
    distance = end - start
    if distance <= 0:
        return 0.0

    stock = service.stock
    at_limits = 0.0
    for entry in service.path.entries:
        overlap = min(entry.end_m, end) - max(entry.start_m, start)
        if overlap <= 0:
            continue
        speed = min(entry.segment.max_speed_ms, stock.max_speed_ms)
        if speed <= 0:
            return float("inf")
        at_limits += overlap / speed

    return max(at_limits, _flat_out_run_s(stock, distance))


def _flat_out_run_s(stock, distance_m: float, dt: float = 0.5) -> float:
    """Time to cover ``distance_m`` from rest to rest, flat out and unopposed.

    The old bound here assumed the train could hold ``max_accel`` all the way to
    line speed, which is a claim no real traction system makes and which this
    simulator no longer makes either: above base speed the effort falls as power
    over speed. Integrating the actual traction curve gives a bound that is both
    tighter and true.

    Still deliberately optimistic - no resistance, no gradient, no brake
    build-up, no signalling, and the brake applied on the instant it is wanted -
    so anything it flags is impossible on physics rather than merely hard.
    """
    speed = 0.0
    covered = 0.0
    elapsed = 0.0
    ceiling = stock.max_speed_ms
    #: A day is longer than any leg anyone will book; the guard is there so a
    #: pathological stock cannot spin here rather than because it can happen.
    while covered < distance_m and elapsed < 86400.0:
        remaining = distance_m - covered
        approach = (2.0 * stock.service_brake * remaining) ** 0.5
        target = min(ceiling, approach)
        if speed < target:
            speed = min(target, speed + dynamics.traction_accel(stock, speed) * dt)
        else:
            speed = target
        if speed <= 0.0:
            break
        covered += speed * dt
        elapsed += dt
    return elapsed


def check_timetable(infrastructure, timetable) -> List["TimetableIssue"]:
    """Check the plan against physics and against itself.

    ``--check`` used to validate only the railway, which meant a timetable
    booking a train to do 30 km in four minutes loaded happily and then simply
    reported the train as late. That is a plan which was never workable being
    reported as a railway that cannot cope, and the two want telling apart.
    """
    issues = []
    issues.extend(_check_ordering_and_physics(timetable))
    issues.extend(_check_platform_clashes(timetable))
    issues.extend(_check_platform_lengths(infrastructure, timetable))
    return issues


def _check_platform_lengths(infrastructure, timetable):
    """Services booked to call where the platform is shorter than the train.

    ``length_m`` on a platform is the concrete a train stands alongside, and it
    is a different thing from ``platform_zone_m``, which is the block section the
    road occupies. The zone is sized for braking and is always the longer of the
    two; the platform is sized for the train, and a unit booked to call at a road
    it does not fit is a real timetabling fault - passengers at the back of the
    train step out onto ballast, and in practice the call is either selective-door
    or it does not happen.
    """
    platforms = infrastructure.network.platforms
    issues = []
    for service in timetable.services:
        train_m = service.stock.length_m
        for stop in service.stops:
            platform = platforms.get(stop.platform)
            if platform is None or platform.length_m >= train_m:
                continue
            issues.append(TimetableIssue(
                "too long", service.id,
                "%s at %s is %.0f m of train in a %.0f m platform (%s)"
                % (service.stock.id, stop.station, train_m,
                   platform.length_m, stop.platform)))
    return issues


def _check_ordering_and_physics(timetable):
    issues = []
    for service in timetable.services:
        previous = None
        for stop in service.stops:
            if (stop.arrival_s is not None and stop.departure_s is not None
                    and stop.departure_s < stop.arrival_s):
                issues.append(TimetableIssue(
                    "ordering", service.id,
                    "%s is booked away at %s, before it arrives at %s"
                    % (stop.station, format_clock(stop.departure_s),
                       format_clock(stop.arrival_s))))
            elif (stop.arrival_s is not None and stop.departure_s is not None
                  and stop.departure_s - stop.arrival_s < stop.min_dwell_s - 1e-6):
                issues.append(TimetableIssue(
                    "ordering", service.id,
                    "%s is booked a %.0f s stand but needs dwell_s %.0f"
                    % (stop.station, stop.departure_s - stop.arrival_s,
                       stop.min_dwell_s)))

            if previous is not None and stop.arrival_s is not None:
                away = previous.departure_s
                if away is None:
                    away = previous.arrival_s
                if away is not None:
                    booked = stop.arrival_s - away
                    if booked < 0:
                        issues.append(TimetableIssue(
                            "ordering", service.id,
                            "%s is booked before %s"
                            % (stop.station, previous.station)))
                    else:
                        needed = minimum_leg_time_s(service, previous, stop)
                        if booked < needed - 1.0:
                            issues.append(TimetableIssue(
                                "impossible", service.id,
                                "%s to %s booked in %.0f s; %.0f s is the "
                                "fastest the train can physically do it"
                                % (previous.station, stop.station, booked,
                                   needed)))
            previous = stop
    return issues


def _check_platform_clashes(timetable):
    """Two services booked into one platform road at the same time.

    The dispatcher copes with this - it holds the second train out - so it never
    shows up as a fault, only as unexplained delay. Which is exactly why it is
    worth saying out loud before the run rather than after it.
    """
    windows = {}
    for service in timetable.services:
        for index, stop in enumerate(service.stops):
            window = _occupancy_window(service, stop, index)
            if window is not None:
                windows.setdefault(stop.platform, []).append(
                    (window[0], window[1], service.id))

    issues = []
    for platform, entries in sorted(windows.items()):
        entries.sort()
        for first, second in zip(entries, entries[1:]):
            if second[0] < first[1] - 1e-6:
                issues.append(TimetableIssue(
                    "clash", second[2],
                    "wants %s at %s, but %s is booked there until %s"
                    % (platform, format_clock(second[0]), first[2],
                       format_clock(first[1]))))
    return issues


def _occupancy_window(service, stop, index):
    """When this call has the platform road, as booked."""
    if index == 0:
        # The train is berthed before its departure time, not at it.
        away = stop.departure_s if stop.departure_s is not None else service.departure_s
        return (away - service.ready_lead_s, away)
    arrival, departure = stop.arrival_s, stop.departure_s
    if arrival is None and departure is None:
        return None
    if arrival is None:
        arrival = departure
    if departure is None:
        departure = arrival + stop.min_dwell_s
    return (arrival, departure)


def summarise_timetable(issues, services: int) -> str:
    """Two sections, because the two kinds of finding mean different things.

    An *impossible* leg or an out-of-order call is a broken plan: no railway and
    no signalling system can run it, and it wants fixing before anything else is
    measured. A *clash* is not broken at all - it is two trains booked to want
    the same platform road, which is a conflict somebody has to resolve. Today
    the dispatcher resolves it by holding the second train out, which is why it
    has always shown up as unexplained delay rather than as a decision. Saying it
    before the run is the difference between a plan that cannot work and a plan
    that needs managing.
    """
    broken = [i for i in issues if i.kind != "clash"]
    clashes = [i for i in issues if i.kind == "clash"]

    if not broken:
        lines = ["timetable      : %d services, workable as booked - no leg is "
                 "faster than physics allows" % (services,)]
    else:
        lines = ["timetable      : %d services, %d UNWORKABLE"
                 % (services, len(broken))]
        for issue in broken[:12]:
            lines.append("  %s" % (issue,))
        if len(broken) > 12:
            lines.append("  ... and %d more" % (len(broken) - 12,))

    if clashes:
        lines.append("")
        lines.append("booked platform conflicts (%d) - not faults; the dispatcher"
                     % (len(clashes),))
        lines.append("holds the second train out, and this is what that costs:")
        for issue in clashes[:8]:
            lines.append("  %s" % (issue,))
        if len(clashes) > 8:
            lines.append("  ... and %d more" % (len(clashes) - 8,))
    return "\n".join(lines)


def warn_about_timetable(scenario):
    """Return a warning if the plan itself is unworkable, else ``None``.

    Platform clashes deliberately do not warn: they are a normal feature of a
    timetable that is being worked hard, and warning about them on every run
    would train the reader to ignore the warnings that matter.
    """
    issues = [i for i in check_timetable(scenario.infrastructure,
                                         scenario.timetable)
              if i.kind != "clash"]
    if not issues:
        return None
    return ("warning: %d leg(s) of this timetable cannot be run by the trains "
            "booked to run them, whatever the signalling does. Run with --check "
            "for detail." % (len(issues),))
