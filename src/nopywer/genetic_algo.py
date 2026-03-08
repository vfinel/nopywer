import copy
import pickle
import random

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pygad
from optimization_tools import phase_assignment_greedy

import nopywer as npw
from nopywer.get_grid_geometry import compute_deepness_list

"""
this is my attemps to build a genetic algo to find the optimal grid.
Its is not working as is.

Algorithm principle: 
    - A power grid is a graph. 
    - The adjacency matrix representation of the graph is used to represent a 'specimen' (ie, a grid).
        This representation will be make it easy to define custom mutation and crossover functions
    - The 'fitness' of a specimen is a the viability of the power grid. 
        It should be calculated from 
        - the voltage drop at each nodes (lower is better, and must be below a given maximum)
        - the total length of the grid (shorter is better)
        - the feasibility of the grid (according to ressources in the inventory)

Ideas:
- custom mutation and crossover functions might be needed to define corresponding operations
- 

TODO:
    - adapt code to use the new nopywer package
    - remove deprecated code
    - reorg code 
        - update functions for mutation, crossover
        - use above functions exclusively
        - 
    - write tests
        - test functions should be added for mutation and crossover functions 

"""


def calculate_fitness(G: nx.DiGraph):
    """
    Calculates the fitness of a genome (lower voltage drop is better).
       Fitness function retuens parameterize that we seek to *maximize*
    """

    grid, _, _ = build_nopywer_grid(G)
    vdrop = analyze_power_grid(G)

    # https://stackoverflow.com/questions/66217836/how-to-sum-up-a-networkx-graphs-edge-weights
    total_length = G.size(weight="length")

    # fitness = [1/voltage_drop, 1/length]  # for multiple objectives
    fitness = 1 / vdrop
    return fitness


def fitness_func_pyGAD(ga_instance: pygad.GA, solution: np.ndarray, solution_idx: int):
    """compute fitness function for pyGAD GA.
    It must accept 3 parameters.
    See https://pygad.readthedocs.io/en/latest/pygad.html#steps-to-use-pygad
    """
    G = pygad_to_nx(solution, nodes_list, nodes_attributes)  # call to global var

    # TODO: remove all geomes that are not valid ? or regenerate valid ones ?
    #   ie: remove loops, get generator as source, remove double inputs (pick only one randomly)
    if is_valid_grid(G):
        fitness = calculate_fitness(G)

    else:
        fitness = 0

    return fitness


def selection(population, fitness_scores, num_parents):
    """Selects the best individuals from the population."""
    # (Placeholder - TODO replace with a selection algorithm like tournament selection
    # inspired from calculate_fitness function)
    # For now, just select the individuals with the lowest fitness scores.
    sorted_population = sorted(zip(population, fitness_scores), key=lambda x: x[1])
    parents = [individual for individual, fitness in sorted_population[:num_parents]]
    return parents


def crossover(parent1, parent2):
    """Performs crossover between two parents.
        - look at common features between parents --> will be given to offsprings
        - look at diverging features --> select randomly one to give to offspring

    TODO: how to do N parents ?
    """
    plot = True
    """ get similarities and differences of parents """
    # get adjacency matrices
    num_nodes = int(parent1.size**0.5)
    adj1 = np.reshape(parent1, (num_nodes, num_nodes))
    adj2 = np.reshape(parent2, (num_nodes, num_nodes))
    print(f"are parents equal? {np.array_equal(parent1, parent2)} --> ", end=" ")
    if not np.array_equal(parent1, parent2):
        print("cool")

    else:
        print("parents are not equal, mutation is not going to be interesting")

    diff_mtx = np.not_equal(adj1, adj2)
    diff_idx = np.where(diff_mtx)
    n_diff = diff_mtx.sum() / 2  # /2 because to acount for swap

    # TODO
    """
    create the offspring. it must have only the common features between all parents
    eq_mtx = np.equal(adj1, adj2)
    offspring = np.zeros(same size as parents)
    offspring(eq_idx) = parent1(eq_idx)

    for (ii, ) enumerate(each diff between parents):
        # chose randomly between the feature of parent1 or parent1 
        # ... 

        # assign it to the offspring
        offspring(diff_idx(ii)) = <parent chosen>(diff_idx(ii))
    """
    # offspring = adj1
    if plot:
        plt.figure(3)
        plt.clf()
        plt.subplot(1, 3, 1)
        plt.imshow(adj1)
        plt.xlabel("dest")
        plt.ylabel("src")
        label_adjacency_mtx()
        plt.title("adj parent 1")

        plt.subplot(1, 3, 2)
        plt.imshow(adj2)
        plt.xlabel("dest")
        plt.ylabel("src")
        label_adjacency_mtx()
        plt.title("adj parent 2")

        plt.subplot(1, 3, 3)
        plt.imshow(diff_mtx)
        plt.xlabel("dest")
        plt.ylabel("src")
        label_adjacency_mtx()
        plt.title("diff mtx")

        plt.show(block=True)

    return offspring


