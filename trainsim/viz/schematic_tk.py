"""Live schematic view, drawn with tkinter.

Static geometry - tracks, platforms, station markers, signal masts, the km ruler
- is created once as canvas items. Every frame only *reconfigures* what changed:
block tints, signal aspect colours, and train positions. tkinter's canvas is
retained-mode, so this is both far cheaper than redrawing and simpler to read
than an immediate-mode loop.

Controls
    space        pause / resume
    b            braking envelopes and authority markers on / off
    . (period)   single step while paused
    + / -        faster / slower
    left / right pan
    z / x        zoom in / out, 0 to reset
    q or escape  quit
"""

import tkinter as tk
from tkinter import font as tkfont

from ..core.units import format_clock, format_delay, ms_to_kmh
from .layout import SchematicLayout
from .renderer import ASPECT_COLOURS, PALETTE, SchematicView

FRAME_MS = 50  # 20 frames per second


class TkSchematicView(SchematicView):
    """A window showing the corridor as a signalling schematic."""

    def __init__(self, scenario, sim, speed: float = 30.0):
        SchematicView.__init__(self, scenario, sim, speed)
        self.layout = SchematicLayout(scenario.infrastructure)
        self._pending_steps = 0.0
        self._single_step = False
        self._block_items = {}
        self._signal_items = {}
        self._indicator_items = {}
        self._point_items = {}
        self._train_items = {}
        self._zone_items = {}
        self._static_drawn = False

        # What this signalling system actually puts on the ground, and how it
        # keeps trains apart. Both change what there is to draw.
        self.lineside = getattr(sim.signalling, "has_lineside_signals", True)
        self.block_separated = getattr(sim.signalling, "separates_by", "block") == "block"
        self.show_zones = True
        self.reaction_s = scenario.driver_config.reaction_time_s

        self.root = tk.Tk()
        self.root.title(scenario.view.get("title") or ("trainsim - %s" % scenario.name))
        self.root.configure(bg=PALETTE["background"])
        self.root.geometry("1320x760")
        self.root.minsize(880, 560)

        self.mono = tkfont.Font(family="Consolas", size=9)
        self.mono_small = tkfont.Font(family="Consolas", size=8)
        self.heading = tkfont.Font(family="Consolas", size=10, weight="bold")

        self._build_widgets()
        self._bind_keys()

    # ------------------------------------------------------------------ widgets

    def _build_widgets(self) -> None:
        header = tk.Frame(self.root, bg=PALETTE["panel"])
        header.pack(side=tk.TOP, fill=tk.X)
        self.clock_label = tk.Label(
            header, text="", font=self.heading, anchor="w",
            bg=PALETTE["panel"], fg=PALETTE["label_bright"], padx=10, pady=6,
        )
        self.clock_label.pack(side=tk.LEFT)
        self.status_label = tk.Label(
            header, text="", font=self.mono, anchor="e",
            bg=PALETTE["panel"], fg=PALETTE["label"], padx=10,
        )
        self.status_label.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(
            self.root, bg=PALETTE["background"], highlightthickness=0,
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_resize)

        footer = tk.Frame(self.root, bg=PALETTE["panel"])
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        # One row per running train plus a header, within reason. The metro
        # scenario books twenty-four services; a fixed twelve-line box would clip
        # half of them without saying so, which is worse than showing fewer and
        # counting the rest.
        self.table_rows = min(18, max(8, len(self.scenario.timetable.services) + 1))
        self.table = tk.Text(
            footer, height=self.table_rows, font=self.mono_small, bd=0,
            bg=PALETTE["panel"], fg=PALETTE["label"], padx=10, pady=6,
            highlightthickness=0, wrap="none",
        )
        self.table.pack(side=tk.TOP, fill=tk.X)
        self.table.configure(state=tk.DISABLED)
        self.table.tag_configure("head", foreground=PALETTE["label_bright"])
        self.table.tag_configure("checked", foreground=PALETTE["yellow"])
        self.table.tag_configure("stopped", foreground=PALETTE["red"])
        self.table.tag_configure("dwell", foreground=PALETTE["train_dwelling"])

        self.help_label = tk.Label(
            footer, font=self.mono_small, anchor="w", padx=10, pady=4,
            bg=PALETTE["panel"], fg=PALETTE["grid"],
            text="space pause   . step   b braking zones   +/- speed   "
                 "left/right pan   z/x zoom   0 reset   q quit",
        )
        self.help_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_keys(self) -> None:
        bindings = {
            "<space>": self._toggle_pause,
            "<period>": self._step_once,
            "b": lambda e: self._toggle_zones(),
            "<plus>": lambda e: self._change_speed(2.0),
            "<equal>": lambda e: self._change_speed(2.0),
            "<minus>": lambda e: self._change_speed(0.5),
            "<Left>": lambda e: self._pan(-0.15),
            "<Right>": lambda e: self._pan(0.15),
            "z": lambda e: self._zoom(1.25),
            "x": lambda e: self._zoom(0.8),
            "0": lambda e: self._reset_view(),
            "q": lambda e: self.root.destroy(),
            "<Escape>": lambda e: self.root.destroy(),
        }
        for sequence, handler in bindings.items():
            self.root.bind(sequence, handler)

    # ------------------------------------------------------------------ actions

    def _toggle_pause(self, event=None) -> None:
        self.paused = not self.paused

    def _step_once(self, event=None) -> None:
        if self.paused:
            self._single_step = True

    def _toggle_zones(self) -> None:
        self.show_zones = not self.show_zones

    def _change_speed(self, factor: float) -> None:
        self.speed = max(1.0, min(600.0, self.speed * factor))

    def _pan(self, fraction: float) -> None:
        self.layout.pan_by(fraction)
        self._redraw_static()

    def _zoom(self, factor: float) -> None:
        self.layout.zoom_by(factor)
        self._redraw_static()

    def _reset_view(self) -> None:
        self.layout.reset_view()
        self._redraw_static()

    def _on_resize(self, event) -> None:
        self.layout.resize(event.width, event.height)
        self._redraw_static()

    # --------------------------------------------------------------- main loop

    def run(self) -> None:
        self.root.after(FRAME_MS, self._tick)
        self.root.mainloop()

    def _tick(self) -> None:
        if self._single_step:
            self.sim.step()
            self._single_step = False
        elif not self.paused and not self.sim.finished:
            self._pending_steps += self.speed * (FRAME_MS / 1000.0) / self.sim.dt
            budget = 0
            while self._pending_steps >= 1.0 and budget < 400:
                self.sim.step()
                self._pending_steps -= 1.0
                budget += 1
                if self.sim.finished:
                    break

        self._draw_dynamic()
        self._update_header()
        self._update_table()
        self.root.after(FRAME_MS, self._tick)

    # ------------------------------------------------------------------- static

    def _redraw_static(self) -> None:
        """Rebuild geometry that only changes when the view changes."""
        canvas = self.canvas
        canvas.delete("static")
        self._block_items.clear()
        self._signal_items.clear()
        self._indicator_items.clear()
        self._point_items.clear()
        layout = self.layout
        infra = self.scenario.infrastructure
        tracks = infra.tracks

        self._draw_ruler()

        for station in infra.network.stations.values():
            x = layout.x(station.km)
            canvas.create_line(
                x, layout.y(layout.y_min), x, layout.y(layout.y_max),
                fill=PALETTE["station_tick"], dash=(2, 4), tags="static",
            )
            canvas.create_text(
                x, layout.y(layout.y_min) - 22, text=station.name.upper(),
                fill=PALETTE["station"], font=self.heading, tags="static",
            )

        for segment in infra.network.segments.values():
            track_y = tracks.get(segment.track, {}).get("y", segment.y)
            points = self._segment_points(segment, track_y)
            width = (max(self.TRACK_WIDTH,
                         int(round(self.PLATFORM_ROAD_WIDTH * self._vscale)))
                     if segment.is_platform else self.TRACK_WIDTH)
            item = canvas.create_line(
                *points, fill=PALETTE["track"], width=width,
                capstyle=tk.ROUND, tags="static",
            )
            block_id = infra.block_of_segment.get(segment.id)
            if block_id:
                self._block_items[block_id] = item
            if segment.is_platform:
                self._draw_platform_face(segment, track_y, width, item)
                mid_km = (segment.km_start + segment.km_end) / 2.0
                # Below the line: train labels sit above it, so they never collide.
                canvas.create_text(
                    layout.x(mid_km),
                    layout.y(segment.y) + (self.PLATFORM_ROAD_WIDTH / 2.0
                                           + self.PLATFORM_LABEL_GAP)
                    * self._vscale,
                    text=segment.platform, fill=PALETTE["label"],
                    font=self.mono_small, tags="static",
                )

        signal_x = self._signal_positions(infra, tracks)
        for signal in infra.signals.values():
            self._draw_signal(signal, tracks, signal_x)

        self._draw_route_indicators(infra, tracks, signal_x)

        for point in infra.points.values():
            self._draw_point(point)

        self._static_drawn = True
        self._draw_dynamic()

    #: Line weights, in pixels. A platform road is drawn one weight heavier than
    #: plain line - enough to pick out, not enough to shout. Its LENGTH is not a
    #: drawing constant: it is the block section's true extent in km, and the way
    #: stations are made to read is SchematicLayout.STATION_STRETCH, which gives
    #: station chainage more of the screen than open line rather than drawing
    #: anything at the wrong size.
    TRACK_WIDTH = 3
    PLATFORM_ROAD_WIDTH = 5
    #: How much of an offset road's length is spent diverging from the running
    #: line at each end. The road is drawn \____/ , and only the flat middle is
    #: actually at the road's own alignment - so anything that belongs to the
    #: road rather than to the junction (its platform, its entry signal) has to
    #: be kept inside that middle or it floats off the rail it belongs to.
    ROAD_TAPER_FRAC = 0.18
    #: How much wider than its road the platform band is drawn. It sits BEHIND
    #: the road line, so this is the only part of it anyone sees: two pixels of
    #: colour either side of the rail. Enough to read, little enough to stay a
    #: background. Hung below the road instead, a slab crowds the next road up -
    #: Marlowe's four are only half a schematic y apart.
    PLATFORM_FACE_EXTRA = 4
    #: Gap between the slab and the road's name label.
    PLATFORM_LABEL_GAP = 9

    @property
    def _vscale(self) -> float:
        """How much of the full vertical scale this window is actually getting.

        Parallel roads are half a schematic ``y`` apart, which is 48 px at the
        layout's full scale but shrinks with the window - and everything drawn
        beside a road (its weight, its platform slab, its label) has to shrink
        with it, or a short window has Marlowe's four roads drawn on top of each
        other. Floored rather than allowed to vanish: below about half scale the
        drawing is illegible whatever it does, and a legible overlap beats an
        invisible tidy one.
        """
        full = float(SchematicLayout.PX_PER_Y)
        return max(0.5, min(1.0, self.layout.y_scale / full))

    def _draw_platform_face(self, segment, track_y, road_width, road_item) -> None:
        """The platform itself - the concrete, not the road it runs along.

        Worth drawing separately because the two are wildly different lengths and
        the difference is the thing people get wrong. The road is a block section
        sized for braking through at line speed - 1200 m on depotline - while the
        platform is sized for the train that stands at it, 220 m. Drawing only the
        road makes every station look like a kilometre of concrete.

        Drawn on the road rather than hung below it. A slab below has to clear
        the road it belongs to, and at a station like Marlowe the next road up is
        only half a schematic y away - so the concrete of one platform ends up in
        the space belonging to the platform above it. Recolouring the road itself
        keeps every platform inside its own lane, and one pixel of extra weight
        is enough to lift the band off the rail once the colour carries it.

        Centred in its road, and the stopping point is derived from the same
        centring in the builder, so a berthed train stands on the concrete drawn
        for it rather than half a kilometre past the end of it.
        """
        platform = self.scenario.infrastructure.network.platforms.get(segment.platform)
        if platform is None or platform.length_m <= 0:
            return
        layout = self.layout
        road_m = abs(segment.km_end - segment.km_start) * 1000.0
        if road_m <= 0:
            return
        # Centred in the road, as a fraction of it either side of the middle.
        # Clamped because a platform longer than its own road would otherwise be
        # drawn off the end of it.
        half = min(0.5, platform.length_m / road_m / 2.0)
        km_a = segment.km_start + (segment.km_end - segment.km_start) * (0.5 - half)
        km_b = segment.km_start + (segment.km_end - segment.km_start) * (0.5 + half)
        x0, x1 = sorted((layout.x(km_a), layout.x(km_b)))
        # A 220 m platform on a 60 km line is a couple of pixels, so give it a
        # floor: the point is to show where it is, not to survive a measurement.
        if x1 - x0 < 3.0:
            x1 = x0 + 3.0
        # A platform road stops at 1170 m of its 1200 m, which on an offset road
        # is inside the closing taper - the slab would be drawn at the road's own
        # height while the rail there has already climbed back to the running
        # line. Slide it back onto the flat instead of leaving concrete in mid
        # air. Slid, not squashed: the platform's length is a real 220 m.
        lo, hi = self._road_span(segment, track_y)
        span = x1 - x0
        if span >= hi - lo:
            x0, x1 = lo, hi
        else:
            if x1 > hi:
                x0, x1 = hi - span, hi
            if x0 < lo:
                x0, x1 = lo, lo + span
        y = layout.y(segment.y)
        face = self.canvas.create_line(
            x0, y, x1, y, fill=PALETTE["platform_face"],
            width=road_width + self.PLATFORM_FACE_EXTRA,
            capstyle=tk.BUTT, tags="static",
        )
        # Behind the road, showing either side of it. The road line carries the
        # block's occupation and route colour, so the platform has to sit under
        # it or it blanks that out for exactly the stretch where trains stand.
        self.canvas.tag_lower(face, road_item)

    def _segment_points(self, segment, track_y):
        """Polyline for a segment; platform roads splay off the running line."""
        layout = self.layout
        x0, x1 = layout.x(segment.km_start), layout.x(segment.km_end)
        y_seg = layout.y(segment.y)
        if abs(segment.end_y - segment.y) > 1e-6:
            # A junction link: a straight ramp from one line's alignment to the
            # other's, which is the one thing on the schematic that is not drawn
            # parallel to everything else.
            return (x0, y_seg, x1, layout.y(segment.end_y))
        if abs(segment.y - track_y) < 1e-6:
            return (x0, y_seg, x1, y_seg)
        # Offset road (a loop or a second platform): draw the divergence.
        y_track = layout.y(track_y)
        taper = (x1 - x0) * self.ROAD_TAPER_FRAC
        return (x0, y_track, x0 + taper, y_seg, x1 - taper, y_seg, x1, y_track)

    def _road_span(self, segment, track_y):
        """The x range over which a road runs at its own alignment.

        End to end for a road on the running line; the flat middle of the
        \\____/ for one offset from it.
        """
        layout = self.layout
        lo, hi = sorted((layout.x(segment.km_start), layout.x(segment.km_end)))
        if abs(segment.end_y - segment.y) > 1e-6:
            return lo, hi          # a junction link: drawn as one straight ramp
        if abs(segment.y - track_y) < 1e-6:
            return lo, hi
        taper = (hi - lo) * self.ROAD_TAPER_FRAC
        return lo + taper, hi - taper

    def _signal_positions(self, infra, tracks):
        """Where every signal lamp goes, as a signal id -> x in pixels.

        Two rules, and they have to be settled together, which is why this is a
        pass over all the signals rather than a decision taken one at a time.

        A lamp belongs on the road it applies to, so one whose chainage falls in
        a road's divergence is slid along to where that road reaches its own
        alignment. And the signals of one throat stand in a vertical line, as
        they do on a real gantry, so the whole group takes a single x.

        The group takes the REARMOST of those positions - the first a train
        reaches. Sliding a lamp back only shows it to a driver sooner, which
        costs nothing; sliding one forward would draw a signal further along the
        line than it stands, which is the direction that lies about where a
        train may run to.
        """
        layout = self.layout
        wanted = {}
        for signal in infra.signals.values():
            x = layout.x(signal.km)
            road = self._signal_road(signal)
            if road is not None:
                road_track_y = tracks.get(road.track, {}).get("y", road.y)
                lo, hi = self._road_span(road, road_track_y)
                if lo <= hi:
                    x = max(lo, min(hi, x))
            wanted[signal.id] = x

        groups = {}
        for signal in infra.signals.values():
            groups.setdefault((signal.node_id, signal.track), []).append(signal.id)

        placed = {}
        for (_, track_id), signal_ids in groups.items():
            # Chainage grows left to right, so the first lamp a train reaches is
            # the leftmost on an up track and the rightmost on a down one.
            up = tracks.get(track_id, {}).get("direction", "up") == "up"
            rearmost = (min if up else max)(wanted[sid] for sid in signal_ids)
            for sid in signal_ids:
                placed[sid] = rearmost
        return placed

    def _signal_road(self, signal):
        """The road a signal is drawn on: the one its own alignment belongs to.

        Either the approach it applies to, where several converge, or the road
        it reads into, where the signals of one throat differ only by that.
        """
        infra = self.scenario.infrastructure
        block = infra.blocks.get(signal.block_id)
        candidates = [signal.from_segment]
        if block is not None:
            candidates.append(block.first_segment)
        for segment_id in candidates:
            segment = infra.network.segments.get(segment_id) if segment_id else None
            if segment is not None and abs(segment.y - signal.y) < 1e-6:
                return segment
        return None

    def _draw_signal(self, signal, tracks, signal_x) -> None:
        """A signal lamp, or an unlit marker board where the level has no signals.

        ETCS Level 2 and above put the authority in the cab and leave nothing lit
        at the lineside, so drawing green lamps under those levels would be a
        picture of a railway that does not exist. Marker boards are drawn instead:
        the block boundaries are still there, they just no longer tell anyone
        anything.
        """
        layout = self.layout
        x = signal_x.get(signal.id, layout.x(signal.km))
        y = layout.y(signal.y)
        track = tracks.get(signal.track, {})
        # Down-line signals sit below their track, up-line above, so a signal is
        # visually on the side its trains are approaching from.
        up = track.get("direction", "up") == "up"
        mast = -9 if up else 9
        # A stretch worked both ways carries two roads over one rail, each with
        # its own signals at the same block boundaries. Putting them on opposite
        # sides is right - that is how a bidirectional line is drawn, and it is
        # what the mast sign above already does - but two identical lamps facing
        # each other at one chainage read as a fault rather than as a signal and
        # its wrong-line counterpart. So the wrong-line one is drawn smaller, on
        # a shorter mast: still a signal, visibly the secondary of the pair.
        wrong_line = bool(track.get("mirrors"))
        if wrong_line:
            mast = mast * 0.62

        if not self.lineside:
            self.canvas.create_line(
                x, y, x, y + mast * 0.6, fill=PALETTE["marker_board"],
                width=1, tags="static",
            )
            return

        self.canvas.create_line(
            x, y, x, y + mast, fill=PALETTE["track"], width=1, tags="static",
        )
        # Lit red until the first refresh says otherwise. A lamp has to be
        # drawn as something before the railway has been asked, and a signal
        # nobody has asked about is at danger.
        radius = 2 if wrong_line else 3
        lamp = self.canvas.create_oval(
            x - radius, y + mast - radius, x + radius, y + mast + radius,
            fill=ASPECT_COLOURS["red"], outline="", tags="static",
        )
        self._signal_items[signal.id] = lamp

    #: Half-extents of a junction indicator rhombus, and how far beyond the lamp
    #: it stands. Drawn small: it is read as present-or-absent long before it is
    #: read as a shape.
    INDICATOR_HALF = 4
    INDICATOR_GAP = 11

    def _junction_groups(self, infra):
        """Signals that are alternatives to one another, keyed by where they are.

        A train standing at one place, having arrived by one road, may be
        signalled into any of several roads ahead - that is a facing divergence,
        and those signals are its alternatives. They share a node and an
        approach and differ only in the road they read into, so that is the key.

        A group of one is not a divergence: there is one way to go and nothing
        to indicate. Those get no rhombus, which is the point of the exercise -
        an indicator that lit everywhere would say nothing anywhere.
        """
        groups = {}
        for signal in infra.signals.values():
            key = (signal.node_id, signal.track, signal.from_segment)
            groups.setdefault(key, []).append(signal)
        return {key: members for key, members in groups.items()
                if len(members) > 1}

    def _through_signal(self, infra, members, tracks):
        """The one of a group that reads into the road straight ahead.

        The through road is the one on the line's own alignment - a platform
        road at y_offset 0, the main road, or the plain line itself where the
        choice is between carrying on and taking a connection. Everything else
        is a divergence.

        It is the ROAD's alignment that decides, not the signal's. Where several
        roads converge on a node the signals of that node are drawn on the
        approach they apply to, so they all share a y and none of them says
        anything about where they read to. The block does.
        """
        track_y = tracks.get(members[0].track, {}).get("y")
        if track_y is None:
            return None
        for signal in members:
            block = infra.blocks.get(signal.block_id)
            if block is None:
                continue
            segment = infra.network.segments.get(block.first_segment)
            if segment is not None and abs(segment.y - float(track_y)) < 1e-6:
                return signal
        return None

    @staticmethod
    def _road_label(infra, block_id: str) -> str:
        """What the indicator displays for a road, if anything.

        A platform road gets its number, which is what a theatre indicator on a
        station approach actually shows: MARLOWE_UP_2 is "2", and the same road
        worked the other way is "1R". Anything else - a connection, the next
        section of plain line - gets nothing but the lit rhombus, because that
        is what a junction indicator on plain line is: there is one way off the
        line here and a lit indication means you are taking it. Numbering it
        would be inventing a road name nobody uses.
        """
        block = infra.blocks.get(block_id)
        if block is None or block.platform is None:
            return ""
        parts = block_id.split("_")
        for index in range(len(parts) - 1, -1, -1):
            if parts[index].isdigit():
                return "".join(parts[index:])
        return ""

    def _draw_route_indicators(self, infra, tracks, signal_x) -> None:
        """A rhombus beside each signal that reads over a facing divergence.

        It carries no aspect. How far a train may go is the lamp's business and
        stays entirely the lamp's business - the indicator says only WHICH road
        the interlocking has set, which is a fact the schematic could not show
        at all before: three roads at Marlowe, one green lamp, and no way to
        tell which of them was set.

        Unlit means the through road, lit means a divergence, and the number in
        it is the road. That is the way round a real one works, and it means the
        indicator is quiet on a railway running normally.
        """
        if not self.lineside:
            return
        layout = self.layout
        for key, members in self._junction_groups(infra).items():
            through = self._through_signal(infra, members, tracks)
            anchor = through or members[0]
            x = signal_x.get(anchor.id, layout.x(anchor.km))
            y = layout.y(anchor.y)
            up = tracks.get(anchor.track, {}).get("direction", "up") == "up"
            gap = -self.INDICATOR_GAP if up else self.INDICATOR_GAP
            cy = y + gap
            half = self.INDICATOR_HALF
            shape = self.canvas.create_polygon(
                x, cy - half, x + half, cy, x, cy + half, x - half, cy,
                fill="", outline=PALETTE["route_indicator_dark"], width=1,
                tags="static",
            )
            text = self.canvas.create_text(
                x, cy, text="", fill=PALETTE["route_indicator_lit"],
                font=self.mono_small, tags="static",
            )
            self._indicator_items[key] = (
                shape, text,
                tuple(signal.id for signal in members),
                through.id if through is not None else None,
                {signal.id: self._road_label(infra, signal.block_id)
                 for signal in members},
            )

    def _refresh_route_indicators(self) -> None:
        """Light the rhombus for whichever road the interlocking has set."""
        interlocking = self.sim.interlocking
        for entry in self._indicator_items.values():
            shape, text, signal_ids, through_id, labels = entry
            shown = None
            if interlocking is not None:
                for signal_id in signal_ids:
                    if (signal_id != through_id
                            and interlocking.route_set_from(signal_id)):
                        shown = signal_id
                        break
            if shown is None:
                self.canvas.itemconfig(
                    shape, fill="",
                    outline=PALETTE["route_indicator_dark"])
                self.canvas.itemconfig(text, text="")
            else:
                self.canvas.itemconfig(
                    shape, fill="",
                    outline=PALETTE["route_indicator_lit"])
                self.canvas.itemconfig(text, text=labels[shown])

    #: Half-extents of a point diamond, along and across the running line.
    POINT_LONG = 7
    POINT_SHORT = 3

    @classmethod
    def _point_shape(cls, x: float, y: float, reverse: bool):
        """Diamond coords for a point, oriented by the road it is set for.

        Lock and position are two independent facts, and one lamp cannot carry
        both: a point is locked exactly when a route is set over it, so a scheme
        that let either win would hide the other almost always. Colour carries
        the lock; the shape carries the position. Normal lies ALONG the running
        line, reverse stands ACROSS it towards the road it has been swung to,
        which is legible at four pixels in a way a third colour is not.
        """
        dx, dy = ((cls.POINT_SHORT, cls.POINT_LONG) if reverse
                  else (cls.POINT_LONG, cls.POINT_SHORT))
        return (x, y - dy, x + dx, y, x, y + dy, x - dx, y)

    def _draw_point(self, point) -> None:
        """A point: a diamond at its node, coloured by lock, shaped by position.

        Facing points sit below the line, trailing points above, so which kind is
        which is readable without a label.
        """
        layout = self.layout
        x = layout.x(point.km)
        y = layout.y(point.y) + (11 if point.kind == "facing" else -11)
        item = self.canvas.create_polygon(
            *self._point_shape(x, y, False),
            fill=PALETTE["point_free"], outline="", tags="static",
        )
        # The anchor is kept: the shape is rebuilt from it every refresh.
        self._point_items[point.id] = (item, x, y)

    def _draw_ruler(self) -> None:
        layout = self.layout
        base = layout.ruler_y()
        self.canvas.create_line(
            layout.x(layout.km_min), base, layout.x(layout.km_max), base,
            fill=PALETTE["grid"], tags="static",
        )
        span = layout.km_max - layout.km_min
        step = 1.0 if span / layout.zoom <= 12 else 5.0
        km = layout.km_min - (layout.km_min % step)
        while km <= layout.km_max + 1e-6:
            x = layout.x(km)
            self.canvas.create_line(x, base - 3, x, base + 3,
                                    fill=PALETTE["grid"], tags="static")
            self.canvas.create_text(
                x, base + 12, text="%g" % km, fill=PALETTE["grid"],
                font=self.mono_small, tags="static",
            )
            km += step

    # ------------------------------------------------------------------ dynamic

    def _draw_dynamic(self) -> None:
        if not self._static_drawn:
            return
        sim = self.sim
        infra = self.scenario.infrastructure

        route_held = (sim.interlocking.route_blocks()
                      if sim.interlocking is not None else {})
        for block_id, item in self._block_items.items():
            occupied = bool(sim.occupancy.trains_in(block_id))
            platform = infra.blocks[block_id].platform is not None
            if occupied and self.block_separated:
                # Only where the block is the unit of safety. Under distance
                # separation nothing is reserved a block at a time, so colouring
                # a whole road because a train is somewhere on it would draw a
                # rule the system does not work by; the train's own mark says
                # where it is, and the gap behind it is what matters.
                colour = PALETTE["platform_occupied"] if platform else PALETTE["track_occupied"]
            elif block_id in route_held and not occupied:
                # Locked by a route but nothing on it yet: the road is reserved.
                colour = PALETTE["route_set"]
            else:
                colour = PALETTE["platform"] if platform else PALETTE["track"]
            self.canvas.itemconfig(item, fill=colour)

        if sim.interlocking is not None:
            state = sim.interlocking.point_state()
            for point_id, (item, px, py) in self._point_items.items():
                info = state.get(point_id, {})
                # Two independent facts, two channels. Colour is the lock, shape
                # is the position - a locked point swung to the loop used to show
                # its lock and say nothing about where it was actually set.
                self.canvas.coords(
                    item, *self._point_shape(px, py, bool(info.get("reverse"))))
                self.canvas.itemconfig(
                    item,
                    fill=(PALETTE["point_locked"] if info.get("locked_by")
                          else PALETTE["point_free"]),
                )

        for signal_id, item in self._signal_items.items():
            aspect = sim.aspects.get(signal_id, "red")
            self.canvas.itemconfig(
                item, fill=ASPECT_COLOURS.get(aspect, ASPECT_COLOURS["red"]))

        self._refresh_route_indicators()

        self._draw_trains()

    #: Shortest a train may be drawn. Below this it is a smear rather than a
    #: shape, and which end is its nose stops being readable.
    MIN_TRAIN_PX = 12

    def _draw_trains(self) -> None:
        layout = self.layout
        tracks = self.scenario.infrastructure.tracks
        live = set()

        for train in self.sim.trains.values():
            if not train.is_active:
                continue
            live.add(train.id)
            front_km = train.path.km_at(train.chainage_m)
            rear_km = train.path.km_at(max(0.0, train.rear_m))
            y = layout.y(train.path.y_at(train.chainage_m))
            segment = train.path.entry_at(train.chainage_m).segment

            # A train is drawn from its rear to its nose, and where that is too
            # few pixels to see it is padded BACKWARDS from the nose. Padding
            # around the centre - which is what this used to do - draws the nose
            # ahead of where the train actually is, and by a long way: sixty
            # kilometres across a window is about 24 m to the pixel, so a 160 m
            # train is three pixels on open line and was being inflated to
            # twelve about its midpoint. The drawn nose then stood 240 m past
            # the real one, over-running the signal the train was actually
            # standing at, and every train looked as though its middle was the
            # thing being positioned. The kernel never thought so - chainage_m
            # is the front and always was - so this was the picture lying about
            # the model, which is the worst way round.
            x_front, x_rear = layout.x(front_km), layout.x(rear_km)
            if abs(x_front - x_rear) < self.MIN_TRAIN_PX:
                ahead = 1.0 if segment.km_end >= segment.km_start else -1.0
                x_rear = x_front - ahead * self.MIN_TRAIN_PX
            x_rear, x_front = min(x_rear, x_front), max(x_rear, x_front)

            direction = tracks.get(segment.track, {}).get("direction", "up")
            if train.state == "dwelling":
                colour = PALETTE["train_dwelling"]
            else:
                colour = PALETTE["train_up"] if direction == "up" else PALETTE["train_down"]

            self._draw_zone(train, y)

            items = self._train_items.get(train.id)
            if items is None:
                body = self.canvas.create_rectangle(
                    0, 0, 0, 0, fill=colour, outline=PALETTE["train_outline"],
                )
                label = self.canvas.create_text(
                    0, 0, text=train.id, fill=PALETTE["label_bright"],
                    font=self.mono_small,
                )
                items = (body, label)
                self._train_items[train.id] = items
            body, label = items
            self.canvas.coords(body, x_rear, y - 4, x_front, y + 4)
            self.canvas.itemconfig(body, fill=colour)
            self.canvas.coords(label, (x_rear + x_front) / 2.0, y - 14)
            self.canvas.tag_raise(body)
            self.canvas.tag_raise(label)

        for train_id in [t for t in self._train_items if t not in live]:
            for item in self._train_items.pop(train_id):
                self.canvas.delete(item)
        for train_id in [t for t in self._zone_items if t not in live]:
            self.canvas.delete(self._zone_items.pop(train_id))

    def _draw_zone(self, train, y) -> None:
        """The braking envelope: how much railway this train needs to stop in.

        This is what a moving block actually is: not a fixed length of track that
        lights up, but the distance this train needs to stop, travelling with it
        and shrinking as it slows. Drawn for every signalling system, because
        seeing it sit inside a whole lit block is the clearest picture of what
        fixed block wastes.

        There used to be a tick here as well, marking where the authority ran
        out. Two marks for one idea, and the tick was the worse of them: it was
        drawn from the authority computed before the train moved, so it lagged a
        tick behind everything else on the screen, and where the authority ended
        at a signal it only repeated what the signal and the route colour were
        already saying.
        """
        layout = self.layout
        zone = self._zone_items.get(train.id)
        if zone is None:
            zone = self.canvas.create_rectangle(
                0, 0, 0, 0, fill=PALETTE["braking_zone"], outline="",
                stipple="gray25",
            )
            self._zone_items[train.id] = zone

        if not self.show_zones or train.speed_ms <= 0.3:
            self.canvas.itemconfigure(zone, state="hidden")
            return
        needed = train.stopping_distance_m(self.reaction_s)
        end = min(train.path.total_m, train.chainage_m + needed)
        x_a = layout.x(train.km)
        x_b = layout.x(train.path.km_at(end))
        left, right = min(x_a, x_b), max(x_a, x_b)
        self.canvas.coords(zone, left, y - 6, right, y + 6)
        self.canvas.itemconfigure(zone, state="normal")

    # ------------------------------------------------------------------- header

    def _update_header(self) -> None:
        sim = self.sim
        state = "PAUSED" if self.paused else ("ENDED" if sim.finished else "running")
        self.clock_label.configure(text="%s   %s" % (format_clock(sim.time_s), state))
        bits = [
            "x%g" % self.speed,
            "%d running" % len(sim.active_trains()),
            "lineside signals" if self.lineside else "cab signalling, no lineside",
            "block separation" if self.block_separated else "distance separation",
            self.scenario.infrastructure.network.name,
            sim.signalling.describe(),
        ]
        if sim.interlocking is not None:
            locked = sim.interlocking.locked_routes()
            if locked:
                bits.insert(2, "routes set: %s" % ", ".join(
                    r.replace("R_", "") for r in locked))
        if sim.violations:
            bits.append("VIOLATIONS %d" % len(sim.violations))
        if self.layout.zoom > 1.0:
            bits.insert(1, "zoom %.1fx" % self.layout.zoom)
        self.status_label.configure(
            text="   ".join(bits),
            fg=PALETTE["warning"] if sim.violations else PALETTE["label"],
        )

    @staticmethod
    def _governed_by(train) -> str:
        """What is holding this train, in the words a signaller would use."""
        if train.state == "dwelling":
            if train.dwell_until_s is None:
                return "at platform"
            return "away %s" % format_clock(train.dwell_until_s)
        return train.authority_reason

    def _update_table(self) -> None:
        rows = [
            "%-4s %-26s %-9s %8s %7s %7s %-11s %s"
            % ("id", "service", "state", "km", "speed", "target", "next stop",
               "governed by"),
        ]
        tags = ["head"]
        for train in sorted(self.sim.trains.values(), key=lambda t: t.id):
            if train.state == "finished":
                continue
            stop = train.next_stop()
            rows.append(
                "%-4s %-26s %-9s %8s %7s %7s %-11s %s"
                % (train.id, train.name[:26], train.state,
                   "%.2f" % train.km,
                   "%.0f" % ms_to_kmh(train.speed_ms),
                   "%.0f" % ms_to_kmh(train.target_speed_ms),
                   stop.station if stop else "-",
                   "%s  %s" % (self._governed_by(train),
                               format_delay(train.delay_s)))
            )
            reason = train.authority_reason
            if train.state == "dwelling":
                tags.append("dwell")
            elif "danger" in reason:
                tags.append("stopped")
            elif "caution" in reason:
                tags.append("checked")
            else:
                tags.append("")

        if len(rows) > self.table_rows:
            hidden = len(rows) - self.table_rows
            rows = rows[:self.table_rows - 1]
            tags = tags[:self.table_rows - 1]
            rows.append("     ... and %d more running" % (hidden + 1,))
            tags.append("head")

        self.table.configure(state=tk.NORMAL)
        self.table.delete("1.0", tk.END)
        for row, tag in zip(rows, tags):
            self.table.insert(tk.END, row + "\n", tag or ())
        self.table.configure(state=tk.DISABLED)
