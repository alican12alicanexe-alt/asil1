"""A small line-chart renderer that writes SVG directly.

The simulator has no plotting dependency and is not worth acquiring one for:
everything drawn here is a few polylines on a grid. So this does the arithmetic
- data coordinates to pixels, a readable tick step, a legend - and emits the
markup, and the scripts that use it worry about what to plot rather than how.

Two things only: :class:`Chart`, which is one panel with axes and any number of
lines on it, and :func:`document`, which lays panels out on a page.
"""

#: Line colours, in the order series are added. Chosen to stay distinguishable
#: printed in grey as well as on screen.
PALETTE = ("#1a6dcc", "#c0392b", "#1a8f5a", "#e08b1a", "#7b4fb5", "#0f8f9e",
           "#b5417a", "#5c6b7a")

_STYLE = (
    "text{font-family:ui-sans-serif,system-ui,sans-serif}"
    ".ti{font-size:15px;font-weight:600;fill:#111}"
    ".no{font-size:11px;fill:#666}"
    ".ax{font-size:11px;fill:#555}"
    ".lg{font-size:11px;text-anchor:end}"
    ".g{stroke:#e6e6e6;stroke-width:1}"
    ".ln{stroke:#999;stroke-width:1}"
    ".h{font-size:19px;font-weight:700;fill:#111}"
    ".s{font-size:12px;fill:#444}"
)


def nice_step(span, target=6):
    """A round tick step giving roughly ``target`` gridlines across ``span``.

    Rounds up to 1, 2 or 5 times a power of ten, which is what makes an axis
    read 0/20/40 rather than 0/17/34.
    """
    if span <= 0:
        return 1.0
    rough = span / float(target)
    power = 10.0 ** (len(str(int(rough))) - 1 if rough >= 1 else
                     -len(str(int(1.0 / rough))))
    for multiple in (1.0, 2.0, 5.0, 10.0):
        if power * multiple >= rough:
            return power * multiple
    return power * 10.0


