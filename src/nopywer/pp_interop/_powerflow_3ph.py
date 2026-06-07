"""Asymmetric (unbalanced three-phase) AC power flow.

The balanced sibling, `_powerflow.py`, runs `pp.runpp` — every load
is an even three-phase draw and the neutral carries nothing. That is
the right model for a well-balanced grid, and a deliberate
simplification everywhere else.

This module runs `pp.runpp_3ph`, which solves each phase
independently and the neutral-return path explicitly. It is the only
way to see two things a balanced solve structurally cannot:

  - **per-leg voltage drop** — when L1 carries 6 kW and L3 carries
    1 kW, the loads on L1 sag further. The balanced model averages
    that away.
  - **neutral-conductor current** — the imbalance returns through
    the neutral. This is the number that decides whether a
    reduced-section-neutral cable (`3G6+½N`) is safe or whether the
    run needs full-section neutral (`4G6`). No balanced tool, and
    no nopywer tree walk, surfaces it at all.

== What it needs that the balanced path does not ==

`runpp_3ph` needs zero-sequence parameters — how the cables and the
source behave to the imbalance current. These have no nopywer
analogue and are not on festival flex spec sheets, so they come from
engineering rule-of-thumb defaults in `config.py`
(`R0_OVER_R1`, `X0_OVER_X1`, `SOURCE_X0X_MAX`, `SOURCE_R0X0_MAX`).
See research doc 10 for the reasoning behind the numbers.

`to_pandapower_3ph` builds an **independent** pandapower net via the
shared `_build_net_skeleton` (which `to_pandapower` also uses). It
does **not** mutate the balanced converter's output. The two paths
are sibling consumers of the same skeleton, so converting the same
`PowerGrid` for both flows is a no-shared-state operation: each call
produces a fresh net and a fresh result object.

The returned `Pandapower3phGrid` keeps the dual load layout visible
in the type: `balanced_load_idx` for loads that stayed in `net.load`
(those with `phase is None`), `asymmetric_load_idx` for loads in
`net.asymmetric_load` (those with an explicit `phase`). Callers can
tell which table a load is in without re-inspecting the net.

Voltage convention: identical to `_powerflow.py`. pandapower returns
per-unit on `vn_kv` (line-to-line); we report nopywer's
phase-to-neutral volts (`vm_pu * vn_kv * 1000 / sqrt(3)`).

== What this module does not (yet) do ==

There is no `compare_3ph_with_tree_walk`. nopywer's tree walk
collapses each node to a single scalar voltage (via the max-phase
current rule), so it has no per-leg voltage to line up against
`runpp_3ph`'s three. A meaningful comparison is a findings-doc
exercise (doc 12), not a drop-in mirror of `compare_with_tree_walk`.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..constants import PF, V0
from ..models import PowerGrid
from . import config
from ._conversion import _build_net_skeleton

import pandapower as pp
if TYPE_CHECKING:
    from pandapower.auxiliary import pandapowerNet
else:
    pandapowerNet = Any

logger = logging.getLogger(__name__)


@dataclass
class Pandapower3phGrid:
    """A `PowerGrid` translated for *asymmetric* three-phase power flow.

    Produced by `to_pandapower_3ph(grid)` and consumed by
    `compute_power_flow_3ph`. A distinct dataclass from
    `PandapowerGrid` because the load layout in `net` is genuinely
    different: loads split across two pandapower tables.

    Attributes:
        net: the `pandapowerNet`, with zero-sequence line parameters
            and source vector-group fields populated. Mutable —
            `compute_power_flow_3ph` writes into `net.res_*_3ph`.
        bus_idx: maps `PowerNode.name` to its pandapower bus index.
            Same shape and meaning as on `PandapowerGrid`.
        balanced_load_idx: maps `PowerNode.name` to its index in
            `net.load`. Contains the loads with `phase is None` —
            `runpp_3ph` treats a plain `pp.load` as an even
            three-phase draw, so balanced loads stay in the balanced
            table.
        asymmetric_load_idx: maps `PowerNode.name` to its index in
            `net.asymmetric_load`. Contains the loads with an
            explicit `phase` (int or list) — these go to
            `pp.asymmetric_load` with per-leg P / Q.
        source: the original `PowerGrid`. Kept as a back-reference
            so callers debugging a converted grid can trace any
            bus/load row back to the nopywer node it came from
            without re-running the conversion. Not read or written
            by `compute_power_flow_3ph` itself.

    A given load name appears in **at most one** of
    `balanced_load_idx` / `asymmetric_load_idx`. The split is decided
    at conversion time from `node.phase` and is fixed for the
    lifetime of this grid object.
    """

    net: pandapowerNet
    bus_idx: dict[str, int]
    source: PowerGrid
    balanced_load_idx: dict[str, int] = field(default_factory=dict)
    asymmetric_load_idx: dict[str, int] = field(default_factory=dict)


def _phase_split(phase: object, power_watts: float) -> tuple[float, float, float]:
    """Split a load's power across (L1, L2, L3) from its `phase` field.

    Mirrors the per-phase rule used by `io.load_geojson` and
    `phases._common._fixed_leg_seed`, so the conversion sees a load
    exactly the way the rest of nopywer does:

      - `phase` is an int 1-3 — the whole load sits on that one leg.
      - `phase` is a list, e.g. `[1, 2]` — the load is split evenly
        across the listed legs (a 10 kW load on `[1, 2]` is 5 kW on
        L1, 5 kW on L2, nothing on L3).
      - anything else (the `"U"` / `"Y"` sub-grid markers, an empty
        or malformed list, or `None`) — balanced: an even third on
        each leg.

    Note on `None`: `to_pandapower_3ph` routes `phase is None` loads
    straight to `pp.load` and never calls this function for them.
    The `None` branch is therefore purely defensive — it exists so
    `_phase_split` is correct in isolation, e.g. for tests that
    parametrise across every `phase` form.

    Args:
        phase: the node's `phase` field, in any of its forms.
        power_watts: the load's total real power.

    Returns:
        A `(p_l1, p_l2, p_l3)` tuple in watts that always sums to
        `power_watts`.
    """
    if isinstance(phase, int) and 1 <= phase <= 3:
        return tuple(power_watts if phase == i + 1 else 0.0 for i in range(3))
    if isinstance(phase, list):
        legs = [p for p in phase if isinstance(p, int) and 1 <= p <= 3]
        if legs:
            share = power_watts / len(legs)
            return tuple(share if i + 1 in legs else 0.0 for i in range(3))
    third = power_watts / 3
    return (third, third, third)


def to_pandapower_3ph(
    grid: PowerGrid,
    *,
    load_pf: float = PF,
    **skeleton_kwargs: object,
) -> Pandapower3phGrid:
    """Convert a `PowerGrid` for asymmetric flow — fresh net, no mutation.

    Builds an **independent** pandapower net via the shared
    `_build_net_skeleton` (which the balanced `to_pandapower` also
    uses), then adds the 3ph-only pieces:

      1. **Zero-sequence line params** — `r0`, `x0`, `c0` on every
         line, derived from the positive-sequence values via the
         `R0_OVER_R1` / `X0_OVER_X1` config ratios.
      2. **Source vector group** — `r0x0_max` / `x0x_max` on the
         ext_grid, describing the genset's zero-sequence return path.
      3. **Loads in their right table** — each non-generator load is
         classified by `node.phase`:

           - `phase is None` → balanced: a `pp.load` in `net.load`,
             keyed by name in `balanced_load_idx`. `runpp_3ph`
             treats this as an even three-phase draw.
           - explicit `int` or `list` → asymmetric: a
             `pp.asymmetric_load` in `net.asymmetric_load`, keyed by
             name in `asymmetric_load_idx`, with per-leg P / Q from
             `_phase_split`.

    No load is in both tables; the split is fixed at conversion
    time. Nothing this function does touches a previously-built
    `PandapowerGrid` — converting the same source grid for both
    balanced and asymmetric flow produces two genuinely independent
    objects.

    Args:
        grid: the nopywer `PowerGrid` to convert. Its cables must
            already be snapped (run `analyze` or load via GeoJSON).
        load_pf: load power factor, used to derive reactive power
            for both balanced and asymmetric loads. Defaults to the
            global `PF`.
        **skeleton_kwargs: forwarded verbatim to
            `_build_net_skeleton` (generator ratings,
            `x_ohm_per_km`, etc.).

    Returns:
        A `Pandapower3phGrid` whose `net` is ready for
        `compute_power_flow_3ph`.

    Raises:
        ValueError: propagated from `_build_net_skeleton` if the
            grid has no cables or a cable references an unknown node.
        ImportError: if pandapower is not installed.
    """
    net, bus_idx = _build_net_skeleton(grid, **skeleton_kwargs)  # type: ignore[arg-type]

    # zero-sequence line parameters
    net.line["r0_ohm_per_km"] = net.line["r_ohm_per_km"] * config.R0_OVER_R1
    net.line["x0_ohm_per_km"] = net.line["x_ohm_per_km"] * config.X0_OVER_X1
    net.line["c0_nf_per_km"] = config.C0_NF_PER_KM

    # source vector group / earthing
    net.ext_grid["r0x0_max"] = config.SOURCE_R0X0_MAX
    net.ext_grid["x0x_max"] = config.SOURCE_X0X_MAX

    # loads, each into the right table by node.phase
    balanced_load_idx: dict[str, int] = {}
    asymmetric_load_idx: dict[str, int] = {}
    tan_phi = math.tan(math.acos(load_pf)) if 0 < load_pf < 1 else 0.0
    for name, node in grid.nodes.items():
        if node.is_generator or node.power_watts <= 0:
            continue
        # Legacy "U" / "Y" string markers have no electrical meaning;
        # treat them the same as `phase is None` (balanced). Logged so
        # the operator knows the marker propagated through to a solve.
        is_balanced = node.phase is None or isinstance(node.phase, str)
        if isinstance(node.phase, str):
            logger.warning(
                "Node %r carries legacy string phase marker %r; routing to "
                "balanced pp.load. Phase markers should be int (1/2/3) or "
                "list ([1, 2]) for runpp_3ph to use them.",
                name,
                node.phase,
            )
        if is_balanced:
            p_mw = node.power_watts / 1e6
            balanced_load_idx[name] = pp.create_load(
                net,
                bus=bus_idx[name],
                p_mw=p_mw,
                q_mvar=p_mw * tan_phi,
                name=name,
            )
        else:
            p_l1, p_l2, p_l3 = _phase_split(node.phase, node.power_watts)
            asymmetric_load_idx[name] = pp.create_asymmetric_load(
                net,
                bus=bus_idx[name],
                p_a_mw=p_l1 / 1e6,
                p_b_mw=p_l2 / 1e6,
                p_c_mw=p_l3 / 1e6,
                q_a_mvar=p_l1 * tan_phi / 1e6,
                q_b_mvar=p_l2 * tan_phi / 1e6,
                q_c_mvar=p_l3 * tan_phi / 1e6,
                name=name,
            )

    return Pandapower3phGrid(
        net=net,
        bus_idx=bus_idx,
        source=grid,
        balanced_load_idx=balanced_load_idx,
        asymmetric_load_idx=asymmetric_load_idx,
    )


@dataclass
class PowerFlow3phResults:
    """Per-leg and neutral results from `runpp_3ph`, in nopywer-native units.

    Every per-leg field is an `(L1, L2, L3)` tuple. Contrast
    `PowerFlowResults` from `_powerflow.py`, whose fields are scalars
    — that is the whole point of running the asymmetric solve.

    Attributes:
        bus_voltage_v: phase-to-neutral volts on each leg, by node
            name. `(230, 230, 230)` would be a perfectly balanced bus
            at nominal.
        bus_vdrop_percent: percent drop from `V0` on each leg, by node
            name. The per-leg spread here is exactly what a balanced
            `runpp` averages away.
        bus_unbalance_percent: voltage unbalance factor (negative- /
            positive-sequence magnitude, percent), by node name. 0 %
            is balanced. Defined as 0.0 where pandapower returns NaN
            (a bus with no load and no imbalance to measure).
        line_current_a: per-leg current, by cable id.
        line_neutral_current_a: neutral-conductor current, by cable
            id. The quantity neither a balanced solve nor the nopywer
            tree walk can give you — and the one that decides whether
            a reduced-section-neutral cable is adequate.
        line_loading_percent: worst-leg loading against `max_i_ka`,
            by cable id (pandapower's own `loading_percent`, which is
            already the max across the three legs).
        converged: whether `runpp_3ph` reached a solution.
    """

    bus_voltage_v: dict[str, tuple[float, float, float]]
    bus_vdrop_percent: dict[str, tuple[float, float, float]]
    bus_unbalance_percent: dict[str, float]
    line_current_a: dict[str, tuple[float, float, float]]
    line_neutral_current_a: dict[str, float]
    line_loading_percent: dict[str, float]
    converged: bool

    def worst_phase_vdrop(self) -> tuple[str, int, float] | None:
        """Find the single most-sagged leg anywhere on the grid.

        Returns:
            `(node_name, leg, vdrop_percent)` for the worst leg, where
            `leg` is 1, 2 or 3. `None` if there are no buses.
        """
        if not self.bus_vdrop_percent:
            return None
        worst_name = ""
        worst_leg = 0
        worst_drop = float("-inf")
        for name, legs in self.bus_vdrop_percent.items():
            for i, drop in enumerate(legs):
                if drop > worst_drop:
                    worst_name, worst_leg, worst_drop = name, i + 1, drop
        return worst_name, worst_leg, worst_drop

    def worst_neutral_current(self) -> tuple[str, float] | None:
        """Find the cable carrying the most neutral current.

        Returns:
            `(cable_id, neutral_current_a)` for the worst cable, or
            `None` if there are no lines.
        """
        if not self.line_neutral_current_a:
            return None
        cid, current = max(self.line_neutral_current_a.items(), key=lambda kv: kv[1])
        return cid, current


def compute_power_flow_3ph(pp_grid: Pandapower3phGrid) -> PowerFlow3phResults:
    """Run asymmetric AC power flow on a net from `to_pandapower_3ph`.

    Calls `pp.runpp_3ph` and translates `res_bus_3ph` / `res_line_3ph`
    into nopywer-native units (volts P-N, amps, percent). Does not
    mutate the source `PowerGrid`.

    Takes a `Pandapower3phGrid` specifically, not a `PandapowerGrid`
    — the type-checker will catch the "I passed the balanced grid to
    the 3ph solver" mistake at the call site rather than at runtime
    with a cryptic pandapower error.

    Args:
        pp_grid: the converted grid from `to_pandapower_3ph`.

    Returns:
        A `PowerFlow3phResults` with per-leg bus voltages, per-leg and
        neutral line currents, and the voltage-unbalance factor.

    Raises:
        pandapower.LoadflowNotConverged: if `runpp_3ph` fails to
            converge — for a festival grid this usually means it is
            past voltage collapse, the same physical signal as a
            failed balanced solve (see doc 11).
        ImportError: if pandapower is not installed.
    """
    pp.runpp_3ph(pp_grid.net)
    net = pp_grid.net

    converged = bool(net["converged"])
    vn_v = net.bus.iloc[0]["vn_kv"] * 1000.0
    pn_v_at_nominal = vn_v / math.sqrt(3)

    bus_voltage_v: dict[str, tuple[float, float, float]] = {}
    bus_vdrop_percent: dict[str, tuple[float, float, float]] = {}
    bus_unbalance_percent: dict[str, float] = {}
    for name, idx in pp_grid.bus_idx.items():
        row = net.res_bus_3ph.loc[idx]
        legs = tuple(
            round(float(row[f"vm_{ph}_pu"]) * pn_v_at_nominal, 2) for ph in ("a", "b", "c")
        )
        bus_voltage_v[name] = legs
        bus_vdrop_percent[name] = tuple(round(100.0 * (V0 - v) / V0, 3) for v in legs)
        unbalance = float(row["unbalance_percent"])
        # pandapower returns NaN for a bus with no load (0/0 sequence ratio).
        bus_unbalance_percent[name] = round(unbalance, 3) if unbalance == unbalance else 0.0

    line_current_a: dict[str, tuple[float, float, float]] = {}
    line_neutral_current_a: dict[str, float] = {}
    line_loading_percent: dict[str, float] = {}
    for line_idx, line_row in net.line.iterrows():
        cable_id = line_row["name"]
        res = net.res_line_3ph.loc[line_idx]
        line_current_a[cable_id] = tuple(
            round(float(res[f"i_{ph}_ka"]) * 1000.0, 3) for ph in ("a", "b", "c")
        )
        line_neutral_current_a[cable_id] = round(float(res["i_n_ka"]) * 1000.0, 3)
        line_loading_percent[cable_id] = round(float(res["loading_percent"]), 2)

    return PowerFlow3phResults(
        bus_voltage_v=bus_voltage_v,
        bus_vdrop_percent=bus_vdrop_percent,
        bus_unbalance_percent=bus_unbalance_percent,
        line_current_a=line_current_a,
        line_neutral_current_a=line_neutral_current_a,
        line_loading_percent=line_loading_percent,
        converged=converged,
    )
