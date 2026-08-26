"""Delay propagation: what one thing going wrong costs the rest of the railway.

A disturbed run on its own says very little. The useful figure is the
*difference* between the disturbed run and the same railway working to plan, so
this module runs the scenario twice - once with its declared disruptions and once
with none - and subtracts, service by service.

That difference splits in two, and the split is the whole point:

**primary delay**
    Time lost by a service the disruption was applied to. A four-minute dwell
    overrun costs that train four minutes; nothing surprising, and nothing a
    signalling system or a dispatcher can prevent.
**knock-on delay** (also called reactionary delay)
    Time lost by services the disruption was *not* applied to, purely because
    they were behind or in the way. This is the part that is a property of the
    railway rather than of the incident, and it is the part better signalling,
    more slack, or a smarter dispatcher can actually reduce.

The ratio between them - seconds of knock-on per second of primary - is the
number performance analysts care about, because it says how much a railway
amplifies its own incidents. Below about 1 the railway absorbs disturbance; well
above it, one incident buys several.

Being a difference between two runs, this needs the kernel to be deterministic.
It is: a test asserts that two runs of a scenario land on identical positions.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ..core.units import format_delay


@dataclass
class ServiceImpact:
    """What one service lost, and whether it was the one that was hit."""

    service: str
    clean_journey_s: float
    disrupted_journey_s: float
    #: True if a disruption was applied to this service directly.
    directly_hit: bool

    @property
    def extra_s(self) -> float:
        return self.disrupted_journey_s - self.clean_journey_s


@dataclass
class Propagation:
    """The comparison between a clean run and a disturbed one."""

    scenario: str
    system: str
    description: str
    impacts: List[ServiceImpact] = field(default_factory=list)
    #: Services that ran clean but did not complete when disrupted, or vice
    #: versa - a run that gridlocked rather than merely lost time.
    incomplete: List[str] = field(default_factory=list)

    @property
    def primary_s(self) -> float:
        return sum(max(0.0, i.extra_s) for i in self.impacts if i.directly_hit)

    @property
    def knock_on_s(self) -> float:
        return sum(max(0.0, i.extra_s) for i in self.impacts if not i.directly_hit)

    @property
    def total_s(self) -> float:
        return self.primary_s + self.knock_on_s

    @property
    def mean_clean_journey_s(self) -> float:
        if not self.impacts:
            return 0.0
        return sum(i.clean_journey_s for i in self.impacts) / len(self.impacts)

    @property
    def mean_disrupted_journey_s(self) -> float:
        """What the trains actually did on the day, not the loss against plan.

        Load-bearing, because knock-on delay is measured against each system's
        *own* clean run. A system whose clean run is already slow has less left
        to lose, so it scores well on propagation while still delivering the
        worse railway - which means the relative figure has to be read next to
        the absolute one, or it will rank the better system lower.
        """
        if not self.impacts:
            return 0.0
        return sum(i.disrupted_journey_s for i in self.impacts) / len(self.impacts)

    @property
    def affected(self) -> List[ServiceImpact]:
        """Services that lost more than a second, worst first."""
        return sorted((i for i in self.impacts if i.extra_s > 1.0),
                      key=lambda i: -i.extra_s)

    @property
    def multiplier(self) -> Optional[float]:
        """Seconds of knock-on delay per second of primary delay."""
        if self.primary_s <= 0.0:
            return None
        return self.knock_on_s / self.primary_s


def directly_hit_services(disruptions, timetable, network) -> Set[str]:
    """Which services a disruption was applied to, rather than merely reached.

    A late start or a dwell overrun names its service. A temporary speed
    restriction names none - it is a change to the railway, and every train whose
    path runs over the restricted stretch meets it head-on rather than
    reactively. Those trains count as directly hit too, or the report would
    attribute an infrastructure restriction to propagation and make the railway
    look worse than it is.
    """
    hit = {d.service for d in disruptions.late_starts}
    hit |= {d.service for d in disruptions.dwell_overruns}

    if disruptions.speed_restrictions:
        for service in timetable.services:
            for segment_id in service.path.segment_ids:
                segment = network.segments[segment_id]
                low = min(segment.km_start, segment.km_end)
                high = max(segment.km_start, segment.km_end)
                for restriction in disruptions.speed_restrictions:
                    if not restriction.applies_to_track(segment.track):
                        continue
                    if high >= restriction.low_km and low <= restriction.high_km:
                        hit.add(service.id)
                        break
                else:
                    continue
                break
    return hit


def measure_propagation(scenario, build_simulation, system: Optional[str] = None,
                        overrides: Optional[dict] = None) -> Propagation:
    """Run ``scenario`` clean and disrupted, and account for the difference."""
    if not scenario.disruptions:
        raise ValueError(
            "%s declares no disruptions, so there is nothing to propagate - add "
            "a disruptions: block to the scenario file" % (scenario.name,)
        )

    spec = dict(scenario.signalling_spec)
    if system is not None:
        spec = {"system": system}
    scenario.signalling_spec = spec

    clean = _journey_times(scenario, build_simulation,
                           dict(overrides or {}, undisrupted=True))
    disrupted_sim, disrupted = _journey_times(
        scenario, build_simulation, dict(overrides or {}), return_sim=True)

    hit = directly_hit_services(scenario.disruptions, scenario.timetable,
                               scenario.infrastructure.network)

    result = Propagation(
        scenario=scenario.name,
        system=disrupted_sim.signalling.name,
        description=scenario.disruptions.describe(),
    )
    for service_id in sorted(set(clean) | set(disrupted)):
        if service_id not in clean or service_id not in disrupted:
            result.incomplete.append(service_id)
            continue
        result.impacts.append(ServiceImpact(
            service=service_id,
            clean_journey_s=clean[service_id],
            disrupted_journey_s=disrupted[service_id],
            directly_hit=service_id in hit,
        ))
    return result


def _journey_times(scenario, build_simulation, overrides, return_sim=False):
    sim = build_simulation(scenario, overrides)
    sim.run()
    times: Dict[str, float] = {}
    for train in sim.trains.values():
        if train.finished_s is not None:
            times[train.id] = train.finished_s - train.origin_departure_s
    return (sim, times) if return_sim else times


def report(result: Propagation) -> str:
    """A readable account of where the time went."""
    lines = [
        "delay propagation - %s under %s" % (result.scenario, result.system),
        "",
        "  what went wrong: %s" % result.description,
        "",
    ]

    header = "  %-6s %9s %10s %9s  %s" % (
        "service", "clean", "disrupted", "extra", "")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    affected = result.affected
    if not affected:
        lines.append("  nothing lost more than a second")
    for impact in affected:
        lines.append("  %-6s %9s %10s %9s  %s" % (
            impact.service,
            _mmss(impact.clean_journey_s),
            _mmss(impact.disrupted_journey_s),
            format_delay(impact.extra_s) if abs(impact.extra_s) >= 30
            else "+%.0fs" % impact.extra_s,
            "primary" if impact.directly_hit else "knock-on",
        ))

    untouched = len(result.impacts) - len(affected)
    if untouched:
        lines.append("  %d other service%s ran unaffected"
                     % (untouched, "" if untouched == 1 else "s"))

    lines.append("")
    lines.append("  primary delay    %6.0f s   (the incident itself)"
                 % result.primary_s)
    lines.append("  knock-on delay   %6.0f s   (everything it got in the way of)"
                 % result.knock_on_s)
    if result.multiplier is not None:
        lines.append("  propagation      %6.2f s of knock-on per second of primary"
                     % result.multiplier)
    if result.incomplete:
        lines.append("  INCOMPLETE: %s did not finish in both runs"
                     % ", ".join(result.incomplete))
    return "\n".join(lines)


def compare_systems(results: List[Propagation]) -> str:
    """How much knock-on each signalling system produced from the same incident.

    Primary delay is a property of the incident and barely moves between systems.
    Knock-on is a property of the railway, so this is the table that says whether
    better train control makes a line more resilient as well as more capacious.
    """
    if not results:
        return "nothing to compare"
    header = "%-22s %9s %9s %14s %9s %11s" % (
        "signalling", "primary", "knock-on", "per s primary", "clean",
        "on the day")
    lines = [header, "-" * len(header)]
    for row in results:
        lines.append("%-22s %8.0fs %8.0fs %14s %9s %11s" % (
            row.system, row.primary_s, row.knock_on_s,
            "-" if row.multiplier is None else "%.2f" % row.multiplier,
            _mmss(row.mean_clean_journey_s),
            _mmss(row.mean_disrupted_journey_s),
        ))
    lines.append("")
    lines.append("Read the last two columns with the first three. Knock-on is measured")
    lines.append("against each system's *own* clean run, so a system that was already")
    lines.append("slow has less left to lose: it can score well on propagation while")
    lines.append("still delivering the worse railway on the day.")
    return "\n".join(lines)


def _mmss(seconds: float) -> str:
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)
