"""Optimal cable layout via minimum spanning tree (MST).

Build a minimum spanning tree that minimises total cable length between
generators and loads using NetworkX.
"""

import networkx as nx

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode


def optimize_layout(
    nodes: list[PowerNode],
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M,
) -> list[Cable]:
    """Find an optimal cable tree connecting *nodes*.

    Returns Cable objects ready for analysis.
    """
    generators = [n for n in nodes if n.is_generator]
    loads = [n for n in nodes if not n.is_generator]

    if not generators:
        raise ValueError("At least one generator is required")
    if not loads:
        return []

    all_nodes = {n.name: n for n in nodes}
    dist_graph = _build_distance_graph(nodes)

    use_super = len(generators) > 1
    if use_super:
        super_name = "__super_gen__"
        for g in generators:
            dist_graph.add_edge(super_name, g.name, weight=0.0)
        gen_root = super_name
    else:
        gen_root = generators[0].name

    mst = nx.minimum_spanning_tree(dist_graph)
    tree = nx.bfs_tree(mst, gen_root)

    cables: list[Cable] = []
    for i, (src, dst) in enumerate(tree.edges()):
        if use_super and "__super" in (src, dst):
            continue
        d = dist_graph[src][dst]["weight"]
        cables.append(
            Cable(
                id=f"optim_{i}",
                length_m=d + extra_cable_m,
                from_node=src,
                to_node=dst,
                from_coords=(all_nodes[src].lon, all_nodes[src].lat),
                to_coords=(all_nodes[dst].lon, all_nodes[dst].lat),
            )
        )

    _compute_power_flow(cables, all_nodes)
    return cables


def _build_distance_graph(nodes: list[PowerNode]) -> nx.Graph:
    g = nx.Graph()
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            d = geodesic_distance_m(a.lon, a.lat, b.lon, b.lat)
            g.add_edge(a.name, b.name, weight=d)
    return g


def _compute_power_flow(cables: list[Cable], all_nodes: dict[str, PowerNode]) -> None:
    children_of: dict[str, list[str]] = {}
    for c in cables:
        children_of.setdefault(c.from_node, []).append(c.to_node)

    cum: dict[str, float] = {}

    def walk(name: str) -> float:
        own = all_nodes[name].power_watts if name in all_nodes else 0.0
        total = own + sum(walk(ch) for ch in children_of.get(name, []))
        cum[name] = total
        return total

    roots = {c.from_node for c in cables} - {c.to_node for c in cables}
    for r in roots:
        walk(r)

    for cable in cables:
        power = cum.get(cable.to_node, 0.0)
        per_phase = power / (3 * V0 * PF)
        cable.current_per_phase = [round(per_phase, 2)] * 3


def layout_to_networkx(
    cables: list[Cable],
    nodes: dict[str, PowerNode] | None = None,
) -> nx.DiGraph:
    """Convert optimizer output to a NetworkX DiGraph for visualization."""
    g = nx.DiGraph()
    for cable in cables:
        g.add_edge(cable.from_node, cable.to_node, weight=cable.length_m)
    if nodes:
        for name, node in nodes.items():
            g.nodes[name]["pos"] = (node.lon, node.lat)
            g.nodes[name]["power"] = node.power_watts
            g.nodes[name]["is_generator"] = node.is_generator
    return g
