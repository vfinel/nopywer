import pickle
import random
import matplotlib.pyplot as plt
import networkx as nx


def calculate_fitness(grid, genome):
    """Calculates the fitness of a genome (lower voltage drop is better)."""
    total_voltage_drop = 0
    # (Placeholder - replace with actual voltage drop calculation)
    # This would require accessing the grid structure and calculating
    # the voltage drop along each edge in the genome.
    # For now, just return a random value as a placeholder.
    return random.random()  # Replace with actual calculation


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
        G.add_node(key, position=(val["x"], val["y"]))

    # this build a fully connected graph
    for e in edges:
        G.add_edge(e[0], e[1], length=e[2])

    return G


def generate_initial_population(G, population_size):
    """build initial population to start with"""

    """build a minimum spanning arborescence to start with"""
    arb = nx.minimum_spanning_arborescence(G, attr="length")
    # arb = nx.DiGraph(nx.random_spanning_tree(G, weight=None))
    nx.set_node_attributes(arb, nx.get_node_attributes(G, "position"), "position")

    # set generator to be the source
    arb = arborescence_from_generator(arb)

    print(f"is first grid valid: {is_valid_grid(arb)}")

    """ v2: build a population directly """
    arb_iterator = nx.ArborescenceIterator(G, weight="length")
    population = []
    for g in arb_iterator:
        nx.set_node_attributes(g, nx.get_node_attributes(G, "position"), "position")
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


if __name__ == "__main__":
    population_size = 10
    num_generations = 100
    mutation_rate = 0.01

    G = load_graph()
    population = generate_initial_population(G, population_size)
    plot_graph(population[0])

    # print("evolution ongoing...")
    # best_genome = run_genetic_algorithm(
    #     grid, population_size, num_generations, mutation_rate
    # )

    # print("Best genome:", best_genome)
