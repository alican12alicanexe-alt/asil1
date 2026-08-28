"""Machinery shared by every train control system.

All five systems modelled here answer the same underlying question - *where is the
first point this train may not pass?* - and differ only in two things:

* **how that point is worked out**: the entry of the first occupied block, or the
  rear of the train in front
* **when the train is told**: at a lineside signal, at a balise, or continuously
  over radio

Separating those two axes is what makes the comparison honest. The braking
physics and the interlocking are identical across all of them, so any difference
in headway or journey time comes from the information, not from a tuned constant.
"""

from typing import Optional, Tuple

from ..train import nearest_ahead


def route_limit(train, sim) -> Optional[Tuple[float, str]]:
    """The first controlled signal ahead with no route set from it.

    No level of ETCS overrides the interlocking. A radio-based authority is still
    bounded by the routes actually locked, so this limit applies to Level 2,
    Hybrid Level 3 and full moving block exactly as it does to lineside signals.
    """
    interlocking = getattr(sim, "interlocking", None)
    if interlocking is None:
        return None
    for section in train.path.sections_ahead(train.chainage_m):
        if section.start_m <= train.chainage_m:
            continue
        signal = sim.signals.get(section.signal_id) if section.signal_id else None
        if signal is None or not interlocking.needs_a_route(signal):
            continue
        if interlocking.route_set_from(signal.id) is None:
            return section.start_m, "no route set at %s" % signal.id
    return None


def block_danger_point(train, sim) -> Tuple[float, str]:
    """Chainage of the first block boundary ahead that this train may not pass.

    Fixed-block train detection: the danger point is the entry to the first block
    held by another train, or guarded by a signal with no route. This is what
    Level 1 and Level 2 both supervise towards; they differ in when they learn it.
    """
    for section in train.path.sections_ahead(train.chainage_m):
        if section.end_m <= train.chainage_m:
            continue
        occupied = sim.occupancy.trains_in(section.block_id)
        if occupied and occupied != {train.id}:
            if section.start_m > train.chainage_m:
                return section.start_m, "block %s occupied" % section.block_id
            # Already inside a block another train is in: should not happen, but
            # fail safe rather than issue an authority into it.
            return train.chainage_m, "block %s shared" % section.block_id

        if section.start_m > train.chainage_m and section.signal_id:
            signal = sim.signals.get(section.signal_id)
            interlocking = getattr(sim, "interlocking", None)
            if (signal is not None and interlocking is not None
                    and interlocking.needs_a_route(signal)
                    and interlocking.route_set_from(signal.id) is None):
                return section.start_m, "no route set at %s" % signal.id

    return train.path.total_m, "end of line"


def train_ahead(train, sim) -> Optional[Tuple[float, str]]:
    """Rear of the nearest train in front, in this train's chainage."""
    return nearest_ahead(train, sim.trains.values())


def limit_by_route(danger_m: float, reason: str, train, sim) -> Tuple[float, str]:
    """Cap an authority at the interlocking's limit, whichever comes first."""
    limit = route_limit(train, sim)
    if limit is not None and limit[0] < danger_m:
        return limit
    return danger_m, reason
