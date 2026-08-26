"""What keys a scenario file may contain, and rejection of anything else.

A misspelled key used to be silent. ``max_speed_kph: 80`` is not
``max_speed_kmh``, so the track quietly kept the 140 km/h default; ``lenght_m``
left a platform at its default length; ``servicebrake`` left a train braking at
0.7 m/s2 instead of the 0.4 that was asked for. Nothing failed, nothing warned,
and the run produced a perfectly plausible number for a railway nobody had
described.

For a simulator whose whole purpose is to produce figures somebody will quote,
that is worse than a crash. So every mapping in every scenario file is checked
against the keys it is allowed to have, and an unknown one is an error with the
nearest legal spelling offered:

    infrastructure: track 'UP': unknown key 'max_speed_kph' - did you mean
    'max_speed_kmh'? Allowed here: block_length_m, block_lengths, direction, ...

The lists below are therefore the authoritative statement of the file format, and
they have to be kept in step with the code that reads them. A test asserts that
every shipped scenario passes, which is what stops them drifting apart.
"""

import difflib
from typing import Iterable, Mapping

#: ``scenario.yaml``
SCENARIO = frozenset({
    "name", "description", "infrastructure", "timetable",
    "simulation", "signalling", "interlocking", "driver", "disruptions", "view",
})
SIMULATION = frozenset({"dt", "start_time", "duration_s", "strict", "seed"})
DRIVER = frozenset({"reaction_time_s", "safety_margin_m", "stop_tolerance_m"})
VIEW = frozenset({"title", "speed"})
INTERLOCKING = frozenset({
    "enabled", "overlaps", "approach_locking_s",
    "route_request_distance_m", "route_request_lead_s",
})

#: ``infrastructure.yaml``
INFRASTRUCTURE = frozenset({"name", "defaults", "stations", "tracks",
                            "platforms", "crossovers"})
DEFAULTS = frozenset({
    "platform_zone_m", "block_length_m", "max_speed_kmh", "stop_margin_m",
    "platform_y_step", "grade_permille",
})
STATION = frozenset({"id", "name", "km"})
TRACK = frozenset({
    "id", "direction", "y", "max_speed_kmh", "block_length_m", "platform_zone_m",
    "serves", "block_lengths", "junction", "grade_permille", "gradients",
})
BLOCK_LENGTHS = frozenset({"from", "to", "block_length_m"})
GRADIENTS = frozenset({"from", "to", "grade_permille"})
JUNCTION = frozenset({"track", "at", "length_m", "max_speed_kmh",
                      "grade_separated", "grade_permille"})
PLATFORM = frozenset({
    "id", "station", "track", "length_m", "max_speed_kmh", "y_offset",
    "grade_permille",
})
CROSSOVER = frozenset({
    "id", "from", "to", "km", "length_m", "max_speed_kmh", "bidirectional",
})

#: ``timetable.yaml``
TIMETABLE = frozenset({"stock", "services"})
STOCK = frozenset({
    "id", "name", "length_m", "max_speed_kmh", "max_accel", "service_brake",
    "emergency_brake", "etcs_level", "tims",
    # Dynamics. All optional: what is not given is derived from the size and
    # performance already declared, in trainsim/core/dynamics.py.
    "mass_t", "rotating_mass_pct", "power_kw",
    "davis_a_n", "davis_b_n_per_ms", "davis_c_n_per_ms2",
    "adhesion", "brake_buildup_s",
})
SERVICE = frozenset({"id", "name", "stock", "departure", "ready_lead_s", "calls"})
CALL = frozenset({"station", "platform", "arrival", "departure", "dwell_s"})

#: ``disruptions:``, per ``kind``. Every entry also carries ``kind`` itself.
DISRUPTION = {
    "late_start": frozenset({"kind", "service", "seconds", "minutes", "reason"}),
    "dwell_overrun": frozenset({
        "kind", "service", "station", "seconds", "minutes", "reason"}),
    "speed_restriction": frozenset({
        "kind", "track", "tracks", "from_km", "to_km", "max_speed_kmh",
        "from_time", "to_time", "reason"}),
}


def check_keys(where: str, mapping: Mapping, allowed: Iterable[str],
               error=ValueError) -> None:
    """Raise unless every key of ``mapping`` is in ``allowed``.

    ``where`` names the thing being checked in the way the person editing the
    file thinks of it - ``"track 'UP'"``, not a line number - because a scenario
    file is read by section, not by line.
    """
    if not isinstance(mapping, dict):
        raise error("%s: expected a mapping, got %s"
                    % (where, type(mapping).__name__))
    allowed = frozenset(allowed)
    unknown = [key for key in mapping if key not in allowed]
    if not unknown:
        return

    problems = []
    for key in sorted(unknown):
        close = difflib.get_close_matches(str(key), sorted(allowed), n=1, cutoff=0.6)
        suggestion = " - did you mean %r?" % (close[0],) if close else ""
        problems.append("unknown key %r%s" % (key, suggestion))
    raise error(
        "%s: %s\n       allowed here: %s"
        % (where, "; ".join(problems), ", ".join(sorted(allowed)))
    )
