"""PowerGrid → pandapowerNet conversion.

Used by every calc function in this package. Produces a `PandapowerGrid`
holding the net, name→bus_idx map, name→load_idx map, and a back-ref
to the source `PowerGrid` for write-back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..constants import PF, RHO_COPPER
from ..models import PowerGrid
from . import config

if TYPE_CHECKING:
    from pandapower.auxiliary import pandapowerNet


def _import_pandapower():
    try:
        import pandapower as pp
        import pandapower.shortcircuit as sc
    except ImportError as e:
        raise ImportError(
            "pandapower is required for this feature. "
            "Install with: pip install nopywer[pandapower]"
        ) from e
    return pp, sc


@dataclass
class PandapowerGrid:
    """A `PowerGrid` translated into pandapower form.

    Produced once by `to_pandapower(grid)` and passed to calc functions
    (`compute_short_circuit`, `compute_power_flow`, ...). The same handle
    is reusable across multiple calc calls.

    Attributes:
        net: the `pandapowerNet`. Mutable — calc functions write into
            `net.res_*` tables. Caller may inspect or modify.
        bus_idx: maps `PowerNode.name` to its pandapower bus index.
        load_idx: maps `PowerNode.name` to its pandapower load index
            (only present for non-generator nodes with power > 0).
        source: the original `PowerGrid`. Calc functions write results
            back onto its `PowerNode`s using `bus_idx`.
    """

    net: "pandapowerNet"
    bus_idx: dict[str, int]
    source: PowerGrid
    load_idx: dict[str, int] = field(default_factory=dict)


def to_pandapower(
    grid: PowerGrid,
    gen_sn_kva: float = config.GEN_SN_KVA,
    gen_xdss_pu: float = config.GEN_XDSS_PU,
    gen_rx: float = config.GEN_RX,
    x_ohm_per_km: float = config.X_OHM_PER_KM,
    load_pf: float = PF,
) -> PandapowerGrid:
    """Translate a `PowerGrid` into a `PandapowerGrid`.

    Cables must already have `from_node` and `to_node` populated (set by
    `io.load_geojson` or by `analyze._snap_cables_to_nodes`).

    The generator becomes an `ext_grid` with
        s_sc_max_mva = (gen_sn_kva / 1000) / gen_xdss_pu

    Each non-generator node with `power_watts > 0` becomes a balanced
    `pp.load` with P = power_watts and Q derived from `load_pf`. Loads
    are needed for `runpp` (power flow) and are harmless for IEC 60909
    `calc_sc` max-case (which standardly ignores prefault load).
    """
    if not grid.cables:
        raise ValueError("At least one cable is required")

    pp, _ = _import_pandapower()

    net = pp.create_empty_network(sn_mva=config.NET_SN_MVA, f_hz=config.F_HZ)

    bus_idx: dict[str, int] = {}
    for name in grid.nodes:
        bus_idx[name] = pp.create_bus(net, vn_kv=config.VN_KV_LL, name=name)

    s_sc_max_mva = (gen_sn_kva / 1000.0) / gen_xdss_pu
    pp.create_ext_grid(
        net,
        bus=bus_idx[grid.generator.name],
        vm_pu=config.GEN_VM_PU,
        s_sc_max_mva=s_sc_max_mva,
        rx_max=gen_rx,
    )

    load_idx: dict[str, int] = {}
    tan_phi = math.tan(math.acos(load_pf)) if 0 < load_pf < 1 else 0.0
    for name, node in grid.nodes.items():
        if node.is_generator or node.power_watts <= 0:
            continue
        p_mw = node.power_watts / 1e6
        load_idx[name] = pp.create_load(
            net,
            bus=bus_idx[name],
            p_mw=p_mw,
            q_mvar=p_mw * tan_phi,
            name=name,
        )

    for cable_id, cable in grid.cables.items():
        if not cable.from_node or not cable.to_node:
            raise ValueError(
                f"Cable {cable_id!r} is not connected to two nodes "
                f"(from_node={cable.from_node!r}, to_node={cable.to_node!r}). "
                "Run io.load_geojson or analyze._snap_cables_to_nodes first."
            )
        if cable.from_node not in bus_idx or cable.to_node not in bus_idx:
            raise ValueError(
                f"Cable {cable_id!r} references unknown node "
                f"({cable.from_node!r} or {cable.to_node!r})."
            )
        length_km = max(cable.length_m, config.MIN_LENGTH_M) / 1000.0
        r_ohm_per_km = RHO_COPPER * 1000.0 / cable.area_mm2
        pp.create_line_from_parameters(
            net,
            from_bus=bus_idx[cable.from_node],
            to_bus=bus_idx[cable.to_node],
            length_km=length_km,
            r_ohm_per_km=r_ohm_per_km,
            x_ohm_per_km=x_ohm_per_km,
            c_nf_per_km=config.C_NF_PER_KM,
            max_i_ka=cable.plugs_and_sockets_a / 1000.0,
            name=cable_id,
        )

    return PandapowerGrid(net=net, bus_idx=bus_idx, source=grid, load_idx=load_idx)
