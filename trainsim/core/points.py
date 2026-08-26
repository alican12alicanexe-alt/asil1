"""Points (switches), derived from the topology rather than declared.

Anywhere the track branches there is a point, and the scenario file should not
have to say so - it is already implied by two segments leaving one node, or two
arriving at it. So points are derived:

* **facing** - several segments *leave* a node. The position decides which road a
  train takes. Getting this wrong sends a train the wrong way.
* **trailing** - several segments *arrive* at a node. The position decides which
  road is connected to the line beyond. Running through a trailing point set
  against you is a derailment, which is why the interlocking locks them.

A point has no intelligence of its own. It holds a position, and it may be locked
by a route; deciding *when* to move and lock it is the interlocking's job, in
:mod:`trainsim.core.interlocking`.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Point:
    """A set of points at one node."""

    id: str
    node: str
    kind: str                 # "facing" | "trailing"
    legs: Tuple[str, ...]     # segment ids this point can connect
    normal: str               # the leg taken as the normal (default) position
    km: float = 0.0
    y: float = 0.0
    track: str = ""

    def describe(self) -> str:
        return "%s point %s (%s)" % (self.kind, self.id, "/".join(self.legs))


def derive_points(network) -> Dict[str, Point]:
    """Find every point in a network, from its segment adjacency.

    The *normal* position is the first leg in schematic order, which for the
    corridor scenario makes the through platform normal and the loop reverse -
    the usual convention.
    """
    points: Dict[str, Point] = {}
    for node_id, node in network.nodes.items():
        for kind, legs in (("facing", network.outgoing(node_id)),
                           ("trailing", network.incoming(node_id))):
            if len(legs) < 2:
                continue
            ordered = _order_legs(network, node, legs)
            point_id = "PT_%s_%s" % (_clean(node_id), kind[0].upper())
            points[point_id] = Point(
                id=point_id,
                node=node_id,
                kind=kind,
                legs=tuple(ordered),
                normal=ordered[0],
                km=node.km,
                y=node.y,
                track=network.segments[ordered[0]].track,
            )
    return points


def points_at(points: Dict[str, Point], node_id: str) -> List[Point]:
    """Every point at a node - a node may have both a facing and a trailing set."""
    return [p for p in points.values() if p.node == node_id]


def _order_legs(network, node, legs) -> List[str]:
    """Legs nearest the running line first, so the through road is normal.

    Judged at each leg's *far* end rather than at the node. At the node itself
    every road is on the same alignment - that is precisely what a point is - so
    only where a road goes says whether it is the straight one. For a loop
    platform that is the same answer as looking at the node; for a junction link
    ramping onto another line it is the only one that works.
    """
    return sorted(legs, key=lambda s: (
        abs(network.segments[s].y_away_from(node.id) - node.y), s))


def _clean(node_id: str) -> str:
    return node_id.replace("@", "_").replace(".", "_")
