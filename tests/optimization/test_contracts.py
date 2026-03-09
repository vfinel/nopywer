import networkx as nx
import pytest

from nopywer.constants import PF, V0
from nopywer.models import Cable125A, Cable16A, Cable32A, Cable63A, PowerGrid, PowerNode, pick_cable_for
from nopywer.optimize import (
    _build_distance_graph,
    _reduce_cable_cost,
    _tree_cost,
    optimize_layout,
)


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


def _basic_nodes() -> list[PowerNode]:
    return [
        _node("generator", 0.0, 0.0, is_generator=True),
        _node("a", 0.0010, 0.0001, 2000),
        _node("b", 0.0024, 0.0005, 3000),
        _node("c", -0.0011, 0.0007, 4000),
        _node("d", 0.0004, -0.0014, 1500),
    ]


def _grid(nodes: list[PowerNode]) -> PowerGrid:
    return PowerGrid(nodes={node.name: node for node in nodes}, cables={})


def _power_for_current(current_a: float, num_phases: int) -> float:
    return current_a * num_phases * V0 * PF


def test_optimize_layout_requires_a_generator():
    loads_only = [
        _node("a", 0.0, 0.0, 1000),
        _node("b", 0.001, 0.0, 2000),
    ]
    with pytest.raises(ValueError, match="At least one generator is required"):
        optimize_layout(_grid(loads_only))


def test_optimize_layout_returns_tree_with_one_parent_per_load():
    nodes = _basic_nodes()
    grid = optimize_layout(_grid(nodes), extra_cable_m=0.0)
    cables = list(grid.cables.values())

    generator_names = {n.name for n in nodes if n.is_generator}
    load_names = {n.name for n in nodes if not n.is_generator}
    graph = nx.DiGraph((c.from_node, c.to_node) for c in cables)

    assert len(cables) == len(load_names)
    assert all(c.from_node != c.to_node for c in cables)
    assert all(c.from_node in generator_names | load_names for c in cables)
    assert all(c.to_node in load_names for c in cables)
    assert all(c.length_m > 0 for c in cables)

    for load in load_names:
        assert graph.in_degree(load) == 1
    for gen in generator_names:
        assert graph.in_degree(gen) == 0

    reachable = set()
    for gen in generator_names:
        reachable.add(gen)
        reachable.update(nx.descendants(graph, gen))
    assert load_names.issubset(reachable)


def test_extra_cable_m_is_added_once_per_edge():
    nodes = _basic_nodes()
    base = optimize_layout(_grid(nodes), extra_cable_m=0.0)
    padded = optimize_layout(_grid(nodes), extra_cable_m=7.5)

    base_cables = list(base.cables.values())
    padded_cables = list(padded.cables.values())
    base_total = sum(c.length_m for c in base_cables)
    padded_total = sum(c.length_m for c in padded_cables)
    assert padded_total - base_total == pytest.approx(7.5 * len(base_cables), abs=1e-6)


def test_reduce_cable_cost_never_increases_tree_cost():
    nodes = _basic_nodes()
    all_nodes = {n.name: n for n in nodes}
    dist_graph = _build_distance_graph(nodes)
    mst = nx.minimum_spanning_tree(dist_graph)
    initial_tree = nx.bfs_tree(mst, "generator")

    initial_cost = _tree_cost(initial_tree, dist_graph, all_nodes, "generator")
    improved_tree = _reduce_cable_cost(initial_tree.copy(), dist_graph, all_nodes, "generator")
    improved_cost = _tree_cost(improved_tree, dist_graph, all_nodes, "generator")

    assert improved_cost <= initial_cost + 1e-9


@pytest.mark.parametrize("amps", [16, 32, 63, 125])
def test_pick_cable_for_thresholds_are_inclusive(amps: int):
    expected = {
        16: Cable16A,
        32: Cable32A,
        63: Cable63A,
        125: Cable125A,
    }[amps]
    cable_cls = pick_cable_for(_power_for_current(float(amps), expected.num_phases))
    assert cable_cls is expected


@pytest.mark.parametrize(
    ("amps", "expected_next"),
    [(16, Cable32A), (32, Cable63A), (63, Cable125A)],
)
def test_pick_cable_for_above_threshold_upsizes(amps: int, expected_next: type):
    num_phases = {16: Cable16A, 32: Cable32A, 63: Cable63A}[amps].num_phases
    cable_cls = pick_cable_for(_power_for_current(float(amps), num_phases) + 1e-6)
    assert cable_cls is expected_next
