"""The signalling interface every train control system implements.

This is the central architectural seam of the simulator. The kernel asks, once per
train per tick, "how far may this train go and how fast?" and gets back a
:class:`MovementAuthority`. Nothing else about a signalling system leaks into the
driver, the trains or the kernel.

That is what keeps the capacity study honest. Conventional signalling, ETCS
Level 2, Hybrid Level 3, full moving block and virtual coupling all share the same
braking physics, the same interlocking and the same timetable. They differ only in
*where the authority ends*, *how fast the train may still be going when it gets
there* and *when the driver learns about it* - and all three of those are expressed
here. Any headway difference therefore falls out of the braking physics rather than
being a tuned constant.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime dependency
    from trainsim.core.simulation import Simulation
    from trainsim.core.train import Train


#: One train per block section: separation is enforced by the interlocking, and
#: two trains in one section is a safety violation.
SEPARATION_BY_BLOCK = "block"

#: Separation by measured distance: the authority ends at a computed point rather
#: than a section boundary, so two trains in one section is correct behaviour.
SEPARATION_BY_DISTANCE = "distance"

SEPARATION_MODES = (SEPARATION_BY_BLOCK, SEPARATION_BY_DISTANCE)


@dataclass(frozen=True)
class MovementAuthority:
    """How far a train may proceed, and how fast.

    Attributes:
        end_distance_m: Distance from the train's front to the point at which it
            must have slowed to ``target_speed_ms``. This is the danger point.
        target_speed_ms: Speed permitted at the end of the authority. Zero for
            every system that brakes to a fixed obstacle - a signal at danger, a
            block boundary, the rear of a stationary train. Non-zero only where
            the danger point is itself moving and its speed is known to the
            following train, which is precisely what distinguishes virtual
            coupling from moving block.
        ceiling_speed_ms: Speed ceiling applying right now, independent of the
            distance to the danger point. ``None`` means "line speed only".
        reason: Short human-readable cause, shown in the schematic view and the
            event log so the behaviour on screen is explainable.
    """

    end_distance_m: float
    target_speed_ms: float = 0.0
    ceiling_speed_ms: Optional[float] = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.end_distance_m < 0.0:
            raise ValueError(
                "end_distance_m must not be negative, got %r - an authority that "
                "ends behind the train is a bug in the signalling system, not a "
                "restrictive aspect" % (self.end_distance_m,)
            )
        if self.target_speed_ms < 0.0:
            raise ValueError(
                "target_speed_ms must not be negative, got %r" % (self.target_speed_ms,)
            )
        if self.ceiling_speed_ms is not None:
            if self.ceiling_speed_ms < 0.0:
                raise ValueError(
                    "ceiling_speed_ms must not be negative, got %r"
                    % (self.ceiling_speed_ms,)
                )
            if self.target_speed_ms > self.ceiling_speed_ms:
                raise ValueError(
                    "target_speed_ms %r exceeds ceiling_speed_ms %r - the train "
                    "would have to accelerate through the ceiling to satisfy the "
                    "authority" % (self.target_speed_ms, self.ceiling_speed_ms)
                )

    @property
    def is_stopping(self) -> bool:
        """Whether the authority ends at a standstill.

        False only where the danger point is moving, which is the defining
        property of a relative-braking system.
        """
        return self.target_speed_ms == 0.0


class SignallingSystem:
    """Base class for train control systems.

    Subclasses implement :meth:`movement_authority`, and may override
    :meth:`observe` to model what information reaches the driver and when - the
    difference between discrete lineside signals and a continuous radio-based
    authority.
    """

    #: Name used in scenario files.
    name = "abstract"

    #: Whether the railway has lineside signals. Radio-based levels do not:
    #: ETCS Level 2 and above replace the lamp with a movement authority sent
    #: to the cab, leaving only unlit marker boards at block boundaries. The
    #: schematic view reads this to decide what to draw.
    has_lineside_signals = True

    #: How trains are kept apart, one of :data:`SEPARATION_MODES`. The kernel
    #: picks its safety invariant from this - under moving block, two trains in
    #: one block is correct behaviour, not a violation.
    separates_by = SEPARATION_BY_BLOCK

    #: Whether the authority may end at a moving point rather than a fixed one.
    #: Only virtual coupling sets this. The kernel reads it to decide whether a
    #: non-zero ``target_speed_ms`` is legitimate or a symptom of a bug, so a
    #: system cannot quietly award itself relative braking.
    permits_relative_braking = False

    def __init__(self) -> None:
        if self.separates_by not in SEPARATION_MODES:
            raise ValueError(
                "%s.separates_by is %r - must be one of %s"
                % (type(self).__name__, self.separates_by, ", ".join(SEPARATION_MODES))
            )

    def observe(self, train: "Train", sim: "Simulation") -> None:
        """Update the train's knowledge of the signalling, before deciding.

        Called once per train per tick, ahead of :meth:`movement_authority`. The
        default does nothing, which suits continuous systems where the authority
        is always current.
        """

    def movement_authority(
        self, train: "Train", sim: "Simulation"
    ) -> MovementAuthority:
        """Return how far this train may proceed, and how fast.

        Called once per train per tick, after :meth:`observe`.
        """
        raise NotImplementedError

    def describe(self) -> str:
        """One-line description for reports and the view's HUD."""
        return self.name
