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
                self._draw_platform_face(segment)
                mid_km = (segment.km_start + segment.km_end) / 2.0
                # Below the line: train labels sit above it, so they never collide.
                canvas.create_text(
                    layout.x(mid_km),
                    layout.y(segment.y) + (self.PLATFORM_FACE_DROP
                                           + self.PLATFORM_FACE_DEPTH
                                           + self.PLATFORM_LABEL_GAP)
                    * self._vscale,
                    text=segment.platform, fill=PALETTE["label"],
                    font=self.mono_small, tags="static",
                )

        for signal in infra.signals.values():
            self._draw_signal(signal, tracks)

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
    #: Depth of the platform slab drawn against the road, and its drop below it.
    PLATFORM_FACE_DEPTH = 7
    PLATFORM_FACE_DROP = 9
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

    def _draw_platform_face(self, segment) -> None:
        """The platform itself - the concrete, not the road it runs beside.

        Worth drawing separately because the two are wildly different lengths and
        the difference is the thing people get wrong. The road is a block section
        sized for braking through at line speed - 1200 m on depotline - while the
        platform is sized for the train that stands at it, 220 m. Drawing only the
        road makes every station look like a kilometre of concrete.

        It is laid against the stopping point, ending where the train's front
        comes to rest, because that is where a platform actually is relative to
        where a driver stops.
        """
        platform = self.scenario.infrastructure.network.platforms.get(segment.platform)
        if platform is None or platform.length_m <= 0:
            return
        layout = self.layout
        road_m = abs(segment.km_end - segment.km_start) * 1000.0
        if road_m <= 0:
            return
        # Where the front of a berthed train stands, as a fraction along the road,
        # and the platform reaching back from it. Clamped because a platform
        # longer than its own road would otherwise be drawn off the end of it.
        stop_frac = max(0.0, min(1.0, platform.stop_offset_m / road_m))
        back_frac = max(0.0, stop_frac - platform.length_m / road_m)
        km_a = segment.km_start + (segment.km_end - segment.km_start) * back_frac
        km_b = segment.km_start + (segment.km_end - segment.km_start) * stop_frac
        x0, x1 = sorted((layout.x(km_a), layout.x(km_b)))
        # A 220 m platform on a 60 km line is a couple of pixels, so give it a
        # floor: the point is to show where it is, not to survive a measurement.
        if x1 - x0 < 3.0:
            x1 = x0 + 3.0
        scale = self._vscale
        y = layout.y(segment.y) + self.PLATFORM_FACE_DROP * scale
        self.canvas.create_rectangle(
            x0, y, x1, y + self.PLATFORM_FACE_DEPTH * scale,
            fill=PALETTE["platform_face"], width=0, tags="static",
        )

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
        taper = (x1 - x0) * 0.18
        return (x0, y_track, x0 + taper, y_seg, x1 - taper, y_seg, x1, y_track)

    def _draw_signal(self, signal, tracks) -> None:
        """A signal lamp, or an unlit marker board where the level has no signals.

        ETCS Level 2 and above put the authority in the cab and leave nothing lit
        at the lineside, so drawing green lamps under those levels would be a
        picture of a railway that does not exist. Marker boards are drawn instead:
        the block boundaries are still there, they just no longer tell anyone
        anything.
        """
        layout = self.layout
        x = layout.x(signal.km)
        y = layout.y(signal.y)
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
        lamp = self.canvas.create_oval(
            x - 3, y + mast - 3, x + 3, y + mast + 3,
            fill=PALETTE["green"], outline="", tags="static",
        )
        self._signal_items[signal.id] = lamp

    def _draw_point(self, point) -> None:
        """A point: a diamond at its node, coloured by lock and position.

        Facing points sit below the line, trailing points above, so which kind is
        which is readable without a label.
        """
        layout = self.layout
        x = layout.x(point.km)
        y = layout.y(point.y) + (11 if point.kind == "facing" else -11)
        size = 4
        item = self.canvas.create_polygon(
            x, y - size, x + size, y, x, y + size, x - size, y,
            fill=PALETTE["point_free"], outline="", tags="static",
        )
        self._point_items[point.id] = item

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
                colour = PALETTE["platform_occupied"] if platform else PALETTE["track_occupied"]
            elif occupied and platform:
                # Under distance separation a block is not the unit of safety, so
                # lighting the whole thing up would misrepresent the system. A
                # platform road is still worth showing as taken.
                colour = PALETTE["platform_occupied"]
            elif block_id in route_held:
                # Locked by a route but nothing on it yet: the road is reserved.
                colour = PALETTE["route_set"]
            else:
                colour = PALETTE["platform"] if platform else PALETTE["track"]
            self.canvas.itemconfig(item, fill=colour)

        if sim.interlocking is not None:
            state = sim.interlocking.point_state()
            for point_id, item in self._point_items.items():
                info = state.get(point_id, {})
                if info.get("locked_by"):
                    colour = PALETTE["point_locked"]
                elif info.get("reverse"):
                    colour = PALETTE["point_reverse"]
                else:
                    colour = PALETTE["point_free"]
                self.canvas.itemconfig(item, fill=colour)

        for signal_id, item in self._signal_items.items():
            aspect = sim.aspects.get(signal_id, "green")
            self.canvas.itemconfig(item, fill=ASPECT_COLOURS.get(aspect, PALETTE["green"]))

        self._draw_trains()

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

            x_front, x_rear = layout.x(front_km), layout.x(rear_km)
            if x_front < x_rear:
                x_front, x_rear = x_rear, x_front
            if x_front - x_rear < 12:
                centre = (x_front + x_rear) / 2.0
                x_rear, x_front = centre - 6, centre + 6

            segment = train.path.entry_at(train.chainage_m).segment
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
            for item in self._zone_items.pop(train_id):
                self.canvas.delete(item)

    def _draw_zone(self, train, y) -> None:
        """The braking envelope, and a tick where the authority runs out.

        This is what a moving block actually is: not a fixed length of track that
        lights up, but the distance this train needs to stop, travelling with it
        and shrinking as it slows. Drawn for every signalling system, because
        seeing it sit inside a whole lit block is the clearest picture of what
        fixed block wastes.
        """
        layout = self.layout
        items = self._zone_items.get(train.id)
        if items is None:
            zone = self.canvas.create_rectangle(
                0, 0, 0, 0, fill=PALETTE["braking_zone"], outline="",
                stipple="gray25",
            )
            tick = self.canvas.create_line(
                0, 0, 0, 0, fill=PALETTE["authority_end"], width=2,
            )
            items = (zone, tick)
            self._zone_items[train.id] = items
        zone, tick = items

        if not self.show_zones or train.speed_ms <= 0.3:
            self.canvas.itemconfigure(zone, state="hidden")
        else:
            needed = train.stopping_distance_m(self.reaction_s)
            end = min(train.path.total_m, train.chainage_m + needed)
            x_a = layout.x(train.km)
            x_b = layout.x(train.path.km_at(end))
            left, right = min(x_a, x_b), max(x_a, x_b)
            self.canvas.coords(zone, left, y - 6, right, y + 6)
            self.canvas.itemconfigure(zone, state="normal")

        if not self.show_zones or train.last_authority_m is None:
            self.canvas.itemconfigure(tick, state="hidden")
        else:
            end = min(train.path.total_m, train.chainage_m + train.last_authority_m)
            x = layout.x(train.path.km_at(end))
            self.canvas.coords(tick, x, y - 10, x, y + 10)
            self.canvas.itemconfigure(tick, state="normal")

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
