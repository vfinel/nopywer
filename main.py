import os

import numpy as np
import qgis.utils
from qgis.core import QgsApplication, QgsProject

try:
    from qgis.core import Qgis  # qgis 3 and above
except ImportError:
    from qgis.core import QGis as Qgis  # qgis 2 and below

import nopywer as npw


def check_qgis_version():
    qgis_version_min = "3.34"
    qgis_version = Qgis.QGIS_VERSION.split(".")

    for idx, ver in enumerate(qgis_version_min.split(".")):
        assert qgis_version[idx] >= ver, (
            f"QGIS version should be at least {qgis_version_min} but is {Qgis.QGIS_VERSION}. Please update"
        )

    return None


def is_running_in_qgis():
    """get QGS application instance"""
    qgs = QgsApplication.instance()
    running_in_qgis = qgs is not None
    print(f"running in QGIS = {running_in_qgis}")
    return running_in_qgis


def get_project(
    param: dict, running_in_qgis: bool
) -> tuple[QgsProject, str, QgsApplication]:
    """get QGIS qgs_project and project file"""
    qgs_project = QgsProject.instance()
    if running_in_qgis:
        project_file = qgs_project.absoluteFilePath()
        qgs = QgsApplication.instance()

    else:
        project_file, qgs = load_qgis_project(param, qgs_project)

    print(f"project filename: {qgs_project.fileName()}\n")
    project_folder = os.path.split(project_file)[0]

    return qgs_project, project_folder, qgs


def load_qgis_project(
    param: dict, qgs_project: QgsProject
) -> tuple[str, qgis._core.QgsApplication]:
    print("initializing QGIS...")
    qgs = QgsApplication([], False)  # second argument to False disables the GUI.
    qgs.initQgis()  # Load providers

    # load project - cf https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
    print("\nloading project...")
    project_file = param["project_file"]
    assert os.path.isfile(project_file), (
        f'the project file does not exists: "{project_file}"'
    )
    status = qgs_project.read(project_file)
    assert status, f'unable to read qgs_project "{project_file}"'

    return project_file, qgs


def run_analysis(
    qgs_project: QgsProject, project_folder: str, param: dict
) -> tuple[dict, dict]:
    # constant data (global variables)
    CONSTANTS = npw.get_constant_parameters()
    V0 = CONSTANTS["V0"]
    PF = CONSTANTS["PF"]
    cables_layers_list = param["cables_layers_list"]

    # find grid geometry
    cables_dict, grid, dlist = npw.get_grid_geometry(qgs_project, param)

    # spreadsheet: assign phases
    # --> user manually assign phases via the spreadsheet
    # TODO: use npw.phase_assignment_greedy(grid)

    # load spreadsheet (power usage + phase) and add it to "grid" dictionnary
    grid, cables_dict, has_no_phase, sh = npw.read_spreadsheet(
        project_folder, grid, cables_dict, param["phase_balance_spreadsheet"]
    )

    # compute cumulated current
    grid, cables_dict = npw.cumulate_current(grid, cables_dict, dlist, V0, PF)

    phase_balance = 100 * np.std(
        grid["generator"].cum_power / np.mean(grid["generator"].cum_power)
    )

    cables_dict = npw.inspect_cable_layers(qgs_project, cables_layers_list, cables_dict)
    grid = npw.compute_distro_requirements(grid, cables_dict)

    print("\ncomputingVDrop...")
    grid, cables_dict = npw.compute_voltage_drop(grid, cables_dict)

    print("\nchecking inventory:")
    npw.choose_cables_in_inventory(project_folder, cables_dict, param["inventory"])
    npw.choose_distros_in_inventory(project_folder, grid, param["inventory"])

    npw.print_grid_info(grid, cables_dict, phase_balance, has_no_phase, dlist)

    if param["update"]["qgis_layers"]:
        npw.update_1phase_layers(grid, cables_dict, qgs_project)
        npw.update_load_layers(grid, param["loads_layers_list"], qgs_project)

    if param["update"]["phase_balance_spreadsheet"]:
        npw.write_spreadsheet(grid, sh)

    return grid, cables_dict


def main() -> tuple[dict, dict, QgsApplication, bool]:
    check_qgis_version()
    running_in_qgis = is_running_in_qgis()
    nopywer_folder = os.path.dirname(__file__)
    print(f"nopywer_folder: {nopywer_folder}")
    if running_in_qgis:
        os.chdir(nopywer_folder)

    param = npw.get_user_parameters()

    qgs_project, project_folder, qgs = get_project(param, running_in_qgis)
    grid, cables_dict = run_analysis(qgs_project, project_folder, param)

    print("\nNopywer analysis completed :)")

    return grid, qgs_project, qgs, running_in_qgis


if (__name__ == "__main__") or (QgsApplication.instance() is not None):
    grid, qgs_project, qgs, running_in_qgis = main()
    if not running_in_qgis:
        qgs.exitQgis()
