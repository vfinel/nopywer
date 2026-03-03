"""Optimal cable layout via MST + cost-based local search.

Phase 1 -- build a minimum spanning tree (MST) that minimises total cable
length.  Phase 2 -- iteratively re-parent nodes so that the total *cable cost*
(length x price-per-metre, where price depends on cable thickness / power
flowing through it) is minimised.  This naturally produces a shallower, more
star-like topology with fewer heavy cables, matching real-world power
distribution practice.
"""

import networkx as nx

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode

_CABLE_TIERS: list[tuple[int, float, int, str]] = [
    (16, 2.5, 16, "1P 16A 2.5mm²"),
    (32, 6.0, 32, "3P 32A 6mm²"),
    (63, 16.0, 63, "3P 63A 16mm²"),
    (125, 35.0, 125, "3P 125A 35mm²"),
]

_TIER_COST_PER_M: dict[int, float] = {16: 1.0, 32: 3.0, 63: 8.0, 125: 20.0}

_CANDIDATE_K = 15


def _size_cable(power_watts: float) -> tuple[float, float, str]:
    """Pick cable area and plug rating for the given power.

    Per-phase current on a balanced 3-phase system:
        I_phase = P / (3 x V_phase x PF)
    """
    per_phase = power_watts / (3 * V0 * PF)
    for max_a, area, plugs, label in _CABLE_TIERS:
        if per_phase <= max_a:
            return area, float(plugs), label
    last = _CABLE_TIERS[-1]
    return last[1], float(last[2]), last[3]


def _tier_cost(power_watts: float) -> float:
    _, plugs, _ = _size_cable(power_watts)
    return _TIER_COST_PER_M.get(int(plugs), 20.0)


def optimize_layout(
    nodes: list[PowerNode],
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M,
) -> list[Cable]:
    """Find an optimal cable tree connecting *nodes*.

    Returns sized Cable objects ready for analysis.
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
    tree = _reduce_cable_cost(tree, dist_graph, all_nodes, gen_root)

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


def _cum_power_map(
    tree: nx.DiGraph, all_nodes: dict[str, PowerNode], root: str
) -> dict[str, float]:
    order = list(reversed(list(nx.bfs_tree(tree, root))))
    cum: dict[str, float] = {}
    for node in order:
        own = all_nodes[node].power_watts if node in all_nodes else 0.0
        cum[node] = own + sum(cum.get(ch, 0.0) for ch in tree.successors(node))
    return cum


def _tree_cost(
    tree: nx.DiGraph,
    dist_graph: nx.Graph,
    all_nodes: dict[str, PowerNode],
    root: str,
) -> float:
    cum = _cum_power_map(tree, all_nodes, root)
    return sum(
        dist_graph[s][d]["weight"] * _tier_cost(cum[d])
        for s, d in tree.edges()
        if "__super" not in s and "__super" not in d
    )


def _reduce_cable_cost(
    tree: nx.DiGraph,
    dist_graph: nx.Graph,
    all_nodes: dict[str, PowerNode],
    root: str,
    max_rounds: int = 20,
) -> nx.DiGraph:
    """Re-parent nodes to minimise total cable cost (length x tier price)."""
    nearest = _precompute_nearest(dist_graph, _CANDIDATE_K)
    best = _tree_cost(tree, dist_graph, all_nodes, root)

    for _ in range(max_rounds):
        improved = False
        order = list(reversed(list(nx.bfs_tree(tree, root))))

        for node in order:
            if node == root:
                continue

            cur_parent = next(tree.predecessors(node))
            desc = set(nx.descendants(tree, node))
            desc.add(node)

            candidates = _gather_candidates(node, cur_parent, root, desc, nearest, tree)
            best_cand = cur_parent

            for cand in candidates:
                tree.remove_edge(cur_parent, node)
                tree.add_edge(cand, node)
                c = _tree_cost(tree, dist_graph, all_nodes, root)
                tree.remove_edge(cand, node)
                tree.add_edge(cur_parent, node)

                if c < best - 0.01:
                    best = c
                    best_cand = cand

            if best_cand != cur_parent:
                tree.remove_edge(cur_parent, node)
                tree.add_edge(best_cand, node)
                improved = True

        if not improved:
            break

    return tree


def _precompute_nearest(dist_graph: nx.Graph, k: int) -> dict[str, list[str]]:
    nearest: dict[str, list[str]] = {}
    for n in dist_graph.nodes():
        neighbors = sorted((dist_graph[n][m]["weight"], m) for m in dist_graph.neighbors(n))
        nearest[n] = [m for _, m in neighbors[:k]]
    return nearest


def _gather_candidates(
    node: str,
    cur_parent: str,
    root: str,
    descendants: set[str],
    nearest: dict[str, list[str]],
    tree: nx.DiGraph,
) -> list[str]:
    cands: set[str] = set()
    cands.update(nearest.get(node, []))
    cands.add(root)
    ancestor = cur_parent
    for _ in range(5):
        preds = list(tree.predecessors(ancestor))
        if not preds:
            break
        ancestor = preds[0]
        cands.add(ancestor)
    cands -= descendants
    cands.discard(cur_parent)
    return list(cands)


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
        area, plugs, _ = _size_cable(power)
        cable.area_mm2 = area
        cable.plugs_and_sockets_a = plugs
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