def mutation(population: list, ga_instance, plot: bool = True) -> list:
    """
    Apply mutation to a graph
    https://gist.github.com/josephlewisjgl/16fad9765b826a5d59a35009c709ebbc#file-ga_mutation-py
    inputs:
        population: a list of flatten adjacency matrices representing a population

        output: a list of mutated flatten adjacency matrices representing the mutated population

    """
    block_fig = False  # useful for debug
    num_nodes = int(len(population[0]) ** 0.5)
    mutants = []
    for idx, individual in enumerate(population):
        # get adjacency matrix
        grid_in = np.reshape(individual, (num_nodes, num_nodes))
        # grid0 = grid.copy()  # to plot !! deepcopy ?!??!
        grid_out = copy.deepcopy(grid_in)

        # randomly selec a load, and connect it elsewhere
        mutate = True
        if mutate:
            # dest_idx = 1  # 1 = MoN
            # new_src = 3  # 3 = werhaus

            # pick a destination (making sure it is not a generator)
            old_src = []
            while len(old_src) == 0:  # if we picked a generator, this will be true
                dest_idx = random.randint(0, num_nodes - 1)
                old_src = np.where(grid_in[:, dest_idx] == 1)[0]  # get src of dest

            # assign a new src to the chosen load (dest)
            new_src = old_src
            k = 0
            while (new_src == old_src) and (k < 1e5):
                new_src = random.randint(0, num_nodes - 1)

            assert new_src != old_src, "unable to find a new src"
            # print(f"load {dest_idx} is now connected to {new_src} instead of {old_src}")
            grid_out[:, dest_idx] = np.zeros((1, num_nodes))  # reset (rm old connection)
            grid_out[new_src, dest_idx] = 1  # update (add new connection)
            assert np.array_equal(grid_in, grid_out) is False, "why mutation didn't worked?"
            # TODO:
            #   - check if grid is valid, otherwise, reject mutation ?
            #   - do mutation but only with new_src that are close enough of the dest (eg, <150m)

        # update grid
        mutants.append(grid_out.flatten())

        if plot:
            plt.figure(3)
            plt.clf()
            plt.subplot(1, 3, 1)
            plt.imshow(grid_in)
            plt.xlabel("dest")
            plt.ylabel("src")
            label_adjacency_mtx()
            plt.title("original")

            plt.subplot(1, 3, 2)
            plt.imshow(grid_out)
            plt.xlabel("dest")
            plt.ylabel("src")
            label_adjacency_mtx()
            plt.title("mutation")

            plt.subplot(1, 3, 3)
            plt.imshow(grid_out - grid_in)
            plt.xlabel("dest")
            plt.ylabel("src")
            label_adjacency_mtx()
            plt.title("diff = out - in")

            plt.show(block=block_fig)

        assert np.array_equal(grid_in, grid_out) is False, "why mutation didn't worked?"

    all_eq = all([np.array_equal(population[i], mutants[i]) for i in range(len(population))])

    assert all_eq is False, "why mutants and pop are all equal ?!"

    return mutants


def run_genetic_algorithm(grid, population_size, num_generations, mutation_rate):
    """Runs the genetic algorithm.
    This was a first attemp, before using pyGAD framework."""
    population = generate_initial_population(grid, population_size)

    for generation in range(num_generations):
        print(f"generation {generation}")
        fitness_scores = [calculate_fitness(genome) for genome in population]
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


def get_src(G):
    """this function seems useless, it can probably be removed"""
    assert nx.is_arborescence(G), "graph should be an arborescence"
    src = [node for node in G.nodes if G._pred[node] == {}]
    return src[0]


def is_valid_grid(G):
    """check that the grid has the generator as the source"""

    def is_generator_src(G):
        return G._pred["generator"] == {}

    return nx.is_arborescence(G) and is_generator_src(G)


