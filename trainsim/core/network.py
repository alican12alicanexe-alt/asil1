"""Schematic infrastructure model: a directed node-link graph.

The topology is deliberately simple and schematic. Segments are *unidirectional*
(a train always travels ``start_node -> end_node``), so double track is two chains
of segments rather than one chain with a direction flag. Parallel platforms at a
station are simply several segments sharing the same pair of nodes, which is how
the loop platform at Beta works and how junctions will work later.

Every node carries explicit ``km`` and ``y`` schematic coordinates. Real signalling
schematics are hand-laid, not auto-routed, so the scenario file decides the drawing
and the renderer just maps those coordinates to pixels.
"""

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Node:
    """A topological point where segments join."""

    id: str
    km: float
    y: float
    kind: str = "plain"  # plain | station | terminus


@dataclass(frozen=True)
class Segment:
    """A directed piece of track between two nodes.

    ``km_start``/``km_end`` are schematic chainage for drawing and reporting; they
    run backwards (end < start) on the down line, which is exactly what makes the
    schematic show down trains moving right-to-left.
    """

    id: str
    start_node: str
    end_node: str
    length_m: float
    max_speed_ms: float
    track: str
    km_start: float
    km_end: float
    y: float
    platform: Optional[str] = None  # platform id if this is a platform track
    station: Optional[str] = None
    #: Schematic ``y`` at the *end* node, where it differs from the start - a
    #: junction link ramps from one line's alignment to another's, and is the
    #: only thing here that is not drawn parallel to the rest of the railway.
    y_end: Optional[float] = None
    #: Rise per thousand *in the direction of travel*: positive is a climb,
    #: negative a fall. Segments are one-way, so the same physical bank is
    #: recorded as +10 on the up line and -10 on the down, and neither the
    #: dynamics nor the driver has to reason about which way round it is.
    grade_permille: float = 0.0

    @property
    def is_platform(self) -> bool:
        return self.platform is not None

    @property
    def end_y(self) -> float:
        return self.y if self.y_end is None else self.y_end

    def y_away_from(self, node_id: str) -> float:
        """Where this segment lies at its *far* end from ``node_id``.

        Used to decide which road through a point is the straight one. At the
        node itself every road is on the same alignment - that is what a point
        is - so the question can only be answered by looking at where each road
        goes."""
        return self.end_y if node_id == self.start_node else self.y

    def km_at(self, offset_m: float) -> float:
        """Schematic km at ``offset_m`` metres into this segment."""
        if self.length_m <= 0:
            return self.km_start
        frac = max(0.0, min(1.0, offset_m / self.length_m))
        return self.km_start + (self.km_end - self.km_start) * frac


@dataclass(frozen=True)
class Platform:
    """A platform road: a segment a train may berth in.

    ``stop_offset_m`` is where the train's front comes to a stand, measured from
    the start of the segment.
    """

    id: str
    station: str
    segment: str
    track: str
    length_m: float
    stop_offset_m: float


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    km: float
    platforms: Tuple[str, ...] = ()


