"""The interlocking: the safety device between control and signals.

Everything that wants a train to move asks the same question - *may this movement
be made?* - and the interlocking answers it. It is the only component allowed to
say yes, and it says yes only when every condition holds:

1. the requested route exists in the route table
2. no other route is currently holding its block
3. every point it needs is either free, or already lying the right way
4. its block is clear of trains
5. anything it crosses on the level is clear and unheld
6. its overlap, if overlaps are in use, is clear

Then and only then does it set and lock the points, lock the route, and let the
signal clear.

Release is **sectional**: each point is released the moment the train's rear has
passed over it, rather than waiting for the whole movement to finish. That is not
an optimisation, it is what makes the railway work - a train standing in a loop
platform releases the points behind it, so a following train can be routed past
on the through road. Hold the points until the loop clears and the overtake the
loop exists for becomes impossible.

**Level crossings of one line by another** - the diamond at a flat junction -
are held for the whole movement, because two trains cannot be on a crossing at
once. Nothing about the crossing is a point and no train is routed *over* it onto
the other line; it is simply a piece of railway two movements share. That is the
mechanism by which a flat junction takes capacity away from the line it crosses,
and it is why grade separation is worth building.

**Approach locking** refuses to give a route back once a train is close enough to
have started braking on the strength of it. A route can only be cancelled from
under an approaching train after a timed release.

This component is deliberately independent of the signalling system above it.
Conventional signals, ETCS L1, L2 and L3 all consume the same route state; what
differs between them is only how the resulting authority reaches the driver. That
is why the interlocking is not a method on ``SignallingSystem``.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .points import Point
from .routes import Route, conflicting_routes


@dataclass(frozen=True)
class RouteDecision:
    """The interlocking's answer to a request."""

    granted: bool
    route_id: str
    reason: str = ""

    def __bool__(self) -> bool:
        return self.granted


@dataclass
class RouteLock:
    """A route currently set, and how far the train has got through it."""

    route_id: str
    train_id: str
    set_at_s: float
    points_held: Set[str]
    entered: bool = False


