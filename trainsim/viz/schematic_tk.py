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
        self._block_items = {}
        self._signal_items = {}
        self._branch_heads = {}
        self._lamp_groups = {}
        self._sharing_lamp = set()
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
        self._branch_heads.clear()
        self._lamp_groups.clear()
        self._sharing_lamp.clear()
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
        self._plan_shared_lamps(infra, tracks, signal_x)
        for signal in infra.signals.values():
            self._draw_signal(signal, tracks, signal_x)

        self._draw_branch_heads(infra, tracks, signal_x)

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
        track = tracks.get(signal.track, {})
        # Down-line signals sit below their track, up-line above, so a signal is
        # visually on the side its trains are approaching from.
        up = track.get("direction", "up") == "up"
        mast = -9 if up else 9

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
        of the group. That is not a fudge: only one route can be set at a time,
        so at most one of them is off, and the one that is off is the one being
        shown to the driver. :meth:`_refresh_branch_heads` then has the last
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
        shows the least restrictive of them - only one route can be set at a
        time, so the one that is off is the one being shown to the driver.

        This is what leaves one lamp per place as an invariant of the drawing,
        which matters more than it sounds: two lamps at one spot showing
        different things is the picture of a failed signal.
        """
        places = {}
        for signal in infra.signals.values():
            if signal.id in self._sharing_lamp:
                continue
            up = tracks.get(signal.track, {}).get("direction", "up") == "up"
            key = (round(signal_x.get(signal.id, 0.0), 1),
                   round(self._signal_y(signal), 1), up)
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
        """The signals for the direction a two-way stretch is NOT being worked.

        A stretch worked in both directions is worked one direction at a time,
        so at any moment half the lamps on it are lamps nothing can be
        approaching. They are drawn - a signal that exists is on the ground
        whether or not it is in use, and hiding it hides the layout - but they
        are drawn DARK.

        Dark is the same word it is on a second head: not this way. A driver
        does not have to work out which of two lamps at a boundary applies to
        them, because only one of them is lit; and the stretch's direction is
        readable at a glance, from which line's signals are alight.

        A section nobody is using rests in its normal direction. It is
        available to either, and lighting neither would say the railway had
        stopped rather than that nothing is on it.
        """
        sim = self.sim
        interlocking = sim.interlocking
        infra = self.scenario.infrastructure
        in_force = {}
        dark = set()
        for signal in infra.signals.values():
            here = self._two_way_section(signal)
            if here is None:
                continue
            section, way = here
            if section not in in_force:
                working = None
                if interlocking is not None:
                    working = interlocking.section_direction(section, sim)
                in_force[section] = working or "normal"
            if way != in_force[section]:
                dark.add(signal.id)
        return dark

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
            main = self._signal_items.get(anchor.id)
            if main is None:
                continue
            x = signal_x.get(anchor.id, layout.x(anchor.km))
            y = self._signal_y(anchor)
            up = tracks.get(anchor.track, {}).get("direction", "up") == "up"
            mast, box = self._branch_coords(x, y, up)

            self._branch_heads[key] = {
                "main": main, "anchor": anchor.id,
                "mast": self.canvas.create_line(
                    *mast, fill=PALETTE["track"], width=1, tags="static"),
                "lamp": self.canvas.create_oval(
                    *box, fill=PALETTE["lamp_dark"], outline="", tags="static"),
                "signals": tuple(signal.id for signal in members),
                "through": through.id if through is not None else None,
            }

    def _branch_coords(self, x, y, up):
        """Mast extension and lamp box for a second head beyond the main one."""
        side = -1 if up else 1
        inner = y + side * self.TWO_WAY_MAST
        outer = inner + side * self.BRANCH_GAP
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
        """
        sim = self.sim
        interlocking = sim.interlocking
        canvas = self.canvas
        for entry in self._branch_heads.values():
            set_from = None
            if interlocking is not None:
                for signal_id in entry["signals"]:
                    if interlocking.route_set_from(signal_id):
                        set_from = signal_id
                        break

            if entry["anchor"] in dark:
                # The whole post is for the direction not in force. Both heads
                # go out with it - a second head on a dark signal would be the
                # one lamp lit at a boundary nothing can be approaching.
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

        dark = self._signals_out_of_use()
        for signal_id, item in self._signal_items.items():
            if signal_id in dark:
                self.canvas.itemconfig(item, fill=PALETTE["lamp_dark"])
                continue
            shared = self._lamp_groups.get(signal_id)
            if shared is None:
                aspect = sim.aspects.get(signal_id, "red")
            else:
                # One post reading into several roads: it shows the aspect of
                # whichever route is set, and only one of them can be.
                aspect = Aspect.least_restrictive(
                    [sim.aspects.get(sid, Aspect.RED) for sid in shared])
            self.canvas.itemconfig(
                item, fill=ASPECT_COLOURS.get(aspect, ASPECT_COLOURS["red"]))

        self._refresh_branch_heads(dark)

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
