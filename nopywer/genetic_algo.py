import pickle
import random
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from optimization_tools import phase_assignment_greedy
from nopywer.get_grid_geometry import compute_deepness_list
import nopywer as npw


def calculate_fitness(G: nx.DiGraph, genome):
    """Calculates the fitness of a genome (lower voltage drop is better)."""

    # grid, _, _ = build_nopywer_grid(G)
    vdrop = analyze_power_grid(G)
    # vdrop = random.random()  #

    # total_length = G.edge.length, or something like this...
    # i think fitness needs to increase !! not decrease

    # fitness = [1/voltage_drop, 1/length]

    return vdrop


def selection(population, fitness_scores, num_parents):
    """Selects the best individuals from the population."""
    # (Placeholder - replace with a selection algorithm like tournament selection)
    # For now, just select the individuals with the lowest fitness scores.
    sorted_population = sorted(zip(population, fitness_scores), key=lambda x: x[1])
    parents = [individual for individual, fitness in sorted_population[:num_parents]]
    return parents


def crossover(parent1, parent2):
    """Performs crossover between two parents."""
    # (Placeholder - replace with a crossover algorithm)
    # For now, just return a random combination of the two parents.
    offspring = random.sample(parent1 + parent2, len(parent1))
    return offspring


def mutation(genome, mutation_rate):
    """Applies mutation to a genome."""
    # (Placeholder - replace with a mutation algorithm)
    # For now, just randomly swap two elements in the genome.
    if len(genome) > 0 and (random.random() < mutation_rate):
        index1 = random.randint(0, len(genome) - 1)
        index2 = random.randint(0, len(genome) - 1)
        genome[index1], genome[index2] = genome[index2], genome[index1]
    return genome


