"""MILP-based cable layout optimizer.

This module provides a first combined MILP that jointly decides:
- tree topology (directed arborescence from one generator),
- cable tier per selected edge,
- power flow on selected edges.

Input and output mirror the heuristic optimizer: `PowerGrid` in,
`PowerGrid` out.

The solver mutates the provided `PowerGrid` in place. It reads optimization
inputs from `grid.nodes`, computes a fresh cable layout, and replaces
`grid.cables` with the optimized result before returning the same `grid`
instance.

IMPORTANT LINEARIZATION NOTE:
This solver uses a linearized electrical model to stay in MILP form.
Voltage-drop and current relationships are approximated from:
`I ~= P / (phase * V0 * PF)` and `V_drop ~= I * R`.
It does NOT solve full nonlinear AC load-flow equations (no angle/reactive
power coupling, no exact meshed-flow physics). Treat results as planning-grade
approximations and validate critical layouts with a detailed power-flow check.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

import pulp

from .constants import EXTRA_CABLE_LENGTH_M, PF, RHO_COPPER, V0
from .geometry import geodesic_distance_m
from .io import load_geojson
from .models import CABLE_TYPES, Cable, PowerGrid, PowerNode


class OptimiseLayoutFn(Protocol):
    def __call__(self, grid: PowerGrid, **kwargs: Any) -> PowerGrid: ...


def optimize_layout(
    grid: PowerGrid,
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M,
    candidate_k: int | None = 12,
    time_limit_s: int | None = 60,
    solver_msg: bool = False,
    weight_cost: float = 1.0,
    weight_length: float = 0.0,
    weight_power_distance: float = 0.0,
    weight_voltage_drop: float = 0.0,
    weight_cumulative_voltage_drop: float = 0.0,
    max_voltage_drop_percent: float | None = None,
    max_voltage_drop_percent_by_node: dict[str, float] | None = None,
) -> PowerGrid:
    """Solve a combined MILP for topology, cable tiering, and power flow.

    This model builds a directed arborescence rooted at the generator while
    simultaneously sizing each selected edge with one cable tier and routing
    electrical demand through that tree.

    Contract:
    Use this on a `PowerGrid` whose `nodes` are populated and whose `cables`
    represent no fixed topology. The solve derives a fresh layout from
    `grid.nodes`, mutates `grid.cables` in place, and returns the same `grid`
    instance, matching the public contract of the heuristic optimizer.

    IMPORTANT:
    Electrical behavior is linearized for tractability. This model is intended
    for optimization/planning, not as a substitute for full AC verification.
    Use a detailed load-flow tool for final engineering sign-off.

    Decision variables:
        - `x[i,j] in {0,1}`:
            1 iff directed edge `(i,j)` is selected in the final topology.
        - `y[i,j,t] in {0,1}`:
            1 iff edge `(i,j)` is selected with cable tier `t`.
            Exactly one tier is chosen when an edge is active.
        - `p[i,j] >= 0`:
            electrical power flow in watts routed on edge `(i,j)`.
        - `u[i,j] >= 0`:
            artificial single-commodity connectivity flow used only to prevent
            disconnected subtours and enforce root reachability.

    Weighted objective:
        Minimize:
            `weight_cost * sum_{i,j,t} L_ij * C_t * y[i,j,t]`
          + `weight_length * sum_{i,j} L_ij * x[i,j]`
          + `weight_power_distance * sum_{i,j} L_ij * p[i,j]`
          + `weight_voltage_drop * sum_{i,j,t} K_ijt * p_t[i,j,t]`
          + `weight_cumulative_voltage_drop * sum_{n in loads} v[n]`
        where:
            - `L_ij = geodesic_distance(i,j) + extra_cable_m`
            - `C_t = tier cost-per-meter coefficient`
            - `p_t[i,j,t]` is power routed on edge `(i,j)` through tier `t`
            - `K_ijt = rho * L_ij / (A_t * phase_t * V0 * PF)`
              (a linearized voltage-drop coefficient)
            - `v[n]` is cumulative source-to-node voltage drop in volts

        Interpretation:
            - Increasing `weight_cost` pushes the model toward cheaper cable
              tiers, potentially accepting longer routes.
            - Increasing `weight_length` pushes the model toward shorter routes,
              potentially requiring more expensive high-capacity tiers.
            - Increasing `weight_power_distance` discourages routing large
              amounts of power over long paths.
            - Increasing `weight_voltage_drop` penalizes long, highly loaded,
              and small-area cable choices.
            - Increasing `weight_cumulative_voltage_drop` directly penalizes
              end-to-end drops at load nodes.

    Constraint families:
        1. Arborescence shape:
            - Every load has exactly one incoming selected edge.
            - Root has zero incoming selected edges.
            - Total selected edges is `|V| - 1`.
        2. Tier-edge coupling and capacity:
            - `sum_t y[i,j,t] = x[i,j]` for each candidate edge.
            - `p[i,j] = sum_t p_t[i,j,t]`.
            - `p_t[i,j,t] <= capacity_t * y[i,j,t]`.
        3. Connectivity commodity (subtour elimination):
            - Each load consumes one unit of `u`.
            - Root emits exactly number-of-loads units of `u`.
            - `u[i,j] <= n_loads * x[i,j]` blocks commodity on inactive edges.
        4. Electrical flow conservation:
            - Each load has net inflow equal to its demand in watts.
            - Root has net outflow equal to total demand.
        5. Cumulative voltage-drop propagation:
            - Root drop is fixed to zero.
            - For selected edge `(i,j)`, enforce `v[j] = v[i] + drop[i,j]`.
            - Optional hard limits cap `v[n]` per load node.

    Args:
        grid: Input power grid. Exactly one generator node is supported in
            this model. All non-generator nodes are treated as loads. The
            solver reads topology inputs from `grid.nodes` and mutates
            `grid.cables` in place to store a newly optimized layout.
        extra_cable_m: Slack length added to each selected cable segment in
            the objective and returned cable lengths.
        candidate_k: Number of nearest-neighbor candidate arcs per node.
            Use `0` or `None` to allow the full directed complete graph.
        time_limit_s: CBC solver time limit in seconds.
        solver_msg: Whether to print CBC solver logs.
        weight_cost: Coefficient for the cable-tier cost objective term:
            `sum(length_m * tier_cost_per_m)`.
        weight_length: Coefficient for the pure cable-length objective term:
            `sum(length_m)`.
        weight_power_distance: Coefficient for power-distance term:
            `sum(length_m * power_watts)`.
        weight_voltage_drop: Coefficient for linearized voltage-drop term:
            `sum(vdrop_proxy_volts)`.
        weight_cumulative_voltage_drop: Coefficient for cumulative
            source-to-node drop term: `sum(vdrop_at_load_volts)`.
        max_voltage_drop_percent: Optional global hard cap on cumulative
            drop for every load node, expressed as `%` of `V0`.
        max_voltage_drop_percent_by_node: Optional per-node hard caps in `%`
            of `V0`, keyed by load node name.

    Returns:
        The same `PowerGrid` instance, after mutating `grid.cables` in place
        with sized optimized cables.

    Raises:
        ValueError: If objective weights are invalid or node-specific voltage
            caps reference unknown nodes.
        RuntimeError: If the MILP does not solve to an optimal solution.
    """
    nodes = list(grid.nodes.values())

    _validate_inputs(
        nodes=nodes,
        weight_cost=weight_cost,
        weight_length=weight_length,
        weight_power_distance=weight_power_distance,
        weight_voltage_drop=weight_voltage_drop,
        weight_cumulative_voltage_drop=weight_cumulative_voltage_drop,
        max_voltage_drop_percent=max_voltage_drop_percent,
        max_voltage_drop_percent_by_node=max_voltage_drop_percent_by_node,
    )
    use_voltage_drop_enhancements: bool = (
        (weight_voltage_drop > 0)
        or (weight_cumulative_voltage_drop > 0)
        or (max_voltage_drop_percent is not None)
        or bool(max_voltage_drop_percent_by_node)
    )

    loads: list[PowerNode] = _select_load_nodes(nodes)

    if not loads:
        grid.cables = {}
        return grid

    root: str = grid.generator.name
    node_by_name: dict[str, PowerNode] = grid.nodes
    names: list[str] = [n.name for n in nodes]
    load_names: list[str] = [n.name for n in loads]

    distance: dict[tuple[str, str], float] = _build_distance_map(nodes)
    arcs: list[tuple[str, str]] = _candidate_arcs(names, root, distance, candidate_k)
    tiers: list[str] = [cable_cls.cable_type_label() for cable_cls in CABLE_TYPES]
    tier_by_label: dict[str, type[Cable]] = {
        cable_cls.cable_type_label(): cable_cls for cable_cls in CABLE_TYPES
    }
    tier_area: dict[str, float] = {
        cable_cls.cable_type_label(): float(cable_cls.area_mm2) for cable_cls in CABLE_TYPES
    }
    tier_cost: dict[str, float] = {
        cable_cls.cable_type_label(): float(cable_cls.tier_cost) for cable_cls in CABLE_TYPES
    }
    tier_cap: dict[str, float] = {
        cable_cls.cable_type_label(): cable_cls.capacity_w() for cable_cls in CABLE_TYPES
    }
    tier_phase: dict[str, int] = {
        cable_cls.cable_type_label(): cable_cls.num_phases for cable_cls in CABLE_TYPES
    }

    prob: Any = pulp.LpProblem("nopywer_layout_milp", pulp.LpMinimize)

    # Symbol mapping (paper -> code):
    # x_ij -> edge_selected[(i, j)]
    # y_ijk -> tier_selected[(i, j, k)]
    # p_ij -> power_flow_w[(i, j)]
    # pt_ijk -> power_flow_w_by_tier[(i, j, k)] [voltage model enabled only]
    # vd_ij -> edge_voltage_drop_v[(i, j)] [voltage model enabled only]
    # v_n -> node_voltage_drop_v[n] [voltage model enabled only]
    # u_ij -> connectivity_flow[(i, j)]
    edge_selected: dict[tuple[str, str], Any] = pulp.LpVariable.dicts(
        "x", arcs, lowBound=0, upBound=1, cat="Binary"
    )
    tier_selected: dict[tuple[str, str, str], Any] = pulp.LpVariable.dicts(
        "y",
        ((i, j, t) for (i, j) in arcs for t in tiers),
        lowBound=0,
        upBound=1,
        cat="Binary",
    )
    power_flow_w: dict[tuple[str, str], Any] = pulp.LpVariable.dicts(
        "p", arcs, lowBound=0, cat="Continuous"
    )
    power_flow_w_by_tier: dict[tuple[str, str, str], Any] = {}
    edge_voltage_drop_v: dict[tuple[str, str], Any] = {}
    node_voltage_drop_v: dict[str, Any] = {}
    if use_voltage_drop_enhancements:
        power_flow_w_by_tier = pulp.LpVariable.dicts(
            "pt",
            ((i, j, t) for (i, j) in arcs for t in tiers),
            lowBound=0,
            cat="Continuous",
        )
        edge_voltage_drop_v = pulp.LpVariable.dicts(
            "vd_edge", arcs, lowBound=0, cat="Continuous"
        )
        node_voltage_drop_v = pulp.LpVariable.dicts(
            "vd_node", names, lowBound=0, cat="Continuous"
        )
    connectivity_flow: dict[tuple[str, str], Any] = pulp.LpVariable.dicts(
        "u", arcs, lowBound=0, cat="Continuous"
    )

    cost_objective = pulp.lpSum(
        (distance[(i, j)] + extra_cable_m) * tier_cost[t] * tier_selected[(i, j, t)]
        for i, j in arcs
        for t in tiers
    )
    length_objective = pulp.lpSum(
        (distance[(i, j)] + extra_cable_m) * edge_selected[(i, j)]
        for i, j in arcs
    )
    power_distance_objective = pulp.lpSum(
        (distance[(i, j)] + extra_cable_m) * power_flow_w[(i, j)]
        for i, j in arcs
    )

    voltage_drop_objective: Any = 0.0
    cumulative_voltage_drop_objective: Any = 0.0
    if use_voltage_drop_enhancements:
        voltage_drop_objective = pulp.lpSum(
            (
                RHO_COPPER
                * (distance[(i, j)] + extra_cable_m)
                / (tier_area[t] * float(tier_phase[t]) * V0 * PF)
            )
            * power_flow_w_by_tier[(i, j, t)]
            for i, j in arcs
            for t in tiers
        )
        cumulative_voltage_drop_objective = pulp.lpSum(
            node_voltage_drop_v[n] for n in load_names
        )

    prob += (
        (weight_cost * cost_objective)
        + (weight_length * length_objective)
        + (weight_power_distance * power_distance_objective)
        + (weight_voltage_drop * voltage_drop_objective)
        + (weight_cumulative_voltage_drop * cumulative_voltage_drop_objective)
    )

    for j in load_names:
        prob += pulp.lpSum(edge_selected[(i, j)] for i, k in arcs if k == j) == 1

    prob += pulp.lpSum(edge_selected[(i, j)] for i, j in arcs if j == root) == 0
    prob += pulp.lpSum(edge_selected[(i, j)] for i, j in arcs) == len(nodes) - 1

    for i, j in arcs:
        prob += pulp.lpSum(tier_selected[(i, j, t)] for t in tiers) == edge_selected[(i, j)]

        if use_voltage_drop_enhancements:
            prob += power_flow_w[(i, j)] == pulp.lpSum(
                power_flow_w_by_tier[(i, j, t)] for t in tiers
            )
            for t in tiers:
                prob += power_flow_w_by_tier[(i, j, t)] <= (
                    tier_cap[t] * tier_selected[(i, j, t)]
                )

            prob += edge_voltage_drop_v[(i, j)] == pulp.lpSum(
                (
                    RHO_COPPER
                    * (distance[(i, j)] + extra_cable_m)
                    / (tier_area[t] * float(tier_phase[t]) * V0 * PF)
                )
                * power_flow_w_by_tier[(i, j, t)]
                for t in tiers
            )
        else:
            prob += power_flow_w[(i, j)] <= pulp.lpSum(
                tier_cap[t] * tier_selected[(i, j, t)] for t in tiers
            )

    n_loads: int = len(load_names)
    for n in load_names:
        prob += (
            pulp.lpSum(connectivity_flow[(i, j)] for i, j in arcs if j == n)
            - pulp.lpSum(connectivity_flow[(i, j)] for i, j in arcs if i == n)
            == 1
        )
    prob += (
        pulp.lpSum(connectivity_flow[(i, j)] for i, j in arcs if i == root)
        - pulp.lpSum(connectivity_flow[(i, j)] for i, j in arcs if j == root)
        == n_loads
    )
    for i, j in arcs:
        prob += connectivity_flow[(i, j)] <= n_loads * edge_selected[(i, j)]

    demand: dict[str, float] = {n.name: max(0.0, float(n.power_watts)) for n in loads}
    total_demand: float = float(sum(demand.values()))
    for n in load_names:
        prob += (
            pulp.lpSum(power_flow_w[(i, j)] for i, j in arcs if j == n)
            - pulp.lpSum(power_flow_w[(i, j)] for i, j in arcs if i == n)
            == demand[n]
        )
    prob += (
        pulp.lpSum(power_flow_w[(i, j)] for i, j in arcs if i == root)
        - pulp.lpSum(power_flow_w[(i, j)] for i, j in arcs if j == root)
        == total_demand
    )

    if use_voltage_drop_enhancements:
        max_edge_drop_v: float = max(
            max(
                (
                    RHO_COPPER
                    * (distance[(i, j)] + extra_cable_m)
                    / (tier_area[t] * float(tier_phase[t]) * V0 * PF)
                )
                * tier_cap[t]
                for t in tiers
            )
            for i, j in arcs
        )
        big_m_vdrop: float = max(1.0, float(len(nodes)) * max_edge_drop_v)
        prob += node_voltage_drop_v[root] == 0
        for i, j in arcs:
            prob += node_voltage_drop_v[j] >= (
                node_voltage_drop_v[i]
                + edge_voltage_drop_v[(i, j)]
                - (big_m_vdrop * (1 - edge_selected[(i, j)]))
            )
            prob += node_voltage_drop_v[j] <= (
                node_voltage_drop_v[i]
                + edge_voltage_drop_v[(i, j)]
                + (big_m_vdrop * (1 - edge_selected[(i, j)]))
            )

        if max_voltage_drop_percent is not None:
            max_drop_v_global = V0 * (max_voltage_drop_percent / 100.0)
            for n in load_names:
                prob += node_voltage_drop_v[n] <= max_drop_v_global
        if max_voltage_drop_percent_by_node:
            for n, max_drop_percent in max_voltage_drop_percent_by_node.items():
                if n == root:
                    continue
                max_drop_v = V0 * (max_drop_percent / 100.0)
                prob += node_voltage_drop_v[n] <= max_drop_v

    solver: Any = pulp.PULP_CBC_CMD(msg=solver_msg, timeLimit=time_limit_s)
    status: int = prob.solve(solver)
    status_name: str = pulp.LpStatus.get(status, "Unknown")
    if status_name != "Optimal":
        raise RuntimeError(
            f"MILP solve failed with status '{status_name}'. "
            "Try increasing candidate_k or time_limit_s."
        )

    chosen_arcs: list[tuple[str, str]] = [
        (i, j)
        for i, j in arcs
        if pulp.value(edge_selected[(i, j)]) and pulp.value(edge_selected[(i, j)]) > 0.5
    ]
    chosen_arcs = sorted(chosen_arcs, key=lambda e: (e[0], e[1]))

    cables: list[Cable] = []
    for idx, (src, dst) in enumerate(chosen_arcs):
        chosen_tiers: list[str] = [
            t
            for t in tiers
            if pulp.value(tier_selected[(src, dst, t)])
            and pulp.value(tier_selected[(src, dst, t)]) > 0.5
        ]
        chosen_label: str = (
            chosen_tiers[0] if chosen_tiers else CABLE_TYPES[0].cable_type_label()
        )
        cable_cls: type[Cable] = tier_by_label[chosen_label]
        power_w: float = float(pulp.value(power_flow_w[(src, dst)]) or 0.0)
        per_phase: float = round(power_w / (cable_cls.num_phases * V0 * PF), 2)

        cables.append(
            cable_cls(
                id=f"milp_{idx}",
                length_m=distance[(src, dst)] + extra_cable_m,
                phase=cable_cls.num_phases,
                from_node=src,
                to_node=dst,
                from_coords=(node_by_name[src].lon, node_by_name[src].lat),
                to_coords=(node_by_name[dst].lon, node_by_name[dst].lat),
                current_per_phase=[per_phase] * cable_cls.num_phases,
            )
        )

    grid.cables = {cable.id: cable for cable in cables}
    return grid


def optimize_layout_to_files(
    input_geojson: Path,
    output_geojson: Path = Path("milp_layout.geojson"),
    candidate_k: int | None = 12,
    time_limit_s: int | None = 60,
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M,
    solver_msg: bool = False,
    weight_cost: float = 1.0,
    weight_length: float = 0.0,
    weight_power_distance: float = 0.0,
    weight_voltage_drop: float = 0.0,
    weight_cumulative_voltage_drop: float = 0.0,
    max_voltage_drop_percent: float | None = None,
) -> int:
    """Run the MILP optimizer from a GeoJSON file and write output artifacts."""
    nodes, _ = load_geojson(input_geojson)
    grid = PowerGrid(nodes=nodes, cables={})
    grid = optimize_layout(
        grid=grid,
        extra_cable_m=extra_cable_m,
        candidate_k=candidate_k,
        time_limit_s=time_limit_s,
        solver_msg=solver_msg,
        weight_cost=weight_cost,
        weight_length=weight_length,
        weight_power_distance=weight_power_distance,
        weight_voltage_drop=weight_voltage_drop,
        weight_cumulative_voltage_drop=weight_cumulative_voltage_drop,
        max_voltage_drop_percent=max_voltage_drop_percent,
    )

    result_geojson = grid.to_geojson()
    with open(output_geojson, "w") as f:
        json.dump(result_geojson, f, indent=2)

    max_vdrop_text = (
        f"max_vdrop_percent={max_voltage_drop_percent}; "
        if max_voltage_drop_percent is not None
        else ""
    )
    print(
        f"optimized {len(grid.nodes)} nodes -> {len(grid.cables)} cables; "
        "weights("
        f"cost={weight_cost}, "
        f"length={weight_length}, "
        f"power_distance={weight_power_distance}, "
        f"voltage_drop={weight_voltage_drop}, "
        f"cumulative_voltage_drop={weight_cumulative_voltage_drop}"
        "); "
        + max_vdrop_text
        + f"geojson: {output_geojson}"
    )
    return 0


def _build_distance_map(nodes: list[PowerNode]) -> dict[tuple[str, str], float]:
    """Build directed pairwise geodesic distances between all distinct nodes."""
    distance: dict[tuple[str, str], float] = {}
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i == j:
                continue
            a, b = nodes[i], nodes[j]
            distance[(a.name, b.name)] = geodesic_distance_m(a.lon, a.lat, b.lon, b.lat)
    return distance


def _candidate_arcs(
    names: list[str],
    root: str,
    distance: dict[tuple[str, str], float],
    candidate_k: int | None,
) -> list[tuple[str, str]]:
    """Select directed candidate arcs for the MILP graph."""
    if candidate_k is None or candidate_k <= 0 or candidate_k >= (len(names) - 1):
        return [(i, j) for i in names for j in names if i != j]

    arcs: set[tuple[str, str]] = set()
    for src in names:
        ranked = sorted((distance[(src, dst)], dst) for dst in names if dst != src)
        for _, dst in ranked[:candidate_k]:
            arcs.add((src, dst))

    for n in names:
        if n == root:
            continue
        arcs.add((root, n))
        arcs.add((n, root))

    return sorted(arcs)


def _select_load_nodes(nodes: Iterable[PowerNode]) -> list[PowerNode]:
    """Return the subset of nodes that are not marked as generators."""
    return [n for n in nodes if not n.is_generator]


def _validate_inputs(
    nodes: list[PowerNode],
    weight_cost: float,
    weight_length: float,
    weight_power_distance: float,
    weight_voltage_drop: float,
    weight_cumulative_voltage_drop: float,
    max_voltage_drop_percent: float | None,
    max_voltage_drop_percent_by_node: dict[str, float] | None,
) -> None:
    objective_weights: dict[str, float] = {
        "weight_cost": weight_cost,
        "weight_length": weight_length,
        "weight_power_distance": weight_power_distance,
        "weight_voltage_drop": weight_voltage_drop,
        "weight_cumulative_voltage_drop": weight_cumulative_voltage_drop,
    }
    if any(weight < 0 for weight in objective_weights.values()):
        raise ValueError("Objective weights must be non-negative")
    if all(weight == 0 for weight in objective_weights.values()):
        raise ValueError("At least one objective weight must be > 0")
    if max_voltage_drop_percent is not None and max_voltage_drop_percent < 0:
        raise ValueError("max_voltage_drop_percent must be non-negative")
    if max_voltage_drop_percent_by_node is None:
        return

    bad_nodes = sorted(set(max_voltage_drop_percent_by_node) - set(n.name for n in nodes))
    if bad_nodes:
        raise ValueError(
            "max_voltage_drop_percent_by_node contains unknown nodes: "
            + ", ".join(bad_nodes)
        )

    bad_values = [
        f"{name}={value}"
        for name, value in max_voltage_drop_percent_by_node.items()
        if value < 0
    ]
    if bad_values:
        raise ValueError(
            "Per-node max voltage-drop percentages must be non-negative: "
            + ", ".join(bad_values)
        )
