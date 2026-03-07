"""Optimal cable layout via MST + cost-based local search.

Phase 1 -- build a minimum spanning tree (MST) that minimises total cable
length.

Phase 2 -- iteratively re-parent nodes so that the total *cable cost*
(length x price-per-metre, where price depends on cable thickness / power
flowing through it) is minimised.

This naturally produces a shallower, more star-like topology with fewer
heavy cables, matching real-world power distribution practices.
"""

import networkx as nx

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode, pick_cable_for


def optimize_layout(
    nodes: list[PowerNode],
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M,
) -> list[Cable]:
    """Compute a cable layout in a few simple steps.

    1. Build the complete distance graph between coordinates
    2. Extract the minimum spanning tree, minimizing total length
    3. Root that tree from the generator (BFS traversal)
    4. Re-parent nodes to reduce total cable cost.
    5. Convert the final tree into sized cables and compute power flow.
    """
    generators = [n for n in nodes if n.is_generator]
    if not generators:
        raise ValueError("At least one generator is required")
    if len(generators) > 1:
        raise ValueError("Only one generator is supported for now")

    nodes_by_name = {n.name: n for n in nodes}
    dist_graph = _build_distance_graph(nodes)

    mst = nx.minimum_spanning_tree(dist_graph)
    tree = nx.bfs_tree(mst, generators[0].name)
    tree = _reduce_cable_cost(tree, dist_graph, nodes_by_name, generators[0].name)

    cables: list[Cable] = []
    for i, (src, dst) in enumerate(tree.edges()):
        d = dist_graph[src][dst]["weight"]
        cables.append(
            Cable(
                id=f"optim_{i}",
                length_m=d + extra_cable_m,
                from_node=src,
                to_node=dst,
                from_coords=(nodes_by_name[src].lon, nodes_by_name[src].lat),
                to_coords=(nodes_by_name[dst].lon, nodes_by_name[dst].lat),
            )
        )

    return _compute_power_flow(cables, nodes_by_name)


def _build_distance_graph(nodes: list[PowerNode]) -> nx.Graph:
    g = nx.Graph()
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            d = geodesic_distance_m(a.lon, a.lat, b.lon, b.lat)
            g.add_edge(a.name, b.name, weight=d)
    return g


def _cum_power_map(
    tree: nx.DiGraph, nodes_by_name: dict[str, PowerNode], root: str
) -> dict[str, float]:
    order = list(reversed(list(nx.bfs_tree(tree, root))))
    cum: dict[str, float] = {}
    for node in order:
        own = nodes_by_name[node].power_watts if node in nodes_by_name else 0.0
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
        dist_graph[s][d]["weight"] * pick_cable_for(cum[d]).tier_cost for s, d in tree.edges()
    )


def _reduce_cable_cost(
    tree: nx.DiGraph,
    dist_graph: nx.Graph,
    all_nodes: dict[str, PowerNode],
    root: str,
    max_rounds: int = 10,  # arbitrary, just to avoid infinite loops
) -> nx.DiGraph:
    """Lower total cable cost by trying simple local rewires.

    Nodes are visited from the leaves back toward the generator so child
    subtrees are mostly settled before their parents are tested.

    For each node, candidate parents are taken from:
    - its 15 closest nodes in the distance graph
    - the generator
    - a few ancestors of its current parent

    Descendants and the current parent are excluded to avoid cycles and
    pointless no-op moves.

    Why 15? It is a heuristic: enough nearby options to try useful rewires,
    but still cheap to evaluate.
    """
    # For each node name, store a list of the 15 closest node names.
    node_to_neighbors = _precompute_nearest(dist_graph, 15)
    # Current best total tree cost: sum(length x cable price) over all edges.
    total_tree_cost = _tree_cost(tree, dist_graph, all_nodes, root)

    for _ in range(max_rounds):
        improved = False
        reversed_order = list(reversed(list(nx.bfs_tree(tree, root))))
        for node in reversed_order:
            if node == root:
                continue

            cur_parent = next(tree.predecessors(node))
            desc = set(nx.descendants(tree, node))
            desc.add(node)

            candidates = _gather_candidates(node, cur_parent, root, desc, node_to_neighbors, tree)
            best_cand = cur_parent

            for cand in candidates:
                tree.remove_edge(cur_parent, node)
                tree.add_edge(cand, node)
                c = _tree_cost(tree, dist_graph, all_nodes, root)
                tree.remove_edge(cand, node)
                tree.add_edge(cur_parent, node)

                if c < total_tree_cost - 0.01:  # at least 1% better !
                    total_tree_cost = c
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
    for _ in range(5):  # try more than 1 or 2 ancestors but not the entire way
        preds = list(tree.predecessors(ancestor))
        if not preds:
            break
        ancestor = preds[0]
        cands.add(ancestor)
    cands -= descendants
    cands.discard(cur_parent)
    return list(cands)


def _compute_power_flow(cables: list[Cable], nodes_by_name: dict[str, PowerNode]) -> list[Cable]:
    children_of: dict[str, list[str]] = {}
    for c in cables:
        children_of.setdefault(c.from_node, []).append(c.to_node)

    cum: dict[str, float] = {}

    def walk(name: str) -> float:
        own = nodes_by_name[name].power_watts if name in nodes_by_name else 0.0
        total = own + sum(walk(ch) for ch in children_of.get(name, []))
        cum[name] = total
        return total

    roots = {c.from_node for c in cables} - {c.to_node for c in cables}
    for r in roots:
        walk(r)

    for i, cable in enumerate(cables):
        power = cum.get(cable.to_node, 0.0)
        cable_cls = pick_cable_for(power)
        per_phase = power / (cable_cls.num_phases * V0 * PF)
        cables[i] = cable_cls(
            id=cable.id,
            length_m=cable.length_m,
            from_node=cable.from_node,
            to_node=cable.to_node,
            from_coords=cable.from_coords,
            to_coords=cable.to_coords,
            current_per_phase=[per_phase] * cable_cls.num_phases,
        )
    return cables
