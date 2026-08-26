"""Timetabled services.

A :class:`Service` is the *plan*: which stock, over which path, calling where and
when. A :class:`~trainsim.core.train.Train` is the *execution* of that plan. The
split matters for the planned rescheduling work - a traffic management system
rewrites services, while trains keep running under the physics.
"""

from dataclasses import dataclass, field
from typing import List

from .train import Path, RollingStock, Stop, Train


@dataclass
class Service:
    """One timetabled train run."""

    id: str
    name: str
    stock: RollingStock
    path: Path
    stops: List[Stop]
    departure_s: float
    #: How early the train appears in the origin platform, ready to depart.
    ready_lead_s: float = 180.0

    @property
    def origin(self) -> str:
        return self.stops[0].station if self.stops else "?"

    @property
    def destination(self) -> str:
        return self.stops[-1].station if self.stops else "?"

    def create_train(self) -> Train:
        """Instantiate the train, standing at its origin platform.

        It starts at the first stop's stopping point with ``next_stop_index`` set
        past that stop: the origin call has, in effect, already been made and only
        the departure remains.
        """
        first = self.stops[0]
        train = Train(
            id=self.id,
            name=self.name,
            stock=self.stock,
            path=self.path,
            stops=self.stops,
            origin_departure_s=self.departure_s,
            chainage_m=first.stop_chainage_m,
            speed_ms=0.0,
            state="dwelling",
            next_stop_index=1,
            dwell_until_s=self.departure_s,
        )
        return train


@dataclass
class Timetable:
    """The full set of planned services."""

    services: List[Service] = field(default_factory=list)

    def sorted_by_departure(self) -> List[Service]:
        return sorted(self.services, key=lambda s: (s.departure_s, s.id))
