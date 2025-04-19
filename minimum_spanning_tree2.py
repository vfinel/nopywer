from pulp import LpProblem, lpSum, LpMinimize, LpVariable, LpInteger, LpStatus, value
import itertools
# https://github.com/AlexBrou/Minimum-Spanning-Tree-with-Linear-Programming/blob/master/main.py

def getCombinations(xs):
    returner = []
    for L in range(2, len(xs) + 1):
        for subset in itertools.combinations(xs, L):
            returner.append(subset)
    return returner


def minimumSpanningTree(edges_with_cost):

    prob = LpProblem(
        "Shortest Path between 2 points with Linear Programming", LpMinimize
    )

    # arrays of variables
    # each variable is binary and is respective to an edge (either if it is part of the solution or not)

    # this array will have all the variables multiplied by the cost
    toSumForObjectiveFunction = []

    # this array will have all the variables multiplied by the cost
    allTheVariables = []

    # this dictionary will have arrays of all the variables, categorized by their starting node
    variablesThatStartWith = {}

    # this array stores the names of the nodes
    nodesNames = []
    print('defining variables...')
    for s, e, c in edges_with_cost:
        # now we update the nodesNames array
        if s not in nodesNames:
            nodesNames.append(s)
        if e not in nodesNames:
            nodesNames.append(e)

        # binary variable declared
        thisVar = LpVariable("BinaryVar_" + str(s) + "_" + str(e), 0, 1, LpInteger)

        # now, we place the variable in the respective array and dictionary
        toSumForObjectiveFunction.append(thisVar * c)

        allTheVariables.append(thisVar)

        tupleOfVarAndCoords = (thisVar, s, e)
        if s in variablesThatStartWith.keys():
            variablesThatStartWith[s].append(tupleOfVarAndCoords)
        else:
            variablesThatStartWith[s] = [tupleOfVarAndCoords]

    # CONSTRAINTS
    print('defining constraints...')
    # if N is the number of nodes, then we must have N-1 edges active
    numberOfActiveEdges = len(nodesNames) - 1
    prob += lpSum(allTheVariables) == numberOfActiveEdges

    # there cannot be cycles. any subset of the graph with N nodes must only have N-1 edges active

    # we get all the combinations and, for each, we declare that the sum of the
    # active edges related to that combination must be <= than the number of current nodes - 1
    combinations = getCombinations(list(nodesNames))
    for comb in combinations:
        toConstraint = []
        for ss in comb:
            if ss in variablesThatStartWith.keys():
                tupleArray = variablesThatStartWith[ss]
            else:
                tupleArray = []
            for varTuples in tupleArray:
                if varTuples[1] in comb and varTuples[2] in comb:
                    toConstraint.append(varTuples[0])
        prob += lpSum(toConstraint) <= len(comb) - 1

    # OBJECTIVE FUNCTION

    prob += lpSum(toSumForObjectiveFunction)

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

    print(minimumSpanningTree(edges_with_cost))