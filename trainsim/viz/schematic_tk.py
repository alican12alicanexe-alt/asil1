"""Live schematic view, drawn with tkinter.

Static geometry - tracks, platforms, station markers, signal masts, the km ruler
- is created once as canvas items. Every frame only *reconfigures* what changed:
block tints, signal aspect colours, and train positions. tkinter's canvas is
retained-mode, so this is both far cheaper than redrawing and simpler to read
than an immediate-mode loop.

Controls
    space        pause / resume
    b            braking envelopes on / off
    a            limit of movement authority on / off
    . (period)   single step while paused
    + / -        faster / slower
    left / right pan
    z / x        zoom in / out, 0 to reset
    q or escape  quit
"""

import math

import tkinter as tk
from tkinter import font as tkfont

from ..core.units import format_clock, format_delay, ms_to_kmh
from .layout import SchematicLayout
from ..core.signals import Aspect
from .renderer import ASPECT_COLOURS, PALETTE, SchematicView

FRAME_MS = 50  # 20 frames per second


class TkSchematicView(SchematicView):
    """A window showing the corridor as a signalling schematic."""

    def __init__(self, scenario, sim, speed: float = 30.0):
        SchematicView.__init__(self, scenario, sim, speed)
        self.layout = SchematicLayout(scenario.infrastructure)
        self._pending_steps = 0.0
        self._single_step = False
        #: Canvas items per block - a LIST, because a block split by a
        #: speed limit is drawn as several segments and all of them have
        #: to take the occupied or route-set colour. Holding one item per
        #: block lit only the last piece: a block in two showed half of
        #: itself set, a block in four a quarter.
        self._block_items = {}
        self._signal_items = {}
        self._branch_heads = {}
        self._lamp_groups = {}
        self._dead_ends = set()
        self._lamp_owner = {}
        self._sharing_lamp = set()
        self._train_items = {}
        self._zone_items = {}
        self._authority_items = {}
        self._static_drawn = False

        # What this signalling system actually puts on the ground, and how it
        # keeps trains apart. Both change what there is to draw.
        self.lineside = getattr(sim.signalling, "has_lineside_signals", True)
        self.block_separated = getattr(sim.signalling, "separates_by", "block") == "block"
        self.show_zones = True
        self.show_authority = True
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
            text="space pause   . step   b braking zones   a authority   "
                 "+/- speed   left/right pan   z/x zoom   0 reset   q quit",
        )
        self.help_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_keys(self) -> None:
        bindings = {
            "<space>": self._toggle_pause,
            "<period>": self._step_once,
            "b": lambda e: self._toggle_zones(),
            "a": lambda e: self._toggle_authority(),
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

    def _toggle_authority(self) -> None:
        self.show_authority = not self.show_authority

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
        self._branch_heads.clear()
        self._lamp_groups.clear()
        self._lamp_owner.clear()
        self._sharing_lamp.clear()
        layout = self.layout
        infra = self.scenario.infrastructure
        tracks = infra.tracks

        self._draw_ruler()
        self._dead_ends = self._dead_end_nodes(infra)

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

        drawn_buffers = set()
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
                self._block_items.setdefault(block_id, []).append(item)
            self._draw_buffer_stops(segment, points, width, drawn_buffers)
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
        self._plan_shared_lamps(infra, tracks, signal_x)
        for signal in infra.signals.values():
            self._draw_signal(signal, tracks, signal_x)

        self._draw_branch_heads(infra, tracks, signal_x)

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

    def _dead_end_nodes(self, infra):
        """Where the railway stops - the nodes with nothing on the far side.

        A node is a dead end when every road that touches it lies on the same
        side of it. Anywhere else, some road carries on: even the last block of
        a plain through line has the next one beyond it. At a depot road's inner
        end there is nothing beyond, in either direction, and that is what makes
        it a depot road rather than a platform.

        Read off the layout rather than declared, so a scenario gets its buffer
        stops from where its roads actually end.
        """
        sides = {}
        for segment in infra.network.segments.values():
            reach = segment.km_end - segment.km_start
            for node, side in ((segment.start_node, reach),
                               (segment.end_node, -reach)):
                if abs(side) < 1e-9:
                    continue
                sides.setdefault(node, set()).add(side > 0)
        return {node for node, ways in sides.items() if len(ways) == 1}

    def _draw_buffer_stops(self, segment, points, road_width, drawn) -> None:
        """The mark at the end of a road that has no beyond.

        This is what a depot road has where a through platform has its second
        signal, and drawing it is what makes the two read differently. A
        platform in a station can be left in either direction, so it carries a
        starting signal at each end of its concrete. A depot road can only be
        left the way the train came in, so it carries one - and the far end,
        with nothing drawn on it, looked like a signal that had been forgotten
        rather than an end of the line.

        Drawn from the road's own polyline rather than from its chainage, so the
        bar sits on the rail even where the road is drawn off the running line.
        A road and the twin that works it the other way are the same rails and
        end at the same place, so the mark is drawn once per place.
        """
        ends = []
        if segment.start_node in self._dead_ends:
            ends.append((points[0], points[1]))
        if segment.end_node in self._dead_ends:
            ends.append((points[-2], points[-1]))
        half = max(3.0, (road_width / 2.0 + 4.0) * self._vscale)
        for x, y in ends:
            key = (round(x, 1), round(y, 1))
            if key in drawn:
                continue
            drawn.add(key)
            self.canvas.create_line(
                x, y - half, x, y + half, fill=PALETTE["buffer_stop"],
                width=2, tags="static",
            )

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
        face = self._platform_face_span(segment, track_y)
        if face is None:
            return
        layout = self.layout
        x0, x1 = face
        y = layout.y(segment.y)
        slab = self.canvas.create_line(
            x0, y, x1, y, fill=PALETTE["platform_face"],
            width=road_width + self.PLATFORM_FACE_EXTRA,
            capstyle=tk.BUTT, tags="static",
        )
        # Behind the road, showing either side of it. The road line carries the
        # block's occupation and route colour, so the platform has to sit under
        # it or it blanks that out for exactly the stretch where trains stand.
        self.canvas.tag_lower(slab, road_item)

    def _platform_on(self, segment):
        """The platform served by a road, including one worked the other way.

        A mirrored road carries no ``platform`` on the segment - the station has
        the roads it has, and a twin is one of them being used backwards rather
        than a second platform that would show up in every count - but there IS
        a platform record whose ``segment`` is that twin, because a diverted
        train calls at the same concrete. The drawing wants the concrete, so it
        asks by segment and takes either answer.
        """
        platforms = self.scenario.infrastructure.network.platforms
        found = platforms.get(segment.platform) if segment.platform else None
        return found if found is not None else platforms.get(segment.id)

    def _platform_face_span(self, segment, track_y):
        """The x range of the concrete on a platform road, or ``None``.

        Split out from the drawing because two things need it: the slab, and the
        starting signal at the platform's departure end. They have to agree, or
        the lamp ends up standing on the ballast beyond the platform it belongs
        to.
        """
        platform = self._platform_on(segment)
        if platform is None or platform.length_m <= 0:
            return None
        layout = self.layout
        road_m = abs(segment.km_end - segment.km_start) * 1000.0
        if road_m <= 0:
            return None
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
            return lo, hi
        if x1 > hi:
            x0, x1 = hi - span, hi
        if x0 < lo:
            x0, x1 = lo, lo + span
        return x0, x1

    def _segment_points(self, segment, track_y):
        """Polyline for a segment; platform roads splay off the running line."""
        layout = self.layout
        x0, x1 = layout.x(segment.km_start), layout.x(segment.km_end)
        y_seg = layout.y(segment.y)
        if abs(segment.end_y - segment.y) > 1e-6:
            if segment.turns:
                # A horseshoe, and it has to look like one. See _turn_points.
                return self._turn_points(x0, y_seg, x1, layout.y(segment.end_y))
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

    #: The straight run-in and run-out either side of the half circle, as a
    #: fraction of its radius. Without them the curve starts turning the instant
    #: it leaves the running line, which reads as a kink rather than as a
    #: junction; a short tangent is what makes the eye see one road leaving
    #: another.
    TURN_LEAD_FRAC = 0.35
    #: Straight pieces the curve is flattened into. Thirty-two puts about three
    #: pixels between samples at the size this draws at, which is past the point
    #: where more of them change the picture.
    TURN_STEPS = 32

    def _turn_geometry(self, x0, y0, x1, y1):
        """A horseshoe as three pieces: run out, half circle, run back.

        A crossover is a diagonal and is honestly drawn as one. A horseshoe is
        not: the train leaves the up line still going up, sweeps round 180
        degrees, and comes back down the down line. Drawn as a straight line
        between its two ends it read as a corner cut at about 120 degrees -
        the wrong shape, and worse, the shape a crossover has, so the one place
        on a ring where a train turns round looked like the ten places where it
        does not.

        A cubic with both control points on one outer x was tried first and is
        not this. It gets the tangents right and the middle wrong: a Bezier is
        not a circle, so the apex came out flat and the two shoulders too tight,
        which is what a badly drawn U looks like. This is an actual half circle
        of radius half the gap between the two roads, joined to each road by a
        short tangent, so every part of it has the same curvature - which is the
        whole of what makes a curve read as a curve.

        Returned as ``(centre_x, middle_y, radius, sign, outward, run_in, arc,
        run_out)``, measured in pixels along the drawing, so that
        :meth:`_turn_xy` can find a point at a distance rather than at a
        parameter. That matters: a train moving at a steady speed has to look
        like it, and a Bezier parameter is not arc length.
        """
        radius = abs(y1 - y0) / 2.0
        middle = (y0 + y1) / 2.0
        # Which way round the circle is swept, and which way it bulges. Outward
        # is simply where the curve leaves from: a horseshoe always rejoins
        # back down the line, so the leaving end is the far end of the railway.
        sign = 1.0 if y1 > y0 else -1.0
        outward = 1.0 if x0 >= x1 else -1.0
        lead = radius * self.TURN_LEAD_FRAC
        centre = (max(x0, x1) if outward > 0 else min(x0, x1)) + outward * lead
        return (centre, middle, radius, sign, outward,
                abs(centre - x0), math.pi * radius, abs(centre - x1))

    @staticmethod
    def _turn_xy(geometry, distance):
        """The point ``distance`` pixels along a horseshoe from where it leaves."""
        centre, middle, radius, sign, outward, run_in, arc, run_out = geometry
        if distance <= run_in:
            return (centre - outward * (run_in - distance),
                    middle - sign * radius)
        distance -= run_in
        if distance <= arc:
            angle = math.pi * distance / arc if arc > 0.0 else 0.0
            return (centre + outward * radius * math.sin(angle),
                    middle - sign * radius * math.cos(angle))
        distance = min(distance - arc, run_out)
        return (centre - outward * distance, middle + sign * radius)

    def _turn_points(self, x0, y0, x1, y1):
        """The polyline a turning loop is drawn as."""
        geometry = self._turn_geometry(x0, y0, x1, y1)
        total = geometry[5] + geometry[6] + geometry[7]
        points = []
        for step in range(self.TURN_STEPS + 1):
            points.extend(self._turn_xy(geometry, total * step / self.TURN_STEPS))
        return tuple(points)

    def _path_xy(self, path, chainage_m):
        """Where a point on a train's path sits on the drawing.

        Everywhere but a horseshoe this is the km and the alignment, read
        straight off the path. On a horseshoe it is not: the drawing goes round
        a curve the km axis knows nothing about, and a train placed by km alone
        cuts the chord and leaves the rails - which is exactly what it did.
        """
        entry = path.entry_at(chainage_m)
        segment = entry.segment
        if segment.turns:
            layout = self.layout
            geometry = self._turn_geometry(
                layout.x(segment.km_start), layout.y(segment.y),
                layout.x(segment.km_end), layout.y(segment.end_y))
            total = geometry[5] + geometry[6] + geometry[7]
            along = (chainage_m - entry.start_m) / max(1e-6, segment.length_m)
            return self._turn_xy(geometry, total * min(1.0, max(0.0, along)))
        x = self.layout.x(path.km_at(chainage_m))
        track_y = self._splay_of(segment)
        if track_y is not None:
            return (x, self._splay_y(segment, track_y, x))
        return (x, self.layout.y(path.y_at(chainage_m)))

    def _splay_of(self, segment):
        """The running line an offset road splays off, or ``None``.

        A loop or a second platform is drawn ``\\____/``: it leaves the line's
        alignment, runs parallel to it for most of its length and comes back.
        Only the flat middle is at the road's own y. A junction link is not
        this - it ramps from one alignment to the other and ends there - and
        neither is a horseshoe.
        """
        if abs(segment.end_y - segment.y) > 1e-6:
            return None
        track_y = self.scenario.infrastructure.tracks.get(
            segment.track, {}).get("y", segment.y)
        if abs(segment.y - track_y) < 1e-6:
            return None
        return track_y

    def _splay_y(self, segment, track_y, x):
        """Where the drawn rail of an offset road is at pixel ``x``.

        The path does not know about the splay. ``Path.y_at`` interpolates a
        junction link, because that segment declares an end_y, and returns a
        flat y for everything else - so a train on an offset platform road was
        drawn at the road's own alignment from the moment it entered the road,
        while the rail it is on was still out at the running line for the first
        eighteen per cent of it. The train jumped the offset in one tick at
        each end: ``______|------`` where the rail is drawn ``______/------``,
        and for the length of the taper it stood beside the road rather than on
        it.

        This is the same fault the horseshoe had and the same fix. Read off the
        drawing rather than off the km axis, so there is one answer to where a
        road is and everything - the rail, the train, its braking envelope, its
        limit of authority - uses it.

        In x rather than along the road, because that is how
        :meth:`_segment_points` lays the taper out, and interpolating the two
        the same way is what keeps them on top of each other to the pixel.
        """
        layout = self.layout
        y_seg, y_track = layout.y(segment.y), layout.y(track_y)
        x0, x1 = layout.x(segment.km_start), layout.x(segment.km_end)
        taper = (x1 - x0) * self.ROAD_TAPER_FRAC
        if abs(taper) < 1e-9:
            return y_seg
        # Distance into each taper, as a fraction of it. Signed division, so a
        # road worked towards lower km - where x1 is left of x0 - reads the
        # same way round.
        fraction = min((x - x0) / taper, (x1 - x) / taper)
        return y_track + (y_seg - y_track) * min(1.0, max(0.0, fraction))

    #: Samples taken along a train, its braking envelope and anything else drawn
    #: as a length of railway rather than a point on one. Straight track needs
    #: two; the rest are for the bends, and on straight track they are collinear
    #: and cost a few floats.
    PATH_STEPS = 8
    #: Ceiling on that, for a stopping envelope kilometres long with a bend in
    #: a few metres of it. Past this the extra samples are smaller than a pixel.
    MAX_PATH_STEPS = 200

    def _path_steps(self, path, from_m, to_m):
        """How finely to sample a stretch of path: as fine as its bends need.

        Even sampling over the whole stretch, so the count has to be set by the
        worst of it. A horseshoe and the splay at each end of an offset road
        are the only two places the drawing leaves the straight, and a braking
        envelope three kilometres long carrying one of them in its last two
        hundred metres would, at eight samples, put one point either side of
        the bend and draw a chord across it. So a bend in range raises the
        count in proportion to how little of the range it occupies.
        """
        lo, hi = min(from_m, to_m), max(from_m, to_m)
        steps = self.PATH_STEPS
        if hi - lo <= 0.0:
            return steps
        for entry in path.entries:
            if entry.end_m <= lo or entry.start_m >= hi:
                continue
            segment = entry.segment
            if not segment.turns and self._splay_of(segment) is None:
                continue
            share = min(hi, entry.end_m) - max(lo, entry.start_m)
            if share > 0.0:
                steps = max(steps, int(math.ceil(
                    self.TURN_STEPS * (hi - lo) / share)))
        return min(steps, self.MAX_PATH_STEPS)

    def _path_polyline(self, path, from_m, to_m, steps=None):
        """A flat coordinate list following the path from one chainage to another."""
        steps = self._path_steps(path, from_m, to_m) if steps is None else steps
        points = []
        for step in range(steps + 1):
            points.extend(self._path_xy(
                path, from_m + (to_m - from_m) * step / steps))
        return points

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

        A starting signal is the exception to the second rule. It stands at the
        departure end of its own platform, not out at the throat with the
        others: that is where a real one is, just ahead of the nose of the train
        standing at the platform, and it is what makes three roads at Marlowe
        read as three roads with three starters rather than one gantry. The
        block boundary is still out at the throat - this is the permitted
        rearward slide, several hundred metres of it.
        """
        layout = self.layout
        wanted = {}
        pinned = set()
        for signal in infra.signals.values():
            x = layout.x(signal.km)
            road = self._signal_road(signal)
            if road is not None:
                road_track_y = tracks.get(road.track, {}).get("y", road.y)
                lo, hi = self._road_span(road, road_track_y)
                if lo <= hi:
                    x = max(lo, min(hi, x))
                platform_end = self._starter_x(signal, road, road_track_y)
                if platform_end is not None:
                    x = platform_end
                    pinned.add(signal.id)
            if not signal.from_segment:
                # The lamp at the closed end of a depot road, and it belongs on
                # the concrete like the starter at the other end of the same
                # platform, not out at the block boundary. A station platform
                # carries a lamp at each end of its face - one per direction -
                # and a depot road was coming out with one, because the second
                # is a starter for a direction it has nowhere to start into
                # and the only signal at that end stands at the stop block
                # instead. Drawn on the near end of the face, the depot reads
                # like the platform it is.
                #
                # Pinned either way. Two of these at a depot are the closed
                # ends of two separate roads and not alternatives at a set of
                # points, so taking the group's rearmost x would drag the
                # offset road's lamp back to where its road is still leaving
                # the running line and hang it in the air beside the splay.
                if road is not None:
                    face = self._platform_face_span(road, road_track_y)
                    if face is not None:
                        x = min(face, key=lambda end: abs(end - x))
                pinned.add(signal.id)
            wanted[signal.id] = x

        groups = {}
        for signal in infra.signals.values():
            if signal.id in pinned:
                continue
            groups.setdefault((signal.node_id, signal.track), []).append(signal.id)

        placed = dict((sid, wanted[sid]) for sid in pinned)
        for (_, track_id), signal_ids in groups.items():
            # Chainage grows left to right, so the first lamp a train reaches is
            # the leftmost on an up track and the rightmost on a down one.
            up = tracks.get(track_id, {}).get("direction", "up") == "up"
            rearmost = (min if up else max)(wanted[sid] for sid in signal_ids)
            for sid in signal_ids:
                placed[sid] = rearmost
        return placed

    def _starter_x(self, signal, road, track_y):
        """Where a platform's starting signal stands, or ``None``.

        A signal is a starter when the road it is drawn on is the one a train
        arrives ON - a platform road - rather than the one it reads INTO. Those
        are the signals a train at a platform is waiting for, and they belong at
        the end of the concrete it is standing on.
        """
        if road.id != signal.from_segment or self._platform_on(road) is None:
            return None
        face = self._platform_face_span(road, track_y)
        if face is None:
            return None
        # The departure end: forward is rightwards on a road whose chainage
        # grows to the right, leftwards on one worked the other way.
        return face[1] if road.km_end >= road.km_start else face[0]

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

    def _signal_y(self, signal):
        """The schematic y a signal is drawn at.

        Normally its own, but a junction link is the one thing here that is not
        parallel to the rest of the railway: it ramps from one line's alignment
        to the other's, and a signal at the far end of one stands on the line it
        JOINS, not the one it left. Taking the link's starting y put the signal
        for a train arriving over a crossover on the line it came from, on top
        of that line's own signal.
        """
        road = self._signal_road(signal)
        if (road is not None and road.y_end is not None
                and abs(road.y_end - road.y) > 1e-6
                and signal.node_id == road.end_node):
            return self.layout.y(road.y_end)
        return self.layout.y(signal.y)

    def _draw_signal(self, signal, tracks, signal_x) -> None:
        """A signal lamp, or an unlit marker board where the level has no signals.

        ETCS Level 2 and above put the authority in the cab and leave nothing lit
        at the lineside, so drawing green lamps under those levels would be a
        picture of a railway that does not exist. Marker boards are drawn instead:
        the block boundaries are still there, they just no longer tell anyone
        anything.

        The alternatives at a facing divergence are not drawn here: they are
        one post on the ground, and :meth:`_plan_shared_lamps` has already
        picked which of them carries it.

        A signal with no road behind it IS drawn, dark, at the closed end of
        the platform it belongs to. A station platform carries a lamp at each
        end of its concrete, one per direction, and a depot platform was
        carrying one: the lamp that would face the other way is a starter for
        a direction there is nothing to start into, and the only signal the
        model has at that end reads INTO the road from beyond the end of the
        railway, which no train can ever do here.

        It is drawn anyway, and on the concrete rather than out at the stop
        block, for the reason a depot road looks like a platform in the first
        place - it is one. The block boundary is real and the layout can grow
        into it: a connection laid beyond that stop block, a junction or an
        extension or a road worked through, gives the signal an approach and
        it starts working. Until then it is a lamp that never lights, which is
        a fact about this layout rather than about the signal.

        It is dark rather than red, and :meth:`_signals_out_of_use` is what
        makes it so. Dark is the right word for it - *not this way* - and red
        would be a danger signal held against a train that cannot exist.

        Every signal on a stretch worked both ways IS drawn, each on its own
        road at its own end. They used to share one lamp per boundary that moved
        to whichever side was in force, which was true but hid the layout: a
        three-platform station came out as one lamp instead of a signal at each
        end of each road. The two directions' signals do not collide, because
        each stands at the departure end of its own road and those are opposite
        ends. Which of them is in force is carried by
        :meth:`_signals_out_of_use` darkening the rest.
        """
        if signal.id in self._sharing_lamp:
            return
        layout = self.layout
        x = signal_x.get(signal.id, layout.x(signal.km))
        y = self._signal_y(signal)
        mast = -self.TWO_WAY_MAST

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
        lamp = self.canvas.create_oval(
            x - 3, y + mast - 3, x + 3, y + mast + 3,
            fill=ASPECT_COLOURS["red"], outline="", tags="static",
        )
        self._signal_items[signal.id] = lamp

    def _plan_shared_lamps(self, infra, tracks, signal_x) -> None:
        """One lamp for the alternatives at a facing divergence.

        Three roads at Marlowe had three lamps at one place, one per road, and a
        train standing there is looking at one signal post. It is one post on
        the ground too: a home signal reading into any of several roads is one
        post, and WHICH road is set is carried by the second head on that post
        rather than by a lamp per road.

        So one of the group keeps the lamp - the one on the line's own
        alignment, where there is one - and shows the least restrictive aspect
        of the group. That is not a fudge: only one road is ever on offer at a
        time, so at most one of them is off, and the one that is off is the one
        being shown to the driver. (Several may be LOCKED at once - sectional
        release leaves a route locked under a train standing in the platform -
        but a locked route whose train is already on it puts no proceed aspect
        on the post, so the least restrictive is still the one being offered.) :meth:`_refresh_branch_heads` then has the last
        word, because a lamp that is off for a DIVERGING road belongs on the
        second head and this one goes back to red.

        A divergence on a stretch worked both ways is no different: it is a
        divergence in one direction, and the signals for the other direction are
        a group of their own at the other end of the same roads.
        """
        for members in self._junction_groups(infra).values():
            anchor = self._through_signal(infra, members, tracks) or members[0]
            self._lamp_groups[anchor.id] = [signal.id for signal in members]
            self._sharing_lamp.update(
                signal.id for signal in members if signal.id != anchor.id)
        self._merge_co_located(infra, tracks, signal_x)

    def _merge_co_located(self, infra, tracks, signal_x) -> None:
        """One lamp per place, for the signals that converge on one.

        The other half of a throat. Where several roads MEET, each approach gets
        its own signal into the block beyond, and where those roads are distinct
        - three platforms at Marlowe - each of them keeps its own post at the end
        of its own concrete, because a train at platform 3 must not be released
        by platform 1's lamp.

        But two approaches can meet on the same rail at the same point: the up
        line and a crossover joining it are one alignment by the time they reach
        the block boundary. The model makes a signal per approach; the ground has
        one lamp there. So any that come out at the same place become one, and it
        shows the least restrictive of them - only one road is on offer at a
        time, so the one that is off is the one being shown to the driver.

        This is what leaves one lamp per place as an invariant of the drawing,
        which matters more than it sounds: two lamps at one spot showing
        different things is the picture of a failed signal.

        A signal with no approach is in this, and has to be now that it is
        drawn: it holds a place like any other lamp. Which of a merged pair
        anchors it does not matter, because a lamp shows the least restrictive
        of the ones IN FORCE and a signal with no approach is never one of
        them - :meth:`_signals_out_of_use` darkens it, so it can only ever be
        outvoted by the signal it shares the place with.
        """
        places = {}
        for signal in infra.signals.values():
            if signal.id in self._sharing_lamp:
                continue
            key = (round(signal_x.get(signal.id, 0.0), 1),
                   round(self._signal_y(signal), 1))
            places.setdefault(key, []).append(signal)
        for members in places.values():
            if len(members) < 2:
                continue
            anchor = members[0]
            merged = []
            for signal in members:
                merged.extend(self._lamp_groups.pop(signal.id, [signal.id]))
            self._lamp_groups[anchor.id] = merged
            self._sharing_lamp.update(
                signal.id for signal in members if signal.id != anchor.id)
        # Which lamp each signal ended up on. A divergence whose own post was
        # merged into another still has a second head - it is on the lamp that
        # absorbed it.
        for owner, members in self._lamp_groups.items():
            for signal_id in members:
                self._lamp_owner[signal_id] = owner

    # ------------------------------------------------- signalled both ways

    def _two_way_section(self, signal):
        """``(section, way)`` if this signal is on a stretch signalled both ways.

        Both ways are legitimate. A line signalled in both directions IS
        signalled in both directions - which way it is set at any moment is a
        state of the railway, the same kind of fact as which way a point lies,
        and not a degraded mode with a right side and a wrong one. So neither of
        the pair at a boundary is the lesser of the two, and neither should be
        drawn as though it were.
        """
        return self.scenario.infrastructure.direction_sections.get(
            signal.block_id)

    #: How far a lamp stands off the rail, and how far its mast reaches.
    TWO_WAY_MAST = 9

    def _signals_out_of_use(self):
        """The signals nothing can be approaching, because the other direction
        has the rails.

        A stretch worked both ways carries two blocks over one set of rails, one
        each way. While a train is on one of them, or a route is set into it,
        the other is a block nothing can enter - so its signal is a lamp nothing
        can be approaching, and it is drawn DARK.

        Dark is the same word it is on a second head: *not this way*. Nobody has
        to work out which of two lamps applies to them, because only one of them
        is lit.

        Asked of the BLOCK, not of the section. A section here is nineteen
        kilometres; asking it would mean a train being worked the other way past
        Kingsford decided what Marlowe's platforms were for, and that is not
        true - a platform road is available in either direction until something
        is actually on it or booked over it. The station lamps stay lit both
        ways, which is what they are: two directions that both work, waiting to
        see which one is asked for.

        Only a twin counts, never any crossing. A diamond at a flat junction is
        a crossing too, and a train on the other line there does not mean this
        line has changed direction - it means wait, which is what red is for.

        Asked of BOTH of a signal's roads, the one it reads into and the one it
        reads out of. Into is the obvious one: no route can be set over a road
        the other direction is using. Out of is the one that matters at a
        platform, and it was missing. A platform road worked both ways has a
        starting signal at each end, one per direction, and a train standing
        there can only ever be looking at one of them - the other reads out of
        the same rails the opposite way, and the train is sitting on them. Its
        own road is what makes it unapproachable, not the road ahead, so asking
        only about the road ahead left it lit, and lit at danger: a red lamp at
        the far end of an occupied platform, for a train that cannot exist.

        A signal with NO road behind it is dark always. That is the lamp at a
        buffer stop: the depot roads are worked both ways like a platform, but
        one end of them is the end of the railway, and the model still puts a
        signal there reading into the road from beyond the blocks. Nothing is
        beyond the blocks, so nothing can ever approach it. Those are no longer
        drawn at all - a buffer stop is drawn where they were - and this line
        stays as the guard that says what they are worth if they ever are.
        """
        sim = self.sim
        interlocking = sim.interlocking
        if interlocking is None:
            return set()
        infra = self.scenario.infrastructure
        taken = {}

        def opposed(block_id):
            """Is this road's twin taken - a train on it, or a route over it?"""
            if block_id not in taken:
                taken[block_id] = self._twin_is_committed(block_id)
            return taken[block_id]

        dark = set()
        for signal in infra.signals.values():
            if not signal.from_segment:
                dark.add(signal.id)
                continue
            behind = infra.block_of_segment.get(signal.from_segment)
            if opposed(signal.block_id) or (behind and opposed(behind)):
                dark.add(signal.id)
        return dark

    def _twin_is_committed(self, block_id):
        """Is the opposite direction over these rails occupied or booked?

        ``False`` for a road that is not worked both ways, which has no twin to
        be committed, and for one whose twin is free.
        """
        sim = self.sim
        infra = self.scenario.infrastructure
        sections = infra.direction_sections
        here = sections.get(block_id)
        if here is None:
            return False
        section, way = here
        for other in infra.crossings.get(block_id, ()):
            there = sections.get(other)
            if there is None or there[0] != section or there[1] == way:
                continue
            if sim.interlocking.block_is_committed(other, sim):
                return True
        return False

    #: The second head, in pixels: how far its centre stands beyond the main
    #: lamp's, and the radius both are drawn at.
    BRANCH_GAP = 8
    LAMP_RADIUS = 3

    def _junction_groups(self, infra):
        """Signals that are alternatives to one another, keyed by where they are.

        A train standing at one place, having arrived by one road, may be
        signalled into any of several roads ahead - that is a facing divergence,
        and those signals are its alternatives. They share a node and an
        approach and differ only in the road they read into, so that is the key.

        A group of one is not a divergence: there is one way to go, so one head
        says everything there is to say and a second would be dark for ever.
        """
        groups = {}
        for signal in infra.signals.values():
            if not signal.from_segment:
                # No approach, so no train standing on one, so no choice being
                # offered to anybody. Two of these at a depot share a node and a
                # track and an approach of None, which grouped them into a
                # facing divergence and hung a second head off a buffer stop.
                continue
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

    def _draw_branch_heads(self, infra, tracks, signal_x) -> None:
        """A second head on the signals that read over a facing divergence.

        An aspect says how far a train may go. It does not say WHICH way, and
        the schematic could not either: three roads at Marlowe, one green lamp,
        and no way to tell which of them the interlocking had set.

        So a signal with a choice of road ahead gets a second head, on the same
        post, further out from the rail. The INNER head is the line ahead; the
        OUTER head is everything that diverges from it. Which head is lit says
        which road; the aspect on it says how far. That is a two-head signal,
        and it is how a railway that signals routes rather than speeds tells a
        driver the same two things.

        The head that is not being used is dark rather than red. A dark head is
        "not this way", which is a different statement from "this way, and
        stop": a driver reading two reds has to work out which of them applies
        to them, and on a schematic the same two reds are indistinguishable from
        a signal that has failed.

        There is one head per divergence, not one per road. Where three roads
        diverge - Marlowe's platforms 2 and 3 off the through road - the outer
        head says "not the line ahead" and the road that lights up on the
        schematic says which. A second head cannot carry a road number, and
        this one does not pretend to.
        """
        if not self.lineside:
            return
        layout = self.layout
        for key, members in self._junction_groups(infra).items():
            through = self._through_signal(infra, members, tracks)
            anchor = through or members[0]
            carrier = self._lamp_owner.get(anchor.id, anchor.id)
            main = self._signal_items.get(carrier)
            if main is None:
                continue
            anchor = infra.signals[carrier] if carrier != anchor.id else anchor
            x = signal_x.get(anchor.id, layout.x(anchor.km))
            mast, box = self._branch_coords(x, self._signal_y(anchor))

            self._branch_heads[key] = {
                "main": main, "anchor": anchor.id,
                "mast": self.canvas.create_line(
                    *mast, fill=PALETTE["track"], width=1, tags="static"),
                "lamp": self.canvas.create_oval(
                    *box, fill=PALETTE["lamp_dark"], outline="", tags="static"),
                "signals": tuple(signal.id for signal in members),
                "through": through.id if through is not None else None,
            }

    def _branch_coords(self, x, y):
        """Mast extension and lamp box for a second head beyond the main one."""
        inner = y - self.TWO_WAY_MAST
        outer = inner - self.BRANCH_GAP
        r = self.LAMP_RADIUS
        return (x, inner, x, outer), (x - r, outer - r, x + r, outer + r)

    def _refresh_branch_heads(self, dark) -> None:
        """Light the head for the road that is set, and darken the other.

        One rule: the head for the road that is set carries the aspect, and the
        other head is dark. Everything else follows from it, including the case
        that is worth spelling out.

        * Nothing set - inner red, outer dark. The train is being stopped and
          there is no road to talk about yet, so the outer head says nothing.
        * The line ahead - inner shows its aspect, outer dark.
        * A diverging road - inner RED, outer shows the aspect. The inner head
          HAS to be red: the route it stands for is not set, and a proceed
          aspect for a route nobody set is exactly what
          ``clear_without_a_route()`` exists to catch.
        * A diverging road, with the train still stopped - BOTH heads red. The
          route is set, so the outer head is the one that applies and it is lit;
          the aspect on it is red because the road beyond is not free yet. That
          is a real and useful thing to be able to see: "you are going that way,
          and you are not going yet" is not the same picture as "you are stopped
          and nobody has decided". Measured on twoway: 4314 ticks of it, against
          114003 of inner-red-outer-dark.

        Nothing here special-cases that fourth state. It falls out of the rule.

        What the rule needs is the right reading of "set". A route stays locked
        until its train has cleared the block, so a train standing in platform 1
        still holds the route that put it there, while the road behind it is
        free and the next train is being signalled into platform 2. Asking
        merely whether a route was locked found the first one and answered for a
        train that was already there: on capacity at 150 s headway, 16363 of the
        32763 post-ticks with a route locked stood for a route somebody had
        already taken, and in 4201 of those a DIFFERENT road was on offer at the
        same post at the same moment. That is a post reading double red at a
        train it has just cleared into the other platform - which is exactly
        what it looked like from outside. :meth:`Interlocking.route_offered_from`
        asks the question the post is actually asking, and only one road is ever
        on offer at once.
        """
        sim = self.sim
        interlocking = sim.interlocking
        canvas = self.canvas
        for entry in self._branch_heads.values():
            set_from = None
            if interlocking is not None:
                for signal_id in entry["signals"]:
                    # Offered, not merely locked. A route the train has already
                    # taken keeps its lock while that train stands in the
                    # platform, and standing for it here made the post answer
                    # for a train that had gone by.
                    if interlocking.route_offered_from(signal_id):
                        set_from = signal_id
                        break

            if all(sid in dark for sid in entry["signals"]):
                # This divergence is for the direction not in force. The second
                # head goes out, whatever the post's inner head is doing - the
                # same lamp may be standing for a signal the other way, and that
                # one has no branch to talk about.
                canvas.itemconfig(entry["lamp"], fill=PALETTE["lamp_dark"])
                continue

            diverging = set_from is not None and set_from != entry["through"]
            if diverging:
                inner = ASPECT_COLOURS["red"]
                outer = ASPECT_COLOURS.get(
                    sim.aspects.get(set_from, "red"), ASPECT_COLOURS["red"])
            else:
                inner = None            # left as the main refresh drew it
                outer = PALETTE["lamp_dark"]
            if inner is not None:
                canvas.itemconfig(entry["main"], fill=inner)
            canvas.itemconfig(entry["lamp"], fill=outer)

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
        for block_id, items in self._block_items.items():
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
            for item in items:
                self.canvas.itemconfig(item, fill=colour)

        dark = self._signals_out_of_use()
        for signal_id, item in self._signal_items.items():
            # A lamp can stand for several signals - the roads at a facing
            # divergence, the approaches that meet at one point, and where a
            # stretch is worked both ways the two directions' signals at the
            # same spot. It is dark only when every one of them is, and
            # otherwise shows the least restrictive of the ones in force: at
            # most one route can be set, so the one that is off is the one
            # being spoken to.
            members = self._lamp_groups.get(signal_id, (signal_id,))
            in_force = [sid for sid in members if sid not in dark]
            if not in_force:
                self.canvas.itemconfig(item, fill=PALETTE["lamp_dark"])
                continue
            aspect = Aspect.least_restrictive(
                [sim.aspects.get(sid, Aspect.RED) for sid in in_force])
            self.canvas.itemconfig(
                item, fill=ASPECT_COLOURS.get(aspect, ASPECT_COLOURS["red"]))

        self._refresh_branch_heads(dark)

        self._draw_trains()

    #: Shortest a train may be drawn. Below this it is a smear rather than a
    #: shape, and which end is its nose stops being readable.
    #:
    #: Three, not twelve. This is a *pixel* floor applied at whatever the local
    #: scale happens to be, so its cost in metres is worst exactly where the
    #: pixels are thinnest - open line, which gives up its share to
    #: STATION_STRETCH. At twelve it drew a 160 m train as 807 m of open line
    #: and swallowed the gaps between trains whole, which is what made virtually
    #: coupled trains appear to run through each other. At three the same train
    #: is drawn about 200 m long and two trains 33 m apart no longer merge.
    MIN_TRAIN_PX = 3

    def _draw_trains(self) -> None:
        tracks = self.scenario.infrastructure.tracks
        live = set()

        for train in self.sim.trains.values():
            if not train.is_active:
                continue
            live.add(train.id)
            segment = train.path.entry_at(train.chainage_m).segment
            points, nose = self._train_points(train)

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
            direction = tracks.get(segment.track, {}).get("direction", "up")
            if train.state == "dwelling":
                colour = PALETTE["train_dwelling"]
            else:
                colour = PALETTE["train_up"] if direction == "up" else PALETTE["train_down"]

            self._draw_zone(train)
            self._draw_authority(train)

            items = self._train_items.get(train.id)
            if items is None:
                # Two lines rather than a rectangle: a rectangle cannot follow a
                # curve, and on the horseshoe the train was drawn as a level bar
                # across the middle of it, off the rails entirely. The lower,
                # wider line in the background colour is what the rectangle's
                # outline used to be - it keeps the train from merging into the
                # road it is standing on.
                halo = self.canvas.create_line(
                    0, 0, 0, 0, fill=PALETTE["train_outline"],
                    width=10, capstyle=tk.BUTT,
                )
                body = self.canvas.create_line(
                    0, 0, 0, 0, fill=colour, width=8, capstyle=tk.BUTT,
                )
                label = self.canvas.create_text(
                    0, 0, text=train.id, fill=PALETTE["label_bright"],
                    font=self.mono_small,
                )
                items = (halo, body, label)
                self._train_items[train.id] = items
            halo, body, label = items
            self.canvas.coords(halo, *points)
            self.canvas.coords(body, *points)
            self.canvas.itemconfig(body, fill=colour)
            self.canvas.coords(label, nose[0], nose[1] - 14)
            self.canvas.tag_raise(halo)
            self.canvas.tag_raise(body)
            self.canvas.tag_raise(label)

        for train_id in [t for t in self._train_items if t not in live]:
            for item in self._train_items.pop(train_id):
                self.canvas.delete(item)
        for train_id in [t for t in self._zone_items if t not in live]:
            self.canvas.delete(self._zone_items.pop(train_id))
        for train_id in [t for t in self._authority_items if t not in live]:
            self.canvas.delete(self._authority_items.pop(train_id))

    #: How far back along the rails a heading is taken from when a train is too
    #: short to draw. Far enough that the two samples are not the same point at
    #: any zoom, short enough to be the direction the nose is actually going.
    MIN_TRAIN_M = 20.0

    @staticmethod
    def _polyline_length(points) -> float:
        total = 0.0
        for i in range(0, len(points) - 3, 2):
            total += math.hypot(points[i + 2] - points[i],
                                points[i + 3] - points[i + 1])
        return total

    def _train_points(self, train):
        """The line a train is drawn as, rear to nose, and where its nose is.

        A train is drawn from its rear to its nose, and where that is too few
        pixels to see it is padded BACKWARDS from the nose. Padding around the
        centre - which this used to do - draws the nose ahead of where the train
        actually is, and by a long way: sixty kilometres across a window is
        about 24 m to the pixel, so a 160 m train is three pixels on open line
        and was being inflated to twelve about its midpoint. The drawn nose then
        stood 240 m past the real one, over-running the signal the train was
        actually standing at, and every train looked as though its middle was
        the thing being positioned. The kernel never thought so - chainage_m is
        the front and always was - so this was the picture lying about the model,
        which is the worst way round.
        """
        path = train.path
        nose = self._path_xy(path, train.chainage_m)
        points = self._path_polyline(path, max(0.0, train.rear_m),
                                     train.chainage_m)
        if self._polyline_length(points) >= self.MIN_TRAIN_PX:
            return points, nose
        behind = self._path_xy(
            path, max(0.0, train.chainage_m - self.MIN_TRAIN_M))
        dx, dy = nose[0] - behind[0], nose[1] - behind[1]
        span = math.hypot(dx, dy)
        if span < 1e-6:
            segment = path.entry_at(train.chainage_m).segment
            dx, dy, span = (1.0 if segment.km_end >= segment.km_start
                            else -1.0), 0.0, 1.0
        scale = self.MIN_TRAIN_PX / span
        return ([nose[0] - dx * scale, nose[1] - dy * scale, nose[0], nose[1]],
                nose)

    #: Half-height of the limit tick, in pixels. Taller than the train body
    #: (4) and than the braking zone (6) on purpose: the three marks belong to
    #: one train and stack into a picture, and the outermost of them is the one
    #: that is a limit rather than a thing occupying the railway.
    AUTHORITY_TICK = 9

    def _draw_authority(self, train) -> None:
        """Where this train's movement authority runs out.

        A tick was tried here before and taken out, for two reasons. One was
        real and is fixed in the kernel: the mark was built by adding a
        distance-from-the-nose to the nose AFTER the train had moved, so it
        stood a tick's travel too far along the line and could be drawn past
        the very signal that had stopped the train. It is now taken from
        ``authority_point_m``, which is fixed to the path before the move.

        The other reason was that the route colour said it already. It does not,
        and the difference is the point. The teal is the INTERLOCKING's: which
        blocks are locked, a whole block at a time, a fact about the railway
        rather than about any one train. The tick is the train's: how far THIS
        train has been told it may run. They are only the same number when the
        lock is what is holding the train.

        Measured over the capacity flight, 28320 authorities per system: under
        fixed block the tick lands SHORT of the far edge of the teal 20388
        times, 72 per cent. The interlocking has locked to the end of the route
        and the aspects only let the train to the next red, and the colour has
        no way to say so - it is the same teal either side of the point the
        train must stop at. Under moving block they agree 94 per cent of the
        time, which is most of what moving block is for. Neither figure is
        visible without both marks.

        The braking envelope is not this fact either: it is how much railway the
        train NEEDS to stop in, and this is how much it HAS. A tick inside its
        own envelope is a train that cannot stop in what it has been given.

        So all three are drawn and each has a key.
        """
        tick = self._authority_items.get(train.id)
        if tick is None:
            tick = self.canvas.create_line(
                0, 0, 0, 0, fill=PALETTE["authority_limit"], width=2)
            self._authority_items[train.id] = tick

        end = train.authority_point_m
        if not self.show_authority or end is None:
            self.canvas.itemconfigure(tick, state="hidden")
            return
        # An authority that ends at the nose is a train standing at a red, and
        # the signal is already saying so. Drawing a tick through the train as
        # well only puts a line across the thing it is about.
        if end - train.chainage_m < 1.0:
            self.canvas.itemconfigure(tick, state="hidden")
            return
        x, tick_y = self._path_xy(train.path, min(train.path.total_m, end))
        half = self.AUTHORITY_TICK
        self.canvas.coords(tick, x, tick_y - half, x, tick_y + half)
        self.canvas.itemconfigure(tick, state="normal")
        self.canvas.tag_raise(tick)

    def _draw_zone(self, train) -> None:
        """The braking envelope: how much railway this train needs to stop in.

        This is what a moving block actually is: not a fixed length of track that
        lights up, but the distance this train needs to stop, travelling with it
        and shrinking as it slows. Drawn for every signalling system, because
        seeing it sit inside a whole lit block is the clearest picture of what
        fixed block wastes.

        Half of a pair. This is how much railway the train NEEDS;
        :meth:`_draw_authority` draws how much it HAS. Neither says the other,
        and the gap between them is the margin the train is running on.
        """
        zone = self._zone_items.get(train.id)
        if zone is None:
            zone = self.canvas.create_line(
                0, 0, 0, 0, fill=PALETTE["braking_zone"], width=12,
                stipple="gray25", capstyle=tk.BUTT,
            )
            self._zone_items[train.id] = zone

        if not self.show_zones or train.speed_ms <= 0.3:
            self.canvas.itemconfigure(zone, state="hidden")
            return
        needed = train.stopping_distance_m(self.reaction_s)
        end = min(train.path.total_m, train.chainage_m + needed)
        self.canvas.coords(
            zone, *self._path_polyline(train.path, train.chainage_m, end))
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
