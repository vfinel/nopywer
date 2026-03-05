from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from .constants import PF, RHO_COPPER, V0


@dataclass
class PowerNode:
    name: str
    lon: float
    lat: float
    power_watts: float = 0.0
    is_generator: bool = False
    phase: int | str | list | None = None

    parent: str | None = None
    children: dict[str, str] = field(default_factory=dict)
    deepness: int | None = None

    cum_power: np.ndarray = field(default_factory=lambda: np.zeros(3))
    power_per_phase: np.ndarray = field(default_factory=lambda: np.zeros(3))
    voltage: float = 0.0
    vdrop_percent: float = 0.0

    cable_to_parent: str | None = None

    distro: dict = field(default_factory=lambda: {"in": None, "out": {}})
    distro_chosen: dict | str = field(default_factory=lambda: {"in": None, "out": {}})


@dataclass
class Cable:
    id: str
    length_m: float
    area_mm2: float = 2.5
    plugs_and_sockets_a: float = 16.0
    phase: int | str | list | None = None

    from_node: str = ""
    to_node: str = ""
    from_coords: tuple[float, float] = (0.0, 0.0)
    to_coords: tuple[float, float] = (0.0, 0.0)

    current_per_phase: list[float] = field(default_factory=list)
    vdrop_volts: float = 0.0

    tier_cost: ClassVar[float] = 1.0
    num_phases: ClassVar[int] = 1
    max_current_a: ClassVar[int] = 16

    @property
    def resistance(self) -> float:
        return RHO_COPPER * self.length_m / self.area_mm2


@dataclass
class Cable16A(Cable):
    tier_cost: ClassVar[float] = 1.0
    num_phases: ClassVar[int] = 1
    max_current_a: ClassVar[int] = 16


@dataclass
class Cable32A(Cable):
    tier_cost: ClassVar[float] = 3.0
    num_phases: ClassVar[int] = 3
    max_current_a: ClassVar[int] = 32
    area_mm2: float = 6.0
    plugs_and_sockets_a: float = 32.0


@dataclass
class Cable63A(Cable):
    tier_cost: ClassVar[float] = 8.0
    num_phases: ClassVar[int] = 3
    max_current_a: ClassVar[int] = 63
    area_mm2: float = 16.0
    plugs_and_sockets_a: float = 63.0


@dataclass
class Cable125A(Cable):
    tier_cost: ClassVar[float] = 20.0
    num_phases: ClassVar[int] = 3
    max_current_a: ClassVar[int] = 125
    area_mm2: float = 35.0
    plugs_and_sockets_a: float = 125.0


_CABLE_TYPES: list[type[Cable]] = [Cable16A, Cable32A, Cable63A, Cable125A]


def pick_cable_for(power_watts: float) -> type[Cable]:
    """Pick the smallest cable type that can handle the given power.

    Each type is checked with: I = P / (num_phases x V0 x PF)
    """
    for cable_cls in _CABLE_TYPES:
        if power_watts / (cable_cls.num_phases * V0 * PF) <= cable_cls.max_current_a:
            return cable_cls
    return _CABLE_TYPES[-1]