class Network:
    """Container plus the graph queries the rest of the simulator needs."""

    def __init__(self, nodes, segments, platforms, stations, name="network"):
        self.name = name
        self.nodes: Dict[str, Node] = {n.id: n for n in nodes}
        self.segments: Dict[str, Segment] = {s.id: s for s in segments}
        self.platforms: Dict[str, Platform] = {p.id: p for p in platforms}
        self.stations: Dict[str, Station] = {s.id: s for s in stations}

        # Segment adjacency both ways. A node with several outgoing segments is a
        # facing point; one with several incoming is a trailing point. Both are
        # derived from these two maps rather than declared in scenario files.
        self._out: Dict[str, List[str]] = {}
        self._in: Dict[str, List[str]] = {}
        for seg in self.segments.values():
            self._out.setdefault(seg.start_node, []).append(seg.id)
            self._in.setdefault(seg.end_node, []).append(seg.id)

        self._validate()

    # ------------------------------------------------------------------ queries

    def outgoing(self, node_id: str) -> List[str]:
        """Ids of segments leaving ``node_id``."""
        return list(self._out.get(node_id, ()))

    def incoming(self, node_id: str) -> List[str]:
        """Ids of segments arriving at ``node_id``."""
        return list(self._in.get(node_id, ()))

    def is_facing_point(self, node_id: str) -> bool:
        """True where a train has a choice of route ahead."""
        return len(self._out.get(node_id, ())) > 1

    def is_trailing_point(self, node_id: str) -> bool:
        """True where several roads converge into one."""
        return len(self._in.get(node_id, ())) > 1

    def successors(self, segment_id: str) -> List[str]:
        """Ids of segments a train may continue onto from ``segment_id``."""
        return self.outgoing(self.segments[segment_id].end_node)

    def find_path(self, from_segment: str, to_segment: str,
                  via: Optional[List[str]] = None) -> List[str]:
        """Shortest segment path from ``from_segment`` to ``to_segment``.

        ``via`` is an ordered list of segment ids that must be traversed in order,
        which is how a service is routed through a specific platform (for example
        the loop road at Beta rather than the through platform).
        """
        waypoints = [from_segment] + list(via or []) + [to_segment]
        path: List[str] = [from_segment]
        for start, goal in zip(waypoints, waypoints[1:]):
            if start == goal:
                continue
            leg = self._quickest(start, goal)
            if leg is None:
                raise ValueError(
                    "no route from segment %r to %r - check the scenario's "
                    "topology and calling pattern" % (start, goal)
                )
            path.extend(leg[1:])
        return path

    def _quickest(self, start: str, goal: str) -> Optional[List[str]]:
        """The way round that takes least time, not fewest block sections.

        Counting sections was the same answer on a railway with one way through,
        and the wrong one the moment there are two. A connection between roads at
        different stations is one long block or a few, against a dozen on the
        line it parallels, so fewest-sections routes every train down it however
        slow it is - the timetable silently moves onto a road nobody booked it
        over. Least *time* picks the road a planner would.
        """
        if start not in self.segments:
            raise KeyError("unknown segment %r" % (start,))
        if goal not in self.segments:
            raise KeyError("unknown segment %r" % (goal,))

        def cost(segment_id: str) -> float:
            segment = self.segments[segment_id]
            speed = segment.max_speed_ms
            return segment.length_m / speed if speed > 0 else segment.length_m

        best: Dict[str, float] = {start: 0.0}
        came_from: Dict[str, Optional[str]] = {start: None}
        queue = [(0.0, start)]
        settled = set()
        while queue:
            spent, current = heapq.heappop(queue)
            if current in settled:
                continue
            settled.add(current)
            if current == goal:
                chain = []
                node: Optional[str] = current
                while node is not None:
                    chain.append(node)
                    node = came_from[node]
                return list(reversed(chain))
            for nxt in self.successors(current):
                through = spent + cost(nxt)
                if through < best.get(nxt, float("inf")) - 1e-9:
                    best[nxt] = through
                    came_from[nxt] = current
                    heapq.heappush(queue, (through, nxt))
        return None

    def platforms_at(self, station_id: str, track: Optional[str] = None) -> List[Platform]:
        """Platforms serving a station, optionally restricted to one track."""
        station = self.stations[station_id]
        found = [self.platforms[p] for p in station.platforms]
        if track is not None:
            found = [p for p in found if p.track == track]
        return found

    # --------------------------------------------------------------- validation

    def _validate(self) -> None:
        for seg in self.segments.values():
            for node_id in (seg.start_node, seg.end_node):
                if node_id not in self.nodes:
                    raise ValueError(
                        "segment %r references unknown node %r" % (seg.id, node_id)
                    )
            if seg.length_m <= 0:
                raise ValueError("segment %r has non-positive length" % (seg.id,))
            if seg.max_speed_ms <= 0:
                raise ValueError("segment %r has non-positive speed limit" % (seg.id,))
        for plat in self.platforms.values():
            if plat.segment not in self.segments:
                raise ValueError(
                    "platform %r references unknown segment %r" % (plat.id, plat.segment)
                )
        for station in self.stations.values():
            for plat_id in station.platforms:
                if plat_id not in self.platforms:
                    raise ValueError(
                        "station %r references unknown platform %r"
                        % (station.id, plat_id)
                    )
