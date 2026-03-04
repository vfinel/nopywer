from dataclasses import dataclass, field

import numpy as np

from .constants import RHO_COPPER


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

    @property
    def resistance(self) -> float:
        return RHO_COPPER * self.length_m / self.area_mm2
