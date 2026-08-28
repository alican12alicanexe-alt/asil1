"""Run metrics, and the comparison between signalling systems.

Enough measurement to make the ERTMS comparison mean something. The figures are
the ones a capacity study reports:

**journey time**
    Origin departure to destination arrival, per service. The headline: does the
    signalling actually get trains there faster?
**time under restraint**
    Seconds a train spent with its speed held down by the signalling rather than
    by line speed or a booked stop. This is the direct cost of the train control
    system, and it is the number that should fall as the level goes up.
**minimum observed headway**
    The shortest gap between two different trains entering the same block. Not a
    design figure - it is what this timetable happened to achieve - but it is
    comparable across systems because the timetable is held constant.
**authority length**
    Mean distance a train was allowed to run to. Fixed block can only ever grant
    to a block boundary; moving block grants to the train in front. Watching this
    grow across the ladder is watching the mechanism, not just the outcome.

Blocking-time theory and UIC 406 compression belong here too and are not done
yet; these are the subset needed to compare train control systems honestly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.units import format_delay


@dataclass
class RunMetrics:
    """What one run of one scenario under one signalling system produced."""

    system: str
    description: str = ""
    services: int = 0
    completed: int = 0
    violations: int = 0

    journey_times: Dict[str, float] = field(default_factory=dict)
    delays: Dict[str, float] = field(default_factory=dict)
    restrained_s: Dict[str, float] = field(default_factory=dict)
    authority_samples: List[float] = field(default_factory=list)
    min_headway_s: Optional[float] = None
    min_headway_where: str = ""

    @property
    def mean_journey_s(self) -> float:
        if not self.journey_times:
            return 0.0
        return sum(self.journey_times.values()) / len(self.journey_times)

    @property
    def total_restrained_s(self) -> float:
        return sum(self.restrained_s.values())

    @property
    def mean_authority_m(self) -> float:
        if not self.authority_samples:
            return 0.0
        return sum(self.authority_samples) / len(self.authority_samples)

    @property
    def mean_delay_s(self) -> float:
        if not self.delays:
            return 0.0
        return sum(self.delays.values()) / len(self.delays)


#: Reasons that mean "the signalling is holding this train back", as opposed to
#: line speed or a booked stop. Matched as substrings of the governing reason.
RESTRAINT_MARKERS = (
    "caution", "danger", "block", "rear of", "no route",
    "vss", ".1 ", ".2 ", ".3 ", ".4 ",
    # Virtual coupling words the same thing its own way: a train held down
    # behind the one in front, whether over the link or on absolute braking
    # distance once the link is gone. Without these the column reads near zero
    # under virtual coupling and the system looks free of a cost it is paying.
    "coupled to", "absolute distance",
)


def measure(sim, description: str = "") -> RunMetrics:
    """Run ``sim`` to completion, collecting metrics as it goes."""
    metrics = RunMetrics(system=sim.signalling.name,
                         description=description or sim.signalling.describe())

    last_entry: Dict[str, tuple] = {}     # block -> (train, time)
    previously_in: Dict[str, set] = {}

    while not sim.finished:
        sim.step()

        for train in sim.trains.values():
            if train.state != "running":
                continue
            reason = (train.authority_reason or "").lower()
            if any(marker in reason for marker in RESTRAINT_MARKERS):
                metrics.restrained_s[train.id] = (
                    metrics.restrained_s.get(train.id, 0.0) + sim.dt
                )
            if train.last_authority_m is not None:
                metrics.authority_samples.append(train.last_authority_m)

        # Headway: time between different trains entering the same block.
        for block_id in sim.blocks:
            here = sim.occupancy.trains_in(block_id)
            before = previously_in.get(block_id, set())
            for train_id in here - before:
                previous = last_entry.get(block_id)
                if previous is not None and previous[0] != train_id:
                    gap = sim.time_s - previous[1]
                    if metrics.min_headway_s is None or gap < metrics.min_headway_s:
                        metrics.min_headway_s = gap
                        metrics.min_headway_where = "%s behind %s at %s" % (
                            train_id, previous[0], block_id)
                last_entry[block_id] = (train_id, sim.time_s)
            previously_in[block_id] = set(here)

    metrics.services = len(sim.trains)
    metrics.violations = len(sim.violations)
    for train in sim.trains.values():
        if train.state == "finished":
            metrics.completed += 1
        if train.entered_s is not None and train.finished_s is not None:
            metrics.journey_times[train.id] = (
                train.finished_s - train.origin_departure_s
            )
        metrics.delays[train.id] = train.delay_s
    return metrics


def compare_table(results: List[RunMetrics]) -> str:
    """A side-by-side report, with the first row as the baseline."""
    if not results:
        return "nothing to compare"

    baseline = results[0]
    header = ("%-22s %9s %9s %10s %9s %8s %6s"
              % ("signalling", "journey", "vs base", "restrained", "min hdwy",
                 "auth m", "done"))
    lines = [header, "-" * len(header)]

    for row in results:
        delta = row.mean_journey_s - baseline.mean_journey_s
        lines.append(
            "%-22s %9s %9s %10s %9s %8s %6s"
            % (
                row.system,
                _mmss(row.mean_journey_s),
                "-" if row is baseline else format_delay(delta),
                "%.0fs" % row.total_restrained_s,
                ("%.0fs" % row.min_headway_s) if row.min_headway_s else "-",
                ("%.0f" % row.mean_authority_m) if row.authority_samples else "-",
                "%d/%d" % (row.completed, row.services),
            )
        )

    lines.append("")
    lines.append("journey    mean origin-to-destination time over all services")
    lines.append("restrained total seconds trains spent held down by signalling")
    lines.append("min hdwy   shortest gap between two trains entering one block")
    lines.append("auth m     mean length of movement authority granted")

    problems = [r for r in results if r.violations or r.completed != r.services]
    for row in problems:
        lines.append("  WARNING %s: %d violations, %d/%d completed"
                     % (row.system, row.violations, row.completed, row.services))
    return "\n".join(lines)


def _mmss(seconds: float) -> str:
    if not seconds:
        return "-"
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)
