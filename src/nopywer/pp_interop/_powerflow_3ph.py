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

`to_pandapower_3ph` builds on the balanced `to_pandapower` and
augments it rather than duplicating the conversion: it bolts the
zero-sequence params onto the lines and ext_grid, and swaps each
explicitly-phased load's balanced `pp.load` for a `pp.asymmetric_load`.

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

import math
from dataclasses import dataclass

from ..constants import PF, V0
from . import config
from ._conversion import PandapowerGrid, _import_pandapower, to_pandapower


def _phase_split(phase: object, power_watts: float) -> tuple[float, float, float]:
    """Split a load's power across (L1, L2, L3) from its `phase` field.

    Mirrors the per-phase rule used by `io.load_geojson` and
    `phases._common._fixed_leg_seed`, so the conversion sees a load
    exactly the way the rest of nopywer does:

      - `phase` is an int 1-3 — the whole load sits on that one leg.
      - `phase` is a list, e.g. `[1, 2]` — the load is split evenly
        across the listed legs (a 10 kW load on `[1, 2]` is 5 kW on
        L1, 5 kW on L2, nothing on L3).
      - anything else (`None`, the `"U"` / `"Y"` sub-grid markers, an
        empty or malformed list) — balanced: an even third on each
        leg.

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
    grid: PandapowerGrid | object, *, load_pf: float = PF, **to_pp_kwargs: object
) -> PandapowerGrid:
    """Convert a `PowerGrid` for asymmetric flow.

    Starts from the balanced `to_pandapower` net and augments it for
    `runpp_3ph`:

      1. **Zero-sequence line params** — `r0`, `x0`, `c0` on every
         line, derived from the positive-sequence values via the
         `R0_OVER_R1` / `X0_OVER_X1` config ratios.
      2. **Source vector group** — `r0x0_max` / `x0x_max` on the
         ext_grid, describing the genset's zero-sequence return path.
      3. **Asymmetric loads** — every load with an explicit `phase`
         (single int or list) has its balanced `pp.load` dropped and
         replaced with a `pp.asymmetric_load` carrying the per-leg
         split from `_phase_split`. Truly balanced loads (`phase`
         `None`) keep their `pp.load` — `runpp_3ph` already treats
         that as an even three-phase draw.

    The returned `PandapowerGrid.load_idx` is pruned to only the
    loads that remain balanced `pp.load`s; the asymmetric ones live
    in `net.asymmetric_load` and are keyed by name there.

    Args:
        grid: the nopywer `PowerGrid` to convert. Its cables must
            already be snapped (run `analyze` or load via GeoJSON).
        load_pf: load power factor, used to derive per-leg reactive
            power for the asymmetric loads. Defaults to the global
            `PF`.
        **to_pp_kwargs: forwarded verbatim to `to_pandapower`
            (generator ratings, `x_ohm_per_km`, etc.).

    Returns:
        A `PandapowerGrid` whose `net` is ready for
        `compute_power_flow_3ph`.

    Raises:
        ValueError: propagated from `to_pandapower` if the grid has
            no cables or a cable references an unknown node.
        ImportError: if pandapower is not installed.
    """
    pp, _ = _import_pandapower()
    pp_grid = to_pandapower(grid, load_pf=load_pf, **to_pp_kwargs)
    net = pp_grid.net

    # 1. zero-sequence line parameters
    net.line["r0_ohm_per_km"] = net.line["r_ohm_per_km"] * config.R0_OVER_R1
    net.line["x0_ohm_per_km"] = net.line["x_ohm_per_km"] * config.X0_OVER_X1
    net.line["c0_nf_per_km"] = config.C0_NF_PER_KM

    # 2. source vector group / earthing
    net.ext_grid["r0x0_max"] = config.SOURCE_R0X0_MAX
    net.ext_grid["x0x_max"] = config.SOURCE_X0X_MAX

    # 3. swap explicitly-phased loads for asymmetric loads
    tan_phi = math.tan(math.acos(load_pf)) if 0 < load_pf < 1 else 0.0
    for name, node in grid.nodes.items():
        if node.is_generator or node.power_watts <= 0:
            continue
        p_l1, p_l2, p_l3 = _phase_split(node.phase, node.power_watts)
        if p_l1 == p_l2 == p_l3:
            continue  # balanced — to_pandapower's pp.load is already correct

        net.load.drop(index=pp_grid.load_idx.pop(name), inplace=True)
        pp.create_asymmetric_load(
            net,
            bus=pp_grid.bus_idx[name],
            p_a_mw=p_l1 / 1e6,
            p_b_mw=p_l2 / 1e6,
            p_c_mw=p_l3 / 1e6,
            q_a_mvar=p_l1 * tan_phi / 1e6,
            q_b_mvar=p_l2 * tan_phi / 1e6,
            q_c_mvar=p_l3 * tan_phi / 1e6,
            name=name,
        )

    return pp_grid


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


def compute_power_flow_3ph(pp_grid: PandapowerGrid) -> PowerFlow3phResults:
    """Run asymmetric AC power flow on a net from `to_pandapower_3ph`.

    Calls `pp.runpp_3ph` and translates `res_bus_3ph` / `res_line_3ph`
    into nopywer-native units (volts P-N, amps, percent). Does not
    mutate the source `PowerGrid`.

    The net must have been built by `to_pandapower_3ph` — a plain
    `to_pandapower` net lacks the zero-sequence parameters and
    `runpp_3ph` will not solve it.

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
    pp, _ = _import_pandapower()
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
