from pathlib import Path

import pytest

from nopywer.io import load_geojson
from nopywer.models import CABLE_TYPES, PowerGrid, PowerNode
from nopywer.optimize_milp import optimize_layout

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _node(
    name: str,
    lon: float,
    lat: float,
    power_watts: float = 0.0,
    is_generator: bool = False,
) -> PowerNode:
    return PowerNode(
        name=name,
        lon=lon,
        lat=lat,
        power_watts=power_watts,
        is_generator=is_generator,
    )


def _grid(nodes: list[PowerNode]) -> PowerGrid:
    return PowerGrid(nodes={node.name: node for node in nodes}, cables={})


def test_cable_tier_labels_are_unique():
    labels = [cable_type.cable_type_label() for cable_type in CABLE_TYPES]
    assert len(labels) == len(set(labels))


def test_optimize_layout_rejects_all_zero_objective_weights():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    with pytest.raises(ValueError, match="At least one objective weight must be > 0"):
        optimize_layout(
            _grid(nodes),
            weight_cost=0.0,
            weight_length=0.0,
            weight_power_distance=0.0,
            weight_voltage_drop=0.0,
            weight_cumulative_voltage_drop=0.0,
        )


def test_optimize_layout_rejects_negative_objective_weight():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    with pytest.raises(ValueError, match="Objective weights must be non-negative"):
        optimize_layout(_grid(nodes), weight_cost=-1.0, weight_length=1.0)


def test_optimize_layout_accepts_voltage_drop_only_weight():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    grid = optimize_layout(
        _grid(nodes),
        weight_cost=0.0,
        weight_length=0.0,
        weight_power_distance=0.0,
        weight_voltage_drop=1.0,
        time_limit_s=10,
        solver_msg=False,
    )
    assert len(grid.cables) == 1


def test_optimize_layout_accepts_cumulative_voltage_drop_only_weight():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    grid = optimize_layout(
        _grid(nodes),
        weight_cost=0.0,
        weight_length=0.0,
        weight_power_distance=0.0,
        weight_voltage_drop=0.0,
        weight_cumulative_voltage_drop=1.0,
        time_limit_s=10,
        solver_msg=False,
    )
    assert len(grid.cables) == 1


def test_optimize_layout_rejects_unknown_node_in_voltage_drop_caps():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    with pytest.raises(ValueError, match="unknown nodes"):
        optimize_layout(
            _grid(nodes),
            max_voltage_drop_percent_by_node={"does_not_exist": 3.0},
        )


def test_optimize_layout_fails_with_impossible_voltage_drop_cap():
    nodes = [
        _node("gen", -0.1, 51.5, is_generator=True),
        _node("load", -0.11, 51.51, power_watts=1000.0),
    ]
    with pytest.raises(RuntimeError, match="Infeasible"):
        optimize_layout(
            _grid(nodes),
            weight_cost=1.0,
            max_voltage_drop_percent=0.0,
            time_limit_s=10,
            solver_msg=False,
        )


@pytest.mark.integration
def test_optimize_milp_runs_on_real_fixture():
    nodes, _ = load_geojson(FIXTURES / "input_nodes.geojson")
    grid = PowerGrid(nodes=nodes, cables={})
    load_count = sum(1 for n in grid.nodes.values() if not n.is_generator)

    grid = optimize_layout(grid, candidate_k=8, time_limit_s=30, solver_msg=False)
    cables = list(grid.cables.values())

    assert len(cables) == load_count
    assert all(c.from_node != c.to_node for c in cables)
    assert all(c.length_m > 0 for c in cables)