class Chart:
    """One panel: axes, a grid, a legend, and any number of lines."""

    def __init__(self, title, xlabel, ylabel, note="",
                 width=470, height=250, y_min=0.0, y_max=None, x_min=None,
                 x_max=None):
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.note = note
        self.width = width
        self.height = height
        self.y_min = y_min
        self.y_max = y_max
        self.x_min = x_min
        self.x_max = x_max
        self.series = []

    def line(self, label, points, colour=None, dash=False):
        """Add a series. ``points`` is ``[(x, y)]``; empty series are dropped."""
        points = [p for p in points if p[1] is not None]
        if not points:
            return self
        if colour is None:
            colour = PALETTE[len(self.series) % len(PALETTE)]
        self.series.append((label, points, colour, dash))
        return self

    # ------------------------------------------------------------------ bounds

    def _bounds(self):
        xs = [p[0] for _, pts, _, _ in self.series for p in pts]
        ys = [p[1] for _, pts, _, _ in self.series for p in pts]
        if not xs:
            return 0.0, 1.0, 0.0, 1.0
        x0 = self.x_min if self.x_min is not None else min(xs)
        x1 = self.x_max if self.x_max is not None else max(xs)
        y0 = self.y_min if self.y_min is not None else min(ys)
        y1 = self.y_max if self.y_max is not None else max(ys) * 1.08
        if x1 <= x0:
            x1 = x0 + 1.0
        if y1 <= y0:
            y1 = y0 + 1.0
        return x0, x1, y0, y1

    # ------------------------------------------------------------------ render

    def render(self, ox, oy):
        """SVG for this panel with its top-left plotting corner at (ox, oy)."""
        pw, ph = self.width, self.height
        x0, x1, y0, y1 = self._bounds()

        def px(v):
            return ox + (v - x0) / (x1 - x0) * pw

        def py(v):
            return oy + ph - (v - y0) / (y1 - y0) * ph

        out = ['<text x="%d" y="%d" class="ti">%s</text>' % (ox, oy - 24, self.title)]
        if self.note:
            out.append('<text x="%d" y="%d" class="no">%s</text>'
                       % (ox, oy - 8, self.note))

        step = nice_step(x1 - x0)
        tick = (int(x0 / step)) * step
        while tick <= x1 + 1e-9:
            if tick >= x0 - 1e-9:
                gx = px(tick)
                out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="g"/>'
                           % (gx, oy, gx, oy + ph))
                out.append('<text x="%.1f" y="%d" class="ax" '
                           'text-anchor="middle">%s</text>'
                           % (gx, oy + ph + 16, _label(tick, step)))
            tick += step

        step = nice_step(y1 - y0, target=5)
        tick = (int(y0 / step)) * step
        while tick <= y1 + 1e-9:
            if tick >= y0 - 1e-9:
                gy = py(tick)
                out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="g"/>'
                           % (ox, gy, ox + pw, gy))
                out.append('<text x="%d" y="%.1f" class="ax" '
                           'text-anchor="end">%s</text>'
                           % (ox - 6, gy + 4, _label(tick, step)))
            tick += step

        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="ln"/>'
                   % (ox, oy, ox, oy + ph))
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="ln"/>'
                   % (ox, oy + ph, ox + pw, oy + ph))
        out.append('<text x="%.0f" y="%d" class="ax" text-anchor="middle">%s</text>'
                   % (ox + pw / 2.0, oy + ph + 36, self.xlabel))
        out.append('<text x="%d" y="%.0f" class="ax" text-anchor="middle" '
                   'transform="rotate(-90 %d %.0f)">%s</text>'
                   % (ox - 44, oy + ph / 2.0, ox - 44, oy + ph / 2.0, self.ylabel))

        legend_y = oy + 14
        for label, points, colour, dash in self.series:
            path = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L",
                                             px(x), py(y))
                            for i, (x, y) in enumerate(points))
            out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s" '
                       'stroke-linejoin="round"%s/>'
                       % (path, colour, "1.6" if dash else "2",
                          ' stroke-dasharray="6 4"' if dash else ""))
            if label:
                out.append('<text x="%d" y="%d" class="lg" fill="%s">%s</text>'
                           % (ox + pw - 8, legend_y, colour, label))
                legend_y += 16
        return "\n".join(out)


def _label(value, step):
    """Tick text with only as many decimals as the step needs."""
    if step >= 1.0:
        return "%.0f" % (value,)
    if step >= 0.1:
        return "%.1f" % (value,)
    return "%.2f" % (value,)


def document(charts, heading="", subheading="", columns=2,
             margin_x=120, margin_y=130, gap_x=100, gap_y=120):
    """Lay ``charts`` out in a grid and return one SVG document.

    Panels are placed left to right, top to bottom. The page is sized from what
    was actually placed, so a run with three panels is not a page with a hole in
    it.
    """
    if not charts:
        raise ValueError("nothing to draw")
    rows = (len(charts) + columns - 1) // columns
    pw = max(c.width for c in charts)
    ph = max(c.height for c in charts)
    width = margin_x + columns * pw + (columns - 1) * gap_x + 60
    height = margin_y + rows * ph + (rows - 1) * gap_y + 60

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d">' % (width, height, width, height),
           "<style>%s</style>" % (_STYLE,),
           '<rect width="100%" height="100%" fill="#fff"/>']
    if heading:
        out.append('<text x="%d" y="34" class="h">%s</text>' % (margin_x - 50, heading))
    if subheading:
        out.append('<text x="%d" y="54" class="s">%s</text>' % (margin_x - 50, subheading))
    for index, chart in enumerate(charts):
        ox = margin_x + (index % columns) * (pw + gap_x)
        oy = margin_y + (index // columns) * (ph + gap_y)
        out.append(chart.render(ox, oy))
    out.append("</svg>")
    return "\n".join(out)
