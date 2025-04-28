import pickle
from qgis.core import QgsApplication, QgsProject

import nopywer as npw
from main import main


def get_optimal_layout():
    """this function will find the optimal edges for given nodes"""

    # get input data
    param = npw.get_user_parameters()
    nodes, edges, grid, qgs_project, running_in_qgis = get_grid_data(param)

    # find optimal layout
    optim_edges = npw.find_optimal_layout(nodes, edges)
    # npw.find_min_spanning_tree(nodes, edges) # too computational intensive

    # if applicable, draw back the grid in QGIS
    if (param["grid_src"] == "compute") and running_in_qgis:
        print(f"drawing optimal cable layer in QGIS: {qgs_project.fileName()}...")
        npw.draw_cable_layer(qgs_project, grid, optim_edges)

    return None


def get_grid_data(
    param: dict,
) -> tuple[dict, list, dict | None, QgsProject | None, bool]:
    qgs_project = None
    grid = None
    running_in_qgis = False
    if param["grid_src"] == "compute":
        # get "nodes" and "edges" from computed grid from QGIS project
        grid, qgs_project, running_in_qgis = main()
        nodes, edges = npw.qgis2list(grid)

    elif param["grid_src"] == "load":
        with open("grid.pkl", "rb") as f:
            nodes, edges = pickle.load(f)

    elif param["grid_src"] == "test":
        nodes, edges = get_toy_example()

    else:
        ValueError("unkwnown data source")

    return nodes, edges, grid, qgs_project, running_in_qgis


def get_toy_example() -> tuple[dict, list]:
    nodes = {
        "A": {"power": 10, "cum_power": None, "x": 1, "y": 1},
        "B": {"power": 20, "cum_power": None, "x": 0, "y": 1},
        "C": {"power": 30, "cum_power": None, "x": 1, "y": 0},
        "generator": {"power": 0, "cum_power": None, "x": 0, "y": 0},
    }

    edges = []
    for src in nodes:
        for dst in nodes:
            if (
                src != dst
            ):  # and (dst!='generator'): allow connection towards generator, this case is managed by pulp constraints
                edges.append(
                    (
                        src,
                        dst,
                        (nodes[src]["x"] - nodes[dst]["x"]) ** 2
                        + (nodes[src]["y"] - nodes[dst]["y"]) ** 2,
                    )
                )

    return nodes, edges


if (__name__ == "__main__") or (QgsApplication.instance() is not None):
    get_optimal_layout()
