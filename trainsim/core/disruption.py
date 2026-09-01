"""Perturbation: the things that go wrong, declared rather than random.

Everything measured so far has been a railway working to plan. That is the right
place to start - a capacity figure taken from a disturbed run means nothing
unless the undisturbed one is understood first - but it leaves out the question
operators actually spend their day on, which is what happens *after* something
slips.

Three kinds of disturbance are modelled, because between them they cover how
delay enters a railway:

``late_start``
    A service is put into its origin platform late. Delay arrives with the train
    and then has to be either absorbed by timetable supplement or passed on.
``dwell_overrun``
    A train stands longer than booked at one station - a door held, a passenger
    incident, a ramp deployed. This is by far the commonest real cause, and it is
    the one that propagates hardest because it happens where trains are closest
    together.
``speed_restriction``
    A stretch of line is limited to a lower speed for a window of time - a
    temporary speed restriction over a defect, a possession handback, hot
    weather. Unlike the other two it hits *every* train that passes, so it
    changes the timetable rather than delaying one service.

They are **declared in the scenario file, not generated randomly**. A random
disturbance model would need calibration nobody here can supply, and it would
make runs non-reproducible, which would destroy the one property that makes the
comparisons in this project trustworthy. A named disruption at a named time
answers "what does *this* do", which is the question a study actually asks.

What a disturbance costs is measured by difference: run the scenario with it and
without it, and subtract. See :mod:`trainsim.analysis.propagation`.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class LateStart:
    """A service enters its origin platform ``delay_s`` late."""

    service: str
    delay_s: float
    reason: str = "late inward working"

    def describe(self) -> str:
        return "%s starts %.0f s late (%s)" % (self.service, self.delay_s, self.reason)


@dataclass(frozen=True)
class DwellOverrun:
    """A service stands ``extra_s`` longer than booked at one station."""

    service: str
    station: str
    extra_s: float
    reason: str = "extended dwell"

    def describe(self) -> str:
        return "%s dwells %.0f s over at %s (%s)" % (
            self.service, self.extra_s, self.station, self.reason)


@dataclass(frozen=True)
class SpeedRestriction:
    """A temporary speed restriction over a stretch of one or more tracks.

    ``from_km``/``to_km`` are schematic chainage and are compared without regard
    to order, so the same restriction covers the up and down lines through a
    stretch without having to be written twice with the kilometres reversed.

    ``tracks`` empty means every track. ``from_s``/``to_s`` unset means the
    restriction is in force for the whole run.
    """

    from_km: float
    to_km: float
    max_speed_ms: float
    tracks: Tuple[str, ...] = ()
    from_s: Optional[float] = None
    to_s: Optional[float] = None
    reason: str = "temporary speed restriction"

    @property
    def low_km(self) -> float:
        return min(self.from_km, self.to_km)

    @property
    def high_km(self) -> float:
        return max(self.from_km, self.to_km)

    def active_at(self, time_s: float) -> bool:
        if self.from_s is not None and time_s < self.from_s:
            return False
        if self.to_s is not None and time_s >= self.to_s:
            return False
        return True

    def covers(self, track: str, km: float) -> bool:
        if self.tracks and track not in self.tracks:
            return False
        return self.low_km - 1e-9 <= km <= self.high_km + 1e-9

    def applies_to_track(self, track: str) -> bool:
        return not self.tracks or track in self.tracks

    def describe(self) -> str:
        from .units import ms_to_kmh
        where = "/".join(self.tracks) if self.tracks else "all lines"
        return "%.0f km/h over %s km %.1f-%.1f (%s)" % (
            ms_to_kmh(self.max_speed_ms), where, self.low_km, self.high_km,
            self.reason)


@dataclass
class Disruptions:
    """Everything declared wrong with one run.

    An empty instance is the undisturbed railway, and is what a scenario without
    a ``disruptions:`` block gets - so every code path below is exercised on
    every run, and the disturbed case is not a separate mode with its own bugs.
    """

    late_starts: List[LateStart] = field(default_factory=list)
    dwell_overruns: List[DwellOverrun] = field(default_factory=list)
    speed_restrictions: List[SpeedRestriction] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.late_starts or self.dwell_overruns
                    or self.speed_restrictions)

    # ------------------------------------------------------------------ lookups

    def late_start_s(self, service_id: str) -> float:
        return sum(d.delay_s for d in self.late_starts if d.service == service_id)

    def dwell_extra_s(self, service_id: str, station: str) -> float:
        return sum(d.extra_s for d in self.dwell_overruns
                   if d.service == service_id and d.station == station)

    def restrictions_at(self, time_s: float) -> List[SpeedRestriction]:
        return [r for r in self.speed_restrictions if r.active_at(time_s)]

    def limit_at(self, track: str, km: float, time_s: float) -> Optional[float]:
        """The tightest active restriction covering this point, if any."""
        limits = [r.max_speed_ms for r in self.speed_restrictions
                  if r.active_at(time_s) and r.covers(track, km)]
        return min(limits) if limits else None

    # ------------------------------------------------------------------ reports

    def describe(self) -> str:
        if not self:
            return "none (railway working to plan)"
        parts = [d.describe() for d in self.late_starts]
        parts += [d.describe() for d in self.dwell_overruns]
        parts += [d.describe() for d in self.speed_restrictions]
        return "; ".join(parts)

    def summary_lines(self) -> List[str]:
        if not self:
            return ["disruptions    : none (railway working to plan)"]
        lines = ["disruptions    : %d declared" % (
            len(self.late_starts) + len(self.dwell_overruns)
            + len(self.speed_restrictions))]
        for item in (list(self.late_starts) + list(self.dwell_overruns)
                     + list(self.speed_restrictions)):
            lines.append("                 %s" % item.describe())
        return lines


# ----------------------------------------------------------------- speed limits

class SpeedLimits(object):
    """What the driver believes the line speed to be, here and ahead.

    Pulled out as its own object because a temporary speed restriction is not a
    property of a segment, a signal or a train: it is a property of a stretch of
    line during a window of time. Giving the driver this interface rather than
    letting it read ``segment.max_speed_ms`` directly means a TSR needs no change
    to the infrastructure model, and the driver still never learns what a
    disruption is.
    """

    def at(self, train, chainage_m: float) -> float:
        return train.path.speed_limit_at(chainage_m)

    def over(self, train, rear_m: float, front_m: float) -> float:
        """The tightest limit anywhere under the train.

        What the driver is actually held to. A limit binds until the train is
        clear of it, not until the driver has passed the end of it, so the whole
        length is asked rather than the nose alone.
        """
        return train.path.speed_limit_over(rear_m, front_m)

    def ahead(self, train, chainage_m: float,
              lookahead_m: float) -> Sequence[Tuple[float, float]]:
        return train.path.restrictions_ahead(chainage_m, lookahead_m)


class DisruptedSpeedLimits(SpeedLimits):
    """Line speed with any active temporary restrictions laid over it."""

    def __init__(self, disruptions: Disruptions, clock):
        #: ``clock`` is a callable returning the current simulation time, so this
        #: object stays valid as the run advances without holding the kernel.
        self.disruptions = disruptions
        self.clock = clock

    def at(self, train, chainage_m: float) -> float:
        limit = train.path.speed_limit_at(chainage_m)
        temporary = self._temporary(train, chainage_m)
        if temporary is not None:
            return min(limit, temporary)
        return limit

    def over(self, train, rear_m: float, front_m: float) -> float:
        """As :meth:`SpeedLimits.over`, with any active restriction laid over it.

        The permanent limits are taken across every segment the train covers.
        The temporary ones are sampled at the two ends, which is exact unless a
        restriction is shorter than the train and falls entirely between its
        nose and its tail - a case worth knowing about rather than pretending
        away, and one no scenario here creates.
        """
        limit = train.path.speed_limit_over(rear_m, front_m)
        for chainage in (max(0.0, min(rear_m, front_m)), max(rear_m, front_m)):
            temporary = self._temporary(train, chainage)
            if temporary is not None:
                limit = min(limit, temporary)
        return limit

    def _temporary(self, train, chainage_m: float):
        entry = train.path.entry_at(chainage_m)
        km = entry.segment.km_at(chainage_m - entry.start_m)
        return self.disruptions.limit_at(entry.segment.track, km, self.clock())

    def ahead(self, train, chainage_m: float,
              lookahead_m: float) -> Sequence[Tuple[float, float]]:
        found = list(train.path.restrictions_ahead(chainage_m, lookahead_m))
        time_s = self.clock()
        for restriction in self.disruptions.restrictions_at(time_s):
            start = _entry_chainage(train.path, restriction, chainage_m)
            if start is None:
                continue
            distance = start - chainage_m
            if 0.0 < distance <= lookahead_m:
                found.append((distance, restriction.max_speed_ms))
        return found


def _entry_chainage(path, restriction: SpeedRestriction,
                    after_m: float) -> Optional[float]:
    """Where this path first enters ``restriction``, beyond ``after_m``.

    Segments carry schematic chainage that runs backwards on the down line, so
    the entry point is whichever end of the restricted stretch the train meets
    first - which is what the interpolation below works out, rather than assuming
    the lower kilometre.
    """
    for entry in path.entries:
        if entry.end_m <= after_m:
            continue
        segment = entry.segment
        if not restriction.applies_to_track(segment.track):
            continue
        a, b = segment.km_start, segment.km_end
        low, high = min(a, b), max(a, b)
        if high < restriction.low_km or low > restriction.high_km:
            continue
        # The first restricted kilometre in this segment's direction of travel.
        target = max(low, restriction.low_km) if b >= a else min(high, restriction.high_km)
        if b == a:
            return max(entry.start_m, after_m)
        fraction = (target - a) / (b - a)
        fraction = max(0.0, min(1.0, fraction))
        return entry.start_m + fraction * segment.length_m
    return None


# ------------------------------------------------------------------- from a spec

class DisruptionError(ValueError):
    """Raised when a ``disruptions:`` block cannot be understood."""


#: What each kind of disruption may be given. Kept here rather than in
#: scenario/schema.py because the disruption vocabulary belongs with the model
#: that implements it, not with the file reader.
_ALLOWED_KEYS = {
    "late_start": frozenset({"kind", "service", "seconds", "minutes", "reason"}),
    "dwell_overrun": frozenset({
        "kind", "service", "station", "seconds", "minutes", "reason"}),
    "speed_restriction": frozenset({
        "kind", "track", "tracks", "from_km", "to_km", "max_speed_kmh",
        "from_time", "to_time", "reason"}),
}


def build_disruptions(spec, parse_time, kmh_to_ms) -> Disruptions:
    """Build from a scenario file's ``disruptions:`` list.

    ``parse_time`` and ``kmh_to_ms`` are passed in rather than imported so this
    module keeps no opinion about clock formats - the loader owns that.
    """
    disruptions = Disruptions()
    for index, entry in enumerate(spec or []):
        if not isinstance(entry, dict):
            raise DisruptionError("disruption %d: expected a mapping" % (index + 1,))
        kind = str(entry.get("kind", "")).lower()
        allowed = _ALLOWED_KEYS.get(kind)
        if allowed is not None:
            unknown = sorted(k for k in entry if k not in allowed)
            if unknown:
                raise DisruptionError(
                    "disruption %d (%s): unknown key(s) %s - allowed here: %s"
                    % (index + 1, kind, ", ".join(repr(k) for k in unknown),
                       ", ".join(sorted(allowed)))
                )
        try:
            if kind == "late_start":
                disruptions.late_starts.append(LateStart(
                    service=str(entry["service"]),
                    delay_s=_seconds(entry),
                    reason=entry.get("reason", "late inward working"),
                ))
            elif kind == "dwell_overrun":
                disruptions.dwell_overruns.append(DwellOverrun(
                    service=str(entry["service"]),
                    station=str(entry["station"]),
                    extra_s=_seconds(entry),
                    reason=entry.get("reason", "extended dwell"),
                ))
            elif kind == "speed_restriction":
                tracks = entry.get("track") or entry.get("tracks") or ()
                if isinstance(tracks, str):
                    tracks = (tracks,)
                disruptions.speed_restrictions.append(SpeedRestriction(
                    from_km=float(entry["from_km"]),
                    to_km=float(entry["to_km"]),
                    max_speed_ms=kmh_to_ms(float(entry["max_speed_kmh"])),
                    tracks=tuple(str(t) for t in tracks),
                    from_s=(parse_time(entry["from_time"])
                            if entry.get("from_time") is not None else None),
                    to_s=(parse_time(entry["to_time"])
                          if entry.get("to_time") is not None else None),
                    reason=entry.get("reason", "temporary speed restriction"),
                ))
            else:
                raise DisruptionError(
                    "disruption %d: unknown kind %r - expected late_start, "
                    "dwell_overrun or speed_restriction" % (index + 1, kind)
                )
        except KeyError as exc:
            raise DisruptionError(
                "disruption %d (%s): missing %s" % (index + 1, kind, exc)
            )
    return disruptions


def _seconds(entry: dict) -> float:
    """``seconds:`` or ``minutes:``, whichever the scenario used."""
    if "seconds" in entry:
        return float(entry["seconds"])
    if "minutes" in entry:
        return float(entry["minutes"]) * 60.0
    raise KeyError("'seconds' or 'minutes'")
