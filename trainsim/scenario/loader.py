"""Read scenario files and assemble a ready-to-run simulation.

A scenario is a directory holding three files:

``scenario.yaml``
    Which infrastructure and timetable to use, plus simulation, signalling and
    driver settings.
``infrastructure.yaml``
    Stations, tracks and platforms - expanded into segments, blocks and signals
    by :mod:`trainsim.scenario.builder`.
``timetable.yaml``
    Rolling stock types and the services that run.

Files may equally be ``.json``; the loader accepts either and falls back to the
other extension if the named one is missing, so a scenario can be shipped in
whichever form the machine can read.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core import signalling as signalling_registry
from ..core.disruption import Disruptions, DisruptionError, build_disruptions
from ..core.dispatcher import TimetableDispatcher
from ..core.interlocking import Interlocking
from ..core.driver import Driver, DriverConfig
from ..core.network import Network
from ..core.simulation import SimConfig, Simulation
from ..core.timetable import Service, Timetable
from ..core.train import Path, RollingStock, Stop
from ..core.units import kmh_to_ms, parse_clock
from . import minyaml, schema
from .builder import Infrastructure, InfrastructureError, build_infrastructure

try:  # PyYAML is authoritative when present, but is not required.
    import yaml as _pyyaml
except ImportError:  # pragma: no cover - depends on the machine
    _pyyaml = None


class ScenarioError(ValueError):
    """Raised when a scenario cannot be read or is internally inconsistent."""


def _check(where: str, mapping, allowed) -> None:
    schema.check_keys(where, mapping, allowed, error=ScenarioError)


@dataclass
class Scenario:
    """A loaded, validated scenario."""

    name: str
    description: str
    directory: str
    infrastructure: Infrastructure
    timetable: Timetable
    sim_config: SimConfig
    signalling_spec: Dict[str, Any] = field(default_factory=dict)
    interlocking_spec: Dict[str, Any] = field(default_factory=dict)
    driver_config: DriverConfig = field(default_factory=DriverConfig)
    #: What has been declared to go wrong on this run; empty unless the scenario
    #: has a ``disruptions:`` block.
    disruptions: Disruptions = field(default_factory=Disruptions)
    view: Dict[str, Any] = field(default_factory=dict)
    #: The scenario file actually loaded. A directory may hold several - the
    #: default and a variant - so anything that reloads must reload *this* one.
    source: str = ""

    @property
    def network(self) -> Network:
        return self.infrastructure.network


# --------------------------------------------------------------------- file I/O

def read_data_file(path: str) -> Any:
    """Read a ``.yaml``/``.yml``/``.json`` file into Python data.

    If the requested file is missing, the sibling with the other extension is
    used, which is what lets a scenario ship as JSON on a machine without PyYAML
    and as YAML everywhere else.
    """
    resolved = _resolve(path)
    with open(resolved, "r", encoding="utf-8") as handle:
        text = handle.read()

    if resolved.lower().endswith(".json"):
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ScenarioError("%s: invalid JSON - %s" % (resolved, exc))

    if _pyyaml is not None:
        try:
            return _pyyaml.safe_load(text)
        except Exception as exc:  # pyyaml raises its own error types
            raise ScenarioError("%s: invalid YAML - %s" % (resolved, exc))
    try:
        return minyaml.parse(text)
    except minyaml.MiniYamlError as exc:
        raise ScenarioError(
            "%s: %s (parsed with the built-in YAML subset because PyYAML is not "
            "installed; see trainsim/scenario/minyaml.py for what is supported)"
            % (resolved, exc)
        )


def _resolve(path: str) -> str:
    if os.path.exists(path):
        return path
    stem, extension = os.path.splitext(path)
    alternatives = {".yaml": [".yml", ".json"], ".yml": [".yaml", ".json"],
                    ".json": [".yaml", ".yml"]}.get(extension.lower(), [])
    for alternative in alternatives:
        candidate = stem + alternative
        if os.path.exists(candidate):
            return candidate
    raise ScenarioError("no such scenario file: %s" % (path,))


# ---------------------------------------------------------------------- loading

def load_scenario(path: str) -> Scenario:
    """Load a scenario from a directory or from a ``scenario.yaml`` file."""
    if os.path.isdir(path):
        directory = path
        scenario_file = _resolve(os.path.join(path, "scenario.yaml"))
    else:
        scenario_file = _resolve(path)
        directory = os.path.dirname(os.path.abspath(scenario_file))

    spec = read_data_file(scenario_file)
    if not isinstance(spec, dict):
        raise ScenarioError("%s: expected a mapping at the top level" % scenario_file)
    _check(scenario_file, spec, schema.SCENARIO)
    for section, allowed in (("simulation", schema.SIMULATION),
                             ("driver", schema.DRIVER),
                             ("view", schema.VIEW),
                             ("interlocking", schema.INTERLOCKING)):
        if spec.get(section) is not None:
            _check("%s: %s" % (scenario_file, section), spec[section], allowed)

    infra_spec = read_data_file(
        os.path.join(directory, spec.get("infrastructure", "infrastructure.yaml"))
    )
    timetable_spec = read_data_file(
        os.path.join(directory, spec.get("timetable", "timetable.yaml"))
    )

    interlocking_spec = dict(spec.get("interlocking") or {})
    try:
        infrastructure = build_infrastructure(
            infra_spec, overlaps=bool(interlocking_spec.get("overlaps", False)),
        )
    except InfrastructureError as exc:
        raise ScenarioError("infrastructure: %s" % (exc,))

    timetable = _build_timetable(timetable_spec, infrastructure)

    sim_spec = spec.get("simulation") or {}
    sim_config = SimConfig(
        dt=float(sim_spec.get("dt", 1.0)),
        start_time_s=parse_clock(sim_spec.get("start_time", 0)),
        duration_s=float(sim_spec.get("duration_s", 3600.0)),
        strict=bool(sim_spec.get("strict", False)),
        seed=int(sim_spec.get("seed", 0)),
    )

    driver_spec = spec.get("driver") or {}
    driver_config = DriverConfig(
        reaction_time_s=float(driver_spec.get("reaction_time_s", 2.0)),
        safety_margin_m=float(driver_spec.get("safety_margin_m", 25.0)),
        stop_tolerance_m=float(driver_spec.get("stop_tolerance_m", 1.0)),
    )

    try:
        disruptions = build_disruptions(spec.get("disruptions"), parse_clock,
                                        kmh_to_ms)
    except DisruptionError as exc:
        raise ScenarioError("%s: %s" % (scenario_file, exc))

    return Scenario(
        name=spec.get("name", os.path.basename(os.path.abspath(directory))),
        description=spec.get("description", ""),
        directory=directory,
        source=scenario_file,
        infrastructure=infrastructure,
        timetable=timetable,
        sim_config=sim_config,
        signalling_spec=dict(spec.get("signalling") or {}),
        interlocking_spec=interlocking_spec,
        driver_config=driver_config,
        disruptions=disruptions,
        view=dict(spec.get("view") or {}),
    )


def build_simulation(scenario: Scenario,
                     overrides: Optional[Dict[str, Any]] = None) -> Simulation:
    """Assemble a :class:`~trainsim.core.simulation.Simulation` from a scenario."""
    spec = dict(scenario.signalling_spec)
    system_name = spec.pop("system", "fixed_block_3aspect")
    try:
        signalling = signalling_registry.create(system_name, **spec)
    except TypeError as exc:
        raise ScenarioError(
            "signalling %r does not accept these settings (%s): %s"
            % (system_name, ", ".join(sorted(spec)), exc)
        )

    config = scenario.sim_config
    if overrides:
        config = SimConfig(
            dt=float(overrides.get("dt", config.dt)),
            start_time_s=config.start_time_s,
            duration_s=float(overrides.get("duration_s", config.duration_s)),
            strict=bool(overrides.get("strict", config.strict)),
            seed=config.seed,
        )

    infra = scenario.infrastructure
    interlocking_spec = dict(scenario.interlocking_spec)
    enabled = interlocking_spec.pop("enabled", True)
    interlocking = None
    if enabled:
        interlocking = Interlocking(
            network=infra.network,
            blocks=infra.blocks,
            signals=infra.signals,
            points=infra.points,
            routes=infra.routes,
            use_overlaps=bool(interlocking_spec.pop("overlaps", False)),
            approach_locking_s=float(
                interlocking_spec.pop("approach_locking_s", 120.0)
            ),
            automatic_signals=bool(
                interlocking_spec.pop("automatic_signals", True)
            ),
        )

    dispatcher = TimetableDispatcher(
        scenario.timetable,
        route_request_distance_m=float(
            interlocking_spec.pop("route_request_distance_m", 2500.0)
        ),
        route_request_lead_s=float(
            interlocking_spec.pop("route_request_lead_s", 60.0)
        ),
        # On a fully route-set railway the signaller has to work at least two
        # signals ahead or every green becomes a yellow; where plain line works
        # itself, the only routes to ask for are the one immediately in front.
        route_lookahead=int(interlocking_spec.pop(
            "route_lookahead",
            1 if (interlocking is None or interlocking.automatic_signals) else 2)),
    )
    if interlocking_spec:
        raise ScenarioError(
            "unknown interlocking settings: %s" % ", ".join(sorted(interlocking_spec))
        )

    disruptions = scenario.disruptions
    if overrides and overrides.get("undisrupted"):
        # The baseline half of a propagation measurement: the same scenario with
        # nothing declared wrong, so the difference is attributable.
        disruptions = Disruptions()

    return Simulation(
        disruptions=disruptions,
        network=infra.network,
        blocks=infra.blocks,
        signals=infra.signals,
        block_of_segment=infra.block_of_segment,
        signalling=signalling,
        dispatcher=dispatcher,
        driver=Driver(scenario.driver_config),
        config=config,
        interlocking=interlocking,
    )


# -------------------------------------------------------------------- timetable

def build_timetable(spec: dict, infra: Infrastructure) -> Timetable:
    """Build a timetable from an already-parsed spec, against an infrastructure.

    Public so that tests and future tools can assemble a timetable without going
    through the filesystem.
    """
    return _build_timetable(spec, infra)


def _build_timetable(spec: dict, infra: Infrastructure) -> Timetable:
    if not isinstance(spec, dict):
        raise ScenarioError("timetable: expected a mapping at the top level")
    _check("timetable", spec, schema.TIMETABLE)

    stock = _build_stock(spec.get("stock") or [])
    services = []
    for entry in spec.get("services") or []:
        services.append(_build_service(entry, stock, infra))
    if not services:
        raise ScenarioError("timetable: no services defined")
    return Timetable(services=services)


def _optional_float(value) -> Optional[float]:
    """``None`` stays ``None`` - it is what tells RollingStock to derive a value."""
    return None if value is None else float(value)


def _build_stock(entries: List[dict]) -> Dict[str, RollingStock]:
    stock: Dict[str, RollingStock] = {}
    for entry in entries:
        _check("timetable: stock %r" % (entry.get("id", "?"),), entry, schema.STOCK)
        try:
            stock_id = str(entry["id"])
            stock[stock_id] = RollingStock(
                id=stock_id,
                name=entry.get("name", stock_id),
                length_m=float(entry.get("length_m", 200.0)),
                max_speed_ms=kmh_to_ms(float(entry.get("max_speed_kmh", 140.0))),
                max_accel=float(entry.get("max_accel", 0.9)),
                service_brake=float(entry.get("service_brake", 0.7)),
                emergency_brake=float(entry.get("emergency_brake", 1.2)),
                etcs_level=str(entry.get("etcs_level", "none")).lower(),
                tims=bool(entry.get("tims", False)),
                v2v=bool(entry.get("v2v", False)),
                # Dynamics. Anything left out is derived in RollingStock from
                # the size and performance above, so a timetable written before
                # there was a traction curve still describes a plausible train.
                mass_t=float(entry.get("mass_t", 0.0)),
                rotating_mass_pct=float(entry.get("rotating_mass_pct", 8.0)),
                power_kw=float(entry.get("power_kw", 0.0)),
                davis_a_n=_optional_float(entry.get("davis_a_n")),
                davis_b_n_per_ms=_optional_float(entry.get("davis_b_n_per_ms")),
                davis_c_n_per_ms2=_optional_float(entry.get("davis_c_n_per_ms2")),
                adhesion=float(entry.get("adhesion", 0.30)),
                brake_buildup_s=float(entry.get("brake_buildup_s", 2.0)),
            )
        except KeyError as exc:
            raise ScenarioError("timetable: stock entry missing %s" % (exc,))
    if not stock:
        raise ScenarioError("timetable: no rolling stock defined")
    return stock


def _build_service(entry: dict, stock: Dict[str, RollingStock],
                   infra: Infrastructure) -> Service:
    network = infra.network
    service_id = str(entry.get("id") or "")
    if not service_id:
        raise ScenarioError("timetable: a service has no id")
    _check("service %s" % (service_id,), entry, schema.SERVICE)
    for call in entry.get("calls") or []:
        _check("service %s: call at %r"
               % (service_id, (call or {}).get("station", "?")),
               call, schema.CALL)

    stock_id = entry.get("stock")
    if stock_id not in stock:
        raise ScenarioError(
            "service %s: unknown stock %r (have: %s)"
            % (service_id, stock_id, ", ".join(sorted(stock)))
        )

    calls = entry.get("calls") or []
    if len(calls) < 2:
        raise ScenarioError("service %s: needs at least an origin and a destination"
                            % (service_id,))

    platform_ids = [_resolve_platform(service_id, call, network) for call in calls]
    segment_ids = [network.platforms[p].segment for p in platform_ids]

    try:
        route = network.find_path(segment_ids[0], segment_ids[-1],
                                  via=segment_ids[1:-1])
    except ValueError as exc:
        raise ScenarioError("service %s: %s" % (service_id, exc))

    path = Path(network, route, infra.block_of_segment, infra.blocks,
                infra.signals)
    stops = _build_stops(service_id, calls, platform_ids, path, network)

    departure = entry.get("departure")
    if departure is None:
        departure = stops[0].departure_s
    if departure is None:
        raise ScenarioError(
            "service %s: no departure time for its origin" % (service_id,)
        )

    return Service(
        id=service_id,
        name=entry.get("name", service_id),
        stock=stock[stock_id],
        path=path,
        stops=stops,
        departure_s=parse_clock(departure),
        ready_lead_s=float(entry.get("ready_lead_s", 180.0)),
    )


def _resolve_platform(service_id: str, call: dict, network: Network) -> str:
    station_id = call.get("station")
    if station_id not in network.stations:
        raise ScenarioError(
            "service %s: unknown station %r" % (service_id, station_id)
        )
    platform_id = call.get("platform")
    if platform_id is None:
        candidates = network.stations[station_id].platforms
        if not candidates:
            raise ScenarioError(
                "service %s: station %s has no platforms" % (service_id, station_id)
            )
        return candidates[0]
    if platform_id not in network.platforms:
        raise ScenarioError(
            "service %s: unknown platform %r" % (service_id, platform_id)
        )
    if network.platforms[platform_id].station != station_id:
        raise ScenarioError(
            "service %s: platform %s is not at station %s"
            % (service_id, platform_id, station_id)
        )
    return platform_id


def _build_stops(service_id: str, calls: List[dict], platform_ids: List[str],
                 path: Path, network: Network) -> List[Stop]:
    """Locate each call along the path and attach its booked times."""
    stops: List[Stop] = []
    cursor = 0
    for call, platform_id in zip(calls, platform_ids):
        platform = network.platforms[platform_id]
        while (cursor < len(path.entries)
               and path.entries[cursor].segment.id != platform.segment):
            cursor += 1
        if cursor >= len(path.entries):
            raise ScenarioError(
                "service %s: platform %s is not on the route, or the calls are "
                "out of order" % (service_id, platform_id)
            )
        entry = path.entries[cursor]
        cursor += 1

        arrival = call.get("arrival")
        departure = call.get("departure")
        stops.append(Stop(
            station=call["station"],
            platform=platform_id,
            segment=platform.segment,
            stop_chainage_m=entry.start_m + platform.stop_offset_m,
            arrival_s=parse_clock(arrival) if arrival is not None else None,
            departure_s=parse_clock(departure) if departure is not None else None,
            min_dwell_s=float(call.get("dwell_s", 45.0)),
        ))
    return stops
