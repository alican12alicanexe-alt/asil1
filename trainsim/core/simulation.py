"""The simulation kernel: a fixed-timestep sense / decide / move / update loop.

One tick, in order:

1. **Dispatch** - introduce services, start and end dwells, terminate arrivals.
2. **Sense** - each running train observes the signalling and receives a movement
   authority, all computed against the *same* occupancy snapshot so the result
   does not depend on the order trains happen to be stored in.
3. **Decide and move** - the driver turns the authority into an acceleration and
   the train integrates one step.
4. **Update** - occupancy and signal aspects are rebuilt, and the block
   exclusivity invariant is checked.

The kernel is deterministic and holds no reference to any concrete signalling
system or dispatch policy, only to the interfaces.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .disruption import DisruptedSpeedLimits, Disruptions
from .network import Network
from .signals import Aspect, BlockSection, Occupancy, Signal, compute_aspects
from .train import Train, nearest_ahead
from .units import format_clock, format_delay, ms_to_kmh


@dataclass
class SimConfig:
    """Kernel settings, from the scenario file."""

    dt: float = 1.0
    start_time_s: float = 0.0
    duration_s: float = 3600.0
    #: Raise on a block-exclusivity violation instead of only logging it.
    strict: bool = False
    seed: int = 0


@dataclass
class Event:
    """One entry in the run log."""

    time_s: float
    kind: str
    train_id: Optional[str]
    detail: str

    def __str__(self) -> str:
        who = self.train_id or "-"
        return "%s  %-12s %-8s %s" % (
            format_clock(self.time_s), self.kind, who, self.detail,
        )


class Simulation(object):
    """Holds all mutable state and advances it one tick at a time."""

    def __init__(self, network: Network, blocks: Dict[str, BlockSection],
                 signals: Dict[str, Signal], block_of_segment: Dict[str, str],
                 signalling, dispatcher, driver, config: Optional[SimConfig] = None,
                 interlocking=None, disruptions: Optional[Disruptions] = None):
        self.network = network
        self.blocks = blocks
        self.signals = signals
        self.block_of_segment = block_of_segment
        self.signalling = signalling
        self.dispatcher = dispatcher
        self.driver = driver
        self.interlocking = interlocking
        self.config = config or SimConfig()
        #: What has been declared to go wrong on this run. Empty is the normal
        #: case and takes the same code path, so the disturbed run is not a
        #: separate mode with its own bugs.
        self.disruptions = disruptions or Disruptions()
        self.limits = DisruptedSpeedLimits(self.disruptions, lambda: self.time_s)

        self.time_s = self.config.start_time_s
        self.dt = self.config.dt
        self.trains: Dict[str, Train] = {}
        self.occupancy = Occupancy(blocks)
        self.events: List[Event] = []
        self.violations: List[str] = []
        self.aspects = self.refresh_aspects()

    # -------------------------------------------------------------------- clock

    @property
    def clock(self) -> str:
        return format_clock(self.time_s)

    @property
    def finished(self) -> bool:
        """True once the run has reached its duration."""
        return self.time_s >= self.config.start_time_s + self.config.duration_s

    @property
    def all_services_done(self) -> bool:
        no_pending = getattr(self.dispatcher, "pending_count", 0) == 0
        running = any(t.is_active for t in self.trains.values())
        return no_pending and not running and bool(self.trains)

    # --------------------------------------------------------------------- step

    def step(self) -> None:
        """Advance the simulation by one timestep."""
        self.dispatcher.step(self)

        # Sense: one consistent snapshot for every train.
        decisions = []
        for train in self.trains.values():
            if train.state != "running":
                continue
            self.signalling.observe(train, self)
            authority = self.signalling.movement_authority(train, self)
            accel, target, reason = self.driver.decide(
                train, authority, self.dt, self.limits)
            decisions.append((train, accel, target, reason, authority))

        # Move.
        for train, accel, target, reason, authority in decisions:
            train.advance(accel, self.dt)
            train.target_speed_ms = target
            train.authority_reason = reason
            train.last_authority_m = authority.end_distance_m

        # Update the railway's view of where everyone is, then let the
        # interlocking give back the points and routes the trains have cleared.
        self.refresh_occupancy()
        if self.interlocking is not None:
            self.interlocking.update(self)
        self.refresh_aspects()

        self.time_s += self.dt
        self._check_invariants()

    def run(self, until_s: Optional[float] = None,
            stop_when_idle: bool = False) -> None:
        """Run to ``until_s`` (default: the configured duration)."""
        limit = until_s
        if limit is None:
            limit = self.config.start_time_s + self.config.duration_s
        while self.time_s < limit:
            self.step()
            if stop_when_idle and self.all_services_done:
                break

    # ---------------------------------------------------------------- occupancy

    def refresh_occupancy(self) -> None:
        for train in self.trains.values():
            if train.is_active:
                self.occupancy.set_train_blocks(train.id, train.occupied_blocks())
            else:
                self.occupancy.remove_train(train.id)

    def refresh_train_occupancy(self, train: Train) -> None:
        """Claim blocks for one train immediately, e.g. on introduction."""
        if train.is_active:
            self.occupancy.set_train_blocks(train.id, train.occupied_blocks())
            self.refresh_aspects()

    def refresh_aspects(self) -> Dict[str, str]:
        """Recompute every signal from occupancy and the interlocking."""
        self.aspects = compute_aspects(
            self.blocks, self.signals, self.occupancy, self.interlocking,
        )
        return self.aspects

    def _check_invariants(self) -> None:
        """Assert the safety property the *current* signalling system claims.

        Block exclusivity is a fixed-block property, not a universal one. Under
        moving block or Hybrid Level 3 two trains sharing a block section is the
        entire point, so asserting exclusivity there would flag correct behaviour
        as a fault. What must hold in every case is physical separation: no
        train's front may pass another train's rear.

        The third property is not about the trains at all but about the
        signalling that authorised them: no controlled signal may be off without
        a route locked from it. That one holds under every system, because none
        of them overrides the interlocking.
        """
        for message in self.check_separation():
            self._violation("trains overlap: " + message)

        if getattr(self.signalling, "separates_by", "block") == "block":
            for block_id in self.occupancy.check_exclusivity():
                trains = ", ".join(sorted(self.occupancy.trains_in(block_id)))
                self._violation("block %s holds %s" % (block_id, trains))

        for signal_id in self.clear_without_a_route():
            self._violation("controlled signal %s is off with no route set"
                            % (signal_id,))

    def clear_without_a_route(self) -> List[str]:
        """Controlled signals showing a proceed aspect with no route locked.

        The interlocking's whole purpose, stated as something that can fail. A
        signal reading over points may only come off once a route is set from it
        and the points under it are locked; if one is ever off without that, the
        movement it is authorising is a movement nobody has checked, and the
        points beneath the train are free to be called elsewhere.

        Automatic plain-line signals are exempt by construction, because there is
        no route to set: they follow occupancy, which is what makes them
        automatic. So the check is exactly the set of signals the route table
        governs, and it holds regardless of which of the five systems is running
        - none of them overrides the interlocking.
        """
        if self.interlocking is None:
            return []
        return sorted(
            signal.id
            for signal in self.signals.values()
            if signal.controlled
            and self.aspects.get(signal.id, Aspect.RED) != Aspect.RED
            and self.interlocking.route_set_from(signal.id) is None
        )

    def _violation(self, message: str) -> None:
        self.violations.append("%s %s" % (self.clock, message))
        self.log_event("VIOLATION", None, message)
        if self.config.strict:
            raise AssertionError(message)

    def check_separation(self) -> List[str]:
        """Trains whose front has passed the rear of the train in front of them.

        The universal safety invariant, and the one that still means something
        when block sections no longer separate trains.
        """
        problems = []
        active = [t for t in self.trains.values() if t.is_active]
        for train in active:
            ahead = nearest_ahead(train, active)
            if ahead is not None and ahead[0] < train.chainage_m:
                problems.append(
                    "%s at %.1f is past the rear of %s at %.1f"
                    % (train.id, train.chainage_m, ahead[1], ahead[0])
                )
        return problems

    # ------------------------------------------------------------------ logging

    def log_event(self, kind: str, train_id: Optional[str], detail: str) -> None:
        self.events.append(Event(self.time_s, kind, train_id, detail))

    # ------------------------------------------------------------------ reports

    def active_trains(self) -> List[Train]:
        return [t for t in self.trains.values() if t.is_active]

    def summary(self) -> str:
        """A short end-of-run summary, printed by the headless runner."""
        lines = [
            "network        : %s" % self.network.name,
            "signalling     : %s" % self.signalling.describe(),
            "interlocking   : %s" % (self.interlocking.describe()
                                     if self.interlocking else "none (automatic block)"),
            "dispatch       : %s" % self.dispatcher.describe(),
        ]
        lines.extend(self.disruptions.summary_lines())
        lines.extend([
            "clock          : %s" % self.clock,
            "services       : %d introduced, %d still running"
            % (len(self.trains), len(self.active_trains())),
            "violations     : %d" % len(self.violations),
        ])
        finished = [t for t in self.trains.values() if t.state == "finished"]
        if finished:
            worst = max(finished, key=lambda t: t.delay_s)
            lines.append(
                "worst arrival  : %s %s" % (worst.id, format_delay(worst.delay_s))
            )
        return "\n".join(lines)

    def train_rows(self) -> List[Dict[str, object]]:
        """Per-train state, for the schematic view's HUD and for reports."""
        rows = []
        for train in sorted(self.trains.values(), key=lambda t: t.id):
            stop = train.next_stop()
            rows.append({
                "id": train.id,
                "name": train.name,
                "state": train.state,
                "km": round(train.km, 2) if train.state != "finished" else None,
                "speed_kmh": round(ms_to_kmh(train.speed_ms), 1),
                "target_kmh": round(ms_to_kmh(train.target_speed_ms), 1),
                "next_stop": stop.station if stop else "-",
                "reason": train.authority_reason,
                "delay_s": train.delay_s,
            })
        return rows
