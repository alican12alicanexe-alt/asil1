"""Unit conversions and clock formatting.

Everything inside the simulation core is SI: metres, seconds, metres per second.
Scenario files and the schematic view speak km/h, kilometres and wall-clock times,
so every conversion lives here rather than as scattered ``/ 3.6`` literals.
"""

MS_PER_KMH = 1.0 / 3.6


def kmh_to_ms(kmh: float) -> float:
    """Convert km/h to m/s."""
    return kmh * MS_PER_KMH


def ms_to_kmh(ms: float) -> float:
    """Convert m/s to km/h."""
    return ms / MS_PER_KMH


def parse_clock(text) -> float:
    """Parse ``HH:MM`` or ``HH:MM:SS`` into seconds since midnight.

    Plain numbers are accepted too and taken as seconds, which keeps hand-written
    test scenarios terse.
    """
    if isinstance(text, (int, float)):
        return float(text)
    parts = str(text).strip().split(":")
    if len(parts) == 2:
        hours, minutes, seconds = parts[0], parts[1], "0"
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError("time must be HH:MM or HH:MM:SS, got %r" % (text,))
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        raise ValueError("time must be HH:MM or HH:MM:SS, got %r" % (text,))


def format_clock(seconds: float) -> str:
    """Format seconds since midnight as ``HH:MM:SS`` (wrapping past midnight)."""
    total = int(round(seconds)) % 86400
    return "%02d:%02d:%02d" % (total // 3600, (total // 60) % 60, total % 60)


def format_delay(seconds: float) -> str:
    """Format a delay as a signed ``M:SS``; on time reads as ``on time``."""
    if abs(seconds) < 30:
        return "on time"
    sign = "+" if seconds > 0 else "-"
    total = int(abs(seconds))
    return "%s%d:%02d" % (sign, total // 60, total % 60)


def braking_distance(speed_ms: float, decel: float, target_ms: float = 0.0) -> float:
    """Distance needed to brake from ``speed_ms`` to ``target_ms`` at ``decel``.

    The single source of truth for the braking curve: the driver model uses it to
    decide when to brake, and the tests use it to check that trains actually stop
    where they should.
    """
    if decel <= 0:
        raise ValueError("deceleration must be positive")
    if speed_ms <= target_ms:
        return 0.0
    return (speed_ms * speed_ms - target_ms * target_ms) / (2.0 * decel)


def speed_from_braking_distance(distance_m: float, decel: float,
                                target_ms: float = 0.0) -> float:
    """Highest speed from which ``distance_m`` is enough to brake to ``target_ms``.

    The inverse of :func:`braking_distance`, and the core of the driver's speed
    ceiling: given how far away the danger point is, how fast may we be now?
    """
    if distance_m <= 0.0:
        return target_ms
    return (target_ms * target_ms + 2.0 * decel * distance_m) ** 0.5
