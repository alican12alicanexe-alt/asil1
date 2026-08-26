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
        self.crossovers_spec = _index(spec.get("crossovers"), "crossovers")
        for station_id, station in self.stations_spec.items():
            _check("station %r" % station_id, station, schema.STATION)
        for track_id, track in self.tracks_spec.items():
            _check("track %r" % track_id, track, schema.TRACK)
            for entry in track.get("block_lengths") or []:
                _check("track %r block_lengths entry" % track_id, entry,
                       schema.BLOCK_LENGTHS)
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
        plain = [t for t in self.tracks_spec if not self.tracks_spec[t].get("junction")]
        branches = [t for t in self.tracks_spec if self.tracks_spec[t].get("junction")]
        for track_id in plain + branches:
            self._build_track(track_id)

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
            network=network,
            blocks=self.blocks,
            signals=self.signals,
            block_of_segment=self.block_of_segment,
            tracks=tracks,
            points=points,
            routes=routes,
        )

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

        Both lines must run the same way. A connection between the up and the
        down line is a different thing entirely: the train would be running
        against the direction the down line is signalled for, which needs
        bidirectional working to be safe and is not modelled. Saying so plainly
        is better than building something that looks right and is not.
        """
        self.crossovers: List[dict] = []
        for crossover_id, spec in self.crossovers_spec.items():
            try:
                from_id, to_id = str(spec["from"]), str(spec["to"])
                km = float(spec["km"])
            except KeyError as exc:
                raise InfrastructureError(
                    "crossover %r: missing %s" % (crossover_id, exc))
            for track_id in (from_id, to_id):
                if track_id not in self.tracks_spec:
                    raise InfrastructureError(
                        "crossover %r: unknown track %r"
                        % (crossover_id, track_id))
            if from_id == to_id:
                raise InfrastructureError(
                    "crossover %r: from and to are the same track"
                    % (crossover_id,))

            from_dir = self.tracks_spec[from_id].get("direction", "up")
            to_dir = self.tracks_spec[to_id].get("direction", "up")
            if from_dir != to_dir:
                raise InfrastructureError(
                    "crossover %r connects %s (%s) to %s (%s), which run in "
                    "opposite directions. A train taking it would be running "
                    "against the way %s is signalled - that is wrong-line "
                    "working, and it needs bidirectional signalling, which is "
                    "not modelled. Crossovers here connect lines that run the "
                    "same way, such as a slow line to a fast line."
                    % (crossover_id, from_id, from_dir, to_id, to_dir, to_id))

            length = float(spec.get("length_m", 300.0))
            from_km, from_sign = self._track_origin(from_id)
            to_km, to_sign = self._track_origin(to_id)
            leave_ch = (km - from_km) * from_sign * 1000.0
            join_ch = (km - to_km) * to_sign * 1000.0 + length
            if leave_ch <= 0 or join_ch <= 0:
                raise InfrastructureError(
                    "crossover %r at km %.3f falls off the end of %s or %s"
                    % (crossover_id, km, from_id, to_id))

            self.required_chainages.setdefault(from_id, []).append(leave_ch)
            self.required_chainages.setdefault(to_id, []).append(join_ch)
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

    def _emit_crossovers(self) -> None:
        """One segment, one block and one signal per connection."""
        for crossover in self.crossovers:
            from_id, to_id = crossover["from"], crossover["to"]
            start = self._node_id(from_id, crossover["leave_ch"])
            end = self._node_id(to_id, crossover["join_ch"])
            for node_id, track_id in ((start, from_id), (end, to_id)):
                if node_id not in self.nodes:
                    raise InfrastructureError(
                        "crossover %r: no block boundary at km %.3f on %s - the "
                        "connection would have nowhere to start or finish"
                        % (crossover["id"], crossover["km"], track_id))

            from_y = float(self.tracks_spec[from_id].get("y", 0.0))
            to_y = float(self.tracks_spec[to_id].get("y", 0.0))
            seg_id = crossover["id"]
            segment = Segment(
                id=seg_id,
                start_node=start,
                end_node=end,
                length_m=crossover["length_m"],
                max_speed_ms=crossover["max_speed_ms"],
                track=from_id,
                km_start=self.nodes[start].km,
                km_end=self.nodes[end].km,
                y=from_y,
                y_end=to_y,
            )
            self.segments.append(segment)
            # Registered as a ramp so that a connection reaching across an
            # intervening line picks up that line as a level crossing, exactly
            # as a junction link does.
            self.ramps.append((seg_id, {}))
            self.blocks[seg_id] = BlockSection(
                id=seg_id,
                segment_ids=(seg_id,),
                track=from_id,
                entry_node=start,
                exit_node=end,
                length_m=segment.length_m,
                km_start=segment.km_start,
                km_end=segment.km_end,
            )
            self.block_of_segment[seg_id] = seg_id

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
                if other_id == segment.track:
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
        """One entry signal per road approaching each block."""
        for block_id, block in list(self.blocks.items()):
            approaches = network.incoming(block.entry_node)
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
                # Draw the signal on the road it applies to.
                y = (network.segments[leg].y if leg is not None
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
        zone_length = float(track.get("platform_zone_m",
                                      self.defaults["platform_zone_m"]))

        def chainage_of(km: float) -> float:
            return (km - start_km) * sign * 1000.0

        # A branch does not lay out its own platforms at the junction station -
        # it uses the ones on the line it joins - so its own layout stops short
        # and a junction link bridges the rest. The branch also measures itself
        # to the *attachment node* rather than to the station's centre, so that
        # the link is drawn the length it actually is.
        junction = self._junction_spec(track_id, track, serves)
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
        self.track_layout[track_id] = {
            "sign": sign, "start_km": start_km, "y": track_y,
            "zones": {station: (start, end) for station, start, end in zones},
        }

        if junction is not None and not junction["joining"]:
            self._emit_junction_link(track_id, track, track_y, sign, start_km,
                                     junction, 0.0, layout_from)

        counter = 0
        cursor = layout_from
        previous_station = None
        for station_id, zone_start, zone_end in zones:
            if zone_start > cursor + 1e-6:
                stretch_length = overrides.get(
                    (previous_station, station_id), block_length)
                counter = self._emit_open_line(
                    track_id, track_y, sign, start_km, cursor, zone_start,
                    stretch_length, line_speed, counter,
                )
            self._emit_platform_zone(
                track_id, track_y, sign, start_km, station_id,
                zone_start, zone_end, line_speed,
            )
            cursor = zone_end
            previous_station = station_id
        if cursor < layout_to - 1e-6:
            self._emit_open_line(
                track_id, track_y, sign, start_km, cursor, layout_to,
                block_length, line_speed, counter,
            )

        if junction is not None and junction["joining"]:
            self._emit_junction_link(track_id, track, track_y, sign, start_km,
                                     junction, layout_to, total)

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

    def _junction_spec(self, track_id, track, serves) -> Optional[dict]:
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
            "node": self._node_id(other_id, attach_chainage),
            "node_km": (layout["start_km"]
                        + layout["sign"] * attach_chainage / 1000.0),
            "node_y": layout["y"],
        }

    def _emit_junction_link(self, track_id, track, track_y, sign, start_km,
                            junction, from_ch, to_ch) -> None:
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
                        block_length, line_speed, counter) -> int:
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
                    block_length, line_speed, counter,
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
            )
        return counter

    def _emit_platform_zone(self, track_id, track_y, sign, start_km, station_id,
                            zone_start, zone_end, line_speed) -> None:
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
            )
            self.platforms.append(Platform(
                id=platform_id,
                station=station_id,
                segment=platform_id,
                track=track_id,
                length_m=float(plat.get("length_m", 200.0)),
                stop_offset_m=max(1.0, zone_length - stop_margin),
            ))
            self.station_platforms.setdefault(station_id, []).append(platform_id)

    def _emit_block(self, track_id, seg_id, block_id, start_ch, end_ch, sign,
                    start_km, y, max_speed_ms, platform, station) -> None:
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


def _index(items, what: str) -> Dict[str, dict]:
    """Turn a list of ``{id: ..., ...}`` mappings into an ordered id -> spec dict."""
    if items is None:
        return {}
    if not isinstance(items, list):
        raise InfrastructureError("%s must be a list" % (what,))
    indexed: Dict[str, dict] = {}
    for entry in items:
        if not isinstance(entry, dict) or "id" not in entry:
            raise InfrastructureError(
                "each entry in %s must be a mapping with an 'id'" % (what,)
            )
        entry_id = str(entry["id"])
        if entry_id in indexed:
            raise InfrastructureError("duplicate id %r in %s" % (entry_id, what))
        indexed[entry_id] = entry
    return indexed
