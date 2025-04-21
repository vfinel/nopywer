from pulp import LpProblem, lpSum, LpMinimize, LpVariable, LpInteger, LpStatus, value
import itertools
# https://github.com/AlexBrou/Minimum-Spanning-Tree-with-Linear-Programming/blob/master/main.py

def get_combinations(xs):
    returner = []
    for L in range(2, len(xs) + 1):
        for subset in itertools.combinations(xs, L):
            returner.append(subset)
    return returner


def minimum_spanning_tree(edges_with_cost):

    prob = LpProblem(
        "Shortest Path between 2 points with Linear Programming", LpMinimize
    )

    # arrays of variables
    # each variable is binary and is respective to an edge (either if it is part of the solution or not)

    # this array will have all the variables multiplied by the cost
    costs_to_sum = []

    # this array will have all the variables multiplied by the cost
    all_vars = []

    # this dictionary will have arrays of all the variables, categorized by their starting node
    vars_starting_with = {}

    # this array stores the names of the nodes
    nodes_names = []
    print('defining variables...')
    for s, e, c in edges_with_cost:
        # now we update the nodes_names array
        if s not in nodes_names:
            nodes_names.append(s)
        if e not in nodes_names:
            nodes_names.append(e)

        # binary variable declared
        var_i = LpVariable("BinaryVar_" + str(s) + "_" + str(e), 0, 1, LpInteger)

        # now, we place the variable in the respective array and dictionary
        costs_to_sum.append(var_i * c)

        all_vars.append(var_i)

        vars_and_coords = (var_i, s, e)
        if s in vars_starting_with.keys():
            vars_starting_with[s].append(vars_and_coords)
        else:
            vars_starting_with[s] = [vars_and_coords]

    # CONSTRAINTS
    print('defining constraints...')
    # if N is the number of nodes, then we must have N-1 edges active
    n_active_edges = len(nodes_names) - 1
    prob += lpSum(all_vars) == n_active_edges

    # there cannot be cycles. any subset of the graph with N nodes must only have N-1 edges active

    # we get all the combinations and, for each, we declare that the sum of the
    # active edges related to that combination must be <= than the number of current nodes - 1
    combinations = get_combinations(list(nodes_names))
    for comb in combinations:
        to_constraint = []
        for ss in comb:
            if ss in vars_starting_with.keys():
                tuple_array = vars_starting_with[ss]
            else:
                tuple_array = []

            for var_tuples in tuple_array:
                if var_tuples[1] in comb and var_tuples[2] in comb:
                    to_constraint.append(var_tuples[0])

        prob += lpSum(to_constraint) <= len(comb) - 1

    # OBJECTIVE FUNCTION

    prob += lpSum(costs_to_sum)

    # solve and return results
    print('solving...')
    prob.solve()

    if LpStatus[prob.status] == "Optimal":
        solution = []
        for v in prob.variables():
            if v.varValue == 1.0:
                solution.append(v.name.split("_")[1:])

        return {"possible": True, "solution": solution, "cost": value(prob.objective)}

    elif LpStatus[prob.status] == "Infeasible":
        return {"possible": False}


if __name__ == "__main__":
    print()

    # input is the graph presented at the wikipedia page
    # https://en.wikipedia.org/wiki/Minimum_spanning_tree
    edges_with_cost = [
        ["A", "D", 4],
        ["A", "B", 1],
        ["A", "E", 3],
        ["B", "D", 4],
        ["D", "E", 4],
        ["B", "E", 2],
        ["E", "C", 4],
        ["E", "F", 7],
        ["C", "F", 5],
    ]

    print(minimum_spanning_tree(edges_with_cost))