class Interlocking(object):
    """Holds point positions and route locks, and polices requests against them."""

    def __init__(self, network, blocks, signals, points: Dict[str, Point],
                 routes: Dict[str, Route], use_overlaps: bool = False,
                 approach_locking_s: float = 120.0,
                 automatic_signals: bool = True,
                 direction_sections: Optional[Dict[str, Tuple[str, str]]] = None):
        self.network = network
        self.blocks = blocks
        self.signals = signals
        self.points = points
        self.routes = routes
        self.use_overlaps = use_overlaps
        self.approach_locking_s = approach_locking_s
        #: Whether plain-line signals work themselves off track occupancy.
        #:
        #: True is automatic block: a signal with no points under it has nothing
        #: for a signaller to set, so it follows occupancy and sits green on an
        #: empty railway. False is a fully route-set railway, where every signal
        #: is controlled and stands at danger until a route is set through it -
        #: so an empty line is a line of red signals, and the greens are a window
        #: that travels ahead of each train.
        self.automatic_signals = bool(automatic_signals)

        self.point_position: Dict[str, str] = {
            pid: point.normal for pid, point in points.items()
        }
        self.point_locked_by: Dict[str, Optional[str]] = {pid: None for pid in points}
        self.locks: Dict[str, RouteLock] = {}

        #: Block -> (section, direction) for stretches of railway that may be
        #: worked either way. Grouped here into section -> direction -> blocks,
        #: which is the form the one question about them is asked in.
        self.direction_sections = dict(direction_sections or {})
        self._section_blocks: Dict[str, Dict[str, List[str]]] = {}
        for block_id, (section, way) in self.direction_sections.items():
            self._section_blocks.setdefault(section, {}).setdefault(
                way, []).append(block_id)

        self._route_of_signal = {r.entry_signal: r.id for r in routes.values()}
        self._points_at_node: Dict[str, List[Point]] = {}
        for point in points.values():
            self._points_at_node.setdefault(point.node, []).append(point)

    # ------------------------------------------------------------------ queries

    def needs_a_route(self, signal) -> bool:
        """Whether this signal may only clear on a route set from it.

        The one place the question is asked. A signal reading over points always
        needs one - granting it takes a road away from somebody else. On a fully
        route-set railway every other signal needs one too, and there are no
        automatic signals at all.
        """
        if not self.automatic_signals:
            return True
        return bool(getattr(signal, "controlled", False))

    def route_for_signal(self, signal_id: str) -> Optional[str]:
        return self._route_of_signal.get(signal_id)

    def route_set_from(self, signal_id: str) -> Optional[str]:
        """The route currently locked from this signal, if any."""
        route_id = self._route_of_signal.get(signal_id)
        if route_id is not None and route_id in self.locks:
            return route_id
        return None

    def route_offered_from(self, signal_id: str) -> Optional[str]:
        """The route set from this signal that no train has taken yet.

        Not the same question as :meth:`route_set_from`, and the difference is
        sectional release. A route keeps its lock until the train has cleared
        the block, so a train standing in a platform still holds the route that
        put it there - but its POINTS go back as soon as the train's rear is
        past them. That is what frees the road behind a standing train, and it
        means two routes off one post can be locked at once, legitimately: the
        first train is in platform 1 and the second is being signalled into
        platform 2.

        For anything that has to say what a post is showing a driver, the first
        of those two is not an answer. The train it was set for has gone by, and
        the post has nothing left to say about it. This returns the one that is
        still an offer, and there is never more than one at a time: measured on
        capacity at 150 s headway, 32763 post-ticks had a route locked and not
        one of them had two routes on offer.
        """
        route_id = self.route_set_from(signal_id)
        if route_id is None:
            return None
        lock = self.locks.get(route_id)
        return None if lock is None or lock.entered else route_id

    def is_locked(self, route_id: str) -> bool:
        return route_id in self.locks

    def locked_routes(self) -> Tuple[str, ...]:
        return tuple(sorted(self.locks))

    def set_route_leg(self, node_id: str) -> Optional[str]:
        """Which road a facing point at ``node_id`` is currently set to."""
        for point in self._points_at_node.get(node_id, ()):
            if point.kind == "facing":
                return self.point_position[point.id]
        return None

    def point_state(self) -> Dict[str, Dict[str, object]]:
        """Point positions and locks, for the view and for reports."""
        return {
            pid: {
                "position": self.point_position[pid],
                "locked_by": self.point_locked_by[pid],
                "normal": point.normal,
                "reverse": self.point_position[pid] != point.normal,
            }
            for pid, point in self.points.items()
        }

    def route_blocks(self) -> Dict[str, str]:
        """Block id -> the train whose set route holds it, crossings included."""
        held: Dict[str, str] = {}
        for lock in self.locks.values():
            route = self.routes[lock.route_id]
            for block_id in (route.block_id,) + route.crossings:
                held[block_id] = lock.train_id
        return held

    # ------------------------------------------------------------------ requests

    def request(self, route_id: str, train_id: str, sim) -> RouteDecision:
        """Ask for a route. Grants it and locks the resources, or explains why not."""
        route = self.routes.get(route_id)
        if route is None:
            return RouteDecision(False, route_id, "no such route")

        existing = self.locks.get(route_id)
        if existing is not None:
            if existing.train_id == train_id:
                return RouteDecision(True, route_id, "already set")
            return RouteDecision(False, route_id,
                                 "already set for %s" % existing.train_id)

        # What the route must find clear. A crossing always: two trains meeting on
        # a flat junction is not a following move and no separation model makes
        # it one. The block the route reads into, only where the block is the
        # unit of separation.
        #
        # Under distance separation it is not, and insisting on it here is what
        # made moving block behave like fixed block with extra steps: the
        # follower's authority was never the rear of the train in front, it was
        # the signal behind the block that train happened to be standing in. The
        # granularity of the reservation became the granularity of the railway.
        # Letting the route be set into an occupied block hands the question back
        # to the signalling system, which is the only thing that knows how far
        # apart these two trains actually have to be.
        #
        # This is safe here because a track has a direction and the route table
        # offers no move against a road's direction, so anything in that block is
        # running the same way. On a bidirectional single line it would need an
        # opposing-move check first.
        exclusive = self._blocks_are_exclusive(sim)
        wanted = (route.block_id,) + route.crossings if exclusive else route.crossings
        for block_id in wanted:
            holder = self._block_held_by(block_id, ignoring=route_id)
            if holder is not None:
                crossed = " (crossing)" if block_id != route.block_id else ""
                return RouteDecision(
                    False, route_id,
                    "%s%s is held by a route set for %s"
                    % (block_id, crossed, holder),
                )
            if not sim.occupancy.is_free(block_id, ignoring=train_id):
                occupier = ", ".join(sorted(sim.occupancy.trains_in(block_id)))
                crossed = " (crossing)" if block_id != route.block_id else ""
                return RouteDecision(
                    False, route_id,
                    "%s%s occupied by %s" % (block_id, crossed, occupier))

        against = self._worked_the_other_way(route.block_id, train_id, sim)
        if against is not None:
            return RouteDecision(False, route_id, against)

        for point_id, leg in route.points.items():
            locked_by = self.point_locked_by.get(point_id)
            if locked_by is not None and self.point_position[point_id] != leg:
                holder = self.locks.get(locked_by)
                return RouteDecision(
                    False, route_id,
                    "%s locked to %s by %s, set for %s"
                    % (point_id, self.point_position[point_id], locked_by,
                       holder.train_id if holder else "?"),
                )

        # An overlap is the room a train needs beyond a signal it might overrun,
        # which is a fixed-block idea: where the authority ends at a computed
        # point rather than at a lamp, there is nothing to overrun.
        if self.use_overlaps and exclusive:
            for overlap in route.overlap_blocks:
                if not sim.occupancy.is_free(overlap, ignoring=train_id):
                    return RouteDecision(False, route_id,
                                         "overlap %s occupied" % (overlap,))

        # Everything holds: set and lock the points, then lock the route.
        moved = []
        for point_id, leg in route.points.items():
            if self.point_position[point_id] != leg:
                self.point_position[point_id] = leg
                moved.append("%s to %s" % (point_id, leg))
            self.point_locked_by[point_id] = route_id

        self.locks[route_id] = RouteLock(
            route_id=route_id,
            train_id=train_id,
            set_at_s=sim.time_s,
            points_held=set(route.points),
        )
        if moved:
            sim.log_event("points", train_id, "; ".join(moved))
        sim.log_event("route_set", train_id, route.describe())
        return RouteDecision(True, route_id, "set")

    def cancel(self, route_id: str, sim) -> RouteDecision:
        """Give a route back, unless a train is already approaching on it."""
        lock = self.locks.get(route_id)
        if lock is None:
            return RouteDecision(False, route_id, "not set")
        if lock.entered:
            return RouteDecision(False, route_id, "train is already in the route")
        if self._approach_locked(lock, sim):
            return RouteDecision(
                False, route_id,
                "approach locked - %s is braking on this signal"
                % (lock.train_id,),
            )
        self._release(route_id, sim, "cancelled")
        return RouteDecision(True, route_id, "cancelled")

    # ------------------------------------------------------------------- release

    def update(self, sim) -> None:
        """Sectional release: give back each resource as the train clears it."""
        for route_id in list(self.locks):
            lock = self.locks[route_id]
            route = self.routes[route_id]
            train = sim.trains.get(lock.train_id)

            if train is None or not train.is_active:
                self._release(route_id, sim, "train gone")
                continue

            if lock.train_id in sim.occupancy.trains_in(route.block_id):
                lock.entered = True

            # Points are released as soon as the train's rear is past them, which
            # is what frees the road behind a train standing in a platform.
            for point_id in list(lock.points_held):
                if self._rear_is_clear_of(train, self.points[point_id]):
                    lock.points_held.discard(point_id)
                    if self.point_locked_by.get(point_id) == route_id:
                        self.point_locked_by[point_id] = None
                        sim.log_event("points_released", train.id, point_id)

            # The route itself goes once the train has been through the block -
            # or, where the block is not what separates trains, as soon as the
            # train is on it and off its points. A route there is a permission to
            # pass, not a reservation of the road ahead: holding it until the
            # train had left the block would keep the follower a whole block back
            # for no safety reason, which is the fixed-block answer to a question
            # distance separation has already answered better.
            if not self._blocks_are_exclusive(sim):
                if lock.entered and not lock.points_held:
                    self._release(route_id, sim, "train is on the route")
            elif lock.entered and lock.train_id not in sim.occupancy.trains_in(route.block_id):
                self._release(route_id, sim, "train has cleared")

    def _release(self, route_id: str, sim, why: str) -> None:
        lock = self.locks.pop(route_id, None)
        if lock is None:
            return
        for point_id in lock.points_held:
            if self.point_locked_by.get(point_id) == route_id:
                self.point_locked_by[point_id] = None
        sim.log_event("route_released", lock.train_id, "%s (%s)" % (route_id, why))

    # ----------------------------------------------------------------- internals

    def _worked_the_other_way(self, block_id: str, train_id: str,
                              sim) -> Optional[str]:
        """Whether a stretch worked in both directions is busy the other way.

        Two blocks over the same rails already refuse each other one at a time -
        that is the crossing check above, and it is what makes working a line in both directions
        *safe*. It does not make it *work*: a train admitted at one end of the
        section and a train admitted at the other meet in the middle, each
        holding what the other needs, and neither can be backed out. Every
        railway that works a section in both directions solves this the same way,
        by giving the whole section to one direction at a time - a token, a staff,
        a pilotman riding in the cab.

        This is that rule. While anything is moving one way through a reversible
        section, nothing may be signalled into it the other way; when the section
        is clear, either direction may have it.
        """
        here = self.direction_sections.get(block_id)
        if here is None:
            return None
        section, way = here
        for other_way, blocks in self._section_blocks.get(section, {}).items():
            if other_way == way:
                continue
            for other in blocks:
                # Held *as its own block*, not as a crossing. Every route over
                # the right line names the reverse-direction block it lies under as a
                # crossing, so asking the general question here would have each
                # up train reading as a movement down the same rails and locking
                # the section against the train behind it.
                holder = self._block_set_for(other)
                if holder is not None and holder != train_id:
                    return ("%s is being worked the other way: %s is held by a "
                            "route set for %s" % (section, other, holder))
                occupants = sim.occupancy.trains_in(other) - {train_id}
                if occupants:
                    return ("%s is being worked the other way: %s holds %s"
                            % (section, other, ", ".join(sorted(occupants))))
        return None

    def block_is_committed(self, block_id: str, sim) -> bool:
        """Whether a block is held by a route set into it, or occupied.

        The two things that mean these rails are spoken for. Held *as its own
        block*, not as a crossing: every route over a stretch worked both ways
        names the block underneath it as a crossing, so the general question
        would have every train read as a movement the other way over the same
        rails.
        """
        if self._block_set_for(block_id) is not None:
            return True
        return bool(sim.occupancy.trains_in(block_id))

    def section_direction(self, section: str, sim) -> Optional[str]:
        """Which way a section worked in both directions is being worked now.

        ``"normal"``, ``"reverse"``, or ``None`` when the section is clear and
        either direction may have it. Both directions are legitimate: a stretch
        signalled both ways is signalled both ways, and which way it is set is a
        state of the railway, not a fault. It is the schematic's business
        because one lamp at each boundary can only be showing one of them.
        """
        for way, blocks in self._section_blocks.get(section, {}).items():
            for block_id in blocks:
                if self._block_set_for(block_id) is not None:
                    return way
                if sim.occupancy.trains_in(block_id):
                    return way
        return None

    @staticmethod
    def _blocks_are_exclusive(sim) -> bool:
        """Whether one train per block is what keeps trains apart on this run.

        Asked of the signalling system rather than stored, because the same
        interlocking is handed to every system in a comparison and the answer
        changes with it.
        """
        signalling = getattr(sim, "signalling", None)
        return getattr(signalling, "separates_by", "block") == "block"

    def _block_set_for(self, block_id: str) -> Optional[str]:
        """The train whose route runs *into* this block, ignoring crossings."""
        for lock in self.locks.values():
            if self.routes[lock.route_id].block_id == block_id:
                return lock.train_id
        return None

    def _block_held_by(self, block_id: str,
                       ignoring: Optional[str] = None) -> Optional[str]:
        """The train whose route holds this block, as its own or as a crossing."""
        for lock in self.locks.values():
            if lock.route_id == ignoring:
                continue
            route = self.routes[lock.route_id]
            if block_id == route.block_id or block_id in route.crossings:
                return lock.train_id
        return None

    @staticmethod
    def _rear_is_clear_of(train, point: Point) -> bool:
        """True once the whole train is past the node the point sits at."""
        node_chainage = None
        for entry in train.path.entries:
            if entry.segment.start_node == point.node:
                node_chainage = entry.start_m
                break
        if node_chainage is None:
            return True  # the point is not on this train's route at all
        return train.rear_m > node_chainage

    def _approach_locked(self, lock: RouteLock, sim) -> bool:
        train = sim.trains.get(lock.train_id)
        if train is None or train.state != "running":
            return False
        route = self.routes[lock.route_id]
        signal = self.signals[route.entry_signal]
        upcoming = train.path.next_signal(train.chainage_m)
        if upcoming is None or upcoming[0] != signal.id:
            return False
        # Within the distance the train would cover before it could be told.
        return (upcoming[1] - train.chainage_m) <= train.speed_ms * self.approach_locking_s

    # ------------------------------------------------------------------- reports

    def describe(self) -> str:
        controlled = sum(1 for r in self.routes.values() if r.controlled)
        crossings = sum(1 for r in self.routes.values() if r.crossings)
        if self.automatic_signals:
            worked = "%d controlled" % (controlled,)
        else:
            worked = "all controlled, no automatic signals"
        described = (
            "%d routes (%s), %d points, overlaps %s"
            % (len(self.routes), worked, len(self.points),
               "on" if self.use_overlaps else "off")
        )
        if crossings:
            described += ", %d routes cross another line on the level" % (crossings,)
        return described

    def conflicts_for(self, route_id: str) -> Tuple[str, ...]:
        route = self.routes.get(route_id)
        if route is None:
            return ()
        return conflicting_routes(route, self.routes)
