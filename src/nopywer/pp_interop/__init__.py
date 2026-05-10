"""Pandapower interop layer.

Optional feature — requires `pip install nopywer[pandapower]`.

Public API:
    to_pandapower(grid, ...) -> PandapowerGrid
    compute_short_circuit(pp_grid) -> {name: i_sc_ka}

All defaults and modelling assumptions live in `config.py`.
"""

from . import config
from ._conversion import PandapowerGrid, to_pandapower
from ._shortcircuit import compute_short_circuit

__all__ = [
    "PandapowerGrid",
    "compute_short_circuit",
    "config",
    "to_pandapower",
]
