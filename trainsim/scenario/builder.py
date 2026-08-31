"""Expand a compact infrastructure description into a full railway.

Scenario files describe a line the way a railway engineer would: stations at
chainages, tracks that serve them, platforms, and a block length. Writing out
every node, segment, signal and block by hand would mean roughly 150 entries for
a three-station corridor, which nobody would edit or review.

This module does the expansion. For each track it walks from the first station to
the last, emitting *platform zones* at the stations and dividing the open line
between them into equal blocks close to the requested block length. Each block
gets one segment (or one per parallel platform road), one entry signal, and an
exclusive occupancy identity.

Parallel platforms - the loop road at Beta - are simply several segments sharing
the same pair of nodes. No switch model is needed for them to be safe: each road
is its own block, and the single approach block ahead of the divergence can hold
only one train, so two trains can never be presented at the points at once.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from ..core.network import Network, Node, Platform, Segment, Station
from ..core.points import Point, derive_points
from ..core.routes import Route, build_routes
from ..core.signals import BlockSection, Signal
from ..core.units import kmh_to_ms
from . import schema


class InfrastructureError(ValueError):
    """Raised when an infrastructure description cannot be expanded."""


@dataclass(frozen=True)
class Connection:
    """A piece of railway built to join two roads, and where it came from.

    Kept so that the connections a scenario asked for can be named back to it
    before anything runs - a generated id is only useful if you can find out what
    it was generated from.
    """

    id: str
    from_road: str
    to_road: str
    km_start: float
    km_end: float
    length_m: float
    max_speed_ms: float
    between_roads: bool


@dataclass
class Infrastructure:
    """Everything the kernel and the renderer need about the railway."""

    network: Network
    blocks: Dict[str, BlockSection]
    signals: Dict[str, Signal]
    block_of_segment: Dict[str, str]
    tracks: Dict[str, dict]
    points: Dict[str, Point]
    routes: Dict[str, Route]
    #: Block -> the blocks it crosses on the level. Symmetric. Empty unless a
    #: junction link has to get past a running line to reach the one it joins.
    crossings: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    #: Connections built from the ``crossovers:`` list, in the order declared.
    connections: Tuple["Connection", ...] = ()
    #: Block -> (section, direction) for stretches worked in both directions.
    #: A section may only be worked one way at a time; see the interlocking.
    direction_sections: Dict[str, Tuple[str, str]] = field(default_factory=dict)

    def platform_segment(self, platform_id: str) -> str:
        return self.network.platforms[platform_id].segment

    def controlled_signals(self) -> Tuple[str, ...]:
        return tuple(sorted(s.id for s in self.signals.values() if s.controlled))


DEFAULTS = {
    "platform_zone_m": 400.0,
    "block_length_m": 2000.0,
    "max_speed_kmh": 140.0,
    "stop_margin_m": 40.0,
    "platform_y_step": 0.45,
    #: Rise per thousand. Level unless a track says otherwise, which keeps a
    #: scenario that does not care about gradients exactly as it was.
    "grade_permille": 0.0,
}


def build_infrastructure(spec: dict, overlaps: bool = False) -> Infrastructure:
    """Expand an infrastructure spec (already parsed from YAML/JSON)."""
    return _Builder(spec).build(overlaps=overlaps)


class _Builder(object):

    def __init__(self, spec: dict):
        self.spec = spec
        _check("infrastructure", spec, schema.INFRASTRUCTURE)
        self.name = spec.get("name", "network")
        _check("infrastructure defaults", spec.get("defaults") or {},
               schema.DEFAULTS)
        self.defaults = dict(DEFAULTS)
        self.defaults.update(spec.get("defaults", {}) or {})

        self.stations_spec = _index(spec.get("stations"), "stations")
        self.tracks_spec = _index(spec.get("tracks"), "tracks")
        self.platforms_spec = _index(spec.get("platforms"), "platforms")
        self.crossovers_spec = _index(spec.get("crossovers"), "crossovers",
                                      name_from=_crossover_name)
        for station_id, station in self.stations_spec.items():
            _check("station %r" % station_id, station, schema.STATION)
        for track_id, track in self.tracks_spec.items():
            _check("track %r" % track_id, track, schema.TRACK)
            for entry in track.get("block_lengths") or []:
                _check("track %r block_lengths entry" % track_id, entry,
                       schema.BLOCK_LENGTHS)
            for entry in track.get("gradients") or []:
                _check("track %r gradients entry" % track_id, entry,
                       schema.GRADIENTS)
            if track.get("junction") is not None:
                _check("track %r junction" % track_id, track["junction"],
                       schema.JUNCTION)
        for platform_id, platform in self.platforms_spec.items():
            _check("platform %r" % platform_id, platform, schema.PLATFORM)
        for crossover_id, crossover in self.crossovers_spec.items():
            _check("crossover %r" % crossover_id, crossover, schema.CROSSOVER)

        self.nodes: Dict[str, Node] = {}
        self.segments: List[Segment] = []
        self.platforms: List[Platform] = []
        self.blocks: Dict[str, BlockSection] = {}
        self.signals: Dict[str, Signal] = {}
        self.block_of_segment: Dict[str, str] = {}
        self.station_platforms: Dict[str, List[str]] = {}
        #: Junction links, kept until every track is laid out so that what each
        #: one has to cross can be worked out from the finished geometry.
        self.ramps: List[Tuple[str, dict]] = []
        #: Where each track's platform zones ended up, so that a branch can find
        #: the node on the main line it has to attach itself to.
        self.track_layout: Dict[str, dict] = {}
        #: Chainages a track must have a node at, whatever its block length says.
        #: A crossover has to start and end somewhere a signal can stand.
        self.required_chainages: Dict[str, List[float]] = {}

        #: Mirror track -> the track whose rails it is laid over. A reversible
        #: line is modelled as a second set of blocks over the same railway,
        #: running the other way, each block conflicting with the one it lies on
        #: top of. See :meth:`_declare_reversible`.
        self.mirror_of: Dict[str, str] = {}
        #: Block -> the blocks over the same rails it may not be used with.
        self.mirror_conflicts: Dict[str, set] = {}
        #: Mirror track -> the km range over which its line may be worked both
        #: ways. Only that stretch gets a twin.
        self.reversible_span: Dict[str, Tuple[float, float]] = {}
        #: Block -> (section id, "normal" or "reverse"). A section may only be
        #: worked one way at a time, which is what stops the two directions
        #: deadlocking head to head inside it.
        self.direction_sections: Dict[str, Tuple[str, str]] = {}
        self._declare_reversible()

    # -------------------------------------------------------------------- build

    def build(self, overlaps: bool = False) -> Infrastructure:
        if not self.stations_spec:
            raise InfrastructureError("infrastructure defines no stations")
        if not self.tracks_spec:
            raise InfrastructureError("infrastructure defines no tracks")

        # Where crossovers meet each line, so those tracks get a block boundary
        # there. Worked out before any track is laid out, because a block plan
        # has to accommodate the connections rather than the other way round.
        self._plan_crossovers()

        # Plain tracks first: a branch attaches to a node on the line it joins,
        # so that line has to exist before the branch can be laid out.
        plain = [t for t in self.tracks_spec
                 if not self.tracks_spec[t].get("junction")
                 and t not in self.mirror_of]
        branches = [t for t in self.tracks_spec
                    if self.tracks_spec[t].get("junction")
                    and t not in self.mirror_of]
        for track_id in plain + branches:
            self._build_track(track_id)

        # The twin road over each reversible line, before the connections that
        # reach it: a crossover onto the other direction's road joins one of these blocks.
        self._emit_mirrors()
        self._emit_crossovers()
        self._link_successors()

        stations = [
            Station(
                id=sid,
                name=s.get("name", sid),
                km=float(s["km"]),
                platforms=tuple(self.station_platforms.get(sid, ())),
            )
            for sid, s in self.stations_spec.items()
        ]
        network = Network(
            nodes=list(self.nodes.values()),
            segments=self.segments,
            platforms=self.platforms,
            stations=stations,
            name=self.name,
        )
        tracks = {
            tid: {
                "id": tid,
                "y": float(t.get("y", 0.0)),
                "direction": t.get("direction", "up"),
                "serves": list(t.get("serves", [])),
                # The line whose rails this one is laid over, where it is the
                # road back along a stretch worked both ways. The schematic
                # needs it: two roads over one rail draw two sets of signals in
                # the same place, and the view has to know they are two
                # directions of one rail rather than two separate roads.
                "mirrors": t.get("mirrors"),
            }
            for tid, t in self.tracks_spec.items()
        }
        # Points fall out of the topology; signals then have to be created per
        # approaching road, because a trailing point means two trains ask
        # different questions of the same block ahead.
        points = derive_points(network)
        crossings = self._derive_crossings(network)
        self._build_signals(network, points)
        routes = build_routes(network, self.blocks, self.signals, points,
                              overlaps=overlaps, crossings=crossings)
        self._mark_controlled_signals(routes)

        return Infrastructure(
            crossings=crossings,
            direction_sections=dict(self.direction_sections),
            connections=tuple(
                Connection(
                    id=c["id"], from_road=c["from"], to_road=c["to"],
                    km_start=self.nodes[self._crossover_ends(c)[0]].km,
                    km_end=self.nodes[self._crossover_ends(c)[1]].km,
                    length_m=c["length_m"], max_speed_ms=c["max_speed_ms"],
                    between_roads=bool(c.get("roads")),
                )
                for c in self.crossovers
            ),
            network=network,
            blocks=self.blocks,
            signals=self.signals,
            block_of_segment=self.block_of_segment,
            tracks=tracks,
            points=points,
            routes=routes,
        )

    # ------------------------------------------------------ reversible working

    def _declare_reversible(self) -> None:
        """Give a line a twin running the other way, wherever the crossovers do.

        Working a line both ways is what a railway does when something is in
        the way: a train crosses to the other line, runs along it against that
        line's usual direction, and crosses back beyond the obstruction. The
        rails are the same rails - what changes is which way trains are being
        signalled over them, and neither way is the wrong one.

        That is modelled as a second set of blocks laid over the same alignment,
        running the other way, each of them declared to *cross* the one beneath
        it. Crossing blocks already mean something to the interlocking - it is
        how a flat junction is policed - so a route one way over a stretch is
        refused while anything holds or occupies it the other way, and a head-on
        movement cannot be set up. Nothing in the kernel, the signalling or the
        driver has to learn about direction at all. The alternative was to teach
        trains to traverse a segment backwards, which touches the path, the
        signals, the routes and the occupancy, and would have made every one of
        them ask "which way is this train facing?". A second set of blocks asks
        nothing.

        What is *not* declared is where. A stretch of line is worked in both
        directions exactly where a train can get onto the opposite line and off
        it again, and that is decided by the crossovers - which is how a real
        railway reads too: bidirectional signalling is provided between the
        crossovers, because between them is the only place it is any use. So the
        scenario draws its connections and the reversible stretch falls out of
        them. Declaring it separately meant saying the same thing twice, in two
        places that could disagree; making every line reversible end to end
        meant signalling twice the railway to no purpose, since a train that
        cannot get back off the other direction's road is not going anywhere.
        """
        connections: Dict[str, List[Tuple[float, float]]] = {}
        for crossover_id, spec in self.crossovers_spec.items():
            pair = self._opposite_direction_pair(crossover_id, spec)
            if pair is None:
                continue
            km = float(spec["km"])
            length = float(spec.get("length_m", 300.0))
            for track_id in pair:
                connections.setdefault(track_id, []).append(
                    (km, km + length / 1000.0))
        for track_id, places in sorted(connections.items()):
            if len(places) < 2:
                raise InfrastructureError(
                    "track %r has one connection to a line running the other "
                    "way, at km %.3f. One is a way onto the other line and no "
                    "way off it - a train would be left on a road with nothing "
                    "in front of it. Working a line both ways needs a "
                    "connection at each end of the stretch to be worked."
                    % (track_id, places[0][0]))
            # One span between each neighbouring pair of connections, not one
            # span from the first to the last. The stretch a train can be worked
            # the other way over is the stretch between the crossover it gets on
            # at and the one it gets off at, and those are neighbours - so each
            # pair is its own SECTION, and a train being worked the other way
            # past Kingsford does not shut the line at Ashdown. One section for
            # the lot would make a sixty-kilometre railway one-direction-at-a-
            # time, which is a working method for a branch, not for this.
            places.sort()
            self._lay_twin(track_id, [(low[0], high[1])
                                      for low, high in zip(places, places[1:])])

    def _opposite_direction_pair(self, crossover_id: str,
                         spec: dict) -> Optional[Tuple[str, str]]:
        """The two tracks of a connection between lines running opposite ways.

        ``None`` for anything else - a connection between platform roads, a
        crossover between two lines that run the same way, or a spec that is
        wrong in a manner :meth:`_plan_crossovers` will report properly. This
        runs before validation and must not pre-empt its error messages.
        """
        from_id, to_id = str(spec.get("from", "")), str(spec.get("to", ""))
        if spec.get("type") == "diamond":
            # Two lines crossing, joined to nothing. Nothing can get onto the
            # other line here, so nothing about it is worked in both directions.
            return None
        if from_id in self.platforms_spec or to_id in self.platforms_spec:
            return None
        if from_id not in self.tracks_spec or to_id not in self.tracks_spec:
            return None
        if "km" not in spec or from_id == to_id:
            return None
        if (self.tracks_spec[from_id].get("direction", "up")
                == self.tracks_spec[to_id].get("direction", "up")):
            return None
        return from_id, to_id

    def _lay_twin(self, track_id: str, spans: List[Tuple[float, float]]) -> None:
        """The road back along ``track_id``, over each of ``spans``.

        One twin track, several sections. The rails are the same rails end to
        end, so there is one road back along them; but which stretch of it may
        be given to a train is settled crossover to crossover, so each span gets
        its own section id.
        """
        track = self.tracks_spec[track_id]
        mirror_id = "%s_R" % track_id
        if mirror_id in self.tracks_spec:
            raise InfrastructureError(
                "%r is worked in both directions, so %r is the name of the road "
                "back along it - the scenario cannot use that name too"
                % (track_id, mirror_id))
        mirror = dict(track)
        mirror["direction"] = ("up" if track.get("direction", "up") == "down"
                               else "down")
        mirror["serves"] = list(reversed(list(track.get("serves") or [])))
        mirror["mirrors"] = track_id
        self.tracks_spec[mirror_id] = mirror
        self.mirror_of[mirror_id] = track_id
        self.reversible_span[mirror_id] = spans

    def _on_the_rails(self, track_id: str, chainage: float) -> float:
        """A chainage on a mirror, restated on the track it lies over.

        The twin runs the other way, so its chainage counts from the other end.
        A node is a place on the ground and belongs to the rails, not to the
        direction anyone is being signalled over them.
        """
        original = self.mirror_of.get(track_id)
        if original is None:
            return chainage
        return self._track_length(original) - chainage

    def _track_length(self, track_id: str) -> float:
        """How long a track is, before it has been laid out."""
        track = self.tracks_spec[track_id]
        serves = list(track.get("serves") or [])
        if len(serves) < 2:
            raise InfrastructureError(
                "track %r must serve at least two stations" % (track_id,))
        first = float(self.stations_spec[serves[0]]["km"])
        last = float(self.stations_spec[serves[-1]]["km"])
        return abs(last - first) * 1000.0

    def _emit_mirrors(self) -> None:
        """Lay each reversible track's twin over it, block for block.

        The twin borrows everything: the same nodes, the same lengths, the same
        speeds, the same platform roads. Only the direction is reversed - so its
        segments run from the original's exit node to its entry node, and its
        gradient is the opposite of the original's, because a climb one way is a
        fall the other.
        """
        for mirror_id, track_id in self.mirror_of.items():
            originals = [b for b in self.blocks.values() if b.track == track_id]
            if not originals:
                raise InfrastructureError(
                    "track %r is reversible but was never laid out"
                    % (track_id,))
            spans = self.reversible_span[mirror_id]
            for index, (low, high) in enumerate(spans):
                if not any(min(b.km_start, b.km_end) >= low - 1e-6
                           and max(b.km_start, b.km_end) <= high + 1e-6
                           for b in originals):
                    raise InfrastructureError(
                        "track %r has no complete block section between km "
                        "%.3f and %.3f, so there is nothing there to work in "
                        "both directions" % (track_id, low, high))
            done = set()
            for index, (low, high) in enumerate(spans):
              section_id = ("%s_%d" % (mirror_id, index + 1) if len(spans) > 1
                            else mirror_id)
              for block in originals:
                inside = (block.id not in done
                          and min(block.km_start, block.km_end) >= low - 1e-6
                          and max(block.km_start, block.km_end) <= high + 1e-6)
                if not inside:
                    continue
                if len(block.segment_ids) != 1:
                    raise InfrastructureError(
                        "block %s spans %d segments, and only single-segment "
                        "blocks can be worked in both directions so far"
                        % (block.id, len(block.segment_ids)))
                source = next(s for s in self.segments
                              if s.id == block.segment_ids[0])
                mirror_seg = "%s_R" % source.id
                self.segments.append(Segment(
                    id=mirror_seg,
                    start_node=source.end_node,
                    end_node=source.start_node,
                    length_m=source.length_m,
                    max_speed_ms=source.max_speed_ms,
                    track=mirror_id,
                    km_start=source.km_end,
                    km_end=source.km_start,
                    y=source.end_y,
                    y_end=source.y,
                    platform=None,
                    station=source.station,
                    grade_permille=-source.grade_permille,
                ))
                self.blocks[mirror_seg] = BlockSection(
                    id=mirror_seg,
                    segment_ids=(mirror_seg,),
                    track=mirror_id,
                    entry_node=source.end_node,
                    exit_node=source.start_node,
                    length_m=source.length_m,
                    km_start=source.km_end,
                    km_end=source.km_start,
                    platform=None,
                    station=block.station,
                )
                self.block_of_segment[mirror_seg] = mirror_seg
                if source.platform is not None:
                    # A platform road worked the other way is still a platform
                    # road: a train diverted onto the other direction's road can call at it,
                    # and the timetable has to be able to say so. It is NOT added
                    # to the station's list of roads - the station has the roads
                    # it has, and this is one of them being used backwards, not a
                    # second platform that would show up in every count.
                    original = next(pl for pl in self.platforms
                                    if pl.id == source.platform)
                    self.platforms.append(Platform(
                        id=mirror_seg,
                        station=original.station,
                        segment=mirror_seg,
                        track=mirror_id,
                        length_m=original.length_m,
                        # The concrete is the same concrete, and it is centred
                        # in the road, so mirroring the road leaves it exactly
                        # where it was. Restating the stopping point from the
                        # other end - which is what this used to do - put a
                        # 160 m train at 350-510 m in a road whose platform runs
                        # 480-720: thirty metres of it alongside the platform
                        # and the rest of it past the end.
                        near_offset_m=original.near_offset_m,
                        stop_margin_m=original.stop_margin_m,
                        berth=original.berth,
                    ))
                # The two are the same rails. Declaring them as each other's
                # crossing is what stops the interlocking setting a route over
                # one while the other is held or occupied.
                self.mirror_conflicts.setdefault(mirror_seg, set()).add(block.id)
                self.mirror_conflicts.setdefault(block.id, set()).add(mirror_seg)
                # Both copies belong to one section, and the section is what may
                # only be worked one way at a time. A block in the overlap
                # between two spans - the crossover's own block, which both
                # neighbouring pairs contain - goes to the first, so a block is
                # in exactly one section.
                done.add(block.id)
                self.direction_sections[block.id] = (section_id, "normal")
                self.direction_sections[mirror_seg] = (section_id, "reverse")

    # -------------------------------------------------------------- crossovers

    def _track_origin(self, track_id: str) -> Tuple[float, float]:
        """``(start_km, sign)`` for a track, without laying it out."""
        track = self.tracks_spec[track_id]
        serves = list(track.get("serves") or [])
        if not serves:
            raise InfrastructureError("track %r serves nothing" % (track_id,))
        sign = -1.0 if track.get("direction", "up") == "down" else 1.0
        return float(self.stations_spec[serves[0]]["km"]), sign

    def _plan_crossovers(self) -> None:
        """Work out where each crossover meets its two lines.

        A crossover is a connection between two running lines, out on the plain
        line rather than at a station: a train leaves one, runs over the points,
        and continues on the other. Both ends need a block boundary - a signal
        has to be able to stand there and a route has to be able to end there -
        so the chainages are collected here, before the block plan is drawn, and
        the tracks are then divided to fit them.

        Three kinds, chosen with ``type``:

        ``single`` (the default)
            One diagonal. ``from`` is the road it leaves and ``to`` the road it
            joins, reading in the direction of increasing km - so ``from: UP,
            to: DN`` is drawn ``\\`` and ``from: DN, to: UP`` is drawn ``/``.
            Which hand it is laid in matters: a single crossover takes a train
            one way across, and the way back needs the other hand somewhere
            else. That is a real constraint and it is now modelled.
        ``scissors``
            Both diagonals over one piece of pointwork, so a train can cross
            either way at the same place.
        ``diamond``
            Not a connection at all: two lines crossing on the level. No train
            changes lines, and two trains cannot be on it at once.
        """
        self.crossovers: List[dict] = []
        self.diamonds: List[dict] = []
        for crossover_id, spec in self.crossovers_spec.items():
            try:
                from_id, to_id = str(spec["from"]), str(spec["to"])
            except KeyError as exc:
                raise InfrastructureError(
                    "crossover %r: missing %s" % (crossover_id, exc))

            kind = str(spec.get("type", "single"))
            if kind not in ("single", "scissors", "diamond"):
                raise InfrastructureError(
                    "crossover %r: unknown type %r. A connection is 'single' "
                    "(one diagonal, the default), 'scissors' (both diagonals "
                    "over one piece of pointwork) or 'diamond' (two lines "
                    "crossing on the level, joining nothing)."
                    % (crossover_id, kind))
            if kind == "diamond":
                self._plan_diamond(crossover_id, spec, from_id, to_id)
                continue

            # Two kinds of end, and which one this is decides everything that
            # follows. A running line has to be *told* where the connection
            # meets it, and the block plan is then bent to put a boundary there.
            # A platform road already ends where it ends: the throat node it
            # shares with the other roads at that station, which is where a
            # connection would leave from in the first place.
            if from_id in self.platforms_spec or to_id in self.platforms_spec:
                self._plan_road_crossover(crossover_id, spec, from_id, to_id)
                continue

            if "km" not in spec:
                raise InfrastructureError(
                    "crossover %r joins two running lines, so it needs a km to "
                    "say where. Only a connection between platform roads can "
                    "leave that out - a road already ends somewhere."
                    % (crossover_id,))
            km = float(spec["km"])
            for track_id in (from_id, to_id):
                if track_id not in self.tracks_spec:
                    raise InfrastructureError(
                        "crossover %r: %r is neither a track nor a platform "
                        "road. Tracks here: %s. "
                        % (crossover_id, track_id,
                           ", ".join(sorted(self.tracks_spec))))
            if from_id == to_id:
                raise InfrastructureError(
                    "crossover %r: from and to are the same track"
                    % (crossover_id,))

            from_dir = self.tracks_spec[from_id].get("direction", "up")
            to_dir = self.tracks_spec[to_id].get("direction", "up")
            if from_dir != to_dir:
                self._plan_two_way_crossover(
                    crossover_id, spec, from_id, to_id, kind)
                continue

            self._plan_line_crossover(crossover_id, spec, from_id, to_id, km)
            if kind == "scissors":
                # The other diagonal, over the same pointwork: the road that was
                # being joined can now be left, and vice versa.
                other = "%s_%s_%s" % (crossover_id, to_id, from_id)
                self._plan_line_crossover(other, spec, to_id, from_id, km)
                self._same_pointwork((crossover_id, other))

    def _plan_line_crossover(self, crossover_id, spec, from_id, to_id,
                             km) -> None:
        """A connection between two roads that run the same way, at ``km``."""
        length = float(spec.get("length_m", 300.0))
        from_km, from_sign = self._track_origin(from_id)
        to_km, to_sign = self._track_origin(to_id)
        leave_ch = (km - from_km) * from_sign * 1000.0
        join_ch = (km - to_km) * to_sign * 1000.0 + length
        if leave_ch <= 0 or join_ch <= 0:
            raise InfrastructureError(
                "crossover %r at km %.3f falls off the end of %s or %s"
                % (crossover_id, km, from_id, to_id))

        # A mirror has no rails of its own: the boundary a connection needs
        # has to be forced on the track it lies over, and the connection then
        # finds it there.
        self._needs_boundary(self.mirror_of.get(from_id, from_id),
                             self._on_the_rails(from_id, leave_ch))
        self._needs_boundary(self.mirror_of.get(to_id, to_id),
                             self._on_the_rails(to_id, join_ch))
        self.crossovers.append({
            "id": crossover_id,
            "from": from_id,
            "to": to_id,
            "leave_ch": leave_ch,
            "join_ch": join_ch,
            "length_m": length,
            "km": km,
            "max_speed_ms": kmh_to_ms(float(
                spec.get("max_speed_kmh", 60.0))),
        })

    def _needs_boundary(self, track_id: str, chainage: float) -> None:
        """Ask for a block boundary at ``chainage``, once.

        Several connections meet a line in the same place - the four movements
        over one crossover do, by definition - and asking twice would divide the
        track there twice, leaving a block of no length between the two copies.
        """
        wanted = self.required_chainages.setdefault(track_id, [])
        if not any(abs(chainage - already) < 1e-6 for already in wanted):
            wanted.append(chainage)

    def _plan_two_way_crossover(self, crossover_id, spec, from_id,
                                   to_id, kind) -> None:
        """A crossover between the up line and the down line.

        One diagonal is two movements, because a diagonal is a piece of railway
        and a piece of railway can be traversed either way: an up train crossing
        from the up line to the down line, and a down train crossing back over
        the same rails in the other direction. Neither is a movement against the
        way its road is signalled, because each names the road for the direction
        it is going - ``DN_R`` is the road *up* the down line, laid over the
        same rails by :meth:`_declare_reversible`.

        ``from`` and ``to`` read in the direction of increasing km, so they say
        which hand the crossover is laid in, and the hand decides who can use
        it. ``from: UP, to: DN`` takes an up train onto the down line and a down
        train back off it; the up train's way back needs the other hand further
        along. That is why a diversion is drawn as a pair - ``\\`` at one end
        and ``/`` at the other - and it is why ``scissors``, which lays both
        diagonals at one place, is the other option.
        """
        km = float(spec["km"])
        far = km + float(spec.get("length_m", 300.0)) / 1000.0
        hands = [(from_id, to_id)]
        if kind == "scissors":
            hands.append((to_id, from_id))
        laid = []
        for near, further in hands:
            # The diagonal runs from `near` at km to `further` at far. A train
            # travelling up traverses it that way round; a train travelling down
            # traverses the same rails the other way, and each takes the road
            # laid for the direction it is going.
            for leaves, joins, at in (
                    (self._road_going_up(near), self._road_going_up(further), km),
                    (self._road_going_down(further), self._road_going_down(near), far)):
                if (leaves not in self.tracks_spec
                        or joins not in self.tracks_spec):
                    # Only reachable if _declare_reversible declined to lay a
                    # twin, and it says why in an error of its own.
                    continue
                movement_id = "%s_%s_%s" % (crossover_id, leaves, joins)
                self._plan_line_crossover(movement_id, spec, leaves, joins, at)
                laid.append(movement_id)
        self._same_pointwork(laid)

    def _road_going_up(self, track_id: str) -> str:
        """The road over ``track_id``'s rails that is worked towards higher km."""
        if self.tracks_spec[track_id].get("direction", "up") == "up":
            return track_id
        return "%s_R" % track_id

    def _road_going_down(self, track_id: str) -> str:
        """The road over ``track_id``'s rails that is worked towards lower km."""
        if self.tracks_spec[track_id].get("direction", "up") == "down":
            return track_id
        return "%s_R" % track_id

    def _same_pointwork(self, movement_ids) -> None:
        """Declare a set of movements to be the same rails.

        Every movement over one crossover runs over the same points, whichever
        road it leaves and whichever way it is going, so two trains cannot be on
        it at once. Crossing blocks are how that is already said here.
        """
        movement_ids = list(movement_ids)
        for movement_id in movement_ids:
            self.mirror_conflicts.setdefault(movement_id, set()).update(
                other for other in movement_ids if other != movement_id)

    def _plan_diamond(self, crossover_id, spec, from_id, to_id) -> None:
        """Two lines crossing on the level, connected to nothing.

        A diamond joins no roads: no train changes lines there, and there is
        nothing to lay. What it costs is exclusivity - two trains cannot be on
        one piece of crossing rail - and that is the whole of what a flat
        junction costs anywhere else here. So it is recorded and turned into a
        crossing between the two blocks once the tracks have been laid out and
        it is known which blocks those are.

        A diamond derived from the drawing already happens: a junction link that
        ramps across an intervening line picks that line up as a crossing. This
        is for the case the drawing cannot show - two lines that cross where
        neither is ramping across the other.
        """
        for track_id in (from_id, to_id):
            if track_id not in self.tracks_spec:
                raise InfrastructureError(
                    "diamond %r: %r is not a track. A diamond is two running "
                    "lines crossing on the level, so both ends have to be "
                    "tracks. Tracks here: %s."
                    % (crossover_id, track_id, ", ".join(sorted(self.tracks_spec))))
        if from_id == to_id:
            raise InfrastructureError(
                "diamond %r: a line cannot cross itself" % (crossover_id,))
        if "km" not in spec:
            raise InfrastructureError(
                "diamond %r needs a km to say where the two lines cross"
                % (crossover_id,))
        self.diamonds.append({
            "id": crossover_id,
            "from": from_id,
            "to": to_id,
            "km": float(spec["km"]),
        })

    def _emit_diamonds(self, network: Network) -> Dict[str, set]:
        """Turn each diamond into a crossing between the blocks that meet there."""
        crossings: Dict[str, set] = {}
        for diamond in self.diamonds:
            blocks = []
            for track_id in (diamond["from"], diamond["to"]):
                block_id = self._block_on_track_at(network, track_id,
                                                   diamond["km"])
                if block_id is None:
                    raise InfrastructureError(
                        "diamond %r is at km %.3f, and %s has no block there "
                        "for it to conflict with"
                        % (diamond["id"], diamond["km"], track_id))
                blocks.append(block_id)
            crossings.setdefault(blocks[0], set()).add(blocks[1])
            crossings.setdefault(blocks[1], set()).add(blocks[0])
        return crossings

    def _plan_road_crossover(self, crossover_id, spec, from_id, to_id) -> None:
        """A connection whose ends are platform roads rather than running lines.

        Nothing is reserved in the block plan for these, because nothing needs to
        be: a platform road already has a node at each end. What is worth being
        plain about is *which* node. Every road at a station shares its throat
        nodes with the others - that sharing is where the points come from - so a
        connection declared from ASHDOWN_1 leaves the Ashdown throat, and a train
        off any Ashdown road can take it. Naming the road says where the
        connection is, not who may use it. A road that is to have an approach of
        its own is a road, not a connection.
        """
        for road_id in (from_id, to_id):
            if road_id not in self.platforms_spec:
                raise InfrastructureError(
                    "crossover %r: %r is not a platform road, and the other end "
                    "is. Both ends have to be the same kind of thing - two "
                    "running lines at a km, or two roads."
                    % (crossover_id, road_id))
        if from_id == to_id:
            raise InfrastructureError(
                "crossover %r: from and to are the same road" % (crossover_id,))
        self.crossovers.append({
            "id": crossover_id,
            "from": from_id,
            "to": to_id,
            "roads": True,
            "length_m": (float(spec["length_m"])
                         if spec.get("length_m") is not None else None),
            "max_speed_ms": kmh_to_ms(float(spec.get("max_speed_kmh", 60.0))),
        })

    def _crossover_ends(self, crossover) -> Tuple[str, str]:
        """The two nodes a connection runs between.

        A road hands over the node it already has: the far end of the road it
        leaves, the near end of the road it joins. A running line is asked for
        the block boundary the plan was bent to provide.
        """
        from_id, to_id = crossover["from"], crossover["to"]
        if crossover.get("roads"):
            leaving, joining = self.blocks.get(from_id), self.blocks.get(to_id)
            for road_id, block in ((from_id, leaving), (to_id, joining)):
                if block is None:
                    raise InfrastructureError(
                        "crossover %r: road %r was never laid out - is its "
                        "station on a track that serves it?"
                        % (crossover["id"], road_id))
            return leaving.exit_node, joining.entry_node

        start = self._node_id(self.mirror_of.get(from_id, from_id),
                              self._on_the_rails(from_id, crossover["leave_ch"]))
        end = self._node_id(self.mirror_of.get(to_id, to_id),
                            self._on_the_rails(to_id, crossover["join_ch"]))
        for node_id, track_id in ((start, from_id), (end, to_id)):
            if node_id not in self.nodes:
                raise InfrastructureError(
                    "crossover %r: no block boundary at km %.3f on %s - the "
                    "connection would have nowhere to start or finish"
                    % (crossover["id"], crossover["km"], track_id))
        return start, end

    def _emit_crossovers(self) -> None:
        """One segment, one block and one signal per connection."""
        for crossover in self.crossovers:
            from_id, to_id = crossover["from"], crossover["to"]
            start, end = self._crossover_ends(crossover)
            if start == end:
                raise InfrastructureError(
                    "crossover %r would start and finish at the same place (%s). "
                    "Roads at one station already meet at their throat - the "
                    "points join them, and a connection between them would be a "
                    "second way of saying so."
                    % (crossover["id"], start))

            if crossover.get("roads"):
                self._check_road_crossover_runs_forward(crossover, start, end)
                from_y = self._road_y(from_id)
                to_y = self._road_y(to_id)
                if crossover["length_m"] is None:
                    # Not given: take it from the ground. The two ends are real
                    # places with real chainages, and the railway between them is
                    # as long as the gap it has to cover.
                    crossover["length_m"] = max(
                        50.0,
                        abs(self.nodes[end].km - self.nodes[start].km) * 1000.0)
                crossover["km"] = self.nodes[start].km
            else:
                from_y = float(self.tracks_spec[from_id].get("y", 0.0))
                to_y = float(self.tracks_spec[to_id].get("y", 0.0))
            track_id = (self._road_track(from_id) if crossover.get("roads")
                        else from_id)
            grade = float(self.tracks_spec[track_id].get(
                "grade_permille", self.defaults["grade_permille"]))
            self._emit_connection(crossover, start, end, track_id,
                                  from_y, to_y, grade)

    def _emit_connection(self, crossover, start, end, track_id,
                         from_y, to_y, grade) -> None:
        """Lay the connection itself: one block, or a line's worth of them.

        A crossover between parallel lines is one block and always was - it is a
        few hundred metres of pointwork and there is nowhere inside it for a
        signal to stand. A connection between roads at different places is a
        different animal: it is a piece of running line, and a piece of running
        line 17 km long that is one block section can hold one train at a time.
        Left like that it does not fail, which is worse - it quietly costs more
        capacity than it adds, and the flight that used to work stops working.

        So a connection is divided the way a track is, to the block length of the
        line it leaves, and gets a signal at every boundary like anything else.
        """
        conn_id = crossover["id"]
        total = float(crossover["length_m"])
        block_length = float(self.tracks_spec[track_id].get(
            "block_length_m", self.defaults["block_length_m"]))
        count = max(1, int(round(total / block_length))) if block_length > 0 else 1
        if not crossover.get("roads"):
            count = 1                      # pointwork, not a line

        km_a, km_b = self.nodes[start].km, self.nodes[end].km
        for index in range(count):
            first, last = index == 0, index == count - 1
            a, b = index / float(count), (index + 1) / float(count)
            seg_id = conn_id if count == 1 else "%s_%d" % (conn_id, index + 1)
            node_a = start if first else self._connection_node(
                conn_id, index, km_a + (km_b - km_a) * a,
                from_y + (to_y - from_y) * a)
            node_b = end if last else self._connection_node(
                conn_id, index + 1, km_a + (km_b - km_a) * b,
                from_y + (to_y - from_y) * b)
            segment = Segment(
                id=seg_id,
                start_node=node_a,
                end_node=node_b,
                length_m=total / count,
                max_speed_ms=crossover["max_speed_ms"],
                track=track_id,
                km_start=self.nodes[node_a].km,
                km_end=self.nodes[node_b].km,
                y=from_y + (to_y - from_y) * a,
                y_end=from_y + (to_y - from_y) * b,
                # A crossover lies between two parallel lines at the same
                # place, so it is on whatever gradient the line it leaves is on.
                grade_permille=grade,
            )
            self.segments.append(segment)
            # Registered as a ramp so that a connection reaching across an
            # intervening line picks up that line as a level crossing, exactly
            # as a junction link does.
            self.ramps.append((seg_id, {}))
            self.blocks[seg_id] = BlockSection(
                id=seg_id,
                segment_ids=(seg_id,),
                track=track_id,
                entry_node=node_a,
                exit_node=node_b,
                length_m=segment.length_m,
                km_start=segment.km_start,
                km_end=segment.km_end,
            )
            self.block_of_segment[seg_id] = seg_id

    def _connection_node(self, conn_id: str, index: int, km: float,
                         y: float) -> str:
        """A block boundary inside a connection, which belongs to it alone."""
        node_id = "%s@%d" % (conn_id, index)
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(id=node_id, km=km, y=y, kind="block")
        return node_id

    def _check_road_crossover_runs_forward(self, crossover, start, end) -> None:
        """Refuse a connection that would run against the way its line is signalled.

        The commonest way to write one by accident is to join two roads at the
        same station: the road it leaves ends at the far throat and the road it
        joins begins at the near one, so the connection runs backwards down the
        railway. Those two roads already meet - the points at each throat are
        exactly that - and there is nothing for a connection to add.
        """
        from_track = self._road_track(crossover["from"])
        to_track = self._road_track(crossover["to"])
        from_dir = self.tracks_spec[from_track].get("direction", "up")
        to_dir = self.tracks_spec[to_track].get("direction", "up")
        if from_dir != to_dir:
            raise InfrastructureError(
                "crossover %r joins %s on %s (%s) to %s on %s (%s), which run in "
                "opposite directions. A train taking it would be running against "
                "the way %s is signalled - working a line in both directions, which needs "
                "bidirectional signalling and is not modelled."
                % (crossover["id"], crossover["from"], from_track, from_dir,
                   crossover["to"], to_track, to_dir, to_track))

        sign = -1.0 if from_dir == "down" else 1.0
        ahead = (self.nodes[end].km - self.nodes[start].km) * sign
        if ahead <= 0:
            raise InfrastructureError(
                "crossover %r runs backwards: %s ends at km %.3f and %s begins "
                "at km %.3f, which is behind it. Two roads at one station "
                "already meet at their throats - the points join them - so a "
                "connection between them has nothing to connect. A connection "
                "goes from a road at one place to a road further along the line."
                % (crossover["id"], crossover["from"], self.nodes[start].km,
                   crossover["to"], self.nodes[end].km))

    def _road_track(self, road_id: str) -> str:
        return str(self.platforms_spec[road_id]["track"])

    def _road_y(self, road_id: str) -> float:
        """Where a road sits, so a connection can be drawn leaving it."""
        segment = next((s for s in self.segments if s.id == road_id), None)
        if segment is not None:
            return segment.y
        return float(self.tracks_spec[self._road_track(road_id)].get("y", 0.0))

    # -------------------------------------------------------------- crossings

    def _derive_crossings(self, network: Network) -> Dict[str, Tuple[str, ...]]:
        """Which junction links have to get past a running line to reach theirs.

        A branch on the far side of a double-track main cannot join the up line
        without crossing the down one, and where that crossing is on the level it
        is a **diamond**: no train changes lines there, but two trains cannot be
        on it at once. That is the whole cost of a flat junction, and it is what
        grade separation - a flyover or a dive-under - is built to remove.

        It is derived from the drawing rather than declared, because on a
        schematic it is already drawn: a link ramping from one alignment to
        another crosses exactly those tracks whose alignment lies between them.
        A link marked ``grade_separated`` is skipped, which is the whole of the
        difference between the two scenarios that use this.
        """
        crossings: Dict[str, set] = {}
        for segment_id, spec in self.ramps:
            if spec.get("grade_separated"):
                continue
            segment = network.segments[segment_id]
            low, high = sorted((segment.y, segment.end_y))
            for other_id, other in self.tracks_spec.items():
                if other_id == segment.track or other_id in self.mirror_of:
                    continue
                other_y = float(other.get("y", 0.0))
                if not (low + 1e-6 < other_y < high - 1e-6):
                    continue
                fraction = (other_y - segment.y) / (segment.end_y - segment.y)
                km = segment.km_start + (segment.km_end - segment.km_start) * fraction
                crossed = self._block_on_track_at(network, other_id, km)
                if crossed is None:
                    raise InfrastructureError(
                        "junction link %s crosses track %r at km %.3f, but there "
                        "is no block there to conflict with"
                        % (segment_id, other_id, km)
                    )
                crossings.setdefault(segment_id, set()).add(crossed)
                crossings.setdefault(crossed, set()).add(segment_id)
        for block_id, others in self.mirror_conflicts.items():
            crossings.setdefault(block_id, set()).update(others)
        for block_id, others in self._emit_diamonds(network).items():
            crossings.setdefault(block_id, set()).update(others)
        return {block: tuple(sorted(others))
                for block, others in crossings.items()}

    def _block_on_track_at(self, network: Network, track_id: str,
                           km: float) -> Optional[str]:
        """The running block on ``track_id`` covering schematic ``km``."""
        for block in self.blocks.values():
            if block.track != track_id:
                continue
            low, high = sorted((block.km_start, block.km_end))
            if low - 1e-9 <= km <= high + 1e-9:
                return block.id
        return None

    # ------------------------------------------------------- signals and routes

    def _build_signals(self, network: Network, points: Dict[str, Point]) -> None:
        """One entry signal per road a train could approach the block by."""
        for block_id, block in list(self.blocks.items()):
            approaches = network.approaches(block.first_segment)
            legs: List[Optional[str]] = list(approaches) if len(approaches) > 1 else [
                approaches[0] if approaches else None
            ]
            signal_ids = []
            for leg in legs:
                if leg is None or len(legs) == 1:
                    signal_id = "S_%s" % (block_id,)
                    leg_for_signal = leg
                else:
                    signal_id = "S_%s_from_%s" % (block_id, leg)
                    leg_for_signal = leg
                # Draw the signal on the road it distinguishes. Where several
                # roads converge on one block, that is the approach it applies
                # to. Where only one approaches - four platform roads off a
                # single throat - the signals differ by the road they read INTO,
                # so each goes on its own; taking the approach's alignment there
                # would draw all four on top of each other.
                y = (network.segments[leg].y if leg is not None and len(legs) > 1
                     else network.segments[block.first_segment].y)
                self.signals[signal_id] = Signal(
                    id=signal_id,
                    block_id=block_id,
                    node_id=block.entry_node,
                    km=block.km_start,
                    y=y,
                    track=block.track,
                    from_segment=leg_for_signal,
                )
                signal_ids.append(signal_id)
            self.blocks[block_id] = replace(block, signal_ids=tuple(signal_ids))

    def _mark_controlled_signals(self, routes: Dict[str, Route]) -> None:
        """A signal reading over points may only clear on a set route."""
        for route in routes.values():
            if not route.controlled:
                continue
            signal = self.signals[route.entry_signal]
            self.signals[signal.id] = replace(signal, controlled=True)

    # ------------------------------------------------------------------- tracks

    def _build_track(self, track_id: str) -> None:
        track = self.tracks_spec[track_id]
        direction = track.get("direction", "up")
        if direction not in ("up", "down"):
            raise InfrastructureError(
                "track %r has direction %r, expected 'up' or 'down'"
                % (track_id, direction)
            )
        serves = list(track.get("serves") or [])
        if len(serves) < 2:
            raise InfrastructureError(
                "track %r must serve at least two stations" % (track_id,)
            )
        for station_id in serves:
            if station_id not in self.stations_spec:
                raise InfrastructureError(
                    "track %r serves unknown station %r" % (track_id, station_id)
                )

        sign = 1.0 if direction == "up" else -1.0
        start_km = float(self.stations_spec[serves[0]]["km"])
        track_y = float(track.get("y", 0.0))
        line_speed = kmh_to_ms(float(track.get("max_speed_kmh",
                                               self.defaults["max_speed_kmh"])))
        block_length = float(track.get("block_length_m",
                                       self.defaults["block_length_m"]))
        track_grade = float(track.get("grade_permille",
                                      self.defaults["grade_permille"]))
        zone_length = float(track.get("platform_zone_m",
                                      self.defaults["platform_zone_m"]))

        def chainage_of(km: float) -> float:
            return (km - start_km) * sign * 1000.0

        # A branch does not lay out its own platforms at the junction station -
        # it uses the ones on the line it joins - so its own layout stops short
        # and a junction link bridges the rest. The branch also measures itself
        # to the *attachment node* rather than to the station's centre, so that
        # the link is drawn the length it actually is.
        junction = self._junction_spec(track_id, track, serves, track_grade)
        if junction is not None:
            start_km = (junction["node_km"] if not junction["joining"]
                        else float(self.stations_spec[serves[0]]["km"]))
            far_km = (junction["node_km"] if junction["joining"]
                      else float(self.stations_spec[serves[-1]]["km"]))
        else:
            far_km = float(self.stations_spec[serves[-1]]["km"])

        total = chainage_of(far_km)
        if total <= 0:
            raise InfrastructureError(
                "track %r: stations in %r are not ordered in the direction of travel"
                % (track_id, serves)
            )

        layout_serves = list(serves)
        layout_from, layout_to = 0.0, total
        if junction is not None:
            link_length = junction["length_m"]
            if junction["joining"]:
                layout_serves = serves[:-1]
                layout_to = total - link_length
            else:
                layout_serves = serves[1:]
                layout_from = link_length
            if layout_to - layout_from <= 0.0:
                raise InfrastructureError(
                    "track %r: the junction link is longer than the branch"
                    % (track_id,)
                )

        zones = self._platform_zones(
            track_id, layout_serves, chainage_of, zone_length,
            layout_from, layout_to,
            open_start=junction is not None and not junction["joining"],
            open_end=junction is not None and junction["joining"],
        )

        overrides = self._stretch_overrides(track_id, track)
        gradients = self._gradient_overrides(track_id, track)
        self.track_layout[track_id] = {
            "sign": sign, "start_km": start_km, "y": track_y,
            "zones": {station: (start, end) for station, start, end in zones},
        }

        if junction is not None and not junction["joining"]:
            self._emit_junction_link(track_id, track, track_y, sign, start_km,
                                     junction, 0.0, layout_from, track_grade)

        counter = 0
        cursor = layout_from
        previous_station = None
        for station_id, zone_start, zone_end in zones:
            if zone_start > cursor + 1e-6:
                stretch = (previous_station, station_id)
                counter = self._emit_open_line(
                    track_id, track_y, sign, start_km, cursor, zone_start,
                    overrides.get(stretch, block_length), line_speed, counter,
                    gradients.get(stretch, track_grade),
                )
            # Stations are taken to stand on the track's own gradient: a
            # platform is levelled where it can be, and a stretch gradient
            # describes the run between two stations rather than the stop at
            # either end of it.
            self._emit_platform_zone(
                track_id, track_y, sign, start_km, station_id,
                zone_start, zone_end, line_speed, track_grade,
            )
            cursor = zone_end
            previous_station = station_id
        if cursor < layout_to - 1e-6:
            self._emit_open_line(
                track_id, track_y, sign, start_km, cursor, layout_to,
                block_length, line_speed, counter, track_grade,
            )

        if junction is not None and junction["joining"]:
            self._emit_junction_link(track_id, track, track_y, sign, start_km,
                                     junction, layout_to, total, track_grade)

    def _stretch_overrides(self, track_id, track) -> Dict[Tuple[str, str], float]:
        """Per-stretch block lengths, keyed by the stations either side.

        Real block lengths are not uniform. The safety floor is the braking
        distance from line speed, but below that ceiling the choice is a capacity
        decision: shorter blocks mean a shorter headway and more trains per hour,
        paid for with more signals. So stretches where capacity matters get
        shorter blocks than fast open line. ``block_lengths`` in the track spec
        expresses that; anything not listed uses the track default.
        """
        overrides: Dict[Tuple[str, str], float] = {}
        for entry in track.get("block_lengths") or []:
            if not isinstance(entry, dict):
                raise InfrastructureError(
                    "track %r: each block_lengths entry must be a mapping"
                    % (track_id,)
                )
            try:
                key = (str(entry["from"]), str(entry["to"]))
                overrides[key] = float(entry["block_length_m"])
            except KeyError as exc:
                raise InfrastructureError(
                    "track %r: block_lengths entry missing %s" % (track_id, exc)
                )
            if overrides[key] <= 0:
                raise InfrastructureError(
                    "track %r: block_length_m must be positive" % (track_id,)
                )
        return overrides

    def _gradient_overrides(self, track_id, track
                            ) -> Dict[Tuple[str, str], float]:
        """Per-stretch gradients, keyed by the stations either side.

        A gradient profile is how a railway is actually described - "1 in 100
        against up trains from Alpha to Beta" - so that is how it is written
        here, as rise per thousand *in the direction the entry is written in*:

            gradients:
              - {from: ALPHA, to: BETA, grade_permille: 10}   # a climb

        The same bank appears on the down line as a fall, and a scenario may say
        so either by writing the pair the other way round on that track or by
        writing the same pair with the sign flipped. Both are accepted: an entry
        found in reverse is negated, because a bank that climbs one way falls the
        other and there is no third possibility.
        """
        overrides: Dict[Tuple[str, str], float] = {}
        for entry in track.get("gradients") or []:
            if not isinstance(entry, dict):
                raise InfrastructureError(
                    "track %r: each gradients entry must be a mapping"
                    % (track_id,)
                )
            try:
                start, end = str(entry["from"]), str(entry["to"])
                grade = float(entry["grade_permille"])
            except KeyError as exc:
                raise InfrastructureError(
                    "track %r: gradients entry missing %s" % (track_id, exc)
                )
            for station_id in (start, end):
                if station_id not in self.stations_spec:
                    raise InfrastructureError(
                        "track %r: gradients entry names unknown station %r"
                        % (track_id, station_id)
                    )
            if abs(grade) > 100.0:
                raise InfrastructureError(
                    "track %r: gradient %g per thousand between %s and %s is "
                    "steeper than 1 in 10 - check the units, which are rise per "
                    "thousand and not a percentage"
                    % (track_id, grade, start, end)
                )
            overrides[(start, end)] = grade
            overrides.setdefault((end, start), -grade)
        return overrides

    def _junction_spec(self, track_id, track, serves,
                       track_grade: float = 0.0) -> Optional[dict]:
        """Parse ``junction:`` - how this branch attaches to the line it works to.

        A branch is not a separate railway: it joins a running line at a set of
        points, and from there its trains are main-line trains competing for the
        same road. The scenario file says only where it attaches; whether that is
        a *joining* move (the branch runs into the junction, a trailing point) or
        a *leaving* one (the branch diverges from it, a facing point) follows
        from whether the junction station is the branch's last or first call.
        """
        spec = track.get("junction")
        if spec is None:
            return None
        if not isinstance(spec, dict):
            raise InfrastructureError(
                "track %r: junction must be a mapping with 'track' and 'at'"
                % (track_id,))
        try:
            other_id, at = str(spec["track"]), str(spec["at"])
        except KeyError as exc:
            raise InfrastructureError("track %r: junction missing %s"
                                      % (track_id, exc))
        if other_id not in self.tracks_spec:
            raise InfrastructureError(
                "track %r: junction onto unknown track %r" % (track_id, other_id))
        if self.tracks_spec[other_id].get("junction"):
            raise InfrastructureError(
                "track %r: cannot join %r, which is itself a branch - a branch "
                "off a branch would need the main line laid out first"
                % (track_id, other_id))
        if at not in (serves[0], serves[-1]):
            raise InfrastructureError(
                "track %r: junction at %r must be this track's first or last "
                "station (it serves %s)" % (track_id, at, ", ".join(serves)))

        layout = self.track_layout.get(other_id)
        if layout is None or at not in layout["zones"]:
            raise InfrastructureError(
                "track %r: track %r does not serve %r, so there is nothing to "
                "join there" % (track_id, other_id, at))

        joining = at == serves[-1]
        zone_start, zone_end = layout["zones"][at]
        # Joining, the branch arrives at the near end of the main platform zone;
        # leaving, it diverges from the far end. Either way it is the node where
        # main-line trains and branch trains have to be sequenced.
        attach_chainage = zone_start if joining else zone_end
        return {
            "track": other_id,
            "at": at,
            "joining": joining,
            "length_m": float(spec.get("length_m", 400.0)),
            "max_speed_ms": kmh_to_ms(float(
                spec.get("max_speed_kmh", self.defaults["max_speed_kmh"]))),
            # A flyover or a dive-under: the link gets past whatever is in the
            # way without sharing any track with it, so nothing has to be held.
            "grade_separated": bool(spec.get("grade_separated", False)),
            "grade_permille": float(spec.get("grade_permille", track_grade)),
            "node": self._node_id(other_id, attach_chainage),
            "node_km": (layout["start_km"]
                        + layout["sign"] * attach_chainage / 1000.0),
            "node_y": layout["y"],
        }

    def _emit_junction_link(self, track_id, track, track_y, sign, start_km,
                            junction, from_ch, to_ch, grade_permille=0.0) -> None:
        """The connecting road between a branch and the line it works to.

        Its own block and its own signal, because it is the piece of railway two
        services compete for. Trailing into the junction, both the main-line
        train and the branch train are asking for the same block beyond, and only
        one of them can have it - which is the first place on this railway where
        the order trains are taken in is a decision rather than a consequence.
        """
        if junction["node"] not in self.nodes:
            raise InfrastructureError(
                "track %r: no node at %s on %s to attach to - the junction "
                "station's platform zone did not land where expected"
                % (track_id, junction["at"], junction["track"]))

        branch_node = self._node(track_id, from_ch if junction["joining"] else to_ch,
                                 sign, start_km, track_y, "plain")
        branch_km = start_km + sign * (
            from_ch if junction["joining"] else to_ch) / 1000.0

        if junction["joining"]:
            start_node, end_node = branch_node, junction["node"]
            km_start, km_end = branch_km, junction["node_km"]
            y, y_end = track_y, junction["node_y"]
        else:
            start_node, end_node = junction["node"], branch_node
            km_start, km_end = junction["node_km"], branch_km
            y, y_end = junction["node_y"], track_y

        seg_id = "%s_JN" % (track_id,)
        segment = Segment(
            id=seg_id,
            start_node=start_node,
            end_node=end_node,
            length_m=to_ch - from_ch,
            max_speed_ms=junction["max_speed_ms"],
            track=track_id,
            km_start=km_start,
            km_end=km_end,
            # The link ramps from one alignment to the other, so it carries a y
            # at each end. Drawing follows the ramp; deciding which road through
            # the points is the straight one looks at the far end of each leg,
            # which is what correctly makes the main line normal here.
            y=y,
            y_end=y_end,
            #: A flyover climbs whichever way it is written; a scenario that
            #: says so declares it on the junction itself, since it is not the
            #: gradient of either line it connects.
            grade_permille=junction["grade_permille"],
        )
        self.segments.append(segment)
        self.ramps.append((seg_id, junction))
        self.blocks[seg_id] = BlockSection(
            id=seg_id,
            segment_ids=(seg_id,),
            track=track_id,
            entry_node=start_node,
            exit_node=end_node,
            length_m=segment.length_m,
            km_start=km_start,
            km_end=km_end,
        )
        self.block_of_segment[seg_id] = seg_id

    def _node_id(self, track_id: str, chainage: float) -> str:
        return "%s@%d" % (track_id, int(round(chainage)))

    def _platform_zones(self, track_id, serves, chainage_of, zone_length,
                        layout_from, layout_to, open_start=False, open_end=False
                        ) -> List[Tuple[str, float, float]]:
        """Chainage range reserved for each station's platforms on this track.

        A terminus gets a zone on one side only - the line stops there - while an
        intermediate station gets one centred on it. ``open_start``/``open_end``
        say that the line carries on past this end even though no further station
        is listed, which is the case for a branch running into a junction.
        """
        zones: List[Tuple[str, float, float]] = []
        last = len(serves) - 1
        for index, station_id in enumerate(serves):
            centre = chainage_of(float(self.stations_spec[station_id]["km"]))
            begins_here = index == 0 and not open_start
            ends_here = index == last and not open_end
            if begins_here and not ends_here:
                start, end = centre, centre + zone_length
            elif ends_here and not begins_here:
                start, end = centre - zone_length, centre
            else:
                start, end = centre - zone_length / 2.0, centre + zone_length / 2.0
            if start < layout_from - 1e-6 or end > layout_to + 1e-6:
                raise InfrastructureError(
                    "track %r: platform zone for %s falls outside the line"
                    % (track_id, station_id)
                )
            if zones and start < zones[-1][2] - 1e-6:
                raise InfrastructureError(
                    "track %r: platform zones for %s and %s overlap - stations are "
                    "closer together than platform_zone_m"
                    % (track_id, zones[-1][0], station_id)
                )
            zones.append((station_id, start, end))
        return zones

    # ----------------------------------------------------------------- emitters

    def _emit_open_line(self, track_id, track_y, sign, start_km, from_ch, to_ch,
                        block_length, line_speed, counter,
                        grade_permille=0.0) -> int:
        """Divide a stretch of open line into blocks, each with a signal.

        Split first at any chainage that *must* be a block boundary - where a
        crossover meets this line - and only then divide each piece into equal
        blocks. A connection has to start and finish somewhere a signal can
        stand, so the block plan accommodates the layout rather than the other
        way round, which is also how it is done on the ground.
        """
        cuts = sorted(c for c in self.required_chainages.get(track_id, ())
                      if from_ch + 1e-6 < c < to_ch - 1e-6)
        if cuts:
            bounds = [from_ch] + cuts + [to_ch]
            for piece_start, piece_end in zip(bounds, bounds[1:]):
                counter = self._emit_open_line(
                    track_id, track_y, sign, start_km, piece_start, piece_end,
                    block_length, line_speed, counter, grade_permille,
                )
            return counter

        length = to_ch - from_ch
        count = max(1, int(round(length / block_length)))
        step = length / count
        for index in range(count):
            block_start = from_ch + index * step
            block_end = block_start + step
            counter += 1
            seg_id = "%s_%03d" % (track_id, counter)
            self._emit_block(
                track_id=track_id,
                seg_id=seg_id,
                block_id=seg_id,
                start_ch=block_start,
                end_ch=block_end,
                sign=sign,
                start_km=start_km,
                y=track_y,
                max_speed_ms=line_speed,
                platform=None,
                station=None,
                grade_permille=grade_permille,
            )
        return counter

    def _emit_platform_zone(self, track_id, track_y, sign, start_km, station_id,
                            zone_start, zone_end, line_speed,
                            grade_permille=0.0) -> None:
        """Emit one block per platform road at a station, in parallel."""
        roads = [
            (pid, p) for pid, p in self.platforms_spec.items()
            if p.get("station") == station_id and p.get("track") == track_id
        ]
        if not roads:
            raise InfrastructureError(
                "station %r has no platform on track %r, but the track serves it"
                % (station_id, track_id)
            )

        step = float(self.defaults["platform_y_step"])
        stop_margin = float(self.defaults["stop_margin_m"])
        zone_length = zone_end - zone_start

        for index, (platform_id, plat) in enumerate(roads):
            offset = plat.get("y_offset")
            y = track_y + (float(offset) if offset is not None else index * step)
            speed = plat.get("max_speed_kmh")
            max_speed = kmh_to_ms(float(speed)) if speed is not None else line_speed

            self._emit_block(
                track_id=track_id,
                seg_id=platform_id,
                block_id=platform_id,
                start_ch=zone_start,
                end_ch=zone_end,
                sign=sign,
                start_km=start_km,
                y=y,
                max_speed_ms=max_speed,
                platform=platform_id,
                station=station_id,
                grade_permille=float(plat.get("grade_permille", grade_permille)),
            )
            # Where a train berths. The platform is centred in its road, and a
            # train draws up at the far end of the concrete - not at the end of
            # the block. That is the whole point of length_m: without it a 160 m
            # train runs 1170 m into a 1200 m road and stands half a kilometre
            # past the platform it is meant to be at. The road stays long
            # because it is sized for braking through at line speed; only the
            # stopping point belongs to the platform.
            platform_length = float(plat.get("length_m", 200.0))
            berth = str(plat.get("berth", "far"))
            if berth not in ("far", "centre", "near"):
                raise InfrastructureError(
                    "platform %r: berth %r is not one of far (front at the far "
                    "end of the concrete), centre or near"
                    % (platform_id, berth))
            # The concrete is centred in the road, which is what makes a road
            # worked in both directions work at all: mirrored, a centred
            # platform lands on itself, so the twin needs no adjustment.
            near = max(0.0, (zone_length - min(platform_length, zone_length))
                       / 2.0)
            self.platforms.append(Platform(
                id=platform_id,
                station=station_id,
                segment=platform_id,
                track=track_id,
                length_m=platform_length,
                near_offset_m=near,
                stop_margin_m=stop_margin,
                berth=berth,
            ))
            self.station_platforms.setdefault(station_id, []).append(platform_id)

    def _emit_block(self, track_id, seg_id, block_id, start_ch, end_ch, sign,
                    start_km, y, max_speed_ms, platform, station,
                    grade_permille=0.0) -> None:
        start_node = self._node(track_id, start_ch, sign, start_km, y,
                                "station" if station else "plain")
        end_node = self._node(track_id, end_ch, sign, start_km, y,
                              "station" if station else "plain")
        km_start = start_km + sign * start_ch / 1000.0
        km_end = start_km + sign * end_ch / 1000.0

        segment = Segment(
            id=seg_id,
            start_node=start_node,
            end_node=end_node,
            length_m=end_ch - start_ch,
            max_speed_ms=max_speed_ms,
            track=track_id,
            km_start=km_start,
            km_end=km_end,
            y=y,
            platform=platform,
            station=station,
            grade_permille=grade_permille,
        )
        self.segments.append(segment)

        # Signals are created in a later pass: how many a block needs depends on
        # how many roads converge on its entry node, which is not known until
        # every track has been laid out.
        self.blocks[block_id] = BlockSection(
            id=block_id,
            segment_ids=(seg_id,),
            track=track_id,
            entry_node=start_node,
            exit_node=end_node,
            length_m=segment.length_m,
            km_start=km_start,
            km_end=km_end,
            platform=platform,
            station=station,
        )
        self.block_of_segment[seg_id] = block_id

    def _node(self, track_id, chainage, sign, start_km, y, kind) -> str:
        node_id = "%s@%d" % (track_id, int(round(chainage)))
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(
                id=node_id,
                km=start_km + sign * chainage / 1000.0,
                y=y,
                kind=kind,
            )
        return node_id

    def _link_successors(self) -> None:
        """Fill in each block's successor blocks, for aspect computation."""
        by_entry_node: Dict[str, List[str]] = {}
        for block in self.blocks.values():
            by_entry_node.setdefault(block.entry_node, []).append(block.id)
        for block_id, block in list(self.blocks.items()):
            successors = tuple(sorted(by_entry_node.get(block.exit_node, ())))
            self.blocks[block_id] = BlockSection(
                id=block.id,
                segment_ids=block.segment_ids,
                track=block.track,
                entry_node=block.entry_node,
                exit_node=block.exit_node,
                length_m=block.length_m,
                km_start=block.km_start,
                km_end=block.km_end,
                signal_ids=block.signal_ids,
                successors=successors,
                platform=block.platform,
                station=block.station,
            )