def run_genetic_algorithm(grid, population_size, num_generations, mutation_rate):
    """Runs the genetic algorithm."""
    population = generate_initial_population(grid, population_size)

    for generation in range(num_generations):
        print(f"generation {generation}")
        fitness_scores = [calculate_fitness(grid, genome) for genome in population]
        parents = selection(population, fitness_scores, population_size // 2)
        offspring = []
        while len(offspring) < population_size:
            parent1 = random.choice(parents)
            parent2 = random.choice(parents)
            child = crossover(parent1, parent2)
            child = mutation(child, mutation_rate)
            offspring.append(child)
        population = offspring

    best_genome = population[0]  # Replace with a selection algorithm
    return best_genome


def is_generator_src(G):
    return G._pred["generator"] == {}


def get_src(G):
    assert nx.is_arborescence(G), "graph should be an arborescence"
    src = [node for node in G.nodes if G._pred[node] == {}]
    return src[0]


def is_valid_grid(G):
    return nx.is_arborescence(G) and is_generator_src(G)


def arborescence_from_generator(G: nx.DiGraph):
    assert nx.is_arborescence(G), "graph should be an arborescence"
    debug = 0
    kk = 0

    node = "generator"  # start from desired source
    parent = list(G._pred[node].keys())
    while len(parent) > 0:
        parent = parent[0]
        grand_parent = list(G._pred[parent].keys())
        if debug:
            print(f"node: {node}, parent: {parent}")

        # reverse direction: from current_node -> parent
        G.remove_edge(parent, node)
        G.add_edge(node, parent)

        # iterate on parent recursively
        node = parent
        parent = grand_parent

        kk += 1
        assert kk < 1e6, "infinite loop seems to be running indefinitely"

    return G


def load_graph():
    with open("grid.pkl", "rb") as f:
        nodes, edges = pickle.load(f)

    G = nx.DiGraph()

    for key, val in nodes.items():
        G.add_node(key, position=(val["x"], val["y"]), power=val["power"], cum_power=0)

    # this build a fully connected graph
    for e in edges:
        G.add_edge(e[0], e[1], length=e[2])

    return G


def generate_initial_population(G: nx.DiGraph, population_size: int) -> list:
    """build initial population to start with"""

    """build a minimum spanning arborescence to start with"""
    arb = nx.minimum_spanning_arborescence(G, attr="length")
    # arb = nx.DiGraph(nx.random_spanning_tree(G, weight=None))
    nx.set_node_attributes(arb, nx.get_node_attributes(G, "position"), "position")
    nx.set_node_attributes(arb, nx.get_node_attributes(G, "power"), "power")

    # set generator to be the source
    arb = arborescence_from_generator(arb)

    print(f"is first grid valid: {is_valid_grid(arb)}")

    """ v2: build a population directly """
    arb_iterator = nx.ArborescenceIterator(G, weight="length")
    population = []
    for g in arb_iterator:
        nx.set_node_attributes(g, nx.get_node_attributes(G, "position"), "position")
        nx.set_node_attributes(g, nx.get_node_attributes(G, "power"), "power")

        g = arborescence_from_generator(g)
        # plot_graph(g)
        assert is_valid_grid(g), "g is not a valid grid"
        population.append(g)
        if len(population) >= population_size:
            break

    if len(population) < population_size:
        print(
            "not enough possibilities to create a population of {population_size}. "
            "Population will have only {len(population)} individiuals."
        )

    return population


def plot_graph(G):
    colormap = ["red" if node == "generator" else "green" for node in G.nodes()]
    nx.draw(
        G,
        pos=nx.get_node_attributes(G, "position"),
        with_labels=True,
        node_color=colormap,
        node_size=100,
        arrows=True,
        horizontalalignment="left",
        font_size=8,
    )

    # edge_labels = {
    #     (e[0], e[1]): f"{e[2]:.0f}m"
    #     for e in edges
    #     if pulp.value(edges_conn[e[0], e[1]])
    # }
    # nx.draw_networkx_edge_labels(G, pos, edge_labels=labels)

    plt.show()

    return None


def build_nopywer_grid(G: nx.DiGraph) -> tuple[dict, dict, list]:
    """build variables expected by nopywer tools"""

    # TODO: dirty assumption: all cables are in the same layer
    cable_layer_name = "norg_3phases_63A_2024"
    cable_r = 0.16
    cables = {cable_layer_name: []}

    grid = {}
    for key, val in nx.get_node_attributes(G, "power").items():
        cables[cable_layer_name].append({"r": cable_r, "current": 0})

        parent = list(G._pred[key])
        if len(parent) == 0:
            parent = ""
        elif len(parent) == 1:
            parent = parent[0]
        else:
            raise ValueError("why this nodes has two parents?!")

        grid[key] = {
            "power": val,
            "cum_power": 0,
            "parent": parent,
            "children": G._succ[key],
            "cable": {
                "layer": cable_layer_name,
                "idx": len(cables[cable_layer_name]) - 1,
            },
            "deepness": 0,
        }

        # get deepness of that node
        deepness = 0
        parent = list(G._pred[key].keys())
        while len(parent) > 0:
            deepness += 1
            parent = list(G._pred[parent[0]].keys())

        grid[key]["deepness"] = deepness

    dlist = compute_deepness_list(grid)

    return grid, cables, dlist


def assign_phases(G: nx.DiGraph) -> tuple[dict, nx.DiGraph]:
    # TODO: build a graph G ready to be imported in pandapower
    grid, _, _ = build_nopywer_grid(G)
    phases, _ = phase_assignment_greedy(grid)
    nx.set_node_attributes(G, phases, "phases")

    return phases, G


def analyze_power_grid(G: nx.DiGraph) -> float:
    grid, cables, dlist = build_nopywer_grid(G)

    # compute cumulated current
    grid, cables = npw.cumulate_current(grid, cables, dlist, V0, PF)

    # cables_dict = npw.inspect_cable_layers(qgs_project, cables_layers_list, cables_dict)
    # grid = npw.compute_distro_requirements(grid, cables_dict)

    grid, cables = npw.compute_voltage_drop(grid, cables, verbose=False)
    voltage_drop = float(np.mean([load["vdrop_percent"] for _, load in grid.items()]))
    print(f"mean voltage drop: {voltage_drop:.1f}%")

    return voltage_drop


if __name__ == "__main__":
    """ genetic algo parameters """
    population_size = 10
    num_generations = 100
    mutation_rate = 0.01

    G = load_graph()
    population = generate_initial_population(G, population_size)
    plot_graph(population[0])

    """ build power grid from graph """
    CONSTANTS = npw.get_constant_parameters()
    V0 = CONSTANTS["V0"]
    PF = CONSTANTS["PF"]

    # TODO: get back updated grid with 'power' distribution
    # or the updated graph G
    _, population[0] = assign_phases(population[0])

    # analyze graph in terms of power grids (TEST)
    # will be used in compute_loss
    vdrop = analyze_power_grid(population[0])  # to test

    # print("evolution ongoing...")
    # best_genome = run_genetic_algorithm(
    #     grid, population_size, num_generations, mutation_rate
    # )

    # print("Best genome:", best_genome)
