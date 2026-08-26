"""Block sections, lineside signals and occupancy.

A block section is a chain of segments that may hold at most one train. That
single rule is the safety backbone of the simulation, asserted every tick by
:meth:`Occupancy.check_exclusivity`.

**Signals belong to legs, not to nodes.** Where several roads converge, each one
gets its own signal reading into the block beyond, because a train on the loop
road and a train on the through road are asking different questions of the same
trailing point. Modelling one shared signal there would let a train in the loop
be given an authority the points were not set for.

Aspect logic is conventional three-aspect - red for an occupied block, yellow
when the block beyond is occupied, green otherwise - with two additions from the
interlocking:

* a **controlled** signal shows red until a route is set from it, which is what
  makes a station or junction signal different from a plain-line one
* successors are filtered by **point position**, so a signal only reads towards
  the road the points are actually set for
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple


class Aspect(object):
    """Three-aspect signal indications, ordered least to most permissive."""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"

    ORDER = (RED, YELLOW, GREEN)

    @staticmethod
    def least_restrictive(aspects: Iterable[str]) -> str:
        best = Aspect.RED
        for aspect in aspects:
            if Aspect.ORDER.index(aspect) > Aspect.ORDER.index(best):
                best = aspect
        return best


@dataclass(frozen=True)
class BlockSection:
    """A chain of segments protected by its entry signals."""

    id: str
    segment_ids: Tuple[str, ...]
    track: str
    entry_node: str
    exit_node: str
    length_m: float
    km_start: float
    km_end: float
    signal_ids: Tuple[str, ...] = ()
    successors: Tuple[str, ...] = ()
    platform: Optional[str] = None
    station: Optional[str] = None

    @property
    def signal_id(self) -> Optional[str]:
        """The first entry signal; the only one unless roads converge here."""
        return self.signal_ids[0] if self.signal_ids else None

    @property
    def first_segment(self) -> str:
        return self.segment_ids[0]


@dataclass(frozen=True)
class Signal:
    """A lineside signal reading into a block section.

    ``from_segment`` is the road it applies to when several converge at its node;
    ``None`` where there is only one approach. ``controlled`` marks a signal that
    reads over points and so needs a route set before it may clear - as opposed
    to a plain-line automatic signal, which follows occupancy alone.
    """

    id: str
    block_id: str
    node_id: str
    km: float
    y: float
    track: str
    from_segment: Optional[str] = None
    controlled: bool = False

    def describe(self) -> str:
        kind = "controlled" if self.controlled else "automatic"
        if self.from_segment:
            return "%s signal %s (from %s)" % (kind, self.id, self.from_segment)
        return "%s signal %s" % (kind, self.id)


class Occupancy:
    """Which trains are in which block sections.

    Rebuilt from train positions each tick rather than maintained incrementally -
    cheap at this scale, and it cannot drift out of step with where the trains
    actually are.
    """

    def __init__(self, blocks: Dict[str, BlockSection]):
        self._blocks = blocks
        self._by_block: Dict[str, Set[str]] = {b: set() for b in blocks}
        self._by_train: Dict[str, Set[str]] = {}

    def clear(self) -> None:
        for trains in self._by_block.values():
            trains.clear()
        self._by_train.clear()

    def set_train_blocks(self, train_id: str, block_ids: Iterable[str]) -> None:
        wanted = set(block_ids)
        for block_id in self._by_train.get(train_id, set()) - wanted:
            self._by_block[block_id].discard(train_id)
        for block_id in wanted:
            self._by_block.setdefault(block_id, set()).add(train_id)
        self._by_train[train_id] = wanted

    def remove_train(self, train_id: str) -> None:
        for block_id in self._by_train.pop(train_id, set()):
            self._by_block[block_id].discard(train_id)

    def trains_in(self, block_id: str) -> Set[str]:
        return self._by_block.get(block_id, set())

    def blocks_of(self, train_id: str) -> Set[str]:
        return self._by_train.get(train_id, set())

    def is_free(self, block_id: str, ignoring: Optional[str] = None) -> bool:
        """True if no train other than ``ignoring`` occupies the block."""
        trains = self._by_block.get(block_id, set())
        if not trains:
            return True
        if ignoring is not None and trains == {ignoring}:
            return True
        return False

    def occupied_blocks(self) -> List[str]:
        return [b for b, trains in self._by_block.items() if trains]

    def check_exclusivity(self) -> List[str]:
        """Block ids holding more than one train.

        The core safety invariant. A non-empty result means the signalling let
        two trains into one block, which is a bug worth failing a test over.
        """
        return sorted(b for b, trains in self._by_block.items() if len(trains) > 1)


def compute_aspects(blocks: Dict[str, BlockSection], signals: Dict[str, Signal],
                    occupancy: Occupancy, interlocking=None) -> Dict[str, str]:
    """Aspect for every signal.

    Done in two passes, because a signal is a function of the signal *ahead* of
    it, not of raw track occupancy. First work out which signals must stand at
    danger; then every other signal shows yellow if all the signals it reads
    towards are at danger, and green otherwise.

    Reading the signal ahead rather than the block ahead matters as soon as there
    is an interlocking: a signal protecting a clear block still stands at danger
    when no route is set over it, and the signal behind must warn a driver about
    that just as it would about an occupied block. Computing from occupancy alone
    would show a green up to a red, with no braking distance in between.
    """
    at_danger = {
        signal.id: _must_stand_at_danger(signal, blocks, occupancy, interlocking)
        for signal in signals.values()
    }

    aspects: Dict[str, str] = {}
    for signal in signals.values():
        if at_danger[signal.id]:
            aspects[signal.id] = Aspect.RED
            continue
        ahead = next_signals(blocks[signal.block_id], blocks, signals, interlocking)
        if not ahead:
            aspects[signal.id] = Aspect.GREEN          # end of the modelled line
        elif any(not at_danger[s] for s in ahead):
            aspects[signal.id] = Aspect.GREEN
        else:
            aspects[signal.id] = Aspect.YELLOW
    return aspects


def _must_stand_at_danger(signal, blocks, occupancy, interlocking) -> bool:
    """Whether a signal has to show red, before looking at anything ahead."""
    if not occupancy.is_free(signal.block_id):
        return True
    if signal.controlled and interlocking is not None:
        # A controlled signal reads over points, so it needs a route locked
        # before it may show anything but danger. With no interlocking modelled
        # at all there are no routes, and every signal falls back to plain
        # automatic block working.
        return not interlocking.route_set_from(signal.id)
    return False


def next_signals(block: BlockSection, blocks: Dict[str, BlockSection],
                 signals: Dict[str, Signal], interlocking=None) -> List[str]:
    """The signals a driver leaving ``block`` will read next.

    One per reachable successor, chosen for the road this block leaves on -
    a train coming off the loop reads the loop's own signal, not the through
    road's.
    """
    leg = block.segment_ids[-1]
    found = []
    for successor_id in reachable_successors(block, blocks, interlocking):
        successor = blocks[successor_id]
        chosen = None
        fallback = None
        for signal_id in successor.signal_ids:
            signal = signals[signal_id]
            if signal.from_segment == leg:
                chosen = signal_id
                break
            if signal.from_segment is None:
                fallback = signal_id
        chosen = chosen or fallback
        if chosen is None and successor.signal_ids:
            chosen = successor.signal_ids[0]
        if chosen is not None:
            found.append(chosen)
    return found


def reachable_successors(block: BlockSection, blocks: Dict[str, BlockSection],
                         interlocking=None) -> Tuple[str, ...]:
    """Successor blocks a train could actually reach, given point positions.

    Without an interlocking every successor counts, which is plain automatic
    block behaviour. With one, a facing point at the block's exit narrows it to
    the single road the points are set for.
    """
    if interlocking is None:
        return block.successors
    segment = interlocking.set_route_leg(block.exit_node)
    if segment is None:
        return block.successors
    return tuple(s for s in block.successors
                 if blocks[s].first_segment == segment)
