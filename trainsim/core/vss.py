"""Virtual Sub-Sections, for Hybrid ERTMS/ETCS Level 3.

Hybrid Level 3 sits between Level 2 and full moving block, and it exists because
full moving block asks for something a mixed fleet cannot give: every train
reporting its position *and* confirming its integrity, all the time.

The compromise is to keep the physical Trackside Train Detection sections - the
block sections that already exist - and subdivide each into several **Virtual
Sub-Sections**. A VSS has no equipment; it is a length of track whose state is
inferred from train position reports, with the TTD underneath as a safety net.
Trains that can report and confirm integrity are resolved to VSS granularity,
giving much of the capacity of moving block. Trains that cannot are still
detected by the TTD, so they are safe - just coarse.

Each VSS holds one of four states, following the ABZ 2018 case-study formulation:

``free``
    No train, and the TTD underneath confirms it.
``occupied``
    A train that reports its position is known to be here.
``ambiguous``
    A train's front has been reported past here, but its integrity is not
    confirmed, so part of it may still be standing in this sub-section.
``unknown``
    The TTD is occupied but no position report accounts for it - an unfitted
    train, or one whose radio has failed.

Only ``free`` may be given away in a movement authority. That single rule is what
makes the whole scheme safe under mixed fitment.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

FREE = "free"
OCCUPIED = "occupied"
AMBIGUOUS = "ambiguous"
UNKNOWN = "unknown"

#: Most to least restrictive - a VSS takes the worst claim made on it.
SEVERITY = {FREE: 0, AMBIGUOUS: 1, UNKNOWN: 2, OCCUPIED: 3}


@dataclass(frozen=True)
class VirtualSubSection:
    """One sub-division of a trackside train detection section."""

    id: str
    block_id: str
    index: int
    #: Position within the parent block, as a fraction of its length.
    from_fraction: float
    to_fraction: float
    length_m: float


def subdivide(blocks, per_block: int = 4) -> Dict[str, List[VirtualSubSection]]:
    """Divide every block into ``per_block`` equal virtual sub-sections.

    Real designs vary the division - shorter sub-sections where capacity is
    wanted, as with block lengths themselves - but an even division keeps the
    comparison against Level 2 clean: the only thing that changed is granularity.
    """
    if per_block < 1:
        raise ValueError("a block must have at least one virtual sub-section")
    table: Dict[str, List[VirtualSubSection]] = {}
    for block_id, block in blocks.items():
        sections = []
        for index in range(per_block):
            sections.append(VirtualSubSection(
                id="%s.%d" % (block_id, index + 1),
                block_id=block_id,
                index=index,
                from_fraction=index / float(per_block),
                to_fraction=(index + 1) / float(per_block),
                length_m=block.length_m / float(per_block),
            ))
        table[block_id] = sections
    return table


class VSSState(object):
    """Current state of every virtual sub-section, rebuilt each tick."""

    def __init__(self, table: Dict[str, List[VirtualSubSection]]):
        self.table = table
        self.state: Dict[str, str] = {
            vss.id: FREE for sections in table.values() for vss in sections
        }
        #: Who caused each claim. Needed because a train must not be stopped by
        #: its own footprint: an unfitted train marks its whole block unknown,
        #: including the sub-sections in front of its own nose.
        self.claimed_by: Dict[str, Set[str]] = {key: set() for key in self.state}

    def reset(self) -> None:
        for key in self.state:
            self.state[key] = FREE
            self.claimed_by[key].clear()

    def claim(self, vss_id: str, state: str, train_id: str = "") -> None:
        """Apply a claim, keeping whichever is more restrictive."""
        if SEVERITY[state] > SEVERITY[self.state[vss_id]]:
            self.state[vss_id] = state
        if train_id:
            self.claimed_by[vss_id].add(train_id)

    def of(self, vss_id: str) -> str:
        return self.state[vss_id]

    def is_free_for(self, vss_id: str, train_id: str) -> bool:
        """True if this sub-section may be given to ``train_id``.

        Free for everyone, or claimed by nobody except this train.
        """
        if self.state[vss_id] == FREE:
            return True
        return self.claimed_by[vss_id] == {train_id}

    def sections_of(self, block_id: str) -> List[VirtualSubSection]:
        return self.table.get(block_id, [])

    def counts(self) -> Dict[str, int]:
        counts = {FREE: 0, OCCUPIED: 0, AMBIGUOUS: 0, UNKNOWN: 0}
        for value in self.state.values():
            counts[value] += 1
        return counts


def update(vss_state: VSSState, sim) -> None:
    """Recompute every sub-section from where the trains actually are.

    Three cases, and they are the whole of Hybrid Level 3:

    * a train that reports position **and** confirms integrity resolves to the
      sub-sections it really covers
    * a train that reports position but **cannot** confirm integrity marks the
      sub-sections it covers as occupied, and everything behind it back to the
      start of its block as *ambiguous* - the rest of the train may be there
    * a train that reports nothing marks its whole block *unknown*, which is
      exactly Level 2 behaviour and is why mixed fitment is safe
    """
    vss_state.reset()

    for train in sim.trains.values():
        if not train.is_active:
            continue
        stock = train.stock
        front = train.chainage_m
        rear = max(0.0, train.rear_m)

        for block_id, start_m, end_m in train.path.block_ranges:
            if start_m >= front or end_m <= rear:
                continue
            sections = vss_state.sections_of(block_id)
            if not sections:
                continue

            if not stock.reports_position:
                for vss in sections:
                    vss_state.claim(vss.id, UNKNOWN, train.id)
                continue

            span = end_m - start_m
            if span <= 0:
                continue
            low = max(0.0, (max(rear, start_m) - start_m) / span)
            high = min(1.0, (min(front, end_m) - start_m) / span)

            for vss in sections:
                if vss.to_fraction > low and vss.from_fraction < high:
                    vss_state.claim(vss.id, OCCUPIED, train.id)
                elif not stock.tims and vss.to_fraction <= low:
                    # No integrity confirmation: what is behind the reported
                    # front might still be part of this train.
                    vss_state.claim(vss.id, AMBIGUOUS, train.id)


def first_blocked(vss_state: VSSState, train, sim) -> Tuple[float, str, bool]:
    """Start of the first sub-section ahead that is not free.

    Returns ``(chainage, reason, blocked)``. ``blocked`` is False when the road
    is clear to the end of the path: the caller must not then apply a
    separation margin, or a train would be stopped short of its own platform.
    """
    for block_id, start_m, end_m in train.path.block_ranges:
        if end_m <= train.chainage_m:
            continue
        span = end_m - start_m
        for vss in vss_state.sections_of(block_id):
            if vss_state.is_free_for(vss.id, train.id):
                continue
            vss_start = start_m + vss.from_fraction * span
            if vss_start <= train.chainage_m:
                continue
            return vss_start, "%s %s" % (vss.id, vss_state.of(vss.id)), True
    return train.path.total_m, "end of line", False
