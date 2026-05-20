"""IEC 60909 short-circuit calculation."""

from __future__ import annotations

import pandapower.shortcircuit as sc 
from . import config
from ._conversion import PandapowerGrid


def compute_short_circuit(pp_grid: PandapowerGrid) -> dict[str, float]:
    """Compute prospective 3-phase short-circuit current at every bus.

    Runs `pp.shortcircuit.calc_sc` (`fault`/`case` from `config.py`)
    against `pp_grid.net`, writes `i_sc_ka` onto each `PowerNode` of
    `pp_grid.source`, and returns a `{name: i_sc_ka}` dict.

    `i_sc_ka` is the IEC 60909 initial symmetric short-circuit current
    (Ikss) in kA at the node's bus.
    """
    sc.calc_sc(pp_grid.net, fault=config.FAULT_TYPE, case=config.FAULT_CASE)

    results: dict[str, float] = {}
    for name, idx in pp_grid.bus_idx.items():
        i_sc_ka = float(pp_grid.net.res_bus_sc.at[idx, "ikss_ka"])
        pp_grid.source.nodes[name].i_sc_ka = i_sc_ka
        results[name] = i_sc_ka
    return results
