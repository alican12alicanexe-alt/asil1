"""Map schematic coordinates to screen pixels.

Infrastructure carries hand-laid ``km`` and ``y`` coordinates - real signalling
schematics are drawn, not auto-routed - so this is a linear mapping plus zoom and
pan. Keeping it in one place means a second rendering backend only has to paint;
it never has to work out where anything goes.

Linear in km, that is, except for one deliberate distortion. **A signalling
schematic is not a scale drawing**, and never has been: a real signalbox diagram
squeezes the empty miles and gives the room to the places where something
happens, because a driver's eye and a signaller's eye both want the points, the
platforms and the signals, not an accurate account of how much nothing lies
between them. depotline is 60 km of which 6 is station, so drawn to scale the
stations get a tenth of the width and every one of them is a smudge.

:data:`SchematicLayout.STATION_STRETCH` therefore gives station chainage several
times the pixels per kilometre that open line gets. The map stays monotonic and
exactly invertible, so zoom, pan and every km-to-x lookup carry on working and
nothing is drawn at a chainage it does not have - a 1200 m platform road is still
1200 m of railway, it is simply given more of the screen than 1200 m of plain
line. Set it to 1.0 for a true-scale drawing.
"""

from typing import List, Tuple


class SchematicLayout(object):
    """Linear km/y to pixel mapping, with zoom and horizontal pan.

    The vertical scale is capped rather than stretched to fill the window.
    Signalling schematics draw parallel tracks close together; letting the up
    and down lines drift to opposite edges of a tall window would look nothing
    like one, and would make the offset platform roads read as vertical spikes.
    """

    #: Maximum pixels per unit of schematic ``y``.
    PX_PER_Y = 96

    #: How much more of the screen a kilometre of station gets than a kilometre
    #: of open line. 1.0 draws the railway to scale and makes the stations tiny;
    #: much above 5 and the open line between them stops reading as distance at
    #: all. This is the knob for "make the platforms longer on screen" - it costs
    #: nothing but the plain line either side of them.
    STATION_STRETCH = 4.0

    def __init__(self, infrastructure, padding: Tuple[int, int, int, int] = (60, 70, 60, 46)):
        self.padding = padding  # left, top, right, bottom
        segments = list(infrastructure.network.segments.values())
        if not segments:
            raise ValueError("cannot lay out a network with no segments")

        kms = [s.km_start for s in segments] + [s.km_end for s in segments]
        ys = [s.y for s in segments]
        self.km_min, self.km_max = min(kms), max(kms)
        self.y_min, self.y_max = min(ys) - 0.45, max(ys) + 0.45
        if self.km_max - self.km_min < 1e-6:
            self.km_max = self.km_min + 1.0

        self._pieces = self._build_pieces(segments)
        self.virtual_span = self._pieces[-1][3] if self._pieces else 1.0

        self.width = 1280
        self.height = 520
        self.zoom = 1.0
        #: Pan is held in virtual units, not km, so that a pan of half a screen
        #: is half a screen wherever on the line it happens.
        self.pan_v = 0.0

    # ------------------------------------------------------- the stretched axis

    def _build_pieces(self, segments) -> List[Tuple[float, float, float, float]]:
        """``(km_start, km_end, weight, cumulative_virtual_end)`` across the line.

        Station chainage - anywhere a platform road lies - is weighted up; the
        rest is weighted 1. Overlapping station ranges are merged first, because
        parallel roads all occupy the same kilometres and counting them once each
        would stretch a four-road station four times as far as a one-road one.
        """
        zones = []
        for seg in segments:
            if getattr(seg, "is_platform", False):
                zones.append((min(seg.km_start, seg.km_end),
                              max(seg.km_start, seg.km_end)))
        merged = []
        for start, end in sorted(zones):
            if merged and start <= merged[-1][1] + 1e-9:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        pieces = []
        cursor = self.km_min
        cumulative = 0.0

        def add(start, end, weight):
            nonlocal cursor, cumulative
            if end - start <= 1e-9:
                return
            cumulative += (end - start) * weight
            pieces.append((start, end, weight, cumulative))
            cursor = end

        for start, end in merged:
            start = max(start, self.km_min)
            end = min(end, self.km_max)
            if end <= cursor:
                continue
            add(cursor, start, 1.0)
            add(max(start, cursor), end, self.STATION_STRETCH)
        add(cursor, self.km_max, 1.0)
        if not pieces:
            pieces.append((self.km_min, self.km_max, 1.0,
                           max(1e-6, self.km_max - self.km_min)))
        return pieces

    def virtual(self, km: float) -> float:
        """Position along the stretched axis. Monotonic in ``km``."""
        if km <= self._pieces[0][0]:
            return 0.0
        for start, end, weight, cumulative in self._pieces:
            if km <= end:
                return cumulative - (end - km) * weight
        return self._pieces[-1][3]

    def real(self, v: float) -> float:
        """Inverse of :meth:`virtual`, so zoom and pan anchor where they should."""
        if v <= 0.0:
            return self._pieces[0][0]
        for start, end, weight, cumulative in self._pieces:
            if v <= cumulative:
                return end - (cumulative - v) / weight
        return self._pieces[-1][1]

    # ------------------------------------------------------------------ metrics

    def resize(self, width: int, height: int) -> None:
        self.width = max(320, int(width))
        self.height = max(200, int(height))

    @property
    def plot_width(self) -> float:
        return max(1.0, self.width - self.padding[0] - self.padding[2])

    @property
    def plot_height(self) -> float:
        return max(1.0, self.height - self.padding[1] - self.padding[3])

    @property
    def px_per_virtual(self) -> float:
        return self.plot_width / self.virtual_span * self.zoom

    # ------------------------------------------------------------------ mapping

    def x(self, km: float) -> float:
        return self.padding[0] + (self.virtual(km) - self.pan_v) * self.px_per_virtual

    @property
    def y_scale(self) -> float:
        span = max(1e-6, self.y_max - self.y_min)
        return min(self.plot_height / span, self.PX_PER_Y)

    def y(self, value: float) -> float:
        centre = self.padding[1] + self.plot_height / 2.0
        middle = (self.y_min + self.y_max) / 2.0
        return centre + (value - middle) * self.y_scale

    def ruler_y(self) -> float:
        """Screen position of the km ruler, below the drawing."""
        return min(
            self.padding[1] + self.plot_height - 6,
            self.y(self.y_max) + 44,
        )

    def km_at_x(self, x: float) -> float:
        return self.real((x - self.padding[0]) / self.px_per_virtual + self.pan_v)

    # --------------------------------------------------------------- navigation

    def zoom_by(self, factor: float, anchor_x: float = None) -> None:
        """Zoom, keeping the km under ``anchor_x`` fixed on screen."""
        if anchor_x is None:
            anchor_x = self.padding[0] + self.plot_width / 2.0
        before = self.virtual(self.km_at_x(anchor_x))
        self.zoom = max(1.0, min(40.0, self.zoom * factor))
        after = self.virtual(self.km_at_x(anchor_x))
        self.pan_v += before - after
        self.clamp()

    def pan_by(self, fraction: float) -> None:
        """Pan by a fraction of the visible width."""
        self.pan_v += fraction * self.virtual_span / self.zoom
        self.clamp()

    def clamp(self) -> None:
        visible = self.virtual_span / self.zoom
        limit = max(0.0, self.virtual_span - visible)
        self.pan_v = max(0.0, min(limit, self.pan_v))

    def reset_view(self) -> None:
        self.zoom = 1.0
        self.pan_v = 0.0
