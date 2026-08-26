"""The signalling interface every train control system implements.

This is the central architectural seam of the simulator. The kernel asks, once per
train per tick, "how far may this train go and how fast?" and gets back a
:class:`MovementAuthority`. Nothing else about a signalling system leaks into the
driver, the trains or the kernel.

That is what makes the planned ERTMS study honest: ETCS Level 2 and Hybrid Level 3
differ from conventional signalling in *where the authority ends* and *when the
driver learns about it*, and both of those are expressed here. The resulting
headway differences fall out of the braking physics instead of being tuned
constants.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MovementAuthority:
    """How far a train may proceed, and how fast.

    Attributes:
        end_distance_m: Distance from the train's front to the point at which it
            must have slowed to ``target_speed_ms``. This is the danger point.
        target_speed_ms: Speed permitted at the end of the authority; normally 0.
        ceiling_speed_ms: Speed ceiling applying right now, independent of the
            distance to the danger point. ``None`` means "line speed only".
        reason: Short human-readable cause, shown in the schematic view and the
            event log so the behaviour on screen is explainable.
    """

    end_distance_m: float
    target_speed_ms: float = 0.0
    ceiling_speed_ms: Optional[float] = None
    reason: str = ""


class SignallingSystem(object):
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

    #: How trains are kept apart: ``"block"`` means one train per block
    #: section, ``"distance"`` means by measured separation. The kernel picks
    #: its safety invariant from this - under moving block, two trains in one
    #: block is correct behaviour, not a violation.
    separates_by = "block"

    def observe(self, train, sim) -> None:
        """Update the train's knowledge of the signalling, before deciding.

        Called once per train per tick, ahead of :meth:`movement_authority`. The
        default does nothing, which suits continuous systems where the authority
        is always current.
        """

    def movement_authority(self, train, sim) -> MovementAuthority:
        raise NotImplementedError

    def describe(self) -> str:
        """One-line description for reports and the view's HUD."""
        return self.name
