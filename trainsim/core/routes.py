"""The route table: what movements exist, and what each one needs.

A **route** is a movement from one signal to the next, over a defined set of
points. Real interlockings work from a finite route table decided at design time,
not from paths computed on the fly - a signaller requests a route by name, and
the interlocking either grants it or says why not.

The table here is generated from the topology, which is what modern signalling
design tools do. One route exists per signal, running from that signal over the
points at its node and through the block beyond:

* a **facing** point at the signal's node must be set to the road the route takes
* a **trailing** point there must be set to the road the train is arriving on

Both points sit just beyond the signal, so both belong to this route and not to
the previous one. That detail is what lets a train stand in a loop platform
without holding the points at the far end - the route out of the loop is a
separate request, made when it departs. Without that split, a stopper in the loop
would block the very overtake the loop exists for.

A route is **controlled** if it needs any points; otherwise it is automatic
plain-line working and its signal simply follows occupancy.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Route:
    """One signalled movement, and the resources it requires."""

    id: str
    entry_signal: str
    block_id: str
    #: Points that must be set and locked: point id -> the leg it must connect.
    points: Dict[str, str]
    #: Blocks beyond the exit that must be clear, if overlaps are in use.
    overlap_blocks: Tuple[str, ...] = ()
    #: Blocks this route physically crosses on the level - a diamond crossing.
    #: They are not on the route and no train over them is going where this train
    #: is going, but two trains cannot be on a crossing at once, so they have to
    #: be held for the movement exactly as the route's own block is.
    crossings: Tuple[str, ...] = ()
    from_segment: Optional[str] = None
    exit_node: str = ""

    @property
    def controlled(self) -> bool:
        """True if this route needs points, or crosses another line on the level.

        Either way a signaller has to ask for it, because either way granting it
        takes something away from somebody else.
        """
        return bool(self.points or self.crossings)

    def describe(self) -> str:
        parts = []
        if self.points:
            parts.append(", ".join(
                "%s to %s" % (point, leg)
                for point, leg in sorted(self.points.items())))
        if self.crossings:
            parts.append("crosses %s" % ", ".join(sorted(self.crossings)))
        if not parts:
            return "%s (automatic, into %s)" % (self.id, self.block_id)
        return "%s (into %s, %s)" % (self.id, self.block_id, "; ".join(parts))


def build_routes(network, blocks, signals, points,
                 overlaps: bool = False,
                 crossings: Optional[Dict[str, Tuple[str, ...]]] = None
                 ) -> Dict[str, Route]:
    """Generate the route table from the topology.

    ``overlaps`` adds the block beyond the exit as a required-clear overlap. Real
    railways use overlaps as a margin against a signal being passed at danger;
    they cost capacity, because a block stays held after the train has left it.
    Off by default so the effect can be measured rather than assumed.
    """
    by_node: Dict[str, List] = {}
    for point in points.values():
        by_node.setdefault(point.node, []).append(point)

    routes: Dict[str, Route] = {}
    for signal in signals.values():
        block = blocks[signal.block_id]
        required: Dict[str, str] = {}
        for point in by_node.get(signal.node_id, ()):
            if point.kind == "facing":
                # Which road the route takes out of this node.
                required[point.id] = block.first_segment
            elif signal.from_segment is not None:
                # Which road the train is arriving on must be connected through.
                required[point.id] = signal.from_segment

        overlap: Tuple[str, ...] = ()
        if overlaps and block.successors:
            overlap = (block.successors[0],)

        route_id = "R_" + signal.id[2:] if signal.id.startswith("S_") else "R_" + signal.id
        routes[route_id] = Route(
            id=route_id,
            entry_signal=signal.id,
            block_id=block.id,
            points=required,
            overlap_blocks=overlap,
            crossings=tuple((crossings or {}).get(block.id, ())),
            from_segment=signal.from_segment,
            exit_node=block.exit_node,
        )
    return routes


def routes_by_signal(routes: Dict[str, Route]) -> Dict[str, str]:
    """Signal id -> route id. One route per signal, by construction."""
    return {route.entry_signal: route.id for route in routes.values()}


def conflicting_routes(route: Route, routes: Dict[str, Route]) -> Tuple[str, ...]:
    """Routes that could never be set at the same time as ``route``.

    Static, and used only for reporting. The interlocking itself checks *live*
    resource locks instead, which matters: two routes over the same points do not
    conflict once the first train has passed and the points have been released.
    """
    clashes = []
    for other in routes.values():
        if other.id == route.id:
            continue
        if other.block_id == route.block_id:
            clashes.append(other.id)
            continue
        if (other.block_id in route.crossings
                or route.block_id in other.crossings):
            clashes.append(other.id)
            continue
        for point, leg in route.points.items():
            if other.points.get(point, leg) != leg:
                clashes.append(other.id)
                break
    return tuple(sorted(clashes))
