"""Shared test fixtures: a minimal railway built in code, not from files.

Tests that exercise the physics and the signalling want a layout small enough to
reason about by hand. ``build_test_railway`` gives a two-station single-track line
whose geometry is known exactly, so an assertion can name the metre a train
should stop on.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trainsim.core.dispatcher import Dispatcher, TimetableDispatcher  # noqa: E402
from trainsim.core.driver import Driver, DriverConfig  # noqa: E402
from trainsim.core.simulation import SimConfig, Simulation  # noqa: E402
from trainsim.core.signalling import ThreeAspectFixedBlock  # noqa: E402
from trainsim.scenario.builder import build_infrastructure  # noqa: E402
from trainsim.scenario.loader import build_timetable  # noqa: E402

SCENARIOS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenarios"
)
CORRIDOR3 = os.path.join(SCENARIOS, "corridor3")
INTENSIVE = os.path.join(SCENARIOS, "corridor3", "scenario-intensive.yaml")
METRO = os.path.join(SCENARIOS, "metro")
METRO_60 = os.path.join(SCENARIOS, "metro", "scenario-60.yaml")
METRO_MIXED = os.path.join(SCENARIOS, "metro", "scenario-mixed.yaml")
METRO_DISRUPTED = os.path.join(SCENARIOS, "metro", "scenario-disrupted.yaml")
CORRIDOR3_DISRUPTED = os.path.join(SCENARIOS, "corridor3",
                                   "scenario-disrupted.yaml")
JUNCTION = os.path.join(SCENARIOS, "junction")
FOURTRACK = os.path.join(SCENARIOS, "fourtrack")
JUNCTION_FLAT = os.path.join(SCENARIOS, "junction", "scenario-flat.yaml")
JUNCTION_FLYOVER = os.path.join(SCENARIOS, "junction",
                                "scenario-flyover.yaml")


#: Two stations 10 km apart on one track. With a 400 m platform zone at each end
#: the open line is 9200 m, divided into 5 blocks of 1840 m.
TEST_INFRA = {
    "name": "testline",
    "defaults": {"platform_zone_m": 400, "stop_margin_m": 40},
    "stations": [
        {"id": "A", "name": "Ayton", "km": 0.0},
        {"id": "B", "name": "Beeton", "km": 10.0},
    ],
    "tracks": [
        {"id": "T", "direction": "up", "y": 0.0, "max_speed_kmh": 140,
         "block_length_m": 2000, "serves": ["A", "B"]},
    ],
    "platforms": [
        {"id": "A_1", "station": "A", "track": "T", "length_m": 200},
        {"id": "B_1", "station": "B", "track": "T", "length_m": 200},
    ],
}

def stock(stock_id="UNIT", etcs_level="l2", tims=True, **overrides):
    """A rolling stock definition, with fitment easy to vary."""
    spec = {
        "id": stock_id,
        "name": "Test unit %s" % stock_id,
        "length_m": 200,
        "max_speed_kmh": 140,
        "max_accel": 0.9,
        "service_brake": 0.7,
        "emergency_brake": 1.2,
        "etcs_level": etcs_level,
        "tims": tims,
    }
    spec.update(overrides)
    return spec


TEST_STOCK = [stock()]


def one_service_timetable(departure="08:00:00"):
    return {
        "stock": TEST_STOCK,
        "services": [{
            "id": "T1",
            "name": "test service",
            "stock": "UNIT",
            "departure": departure,
            "calls": [
                {"station": "A", "platform": "A_1", "departure": departure,
                 "dwell_s": 0},
                {"station": "B", "platform": "B_1", "dwell_s": 30},
            ],
        }],
    }


class ManualDispatcher(Dispatcher):
    """Does nothing, so a test can place trains itself and control the scene."""

    name = "manual"
    pending_count = 0

    def step(self, sim):
        pass


def sloped_infra(grade_permille):
    """The test line, laid on a constant gradient from A to B.

    Positive is a climb in the direction the single track runs, so a train from
    A to B is working uphill and one on a negative gradient is running down.
    """
    spec = copy.deepcopy(TEST_INFRA)
    spec["tracks"][0]["gradients"] = [
        {"from": "A", "to": "B", "grade_permille": grade_permille},
    ]
    return spec


def build_test_sim(timetable_spec=None, dispatcher=None, duration_s=1800.0,
                   start_time_s=8 * 3600.0, driver_config=None, strict=True,
                   signalling=None, interlocking=False, disruptions=None,
                   infra_spec=None):
    """A simulation over the two-station test line."""
    infra = build_infrastructure(infra_spec or TEST_INFRA)
    timetable = build_timetable(timetable_spec or one_service_timetable(), infra)
    lock = None
    if interlocking:
        from trainsim.core.interlocking import Interlocking
        lock = Interlocking(infra.network, infra.blocks, infra.signals,
                            infra.points, infra.routes)
    sim = Simulation(
        interlocking=lock,
        disruptions=disruptions,
        network=infra.network,
        blocks=infra.blocks,
        signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=signalling or ThreeAspectFixedBlock(sighting_distance_m=250.0),
        dispatcher=dispatcher or TimetableDispatcher(timetable),
        driver=Driver(driver_config or DriverConfig()),
        config=SimConfig(dt=1.0, start_time_s=start_time_s,
                         duration_s=duration_s, strict=strict),
    )
    return sim, infra, timetable


def running_blocks(infra, track="T"):
    """Block sections on the open line, in order of chainage."""
    blocks = [b for b in infra.blocks.values()
              if b.track == track and b.platform is None]
    return sorted(blocks, key=lambda b: b.km_start)


def block_start_on_path(path, block_id):
    """Chainage at which ``block_id`` begins along ``path``."""
    for candidate, start_m, _ in path.block_ranges:
        if candidate == block_id:
            return start_m
    raise AssertionError("block %s is not on this path" % (block_id,))
