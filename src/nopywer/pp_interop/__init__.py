"""Pandapower interop layer.

Optional feature — requires `uv sync --extra pandapower`.

Public API:
    to_pandapower(grid, ...) -> PandapowerGrid
    compute_short_circuit(pp_grid) -> {name: i_sc_ka}
    compute_power_flow(pp_grid) -> PowerFlowResults
    compare_with_tree_walk(grid, ...) -> TreeWalkVsAcDiff

All defaults and modelling assumptions live in `config.py`.
"""

from . import config
from ._conversion import PandapowerGrid, to_pandapower
from ._powerflow import (
    PowerFlowResults,
    TreeWalkVsAcDiff,
    compare_with_tree_walk,
    compute_power_flow,
)
from ._powerflow_3ph import (
    PowerFlow3phResults,
    compute_power_flow_3ph,
    to_pandapower_3ph,
)
from ._shortcircuit import compute_short_circuit

__all__ = [
    "PandapowerGrid",
    "PowerFlow3phResults",
    "PowerFlowResults",
    "TreeWalkVsAcDiff",
    "compare_with_tree_walk",
    "compute_power_flow",
    "compute_power_flow_3ph",
    "compute_short_circuit",
    "config",
    "to_pandapower",
    "to_pandapower_3ph",
]