def arborescence_from_generator(G: nx.DiGraph):
    """utility function allowing to orient the direct graph passed as input so that the graph origin is the generator."""
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
    """load sample graph
    TODO: use geojson file from tests
    """
    with open("grid.pkl", "rb") as f:
        nodes, edges = pickle.load(f)

    G = nx.DiGraph()

    for key, val in nodes.items():
        G.add_node(key, position=(val["x"], val["y"]), power=val["power"], cum_power=0)

    # this build a fully connected graph
    for e in edges:
        G.add_edge(e[0], e[1], length=e[2])

    # get nodes list
    nodes_list = list(G.nodes())

    # reorder it: place generator first
    idx_generator = nodes_list.index("generator")
    idx_reorder = list(range(len(nodes_list)))
    idx_reorder.remove(idx_generator)
    idx_reorder.insert(0, idx_generator)
    nodes_list = [nodes_list[i] for i in idx_reorder]

    return G, nodes_list


def generate_initial_population(G: nx.DiGraph, population_size: int) -> list:
    """build initial population to start the GA."""

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
    """utility function to plot a graph"""
    # TODO: add options to plot
    #   - adjacency matrix alone ??
    # (done?)  - how will i do to compare two graphs ?  comb of the two options + subplot ?
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

    # plt.show()

    return None


def build_nopywer_grid(G: nx.DiGraph) -> tuple[dict, dict, list]:
    """convert a networkx graph to a nopywer grid representation
    TODO: update to use new nopywer framework"""

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
    """take a graph, build the corresponding nopywer grid, and assign phases
    This will be necessary to be able to compute cumulated current and thus voltage drop
    """
    grid, _, _ = build_nopywer_grid(G)
    phases, _ = phase_assignment_greedy(grid)
    nx.set_node_attributes(G, phases, "phases")

    return phases, G


def nx_to_pygad(
    G: nx.DiGraph | list[nx.DiGraph], nodes_list: list
) -> np.ndarray | list[np.ndarray]:
    """convert a directed graph to its adjacency matrix representation
    inputs and outputs can be lists"""
    if isinstance(G, list):
        adjacency_mtx = []
        for g in G:
            mtx = nx.to_numpy_array(g, nodelist=nodes_list)
            adjacency_mtx.append(mtx.flatten())

    else:
        adjacency_mtx = nx.to_numpy_array(G, nodelist=nodes_list)
        adjacency_mtx.flatten()

    return adjacency_mtx


def pygad_to_nx(
    adjency_vector: np.ndarray, nodes_list, nodes_attributes: dict, debug: bool = False
) -> nx.DiGraph:
    """convert a network from its adjacency matrix representation to its networkx representation"""
    # TODO: verifier que pygad_to_nx(nx_to_pygad(G)) == G
    # this is dirty, works because adjency_mtx is a global var
    shape = adjacency_mtx.shape
    adjency_mtx = np.reshape(adjency_vector, shape)
    G = nx.from_numpy_array(adjency_mtx, nodelist=nodes_list, create_using=nx.DiGraph)

    # need to add power info (nodes and edges)
    # (to be able to compute vdrop for fitness_fct)
    node_list = list(Gfc.nodes)  # call global variable
    mapping = {i: node for i, node in enumerate(node_list)}
    G = nx.relabel_nodes(G, mapping)
    nx.set_node_attributes(G, nx.get_node_attributes(Gfc, "name"), "name")
    nx.set_node_attributes(G, nx.get_node_attributes(Gfc, "position"), "position")
    nx.set_node_attributes(G, nx.get_node_attributes(Gfc, "power"), "power")

    if debug:
        plot_graph(G)

    return G


def analyze_power_grid(G: nx.DiGraph, verbose: bool = False) -> float:
    grid, cables, dlist = build_nopywer_grid(G)

    # compute cumulated current
    grid, cables = npw.cumulate_current(grid, cables, dlist, V0, PF)

    # cables_dict = npw.inspect_cable_layers(qgs_project, cables_layers_list, cables_dict)
    # grid = npw.compute_distro_requirements(grid, cables_dict)

    grid, cables = npw.compute_voltage_drop(grid, cables, verbose=False)
    voltage_drop = float(np.mean([load["vdrop_percent"] for _, load in grid.items()]))
    if verbose:
        print(f"mean voltage drop: {voltage_drop:.1f}%")

    return voltage_drop


def on_gen(ga_instance):
    """pyGAD utility function. Use it to trig specific actions when a population is generated."""
    print(
        f"Generation: {ga_instance.generations_completed} "
        + f"Fitness: {ga_instance.best_solution()[1]}"
    )


def label_adjacency_mtx():
    """label the adjacency matrix representation with the names of the loads"""
    plt.xlabel("dest")
    plt.ylabel("src")
    plt.xticks(
        range(len(nodes_list)),
        nodes_list,
        size="small",
        rotation="vertical",
    )

    plt.yticks(  # TODO: how can i avoid copy pasting here ?
        range(len(nodes_list)),
        nodes_list,
        size="small",
        rotation="horizontal",
    )

    plt.grid()

    return None


