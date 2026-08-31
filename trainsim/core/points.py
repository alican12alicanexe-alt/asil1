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
            for way, group in sorted(_by_direction(network, legs).items()):
                if len(group) < 2:
                    continue
                ordered = _order_legs(network, node, group)
                point_id = "PT_%s_%s%s" % (_clean(node_id), kind[0].upper(),
                                           "" if way >= 0 else "R")
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


def _by_direction(network, legs) -> Dict[int, List[str]]:
    """Legs grouped by which way along the railway they run.

    Two roads at a node are alternatives - a point - only if a train could take
    either one. Roads running opposite ways are not alternatives at all: they are
    the two directions of the same place, and on a reversible line, often the two
    directions of the very same rails. Grouping by direction is what keeps a
    line worked both ways from sprouting a set of points at every block boundary.

    Direction is read off the schematic chainage rather than declared, so it
    holds for a crossover landing on the other direction's road as much as for plain track:
    what matters is which way a train on that road would be travelling here.
    """
    groups: Dict[int, List[str]] = {}
    for leg in legs:
        segment = network.segments[leg]
        way = -1 if segment.km_end < segment.km_start else 1
        groups.setdefault(way, []).append(leg)
    return groups


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
