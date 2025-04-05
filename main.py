from qgis.core import QgsApplication, QgsProject
import qgis.utils
import numpy as np
import os

import nopywer as npw

# --------------------------------------------------------- #
# --- constant data (global variables)
CONSTANTS = npw.get_constant_parameters()
V0 = CONSTANTS["V0"]
PF = CONSTANTS["PF"]

# user parameters
updateStuff = 0
param = npw.get_user_parameters()
cablesLayersList = param["cablesLayersList"]

project = QgsProject.instance()

standalone_exec = __name__ == "__main__"

if param["grid_src"] == "compute":
    print("computing from qgis project...")
    if standalone_exec:  # code is not ran from QGIS
        # --- run qgis (to be able to run code from vscode - NOT HELPING)
        # Supply path to qgis install location
        # QgsApplication.setPrefixPath("C:/Program Files/QGIS 3.34.3/apps/qgis/", True) # true=default paths to be used
        print("initializing QGIS...")
        qgs = QgsApplication([], False)  # second argument to False disables the GUI.
        qgs.initQgis()  # Load providers

        # --- load project
        # from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
        print("\nloading project...")
        project_file = param["project_file"]
        assert os.path.isfile(
            project_file
        ), f'the project file does not exists: "{project_file}"'
        status = project.read(project_file)
        assert status, f'unable to read project "{project_file}"'

    else:  # code is ran from QGIS
        project_file = project.absoluteFilePath()

    print(f"project filename: {project.fileName()}\n")

    # find grid geometry
    cablesDict, grid, dlist = npw.getGridGeometry(project)

    # spreadsheet: assign phases
    # .....

    # load spreadsheet (power usage + phase) and add it to "grid" dictionnary
    project_path = os.path.split(project_file)[0]
    grid, cablesDict, hasNoPhase = npw.readSpreadsheet(
        project_path, grid, cablesDict, param["spreadsheet"]
    )

    # compute cumulated current
    grid, cablesDict = npw.cumulateCurrent(grid, cablesDict, dlist, V0, PF)

    phaseBalance = 100 * np.std(
        grid["generator"]["cumPower"] / np.mean(grid["generator"]["cumPower"])
    )

    cablesDict = npw.inspectCableLayers(project, cablesLayersList, cablesDict)
    grid = npw.computeDistroRequirements(grid, cablesDict)

    print("\ncomputingVDrop...")
    grid, cablesDict = npw.computeVDrop(grid, cablesDict)

    print("\nchecking inventory:")
    npw.choose_cables_in_inventory(project_path, cablesDict, param["inventory"])
    npw.choose_distros_in_inventory(project_path, grid, param["inventory"])

    npw.printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

    if updateStuff:
        npw.update1PhaseLayers(grid, cablesDict, project)
        npw.updateLoadLayers(grid, param["loadLayersList"], project)
        # npw.writeSpreadsheet(grid, sh)

    # qgis2list:
    #   - should be executed along with the above commented code (when 'grid' is computed):
    #   - can be skipped (and other code) when either:
    #       - running a simple toy example
    #       - loading precalculated grid from pickle object
    nodes, edges = npw.qgis2list(grid)
    #
    # TODO :
    #   - clean management of the above (not with comments)
    #      - create a main() fct that computes the grid stuff "as in in 2024"
    #      - create an automatic() fct too ? that takes in arg the data
    #      - create a load data, that can give the pickle data, or the simple toy, (or recompute the grid ? )
    #       --> maybe the autmatic experiments shiuld be put away from main.py and have their own function
    #

elif param["grid_src"] == "load":
    import pickle

    with open("grid.pkl", "rb") as f:  # Python 3: open(..., 'rb')
        nodes, edges = pickle.load(f)

elif param["grid_src"] == "test":
    nodes = {
        "A": {"power": 10, "cumPower": None, "x": 1, "y": 1},
        "B": {"power": 20, "cumPower": None, "x": 0, "y": 1},
        "C": {"power": 30, "cumPower": None, "x": 1, "y": 0},
        "generator": {"power": 0, "cumPower": None, "x": 0, "y": 0},
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

else:
    ValueError("unkwnown data source")

optim_edges = npw.find_optimal_layout(nodes, edges)
# npw.find_min_spanning_tree(nodes, edges) # too computational intensive
if param["grid_src"] == "compute":
    npw.draw_cable_layer(project, grid, optim_edges)

# npw.phase_assignment_greedy(grid)

print("\n end of script for now :)")

"""
if standalone_exec:
    qgs.exitQgis()
"""
