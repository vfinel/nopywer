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
    project_folder = os.path.split(project_file)[0]

    return qgs_project, project_folder, qgs, running_in_qgis


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


def run_analysis(qgs_project: QgsProject, project_folder: str, param: dict) -> tuple[dict, dict]:
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
    # TODO: use npw.phase_assignment_greedy(grid)


    # load spreadsheet (power usage + phase) and add it to "grid" dictionnary
    grid, cablesDict, hasNoPhase = npw.readSpreadsheet(
        project_folder, grid, cablesDict, param["spreadsheet"]
    )

    # compute cumulated current
    grid, cablesDict = npw.cumulate_current(grid, cablesDict, dlist, V0, PF)

    phaseBalance = 100 * np.std(
        grid["generator"]["cumPower"] / np.mean(grid["generator"]["cumPower"])
    )

    cablesDict = npw.inspectCableLayers(qgs_project, cablesLayersList, cablesDict)
    grid = npw.computeDistroRequirements(grid, cablesDict)

    print("\ncomputingVDrop...")
    grid, cablesDict = npw.compute_voltage_drop(grid, cablesDict)

    print("\nchecking inventory:")
    npw.choose_cables_in_inventory(project_folder, cablesDict, param["inventory"])
    npw.choose_distros_in_inventory(project_folder, grid, param["inventory"])

    npw.printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

    if updateStuff:
        npw.update1PhaseLayers(grid, cablesDict, qgs_project)
        npw.updateLoadLayers(grid, param["loadLayersList"], qgs_project)
        # npw.writeSpreadsheet(grid, sh)

    return grid, cablesDict


def main() -> tuple[dict, dict, str]:
    param = npw.get_user_parameters()
    
    qgs_project, project_folder, qgs, running_in_qgis = get_project(param)
    grid, cablesDict = run_analysis(qgs_project, project_folder, param)
    if not running_in_qgis:
        qgs.exitQgis()

    print("\n end of script for now :)")
    
    return grid, qgs_project, running_in_qgis


if( __name__ == "__main__") or (QgsApplication.instance() is not None):
    main()