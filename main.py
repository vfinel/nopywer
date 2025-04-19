from qgis.core import QgsApplication, QgsProject
import qgis.utils
import numpy as np
import os

import nopywer as npw


def get_project(param: dict) -> tuple[QgsProject, str, qgis._core.QgsApplication, bool]:
    """ get QGIS qgs_project and project file, and QGS application instance """
    qgs_project = QgsProject.instance()
    qgs = QgsApplication.instance()
    running_in_qgis = qgs is not None
    print(f"running in QGIS = {running_in_qgis}")
    if running_in_qgis:
        project_file = qgs_project.absoluteFilePath()

    else:
        project_file, qgs = load_qgis_project(param, qgs_project)

    print(f"project filename: {qgs_project.fileName()}\n")

    return qgs_project, project_file, qgs, running_in_qgis


def load_qgis_project(param: dict, qgs_project: QgsProject) -> tuple[str, qgis._core.QgsApplication]:
    print("initializing QGIS...")
    qgs = QgsApplication([], False) # second argument to False disables the GUI.
    qgs.initQgis()  # Load providers

    # load project - cf https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
    print("\nloading project...")
    project_file = param["project_file"]
    assert os.path.isfile(project_file), f'the project file does not exists: "{project_file}"'
    status = qgs_project.read(project_file)
    assert status, f'unable to read qgs_project "{project_file}"'

    return project_file, qgs


def run_analysis(qgs_project: QgsProject, project_file: str, param: dict) -> tuple[dict, dict]:
    # constant data (global variables)
    CONSTANTS = npw.get_constant_parameters()
    V0 = CONSTANTS["V0"]
    PF = CONSTANTS["PF"]

    # user parameters
    updateStuff = 0 # TODO: move to get_user_parameters()    
    cablesLayersList = param["cablesLayersList"]

    # find grid geometry
    cablesDict, grid, dlist = npw.getGridGeometry(qgs_project)

    # spreadsheet: assign phases
    # --> user manually assign phases via the spreadsheet

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

    cablesDict = npw.inspectCableLayers(qgs_project, cablesLayersList, cablesDict)
    grid = npw.computeDistroRequirements(grid, cablesDict)

    print("\ncomputingVDrop...")
    grid, cablesDict = npw.computeVDrop(grid, cablesDict)

    print("\nchecking inventory:")
    npw.choose_cables_in_inventory(project_path, cablesDict, param["inventory"])
    npw.choose_distros_in_inventory(project_path, grid, param["inventory"])

    npw.printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

    if updateStuff:
        npw.update1PhaseLayers(grid, cablesDict, qgs_project)
        npw.updateLoadLayers(grid, param["loadLayersList"], qgs_project)
        # npw.writeSpreadsheet(grid, sh)

    return grid, cablesDict


def main() -> tuple[dict, dict]:
    param = npw.get_user_parameters()
    qgs_project, project_file, qgs, running_in_qgis = get_project(param)
    grid, cablesDict = run_analysis(qgs_project, project_file, param)
    if not running_in_qgis:
        qgs.exitQgis()

    return grid, cablesDict 



# if param["grid_src"] == "compute":

#     # get "nodes" and "edges" from computed grid
#     #   - should be executed along with the above commented code (when 'grid' is computed):
#     #   - can be skipped (and other code) when either:
#     #       - running a simple toy example
#     #       - loading precalculated grid from pickle object
#     nodes, edges = npw.qgis2list(grid, project_path)

#     # TODO :
#     #   - clean management of the above (not with comments)
#     #      - ok: create a main() fct that computes the grid stuff "as in in 2024"
#     #      - create an automatic() fct too ? that takes in arg the data
#     #      - create a load data, that can give the pickle data, or the simple toy, (or recompute the grid ? )
#     #       --> maybe the autmatic experiments shiuld be put away from main.py and have their own function
#     #

# elif param["grid_src"] == "load":
#     import pickle

#     with open("grid.pkl", "rb") as f:  # Python 3: open(..., 'rb')
#         nodes, edges = pickle.load(f)

# elif param["grid_src"] == "test":
#     nodes = {
#         "A": {"power": 10, "cumPower": None, "x": 1, "y": 1},
#         "B": {"power": 20, "cumPower": None, "x": 0, "y": 1},
#         "C": {"power": 30, "cumPower": None, "x": 1, "y": 0},
#         "generator": {"power": 0, "cumPower": None, "x": 0, "y": 0},
#     }
#     edges = []
#     for src in nodes:
#         for dst in nodes:
#             if (
#                 src != dst
#             ):  # and (dst!='generator'): allow connection towards generator, this case is managed by pulp constraints
#                 edges.append(
#                     (
#                         src,
#                         dst,
#                         (nodes[src]["x"] - nodes[dst]["x"]) ** 2
#                         + (nodes[src]["y"] - nodes[dst]["y"]) ** 2,
#                     )
#                 )

# else:
#     ValueError("unkwnown data source")

# optim_edges = npw.find_optimal_layout(nodes, edges)
# # npw.find_min_spanning_tree(nodes, edges) # too computational intensive
# if (param["grid_src"] == "compute") and (not standalone_exec):
#     print(f"drawing optimal cable layer in QGIS: {project_file}...")
#     npw.draw_cable_layer(qgs_project, grid, optim_edges)

# # npw.phase_assignment_greedy(grid)

# print("\n end of script for now :)")

if __name__ == "__main__":
    main()