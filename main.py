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
    cables_layers_list = param["cables_layers_list"]

    # find grid geometry
    cables_dict, grid, dlist = npw.get_grid_geometry(qgs_project)

    # spreadsheet: assign phases
    # --> user manually assign phases via the spreadsheet
    # TODO: use npw.phase_assignment_greedy(grid)


    # load spreadsheet (power usage + phase) and add it to "grid" dictionnary
    grid, cables_dict, has_no_phase = npw.read_spreadsheet(
        project_folder, grid, cables_dict, param["spreadsheet"]
    )

    # compute cumulated current
    grid, cables_dict = npw.cumulate_current(grid, cables_dict, dlist, V0, PF)

    phaseBalance = 100 * np.std(
        grid["generator"]["cum_power"] / np.mean(grid["generator"]["cum_power"])
    )

    cables_dict = npw.inspect_cable_layers(qgs_project, cables_layers_list, cables_dict)
    grid = npw.compute_distro_requirements(grid, cables_dict)

    print("\ncomputingVDrop...")
    grid, cables_dict = npw.compute_voltage_drop(grid, cables_dict)

    print("\nchecking inventory:")
    npw.choose_cables_in_inventory(project_folder, cables_dict, param["inventory"])
    npw.choose_distros_in_inventory(project_folder, grid, param["inventory"])

    npw.print_grid_info(grid, cables_dict, phaseBalance, has_no_phase, dlist)

    if updateStuff:
        npw.update1PhaseLayers(grid, cables_dict, qgs_project)
        npw.updateLoadLayers(grid, param["loads_layers_list"], qgs_project)
        # npw.write_spreadsheet(grid, sh)

    return grid, cables_dict


def main() -> tuple[dict, dict, str]:
    param = npw.get_user_parameters()
    
    qgs_project, project_folder, qgs, running_in_qgis = get_project(param)
    grid, cables_dict = run_analysis(qgs_project, project_folder, param)
    if not running_in_qgis:
        qgs.exitQgis()

    print("\n end of script for now :)")
    
    return grid, qgs_project, running_in_qgis


if( __name__ == "__main__") or (QgsApplication.instance() is not None):
    main()