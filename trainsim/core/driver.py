"""The driver model: turn a movement authority into an acceleration.

Each tick the driver builds a list of *constraints* - "be down to speed V in D
metres" - from the movement authority, the next scheduled stop and any speed
restriction coming up. Each constraint is converted to a speed permitted right now
via the braking curve, and the lowest wins.

The model is deliberately signalling-agnostic. It never asks what an aspect is; it
only consumes :class:`~trainsim.core.signalling.base.MovementAuthority`. Swapping
in ETCS Level 2 later therefore changes braking behaviour without touching a line
of this file.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .disruption import SpeedLimits
from .units import braking_distance, speed_from_braking_distance


@dataclass(frozen=True)
class DriverConfig:
    """Driver behaviour parameters, from the scenario file."""

    reaction_time_s: float = 2.0
    #: Standing distance kept short of a danger point.
    safety_margin_m: float = 25.0
    #: Within this distance a stop is treated as reached.
    stop_tolerance_m: float = 1.0
    #: Speed band treated as "at target"; avoids hunting around the target speed.
    speed_deadband_ms: float = 0.3


class Driver:
    """Decides acceleration for one tick."""

    def __init__(self, config: Optional[DriverConfig] = None):
        self.config = config or DriverConfig()
        #: Used when the caller passes none - the infrastructure's own speeds.
        self.limits = SpeedLimits()

    def decide(self, train, authority, dt: float,
               limits=None) -> Tuple[float, float, str]:
        """Return ``(acceleration, target_speed_ms, governing_reason)``.

        ``limits`` says what the line speed is here and ahead. It defaults to the
        speeds written into the infrastructure; a run with a temporary speed
        restriction passes one that lays the restriction over them. The driver
        does not know which it has been given, which is the point.
        """
        stock = train.stock
        speed = train.speed_ms
        cfg = self.config
        limits = limits or self.limits

        target = min(stock.max_speed_ms, limits.at(train, train.chainage_m))
        reason = "line speed"

        if authority.ceiling_speed_ms is not None and authority.ceiling_speed_ms < target:
            target = authority.ceiling_speed_ms
            reason = authority.reason or "authority ceiling"

        constraints = self._constraints(train, authority, speed, limits)
        for distance, limit, label in constraints:
            allowed = speed_from_braking_distance(distance, stock.service_brake, limit)
            if allowed < target:
                target = allowed
                reason = label

        target = max(0.0, target)

        # If a stopping point falls inside this tick, brake at exactly the rate that
        # brings the train to a stand on it. advance() then lands on it precisely,
        # which keeps platform berthing and stopping short of a red signal accurate
        # rather than asymptotic.
        exact = self._exact_stop_accel(constraints, speed, dt, stock)
        if exact is not None:
            return exact[0], 0.0, exact[1]

        delta = target - speed
        if delta > cfg.speed_deadband_ms:
            accel = min(stock.max_accel, delta / dt)
        elif delta < -cfg.speed_deadband_ms:
            accel = max(-stock.service_brake, delta / dt)
        else:
            accel = delta / dt
        return accel, target, reason

    # ---------------------------------------------------------------- internals

    def _constraints(self, train, authority, speed: float, limits
                     ) -> List[Tuple[float, float, str]]:
        """``(distance, speed_at_that_point, label)`` for everything ahead."""
        cfg = self.config
        stock = train.stock
        found: List[Tuple[float, float, str]] = []

        # The movement authority, held back by a standing margin and by how far the
        # train runs before the driver reacts.
        reaction_allowance = speed * cfg.reaction_time_s
        ma_distance = authority.end_distance_m - cfg.safety_margin_m - reaction_allowance
        found.append((
            max(0.0, ma_distance),
            authority.target_speed_ms,
            authority.reason or "movement authority",
        ))

        # The next scheduled stop.
        to_stop = train.distance_to_next_stop()
        if to_stop is not None:
            stop = train.next_stop()
            found.append((max(0.0, to_stop), 0.0, "station stop %s" % stop.station))

        # Slower stretches coming up - permanent, like a loop road, or a
        # temporary restriction laid on for this run. Brake before reaching them.
        lookahead = braking_distance(stock.max_speed_ms, stock.service_brake) + 200.0
        for distance, limit in limits.ahead(train, train.chainage_m, lookahead):
            if limit < speed:
                found.append((max(0.0, distance), limit, "speed restriction"))

        return found

    def _exact_stop_accel(self, constraints, speed: float, dt: float, stock
                          ) -> Optional[Tuple[float, str]]:
        """Deceleration that stops exactly on a stopping point inside this tick."""
        if speed <= 0.0:
            return None
        reach = speed * dt
        best: Optional[Tuple[float, str]] = None
        for distance, limit, label in constraints:
            if limit > 0.0:
                continue
            if distance > reach:
                continue
            if distance <= self.config.stop_tolerance_m:
                return -min(speed / dt, stock.emergency_brake), label
            needed = (speed * speed) / (2.0 * distance)
            accel = -min(needed, stock.emergency_brake)
            if best is None or accel < best[0]:
                best = (accel, label)
        return best
