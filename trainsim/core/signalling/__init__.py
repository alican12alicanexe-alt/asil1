"""Pluggable signalling systems.

Every train control system - conventional lineside signalling, ETCS Levels 1 and
2, Hybrid Level 3, full moving block and virtual coupling - is an implementation of
:class:`~trainsim.core.signalling.base.SignallingSystem`. The kernel never imports
a concrete one, so comparing systems is a scenario setting rather than a rewrite,
and `--compare` runs one timetable through all of them.

They all share the same braking physics, the same interlocking and the same
timetable. Any difference in headway or journey time between them therefore comes
from what the train is told and when, which is the only honest way to make the
comparison.
"""

import dataclasses

from ..driver import DriverConfig
from .base import MovementAuthority, SignallingSystem
from .etcs import ETCSLevel1, ETCSLevel2, MovingBlock
from .fixed_block import ThreeAspectFixedBlock
from .hybrid_l3 import HybridLevel3
from .virtual_coupling import VirtualCoupling

#: Name used in scenario files -> implementation.
REGISTRY = {
    "fixed_block_3aspect": ThreeAspectFixedBlock,
    "etcs_l1": ETCSLevel1,
    "etcs_l2": ETCSLevel2,
    "etcs_hybrid_l3": HybridLevel3,
    "etcs_moving_block": MovingBlock,
    "virtual_coupling": VirtualCoupling,
}

#: The order a comparison report presents them in: oldest technology first.
LADDER = (
    "fixed_block_3aspect",
    "etcs_l1",
    "etcs_l2",
    "etcs_hybrid_l3",
    "etcs_moving_block",
    "virtual_coupling",
)


#: What a train has to be fitted with to get the benefit of each system:
#: ``(etcs_level, tims, v2v)``.
#:
#: The physical train never changes - same length, same power, same brake. What
#: changes is the equipment, and it has to change with the system or every
#: system is measured on the same unfitted unit and reports the same fallback
#: under several different names. That is a quiet way to make a comparison say
#: nothing, because the runs all complete and the table looks reasonable.
#:
#: Each system gets what it needs and nothing more. Moving block follows the
#: rear of the train in front, so it needs the integrity report - a rear that
#: cannot be confirmed cannot be followed. Virtual coupling needs the radio link
#: on top of that, because it plans to stop where the leader will stop rather
#: than where the leader currently stands. Lineside signalling needs none of it:
#: the driver reads the signal.
FITMENT = {
    "fixed_block_3aspect": ("none", False, False),
    "etcs_l1":             ("l1",   False, False),
    "etcs_l2":             ("l2",   False, False),
    "etcs_hybrid_l3":      ("l3",   True,  False),
    "etcs_moving_block":   ("l3",   True,  False),
    "virtual_coupling":    ("l3",   True,  True),
}


def fitment_for(name):
    """``(etcs_level, tims, v2v)`` a train needs to work ``name``."""
    try:
        return FITMENT[name]
    except KeyError:
        raise ValueError(
            "no fitment declared for signalling system %r - add it to FITMENT"
            % (name,))


def fit_timetable(timetable, name):
    """Re-equip every train in ``timetable`` for the signalling system ``name``.

    Changes what the train carries, never what it is: length, power, brake and
    mass come through untouched, so a fitted run and an unfitted one differ by
    the equipment alone.

    Returns the stock ids it changed, in the order it met them, which is what
    the caller reports. Nothing is changed if the fleet is already fitted.
    """
    level, tims, v2v = fitment_for(name)
    changed = []
    replacements = {}
    for service in timetable.services:
        stock = service.stock
        if (stock.etcs_level, stock.tims, stock.v2v) == (level, tims, v2v):
            continue
        if stock.id not in replacements:
            replacements[stock.id] = dataclasses.replace(
                stock, etcs_level=level, tims=tims, v2v=v2v)
            changed.append(stock.id)
        service.stock = replacements[stock.id]
    return changed


#: Who is driving, per system: driver settings that follow from the system
#: rather than from the railway.
#:
#: Lineside signalling and ETCS Levels 1 and 2 are driven by a person reading a
#: signal or a screen, so they carry a reaction time. Level 3 and virtual
#: coupling are driven by ATO - virtual coupling has to be, because the
#: separations it works at are shorter than a person can safely hold - and an
#: ATO has no reaction time in the sense this term means.
#:
#: That does not make the response instantaneous, and nothing here claims it
#: is. What a train still pays for is modelled elsewhere and would be counted
#: twice here: the control cycle is the simulation timestep, so a train runs a
#: whole tick on its last decision whatever this says; the radio delay is
#: ``v2v_latency_s`` in virtual coupling; and the brake takes
#: ``brake_buildup_s`` to come on, which the jerk limit applies and the
#: driver's braking curves already allow for. This term is the human, and with
#: no human it is zero.
#:
#: Moving block is the one to watch. It is given ATO here, following the
#: literature, but it has no latency term of its own - so it is being credited
#: with instant radio updates that virtual coupling pays for. That is
#: conservative in the direction this project cares about: it flatters moving
#: block in the comparison against virtual coupling, not the other way round.
DRIVING = {
    "fixed_block_3aspect": {"reaction_time_s": 2.0},
    "etcs_l1":             {"reaction_time_s": 2.0},
    "etcs_l2":             {"reaction_time_s": 2.0},
    "etcs_hybrid_l3":      {"reaction_time_s": 2.0},
    "etcs_moving_block":   {"reaction_time_s": 0.0},
    "virtual_coupling":    {"reaction_time_s": 0.0},
}


def driving_for(name):
    """Driver settings that follow from the signalling system ``name``."""
    try:
        return dict(DRIVING[name])
    except KeyError:
        raise ValueError(
            "no driving profile declared for signalling system %r - add it to "
            "DRIVING" % (name,))


def fit_driver(config, name):
    """``config`` with the settings ``name`` decides overridden.

    Everything the scenario declared and the system has no opinion about -
    stopping tolerance, the speed deadband, the standing safety margin - comes
    through untouched.
    """
    return dataclasses.replace(config, **driving_for(name))


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
    "VirtualCoupling",
    "REGISTRY",
    "LADDER",
    "FITMENT",
    "DRIVING",
    "create",
    "fitment_for",
    "fit_timetable",
    "driving_for",
    "fit_driver",
]
