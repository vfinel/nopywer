"""AC power flow validation of the optimiser.

`compute_power_flow` runs `pp.runpp` (Newton-Raphson) on the converted
net. `compare_with_tree_walk` runs the existing `analyze` tree walk
and the AC power flow side-by-side, returning a per-node / per-cable
diff so you can see where the linearised model disagrees with the AC
truth.

Voltage convention: pandapower returns per-unit on `vn_kv` (L-L). We
report nopywer's phase-to-neutral volts (`vm_pu * vn_kv * 1000 / sqrt(3)`)
to match `PowerNode.voltage`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..analyze import analyze
from ..constants import V0
from ..models import PowerGrid
from ._conversion import PandapowerGrid, _import_pandapower, to_pandapower


@dataclass
class PowerFlowResults:
    """Per-bus and per-line AC power flow results in nopywer-native units.

    bus_voltage_v: phase-to-neutral volts at each bus, mapped by node name.
    bus_vdrop_percent: percent drop from V0 (= 230 V) at each bus.
    line_current_a: branch current in amps, mapped by cable id.
    line_loading_percent: branch loading vs `max_i_ka`, mapped by cable id.
    converged: whether `runpp` converged.
    """

    bus_voltage_v: dict[str, float]
    bus_vdrop_percent: dict[str, float]
    line_current_a: dict[str, float]
    line_loading_percent: dict[str, float]
    converged: bool


def compute_power_flow(pp_grid: PandapowerGrid) -> PowerFlowResults:
    """Run balanced AC power flow on the converted net.

    Returns nopywer-native units (volts P-N, amps, percent). Does not
    mutate the source `PowerGrid` — the AC and tree-walk results are
    different views of the same physics, so we keep them separate
    and let `compare_with_tree_walk` line them up.
    """
    pp, _ = _import_pandapower()
    pp.runpp(pp_grid.net)

    converged = bool(pp_grid.net.converged)
    vn_v = pp_grid.net.bus.iloc[0]["vn_kv"] * 1000.0
    pn_v_at_nominal = vn_v / math.sqrt(3)

    bus_voltage_v: dict[str, float] = {}
    bus_vdrop_percent: dict[str, float] = {}
    for name, idx in pp_grid.bus_idx.items():
        vm_pu = float(pp_grid.net.res_bus.at[idx, "vm_pu"])
        v_pn = vm_pu * pn_v_at_nominal
        bus_voltage_v[name] = round(v_pn, 2)
        bus_vdrop_percent[name] = round(100.0 * (V0 - v_pn) / V0, 3)

    line_current_a: dict[str, float] = {}
    line_loading_percent: dict[str, float] = {}
    for line_idx, row in pp_grid.net.line.iterrows():
        cable_id = row["name"]
        i_ka = float(pp_grid.net.res_line.at[line_idx, "i_ka"])
        loading = float(pp_grid.net.res_line.at[line_idx, "loading_percent"])
        line_current_a[cable_id] = round(i_ka * 1000.0, 3)
        line_loading_percent[cable_id] = round(loading, 2)

    return PowerFlowResults(
        bus_voltage_v=bus_voltage_v,
        bus_vdrop_percent=bus_vdrop_percent,
        line_current_a=line_current_a,
        line_loading_percent=line_loading_percent,
        converged=converged,
    )


@dataclass
class TreeWalkVsAcDiff:
    """Side-by-side of nopywer's tree-walk vs pandapower's AC power flow.

    Each entry is `(tree_walk_value, ac_value, delta = ac - tree)`.
    bus_voltage_v / bus_vdrop_percent are keyed by node name.
    line_current_a is keyed by cable id (max phase current vs AC i_ka).
    """

    bus_voltage_v: dict[str, tuple[float, float, float]]
    bus_vdrop_percent: dict[str, tuple[float, float, float]]
    line_current_a: dict[str, tuple[float, float, float]]
    converged: bool

    def worst_voltage_disagreement(self) -> tuple[str, float] | None:
        if not self.bus_voltage_v:
            return None
        name, (_, _, delta) = max(
            self.bus_voltage_v.items(), key=lambda kv: abs(kv[1][2])
        )
        return name, delta

    def worst_current_disagreement(self) -> tuple[str, float] | None:
        if not self.line_current_a:
            return None
        cid, (_, _, delta) = max(
            self.line_current_a.items(), key=lambda kv: abs(kv[1][2])
        )
        return cid, delta


def compare_with_tree_walk(grid: PowerGrid, **to_pp_kwargs) -> TreeWalkVsAcDiff:
    """Run nopywer's tree walk and pandapower's AC flow, return the diff.

    Mutates `grid` (analyze writes voltages/currents back). Caller can
    inspect `grid` afterwards for the tree-walk view; the returned
    diff lines tree-walk against AC values per node and per cable.

    If `analyze` has already been run on the grid (`grid.tree` populated),
    this is a no-op — re-running would trip the cycle-detection guard.
    """
    if not grid.tree:
        analyze(grid)

    pp_grid = to_pandapower(grid, **to_pp_kwargs)
    ac = compute_power_flow(pp_grid)

    bus_voltage_v: dict[str, tuple[float, float, float]] = {}
    bus_vdrop_percent: dict[str, tuple[float, float, float]] = {}
    for name, node in grid.nodes.items():
        tw_v = float(node.voltage)
        ac_v = ac.bus_voltage_v[name]
        bus_voltage_v[name] = (tw_v, ac_v, round(ac_v - tw_v, 2))
        tw_d = float(node.vdrop_percent)
        ac_d = ac.bus_vdrop_percent[name]
        bus_vdrop_percent[name] = (tw_d, ac_d, round(ac_d - tw_d, 3))

    line_current_a: dict[str, tuple[float, float, float]] = {}
    for cable_id, cable in grid.cables.items():
        tw_i = max(cable.current_per_phase) if cable.current_per_phase else 0.0
        ac_i = ac.line_current_a.get(cable_id, 0.0)
        line_current_a[cable_id] = (round(tw_i, 2), ac_i, round(ac_i - tw_i, 2))

    return TreeWalkVsAcDiff(
        bus_voltage_v=bus_voltage_v,
        bus_vdrop_percent=bus_vdrop_percent,
        line_current_a=line_current_a,
        converged=ac.converged,
    )
