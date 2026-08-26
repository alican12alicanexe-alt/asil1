"""Map schematic coordinates to screen pixels.

Infrastructure carries hand-laid ``km`` and ``y`` coordinates - real signalling
schematics are drawn, not auto-routed - so this is a straight linear mapping plus
zoom and pan. Keeping it in one place means a second rendering backend only has
to paint; it never has to work out where anything goes.
"""

from typing import Tuple


class SchematicLayout(object):
    """Linear km/y to pixel mapping, with zoom and horizontal pan.

    The vertical scale is capped rather than stretched to fill the window.
    Signalling schematics draw parallel tracks close together; letting the up
    and down lines drift to opposite edges of a tall window would look nothing
    like one, and would make the offset platform roads read as vertical spikes.
    """

    #: Maximum pixels per unit of schematic ``y``.
    PX_PER_Y = 96

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

        self.width = 1280
        self.height = 520
        self.zoom = 1.0
        self.pan_km = 0.0

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
    def px_per_km(self) -> float:
        return self.plot_width / (self.km_max - self.km_min) * self.zoom

    # ------------------------------------------------------------------ mapping

    def x(self, km: float) -> float:
        return self.padding[0] + (km - self.km_min - self.pan_km) * self.px_per_km

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
        return (x - self.padding[0]) / self.px_per_km + self.km_min + self.pan_km

    # --------------------------------------------------------------- navigation

    def zoom_by(self, factor: float, anchor_x: float = None) -> None:
        """Zoom, keeping the km under ``anchor_x`` fixed on screen."""
        if anchor_x is None:
            anchor_x = self.padding[0] + self.plot_width / 2.0
        before = self.km_at_x(anchor_x)
        self.zoom = max(1.0, min(40.0, self.zoom * factor))
        after = self.km_at_x(anchor_x)
        self.pan_km += before - after
        self.clamp()

    def pan_by(self, fraction: float) -> None:
        """Pan by a fraction of the visible width."""
        self.pan_km += fraction * (self.km_max - self.km_min) / self.zoom
        self.clamp()

    def clamp(self) -> None:
        visible = (self.km_max - self.km_min) / self.zoom
        limit = max(0.0, (self.km_max - self.km_min) - visible)
        self.pan_km = max(0.0, min(limit, self.pan_km))

    def reset_view(self) -> None:
        self.zoom = 1.0
        self.pan_km = 0.0
