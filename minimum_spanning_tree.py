from pulp import *
# https://medium.com/analytics-vidhya/integer-programming-for-graph-theory-and-others-with-python-03-minimum-spanning-tree-and-42a5bd75b663

prob = LpProblem("Minimum Spanning Tree", LpMinimize)

# declare all possible edges 
a_b = LpVariable("edge from A to B", 0, 1, LpInteger)
b_c = LpVariable("edge from B to C", 0, 1, LpInteger)
c_d = LpVariable("edge from C to D", 0, 1, LpInteger)
c_e = LpVariable("edge from C to E", 0, 1, LpInteger)
d_e = LpVariable("edge from D to E", 0, 1, LpInteger)

""" define the objective fonction """
# We want to connect all the nodes directly or indirectly with the lowest cost possible, 
# without creating cycles. In other words, minimize the sum of the used edges’ cost.
prob += 2*a_b + 6*b_c + 3*c_d + 1*c_e + 1*d_e    # 2, 6, 3 etc are the cost of edge edges

""" add constraints """
# For a graph with N nodes, you need N-1 edges to build its Minimum Spanning Tree
# in other words: n_used_edges == (n_nodes)-1
prob += a_b + b_c + c_d + c_e + d_e == 4

# make sure that each node has at least one edge connected to it
prob += a_b >= 1 # A
prob += a_b + b_c >= 1 # B
prob += c_d + c_e >= 1 # C
prob += c_d + d_e >= 1 # D
prob += c_e + d_e >= 1 # E
"""