def _check(where: str, mapping, allowed) -> None:
    schema.check_keys(where, mapping, allowed, error=InfrastructureError)


def _crossover_name(entry: dict) -> str:
    """The name a connection gets when the scenario does not give it one.

    Named for what it joins, because that is the only thing about it anyone will
    want to look up in the route table or in an event log: ``X_ASHDOWN_1_KINGSFORD_2``
    is a connection, and it is obvious which one.
    """
    ends = (str(entry.get("from", "?")), str(entry.get("to", "?")))
    return "X_%s_%s" % ends


def _index(items, what: str, name_from=None) -> Dict[str, dict]:
    """Turn a list of ``{id: ..., ...}`` mappings into an ordered id -> spec dict.

    ``name_from`` makes the id optional: a connection between two roads has an
    obvious name, and writing it out by hand is a chance to write it wrong.
    """
    if items is None:
        return {}
    if not isinstance(items, list):
        raise InfrastructureError("%s must be a list" % (what,))
    indexed: Dict[str, dict] = {}
    for entry in items:
        if isinstance(entry, dict) and "id" not in entry and name_from is not None:
            entry = dict(entry, id=name_from(entry))
        if not isinstance(entry, dict) or "id" not in entry:
            raise InfrastructureError(
                "each entry in %s must be a mapping with an 'id'" % (what,)
            )
        entry_id = str(entry["id"])
        if entry_id in indexed:
            raise InfrastructureError("duplicate id %r in %s" % (entry_id, what))
        indexed[entry_id] = entry
    return indexed
