import itertools
import pickle

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pulp

from .geometry import geodesic_distance_m


def grid2list(grid):
    """Extract nodes and edges from the grid for optimization.

    Accepts a dict[str, PowerNode] (keyed by node name).

    Returns:
        nodes: dict with only the info needed for optimization
        edges: all possible connections between two loads with geodesic distances
    """
    edges = []
    nodes = {}
    for src_name, source in grid.items():
        nodes[src_name] = {
            "power": source.power_per_phase,
            "cum_power": source.cum_power,
            "x": source.lon,
            "y": source.lat,
        }

        for dst_name, dest in grid.items():
            if src_name != dst_name:
                dist = geodesic_distance_m(
                    source.lon,
                    source.lat,
                    dest.lon,
                    dest.lat,
                )
                edges.append((src_name, dst_name, dist))

    with open("grid.pkl", "wb") as f:
        pickle.dump([nodes, edges], f)

    return nodes, edges


def find_optimal_layout(grid, edges):
    prob = pulp.LpProblem("grid_layout", pulp.LpMinimize)

    edges_conn = {
        (u, v): pulp.LpVariable(
            f"{u}_{v}",
            lowBound=0,
            upBound=1,
            cat="Integer",
        )
        for u, v, _ in edges
    }
    nodes = dict.fromkeys(grid.keys())
    for node in grid:
        nodes[node] = {
            "n_in": None,
            "n_out": None,
            "parent": "",
            "children": [],
            "power": np.sum(grid[node].power_per_phase),
            "cum_power": pulp.LpVariable(
                f"cum_power_{node}",
                lowBound=0,
                cat="Continuous",
            ),
        }

    print("\t creating objective function")
    prob += pulp.lpSum(edges_conn[e[0], e[1]] * e[2] for e in edges)

    for n in nodes:
        n_out = pulp.lpSum([edges_conn[src, dst] for src, dst, _ in edges if src == n])
        n_in = pulp.lpSum([edges_conn[src, dst] for src, dst, _ in edges if dst == n])
        nodes[n]["n_out"] = n_out
        nodes[n]["n_in"] = n_in
        if n == "generator":
            prob += n_in == 0
            prob += n_out >= 1
            prob += nodes[n]["cum_power"] == sum([load["power"] for _, load in nodes.items()])
        else:
            prob += n_in == 1

    for e in edges:
        prob.add(
            pulp.LpConstraint(
                e=edges_conn[e[0], e[1]] + edges_conn[e[1], e[0]],
                sense=pulp.LpConstraintLE,
                name=f"no_dbl_co_between_{e[0]}-{e[1]}",
                rhs=1,
            )
        )

    prob += pulp.lpSum(edges_conn) == (len(nodes) - 1)

    # Flow conservation (subtour elimination)
    vars_f = pulp.LpVariable.dicts(
        "Flow",
        (nodes, nodes),
        0,
        None,
        pulp.LpInteger,
    )
    n_nodes = len(nodes) - 1
    for d in nodes:
        for a in nodes:
            if d != a:
                prob += vars_f[d][a] <= n_nodes * edges_conn[d, a]

    for o in nodes:
        if o != "generator":
            prob += (
                pulp.lpSum([vars_f[a][o] - vars_f[o][a] for a in nodes]) == 1,
                f"Flow_balance_{o}",
            )

    print("\t solving problem")
    prob.solve()

    print(f"prob status: {pulp.LpStatus[prob.status]}")
    if pulp.LpStatus[prob.status] == "Infeasible":
        return []

    print(f"\nObjective Value: {pulp.value(prob.objective)} \n")
    print("connections:")
    for u, v in edges_conn:
        if pulp.value(edges_conn[u, v]):
            print(f"\t{u} connected to {v}")

    print("\nloads info:")
    for n in nodes:
        print(f"\t{n} cum_power = {pulp.value(nodes[n]['cum_power'])}")

    edges_final = [(e[0], e[1], e[2]) for e in edges if edges_conn[e[0], e[1]]]

    G = nx.DiGraph()
    G.add_weighted_edges_from(edges_final)
    pos = {name: (node.lon, node.lat) for name, node in grid.items()}
    colormap = ["red" if name == "generator" else "green" for name in G.nodes()]
    nx.draw(
        G,
        pos,
        with_labels=True,
        node_color=colormap,
        node_size=100,
        arrows=True,
        horizontalalignment="left",
        font_size=8,
    )
    labels = {(e[0], e[1]): f"{e[2]:.0f}m" for e in edges if pulp.value(edges_conn[e[0], e[1]])}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=labels)
    plt.show()

    return edges_final


def _all_subsets(xs):
    result = []
    for length in range(2, len(xs) + 1):
        for subset in itertools.combinations(xs, length):
            result.append(subset)
    return result


def minimum_spanning_tree(edges_with_cost):
    prob = pulp.LpProblem("Minimum_Spanning_Tree", pulp.LpMinimize)

    costs_to_sum = []
    all_vars = []
    vars_starting_with = {}
    nodes_names = []

    for s, e, c in edges_with_cost:
        if s not in nodes_names:
            nodes_names.append(s)
        if e not in nodes_names:
            nodes_names.append(e)

        var_i = pulp.LpVariable(
            f"BinaryVar_{s}_{e}",
            0,
            1,
            pulp.LpInteger,
        )
        costs_to_sum.append(var_i * c)
        all_vars.append(var_i)

        vars_and_coords = (var_i, s, e)
        if s in vars_starting_with:
            vars_starting_with[s].append(vars_and_coords)
        else:
            vars_starting_with[s] = [vars_and_coords]

    n_active_edges = len(nodes_names) - 1
    prob += pulp.lpSum(all_vars) == n_active_edges

    for comb in _all_subsets(nodes_names):
        to_constraint = []
        for ss in comb:
            for var_tuples in vars_starting_with.get(ss, []):
                if var_tuples[1] in comb and var_tuples[2] in comb:
                    to_constraint.append(var_tuples[0])
        prob += pulp.lpSum(to_constraint) <= len(comb) - 1

    prob += pulp.lpSum(costs_to_sum)
    prob.solve()

    if pulp.LpStatus[prob.status] == "Optimal":
        solution = [v.name.split("_")[1:] for v in prob.variables() if v.varValue == 1.0]
        return {
            "possible": True,
            "solution": solution,
            "cost": pulp.value(prob.objective),
        }

    return {"possible": False}


def find_min_spanning_tree(grid, edges):
    print(f"number of possible edges: {len(edges)}")
    print(f"number of nodes: {len(grid)}")
    edges_with_cost = [[e[0], e[1], e[2]] for e in edges]
    return minimum_spanning_tree(edges_with_cost)
