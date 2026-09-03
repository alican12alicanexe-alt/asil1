"""A small line-chart renderer, drawn with matplotlib.

Two things only: :class:`Chart`, which is one panel with axes and any number of
lines on it, and :func:`document`, which lays panels out on a page and returns
the SVG for it. The scripts that use it worry about what to plot rather than
how.

matplotlib is the one thing in this project that is not the standard library,
and it is needed only to *draw*. Nothing under ``trainsim/core`` or
``trainsim/scenario`` imports this module, so a run, a ``--check`` and a
``--log`` spreadsheet all still work on a bare Python install with pip blocked -
which was the constraint the hand-written SVG writer here used to serve. What
that writer could not do is a plotting library's ordinary work: tick location,
label placement, layout that reflows when a panel changes size.

    pip install --user -r requirements-optional.txt
"""

try:
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator
except ImportError as exc:  # keep the cause; say what to do about it
    raise ImportError(
        "the graphs are drawn with matplotlib, which is not installed: "
        "pip install --user -r requirements-optional.txt"
    ) from exc

from io import StringIO

#: Line colours, in the order series are added. Chosen to stay distinguishable
#: printed in grey as well as on screen.
PALETTE = ("#1a6dcc", "#c0392b", "#1a8f5a", "#e08b1a", "#7b4fb5", "#0f8f9e",
           "#b5417a", "#5c6b7a")

#: Chart chrome. The lines carry the identity; the grid, the axes and the text
#: stay out of their way, and none of them borrows a series colour.
GRID = "#e6e6e6"
AXIS = "#999999"
INK = "#111111"
MUTED = "#666666"
LABEL = "#555555"

#: Pixels per inch, so a panel declared 470x250 is 470x250 pixels of plotting
#: area. Everything outside it - titles, ticks, axis labels - is allowed for on
#: top of that, which is what PAD_IN is.
DPI = 100.0
PAD_X_IN = 1.15
PAD_Y_IN = 1.25
HEADER_IN = 1.0


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

    # ------------------------------------------------------------------ render

    def draw(self, ax):
        """Draw this panel onto ``ax``, a matplotlib axes."""
        labelled = []
        for label, points, colour, dash in self.series:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            ax.plot(xs, ys, color=colour,
                    linewidth=1.6 if dash else 2.0,
                    linestyle=(0, (6, 4)) if dash else "solid",
                    solid_joinstyle="round",
                    label=label or "_nolegend_")
            if label:
                labelled.append((label, xs[-1], ys[-1], colour))

        ax.set_title(self.title, loc="left", pad=26, color=INK,
                     fontsize=15, fontweight="bold")
        if self.note:
            ax.text(0.0, 1.025, self.note, transform=ax.transAxes,
                    ha="left", va="bottom", fontsize=11, color=MUTED)
        ax.set_xlabel(self.xlabel, fontsize=11, color=LABEL, labelpad=8)
        ax.set_ylabel(self.ylabel, fontsize=11, color=LABEL, labelpad=8)

        # 1/2/5 times a power of ten, which is what keeps an axis reading
        # 0/20/40 rather than 0/17/34.
        ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 5, 10]))
        ax.tick_params(labelsize=11, colors=LABEL, length=0)
        ax.grid(True, color=GRID, linewidth=1.0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AXIS)
            ax.spines[side].set_linewidth(1.0)

        ax.margins(y=0.08)
        if self.x_min is not None:
            ax.set_xlim(left=self.x_min)
        if self.x_max is not None:
            ax.set_xlim(right=self.x_max)
        if self.y_min is not None:
            ax.set_ylim(bottom=self.y_min)
        if self.y_max is not None:
            ax.set_ylim(top=self.y_max)

        # Two or more series need telling apart, so they get a legend. One does
        # not: it gets its name at the end of its own line, which is one less
        # thing between the reader and the shape of it.
        if len(labelled) > 1:
            # A panel is usually full of line, so the legend sits on top of
            # some of it. White behind and no border keeps it readable without
            # drawing a box the eye has to get past.
            ax.legend(loc="upper right", fontsize=11, labelcolor=INK,
                      handlelength=1.6, borderpad=0.3, labelspacing=0.35,
                      frameon=True, facecolor="#ffffff", edgecolor="none",
                      framealpha=0.85)
        elif labelled:
            label, x, y, colour = labelled[0]
            ax.annotate(label, (x, y), textcoords="offset points",
                        xytext=(-4, 7), ha="right", fontsize=11, color=INK)


def figure(charts, heading="", subheading="", columns=2):
    """Lay ``charts`` out in a grid and return the matplotlib figure.

    Panels are placed left to right, top to bottom. The page is sized from what
    was actually placed, so a run with three panels is not a page with a hole in
    it, and a grid that does not fill its last row leaves no empty axes behind.

    Separate from :func:`document` so the same page can go to any backend
    matplotlib has - a PNG to look at while working on it, say - without the
    caller reaching into how it was built.
    """
    if not charts:
        raise ValueError("nothing to draw")
    columns = min(columns, len(charts))
    rows = (len(charts) + columns - 1) // columns
    panel_w = max(c.width for c in charts) / DPI
    panel_h = max(c.height for c in charts) / DPI
    header = HEADER_IN if (heading or subheading) else 0.0

    fig = Figure(figsize=(columns * (panel_w + PAD_X_IN),
                          rows * (panel_h + PAD_Y_IN) + header),
                 dpi=DPI, layout="constrained")
    fig.patch.set_facecolor("#ffffff")
    axes = fig.subplots(rows, columns, squeeze=False)
    for index, chart in enumerate(charts):
        chart.draw(axes[index // columns][index % columns])
    for spare in range(len(charts), rows * columns):
        axes[spare // columns][spare % columns].set_visible(False)

    if header:
        # Keep the layout engine out of the top strip rather than leaving the
        # heading to be laid over the first panel's own title. A suptitle would
        # reserve the band but only holds one piece of text, and these two are
        # not the same size.
        band = header / fig.get_figheight()
        fig.get_layout_engine().set(rect=(0.0, 0.0, 1.0, 1.0 - band))
        if heading:
            fig.text(0.012, 1.0 - 0.30 * band, heading, ha="left", va="center",
                     fontsize=19, fontweight="bold", color=INK)
        if subheading:
            # wrap: a subheading naming several trains and a sampling
            # interval outgrows a two-column page, and running off the edge
            # loses the end of it.
            fig.text(0.012, 1.0 - 0.68 * band, subheading, ha="left",
                     va="center", fontsize=12, color="#444444", wrap=True)

    return fig


def document(charts, heading="", subheading="", columns=2):
    """The SVG for :func:`figure`, as a string ready to write to a file."""
    out = StringIO()
    FigureCanvasSVG(figure(charts, heading, subheading, columns)).print_svg(out)
    return out.getvalue()
