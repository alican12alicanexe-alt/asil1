"""Pluggable signalling systems.

Every train control system - conventional lineside signalling, ETCS Levels 1 and
2, Hybrid Level 3 and full moving block - is an implementation of
:class:`~trainsim.core.signalling.base.SignallingSystem`. The kernel never imports
a concrete one, so comparing systems is a scenario setting rather than a rewrite,
and `--compare` runs one timetable through all of them.

They all share the same braking physics, the same interlocking and the same
timetable. Any difference in headway or journey time between them therefore comes
from what the train is told and when, which is the only honest way to make the
comparison.
"""

from .base import MovementAuthority, SignallingSystem
from .etcs import ETCSLevel1, ETCSLevel2, MovingBlock
from .fixed_block import ThreeAspectFixedBlock
from .hybrid_l3 import HybridLevel3

#: Name used in scenario files -> implementation.
REGISTRY = {
    "fixed_block_3aspect": ThreeAspectFixedBlock,
    "etcs_l1": ETCSLevel1,
    "etcs_l2": ETCSLevel2,
    "etcs_hybrid_l3": HybridLevel3,
    "etcs_moving_block": MovingBlock,
}

#: The order a comparison report presents them in: oldest technology first.
LADDER = (
    "fixed_block_3aspect",
    "etcs_l1",
    "etcs_l2",
    "etcs_hybrid_l3",
    "etcs_moving_block",
)


def create(name, **kwargs):
    """Build a signalling system by its scenario-file name."""
    try:
        factory = REGISTRY[name]
    except KeyError:
        raise ValueError(
            "unknown signalling system %r - available: %s"
            % (name, ", ".join(sorted(REGISTRY)))
        )
    return factory(**kwargs)


__all__ = [
    "MovementAuthority",
    "SignallingSystem",
    "ThreeAspectFixedBlock",
    "ETCSLevel1",
    "ETCSLevel2",
    "HybridLevel3",
    "MovingBlock",
    "REGISTRY",
    "LADDER",
    "create",
]
