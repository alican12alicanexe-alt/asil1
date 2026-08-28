"""Train lifecycle and operational decisions.

The dispatcher owns everything a signaller or control centre would decide:
when a service is put into its platform, when it is allowed to leave, and when it
terminates. It does *not* touch physics or signalling.

Milestone 1 implements the simplest possible policy - run the timetable as
written, hold a departure only if the platform is still occupied. The interface is
what matters: a traffic management system doing conflict detection and resolution,
or a learning agent, replaces :class:`TimetableDispatcher` without any other part
of the simulator changing.
"""

from typing import Dict, List

from .timetable import Service, Timetable
from .units import format_clock


class Dispatcher(object):
    """Base class for train despatch and control policies."""

    name = "abstract"

    def step(self, sim) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class TimetableDispatcher(Dispatcher):
    """Runs services to plan, with no conflict resolution.

    Arrival is detected by the train having come to a stand on its next stopping
    point. Departure is the later of the booked time and the minimum dwell, which
    is what makes a late train recover time by cutting dwell to the minimum rather
    than departing early.
    """

    name = "timetable"

    #: How close to the stopping point counts as berthed.
    STOP_TOLERANCE_M = 2.0
    #: Speed below which the train is considered stationary.
    STATIONARY_MS = 0.2

    def __init__(self, timetable: Timetable, route_request_distance_m: float = 2500.0,
                 route_request_lead_s: float = 60.0,
                 route_lookahead: int = 1):
        self.timetable = timetable
        self._pending: List[Service] = timetable.sorted_by_departure()
        #: How far out a running train asks for the route ahead.
        self.route_request_distance_m = route_request_distance_m
        #: How many signals ahead the signaller keeps routes set.
        #:
        #: One is enough where plain line works itself: the only routes to ask
        #: for are over points, and a train needs the one immediately in front of
        #: it. On a fully route-set railway it must be at least **two**, because
        #: a three-aspect signal shows green only when the signal beyond it is
        #: off, and that one is off only if a route has been set through it too.
        #: Set routes one signal ahead there and every driver runs on yellows.
        #:
        #: Two is also the most that costs nothing. A green already means the two
        #: blocks beyond are clear, so holding exactly those two takes nothing
        #: from a follower that a green had not already denied it. Three starts
        #: reserving a block the signalling never required, and the headway pays.
        self.route_lookahead = max(1, int(route_lookahead))
        #: How early a standing train asks for the route out of its platform.
        #:
        #: This is a real dispatching decision, not a detail. Ask too early and a
        #: train dwelling in a loop holds the points at the far end, blocking the
        #: very overtake the loop exists to allow. Ask too late and it sits at a
        #: red signal past its booked time.
        self.route_request_lead_s = route_request_lead_s
        self._last_refusal: Dict[str, str] = {}

    # ---------------------------------------------------------------- main step

    def step(self, sim) -> None:
        self._introduce(sim)
        self._manage_stops(sim)
        self._request_routes(sim)

    # ---------------------------------------------------------------- internals

    def _introduce(self, sim) -> None:
        """Place services into their origin platform once it is time and clear."""
        still_pending = []
        for service in self._pending:
            # A late start moves when the train appears, not when it was booked
            # away - so the delay is carried by the train and shows up against
            # the plan, exactly as an inward working running late would.
            late = sim.disruptions.late_start_s(service.id)
            if sim.time_s < service.departure_s + late - service.ready_lead_s:
                still_pending.append(service)
                continue

            origin_block = sim.block_of_segment.get(service.stops[0].segment)
            if origin_block is not None and not sim.occupancy.is_free(origin_block):
                # Platform still occupied: hold the service out and try again.
                still_pending.append(service)
                if sim.time_s >= service.departure_s:
                    sim.log_event(
                        "held_out", service.id,
                        "origin platform %s occupied" % service.stops[0].platform,
                    )
                continue

            train = service.create_train()
            train.entered_s = sim.time_s
            # The origin call is already made when the train is created, so a
            # disturbance there has to be applied here rather than in
            # _maybe_arrive: a late inward working is not away on time just
            # because it happened to be berthed before its booked minute.
            held = sim.disruptions.dwell_extra_s(service.id,
                                                 service.stops[0].station)
            if late or held:
                # A train is created standing in its origin platform with a
                # departure already set, so this is never None in practice - but
                # the attribute is optional for the rest of the journey, and
                # reaching across modules to rely on that is how a None gets into
                # arithmetic later. Take the booked time explicitly instead.
                booked_away = train.dwell_until_s
                if booked_away is None:
                    booked_away = service.departure_s
                away = max(booked_away, sim.time_s,
                           service.departure_s + late + held)
                train.dwell_until_s = away
                sim.log_event(
                    "disrupted", train.id,
                    "away %s instead of %s"
                    % (format_clock(away), format_clock(service.departure_s)),
                )
            sim.trains[train.id] = train
            sim.refresh_train_occupancy(train)
            sim.log_event(
                "introduced", train.id,
                "at %s platform %s, booked away %s"
                % (service.stops[0].station, service.stops[0].platform,
                   format_clock(service.departure_s)),
            )
        self._pending = still_pending

    def _request_routes(self, sim) -> None:
        """Ask the interlocking for the route ahead of each train.

        The seat a traffic management system will take: today it asks for
        whatever the train's own path needs, as soon as it is close enough. A TMS
        would instead decide *which* route, and in what order, having looked at
        every train on the railway.
        """
        interlocking = getattr(sim, "interlocking", None)
        if interlocking is None:
            return

        for train in sim.trains.values():
            if not train.is_active:
                continue
            if not self._ready_to_ask(sim, train):
                continue

            upcoming = train.path.next_signal(train.chainage_m)
            if upcoming is None:
                continue
            _, first_m, first_index = upcoming
            # The distance gate says whether this train is being worked yet, not
            # which of its signals get routes. Once it is close enough to the
            # first one, the signaller sets the next few in one go.
            if first_m - train.chainage_m > self.route_request_distance_m:
                continue

            # Never reach past a call the train has not made yet. The route out
            # of a platform is set once the train is standing in it - asking on
            # the approach would have a train claim the points at the far end of
            # a loop for the whole of its dwell, holding up everything behind it.
            to_stop = train.distance_to_next_stop()

            for offset in range(self.route_lookahead):
                ahead = train.path.signal_at_index(first_index + offset)
                if ahead is None:
                    break
                signal_id, signal_m = ahead
                if (train.state == "running" and to_stop is not None
                        and signal_m - train.chainage_m >= to_stop):
                    break  # the rest of the lookahead is beyond the next stop

                signal = sim.signals.get(signal_id)
                if signal is None or not interlocking.needs_a_route(signal):
                    continue  # automatic signal: there is no route to ask for
                if interlocking.route_set_from(signal_id) is not None:
                    continue

                route_id = interlocking.route_for_signal(signal_id)
                if route_id is None:
                    continue
                decision = interlocking.request(route_id, train.id, sim)
                self._note_decision(sim, train, decision)

    def _ready_to_ask(self, sim, train) -> bool:
        if train.state == "running":
            return True
        # Standing at a platform: ask only as departure approaches.
        if train.dwell_until_s is None:
            return False
        return train.dwell_until_s - sim.time_s <= self.route_request_lead_s

    def _note_decision(self, sim, train, decision) -> None:
        """Log a refusal once, not every tick, and note when it clears."""
        key = "%s/%s" % (train.id, decision.route_id)
        if decision.granted:
            if key in self._last_refusal:
                del self._last_refusal[key]
            return
        if self._last_refusal.get(key) != decision.reason:
            self._last_refusal[key] = decision.reason
            sim.log_event("route_refused", train.id,
                          "%s: %s" % (decision.route_id, decision.reason))

    def _manage_stops(self, sim) -> None:
        for train in list(sim.trains.values()):
            if train.state == "running":
                self._maybe_arrive(sim, train)
            elif train.state == "dwelling":
                self._maybe_depart(sim, train)

    def _maybe_arrive(self, sim, train) -> None:
        stop = train.next_stop()
        if stop is None:
            # No further calls: the service ends when it reaches the end of its path.
            if train.chainage_m >= train.path.total_m - self.STOP_TOLERANCE_M:
                self._terminate(sim, train, "end of path")
            return
        remaining = stop.stop_chainage_m - train.chainage_m
        if remaining > self.STOP_TOLERANCE_M or train.speed_ms > self.STATIONARY_MS:
            return

        train.speed_ms = 0.0
        train.chainage_m = stop.stop_chainage_m
        train.state = "dwelling"
        train.actual_arrivals[stop.station] = sim.time_s
        train.next_stop_index += 1

        if stop.arrival_s is not None:
            train.delay_s = sim.time_s - stop.arrival_s
        booked = format_clock(stop.arrival_s) if stop.arrival_s is not None else "-"
        sim.log_event(
            "arrived", train.id,
            "%s platform %s (booked %s)" % (stop.station, stop.platform, booked),
        )

        overrun = sim.disruptions.dwell_extra_s(train.id, stop.station)
        departure = sim.time_s + stop.min_dwell_s + overrun
        if stop.departure_s is not None:
            departure = max(departure, stop.departure_s + overrun)
        train.dwell_until_s = departure
        if overrun:
            sim.log_event("dwell_overrun", train.id,
                          "%s held %.0f s over, away %s"
                          % (stop.station, overrun, format_clock(departure)))

    def _maybe_depart(self, sim, train) -> None:
        if train.dwell_until_s is None or sim.time_s < train.dwell_until_s:
            return

        # The stop just served is the one before next_stop_index.
        served = train.stops[train.next_stop_index - 1] if train.next_stop_index else None
        if train.next_stop_index >= len(train.stops):
            where = served.station if served is not None else "destination"
            self._terminate(sim, train, "terminated at %s" % where)
            return

        train.state = "running"
        train.dwell_until_s = None
        if served is not None:
            train.actual_departures[served.station] = sim.time_s
            if served.departure_s is not None:
                train.delay_s = sim.time_s - served.departure_s
            sim.log_event("departed", train.id, "%s" % served.station)

    def _terminate(self, sim, train, why: str) -> None:
        train.state = "finished"
        train.finished_s = sim.time_s
        train.speed_ms = 0.0
        sim.occupancy.remove_train(train.id)
        sim.log_event("terminated", train.id, why)

    # ------------------------------------------------------------------ reports

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def describe(self) -> str:
        return "timetable (%d services)" % (len(self.timetable.services),)
