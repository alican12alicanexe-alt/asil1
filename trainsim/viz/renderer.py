"""The view contract, and the palette shared by every backend.

The seam between the simulator and its display sits at the *view* level, not at
individual drawing primitives. A backend owns its window, its event loop and its
painting; all it must promise is:

* ``run()`` - open, animate until the user closes it, return
* never mutate the simulation except by calling :meth:`Simulation.step`

tkinter is the default backend because it is in the standard library and so runs
on a machine where nothing can be installed. A pygame backend would implement the
same contract and be selected the same way.
"""


class SchematicView(object):
    """Base class for schematic views."""

    def __init__(self, scenario, sim, speed: float = 30.0):
        self.scenario = scenario
        self.sim = sim
        #: Simulated seconds per real second.
        self.speed = max(1.0, float(speed))
        self.paused = False

    def run(self) -> None:
        raise NotImplementedError


#: Control-room palette: dark ground, so signal aspects read as the brightest
#: thing on screen, which is what the eye should be drawn to.
PALETTE = {
    "background": "#0e1218",
    "panel": "#151b24",
    "grid": "#232c38",
    "track": "#4a5666",
    "track_occupied": "#8c3a3a",
    "platform": "#7d8b9e",
    "platform_occupied": "#a8574a",
    #: The concrete a train stands alongside, as opposed to the road it stands
    #: on. Drawn as a band centred in the platform road and BEHIND it, a little
    #: wider, so the road's own colour still runs over the top and only a fringe
    #: of platform shows either side - enough to tell the two lengths apart, the
    #: block section and the platform itself, without hiding the occupation and
    #: route the road line carries. Purple because at that width the colour is
    #: the whole signal, and it has to be a hue nothing else on the track uses:
    #: aspects own red, yellow and green, occupation and route own the reds and
    #: teals.
    "platform_face": "#c9b6f0",
    "station": "#cfd8e3",
    "station_tick": "#38424f",
    "label": "#8d9aab",
    "label_bright": "#e6edf5",
    "red": "#ff4d4d",
    "yellow": "#ffc233",
    "green": "#3ad07f",
    "train_up": "#4da3ff",
    "train_down": "#ff9d4d",
    "train_dwelling": "#a98fe0",
    "train_outline": "#0e1218",
    "warning": "#ff6b6b",
    # Moving block: the space a train needs to stop, drawn as a zone that
    # travels with it instead of a block that lights up. It is the only mark a
    # train carries about its own authority - a second one, a tick at the end of
    # the authority itself, said the same thing a tick later and is gone.
    "braking_zone": "#b8433a",
    "marker_board": "#5a6472",
    # Interlocking
    "route_set": "#5ad2c8",       # a route locked but not yet occupied
    # A point's colour is its lock, and only its lock. Where it is actually set
    # is carried by the shape of the diamond, because the two facts coincide -
    # a point is locked exactly when a route is set over it - and a single
    # colour asked to say both ends up hiding one of them.
    "point_free": "#6b788a",
    "point_locked": "#5ad2c8",
    # A route indicator: the mark beside a signal that says WHICH road the route
    # is set for - a theatre box with the platform number at a station, a
    # feather at a junction. A feather is unlit for the line ahead and lit for
    # the connection off it, which is how a driver reads a real one: the
    # indication is the exception, not the rule.
    "route_indicator_dark": "#3a434f",
    "route_indicator_lit": "#e8eef6",
}

ASPECT_COLOURS = {
    "red": PALETTE["red"],
    "yellow": PALETTE["yellow"],
    "green": PALETTE["green"],
}
