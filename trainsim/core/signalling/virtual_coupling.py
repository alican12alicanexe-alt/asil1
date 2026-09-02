"""Virtual coupling: relative braking distance over a train-to-train link.

The last rung, and the only one on this ladder that no railway runs. Moving
block already lets a train run up to the rear of the train in front less a
margin, and that is as close as absolute braking distance allows: the follower
must be able to stop short of where the leader is *now*, because the leader
might be a wall.

Virtual coupling drops that assumption. A continuous train-to-train radio link
tells the follower what the leader is doing, so the follower may plan to stop
where the leader will stop rather than where it currently stands. The distance
it borrows is the leader's own braking distance, which is why the benefit is
largest at speed and vanishes entirely against a stationary train - there is
nothing left to borrow from a train that has already stopped.

Two things pay for that, and both are modelled here. The link has latency, so
the follower keeps running for a moment after the leader starts braking; and
the whole justification disappears when the link does, which is why the
degraded margin is the one moving block would have used rather than the tight
coupled one.
"""

from ..units import braking_distance
from .base import SEPARATION_BY_DISTANCE, MovementAuthority, SignallingSystem
from .common import block_danger_point, limit_by_route, train_ahead


class VirtualCoupling(SignallingSystem):
    """Relative braking distance over a train-to-train link."""

    name = "virtual_coupling"
    has_lineside_signals = False
    # Trains are kept apart by measured distance, as under moving block. The
    # kernel's block-exclusivity check stays switched off; what still holds, and
    # what the tests lean on, is that no train's front passes another's rear.
    separates_by = SEPARATION_BY_DISTANCE
    # The danger point is another train that is still moving, which no other
    # system here may say. This one expresses that by placing the point where
    # the leader will have stopped rather than by issuing a non-zero target
    # speed, but it is the same licence either way: a system without this flag
    # handing back a moving danger point is a bug, and the kernel says so.
    permits_relative_braking = True

    #: What the follower may credit the leader's brake with. Not a tuning
    #: knob: the two answers rest on different safety cases, and which one is
    #: defensible is the open question in the concept.
    LEADER_BRAKE = ("emergency", "service")

    def __init__(self, safety_margin_m: float = 50.0,
                 fallback_margin_m: float = 100.0,
                 v2v_latency_s: float = 0.5,
                 assume_leader_brakes: bool = True,
                 leader_brake: str = "emergency"):
        super().__init__()
        if leader_brake not in self.LEADER_BRAKE:
            raise ValueError(
                "leader_brake must be one of %s, not %r"
                % (", ".join(self.LEADER_BRAKE), leader_brake))
        #: See :meth:`_run_on_m`. ``"emergency"`` is the conservative default.
        self.leader_brake = leader_brake
        #: Standing separation held even at rest. Smaller than moving block's,
        #: because it is no longer doing the work a braking distance did.
        self.safety_margin_m = float(safety_margin_m)
        #: Time for news of the leader's braking to reach the follower. Turns
        #: into distance at the follower's speed, so it costs more the faster
        #: the convoy runs - which is why the concept waits on FRMCS rather
        #: than GSM-R.
        self.v2v_latency_s = float(v2v_latency_s)
        #: Margin used once the link is gone and separation is back to absolute
        #: braking distance. Deliberately larger than ``safety_margin_m``, and
        #: defaulting to moving block's own figure.
        #:
        #: The tight coupled margin is only justified *by* the V2V link: it is
        #: small because the follower is being told, continuously, what the
        #: train in front is doing. When that stops being true the justification
        #: goes with it, and carrying the tight margin into the degraded mode
        #: would make an unfitted train appear to outperform moving block on
        #: identical physics - which is how this was found.
        self.fallback_margin_m = float(fallback_margin_m)
        #: Whether the leader may be assumed to be braking rather than to have
        #: stopped dead. False is moving block, and is here so that the entire
        #: benefit of virtual coupling can be switched off and measured.
        self.assume_leader_brakes = bool(assume_leader_brakes)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _linked(follower, leader) -> bool:
        """Whether these two may be separated by relative braking distance.

        Both ends need the V2V link, and the leader's rear position has to be
        trustworthy - an unmonitored train might have left part of itself
        behind, and the whole calculation is about where its rear is.
        """
        return bool(follower.stock.v2v and leader.stock.v2v and leader.stock.tims)

    def _run_on_m(self, leader) -> float:
        """How much further the leader's rear travels if it brakes now.

        The entire benefit of virtual coupling, in one line. Zero when the leader
        is standing, which is why a convoy closing on a stopped train behaves
        exactly like moving block - correctly, since there is nothing left to
        borrow.

        Which rate to credit the leader with is the open question in the whole
        concept, so it is a setting rather than a decision made here.

        ``leader_brake="emergency"``, the default, takes the *hardest* rate the
        leader can brake at rather than the rate it would normally use. The
        follower is planning to stop where the leader stops, so it assumes the
        leader stops as short as it possibly can: crediting a service
        application would put the danger point beyond where an emergency brake
        would actually leave the train, and the follower would run into it. The
        follower therefore absorbs the whole difference between the two rates,
        permanently, at every speed.

        ``leader_brake="service"`` takes that penalty away, and it is what the
        literature does. The V2V layer tells the leader the braking rate of
        everything coupled behind it and the convoy brakes at the weakest rate
        in it, so the leader may not stop shorter than the follower can. What
        that buys is large - it is the single biggest term in the separation -
        and what it costs is that the safety case now rests on the leader
        honouring a rule rather than on physics.

        This model does not enforce that rule, and cannot claim to: nothing in
        it ever demands more than a service application, so there is no
        behaviour here for the constraint to bind on. The setting is an
        assumption about the degraded case, declared and switchable, not a
        mechanism. Read a run made with it as "what virtual coupling is worth if
        the convoy braking rule holds", which is exactly the question the
        concept turns on.
        """
        if not self.assume_leader_brakes:
            return 0.0
        if self.leader_brake == "service":
            decel = leader.stock.service_brake
        else:
            decel = max(leader.stock.service_brake, leader.stock.emergency_brake)
        if decel <= 0.0:
            return 0.0
        return braking_distance(leader.speed_ms, decel)

    def _margin_m(self, follower) -> float:
        """Standing margin plus what the follower covers awaiting the news."""
        return self.safety_margin_m + follower.speed_ms * self.v2v_latency_s

    # -------------------------------------------------------- movement authority

    def movement_authority(self, train, sim) -> MovementAuthority:
        ahead = train_ahead(train, sim)

        if ahead is None:
            danger, reason = train.path.total_m, "clear ahead"
        else:
            rear_m, other_id = ahead
            leader = sim.trains.get(other_id)

            if leader is None or not self._linked(train, leader):
                # No link, or a leader whose rear cannot be trusted. Fall back to
                # absolute braking distance behind it, which is moving block. If
                # the leader cannot even report its position, fall back further,
                # to block granularity.
                why = self._unlinked_reason(train, leader, other_id)
                if leader is not None and leader.stock.tims:
                    danger = rear_m - self.fallback_margin_m
                    reason = "%s, absolute distance to %s" % (why, other_id)
                else:
                    danger, block_reason = block_danger_point(train, sim)
                    reason = "%s (%s)" % (why, block_reason)
            else:
                # Relative braking distance. The authority ends where the leader
                # will stop, not where its rear is now: the driver's ordinary
                # absolute-braking curve to that point is the relative-braking
                # curve to the leader.
                danger = rear_m + self._run_on_m(leader) - self._margin_m(train)
                reason = "coupled to %s" % other_id

        danger, reason = limit_by_route(danger, reason, train, sim)
        return MovementAuthority(
            end_distance_m=max(0.0, danger - train.chainage_m),
            target_speed_ms=0.0,
            reason="VC: %s" % reason,
        )

    @staticmethod
    def _unlinked_reason(follower, leader, other_id: str) -> str:
        if leader is None:
            return "%s unknown" % other_id
        if not follower.stock.v2v:
            return "not V2V fitted"
        if not leader.stock.v2v:
            return "%s not V2V fitted" % other_id
        return "%s has no integrity report" % other_id

    # ------------------------------------------------------------------ reporting

    def convoy_of(self, train, sim, coupling_distance_m: float = 400.0):
        """Trains running close enough ahead of ``train`` to count as coupled.

        Reporting only - nothing in the safety case depends on it. A convoy here
        is an emergent property of the separation rather than a declared state,
        which is a simplification: real virtual coupling has explicit coupling
        and decoupling manoeuvres with costs of their own.
        """
        members = []
        current = train
        seen = {train.id}
        while True:
            ahead = train_ahead(current, sim)
            if ahead is None:
                break
            rear_m, other_id = ahead
            if other_id in seen:
                break
            leader = sim.trains.get(other_id)
            if leader is None or not self._linked(current, leader):
                break
            if rear_m - current.chainage_m > coupling_distance_m:
                break
            members.append(other_id)
            seen.add(other_id)
            current = leader
        return members

    def describe(self) -> str:
        if not self.assume_leader_brakes:
            return ("virtual coupling with relative braking disabled "
                    "(equivalent to moving block, margin %.0f m)"
                    % (self.safety_margin_m,))
        return ("virtual coupling / relative braking distance "
                "(margin %.0f m, %.0f m degraded, V2V latency %.1f s, "
                "leader credited with its %s brake)"
                % (self.safety_margin_m, self.fallback_margin_m,
                   self.v2v_latency_s, self.leader_brake))