if __name__ == "__main__":
    population_size = 20  # 10 ? 200 ?
    verbose = 0

    """ population initialization """
    print("generate initial population")
    graph, nodes_list = load_graph()
    population = generate_initial_population(graph, population_size)

    """ convert networkx graph to pygad representation """
    Gfc = graph.copy()  # this is a shallow copy... not so interesting
    nodes_attributes = graph._node
    adjacency_mtx = nx_to_pygad(graph, nodes_list)
    num_nodes = len(nodes_attributes)

    """ mutate original population to start with a "rich" population """
    pop0_pygad = nx_to_pygad(population, nodes_list)
    popm_pygad = mutation(pop0_pygad, None, plot=False)
    # gut feeling: many mutations are better, so let's go for 2nd round
    popm_pygad = mutation(popm_pygad, None, plot=False)
    # convert mutated inital population back to nx for display
    popm_nx = [pygad_to_nx(p, nodes_list, nodes_attributes) for p in popm_pygad]

    # check that grids aren't equal
    eq_grids = [np.array_equal(pop0_pygad[i], popm_pygad[i]) for i in range(len(pop0_pygad))]
    all_eq = all(eq_grids)
    assert all_eq is False, "why pop0 and popm are all equal ?!"  # TODO: fix

    """ plot some specimen of population """
    for i, g in enumerate(population):
        cond = i < 20
        if cond:
            plt.figure(1)
            plt.clf()
            plt.subplot(1, 2, 1)
            plot_graph(g)
            plt.title(f"pop {i}")

            # plot adj matrix of that grid
            plt.subplot(1, 2, 2)
            grid = np.reshape(pop0_pygad[i], (num_nodes, num_nodes))
            plt.imshow(grid)
            label_adjacency_mtx()
            plt.show(block=False)

        if cond:
            # plot mutation exmple
            plt.figure(2)
            plt.clf()
            plt.subplot(1, 1, 1)
            plot_graph(popm_nx[i])
            plt.title(f"mutation example: popm {i}")
            plt.show(block=False)

        if cond:  # plot crossover (test)
            offspring = crossover(pop0_pygad[i], popm_pygad[i])

            plt.figure(4)
            plt.clf()
            plt.suptitle(f"crossover {i}")

            plt.subplot(1, 3, 1)
            plot_graph(population[i])
            plt.title("parent 1")

            plt.subplot(1, 3, 2)
            plot_graph(popm_nx[i])
            plt.title("parent 2")

            plt.subplot(1, 3, 3)
            plot_graph(pygad_to_nx(offspring, nodes_list, nodes_attributes))
            plt.title("offspring")
            plt.show(block=True)

    """ build power grid from graph """
    # TODO: get back updated grid with 'power' distribution
    _, population[0] = assign_phases(population[0])
    analyze_power_grid(population[0], verbose=True)  # TODO: test

    """ genetic algo parameters """
    num_generations = 50
    num_parents_mating = 10

    fitness_function = fitness_func_pyGAD

    sol_per_pop = population_size  # specimen in population
    num_genes = adjacency_mtx.size

    init_range_low = 0
    init_range_high = 1

    parent_selection_type = "sss"
    keep_parents = num_parents_mating

    crossover_type = "single_point"

    mutation_type = "random"
    pygag_population = popm_pygad  # init population

    """ start genetic algo optimization """
    # TODO : add custom mutation function https://stackoverflow.com/a/66344562
    ga_instance = pygad.GA(
        num_generations=num_generations,
        num_parents_mating=num_parents_mating,
        fitness_func=fitness_function,
        sol_per_pop=sol_per_pop,
        num_genes=num_genes,
        gene_space=[0, 1],
        initial_population=pygag_population,
        parent_selection_type=parent_selection_type,
        keep_parents=keep_parents,
        crossover_type=crossover_type,
        mutation_type=mutation_type,
        on_generation=on_gen,
    )

    print("evolution ongoing...")
    ga_instance.run()

    """ analyze results """
    ga_instance.plot_fitness()
    solution, solution_fitness, solution_idx = ga_instance.best_solution()
    _ = pygad_to_nx(solution, nodes_list, nodes_attributes, debug=True)
    if verbose:
        print(f"Parameters of the best solution : {solution}")
        print(f"Fitness value of the best solution = {solution_fitness}")
        print(f"Index of the best solution : {solution_idx}")

    print(f"best vdrop: {1 / solution_fitness}")

    """ attempt to use custom algo without PyGAD"""
    # best_genome = run_genetic_algorithm(
    #     grid, population_size, num_generations, mutation_rate
    # )
    # print("Best genome:", best_genome)
