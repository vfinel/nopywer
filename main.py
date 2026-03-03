import logging
import os
from pathlib import Path

import numpy as np
from qgis.core import QgsApplication, QgsProject

import nopywer as npw
from nopywer.constants import V0, PF

logger = logging.getLogger(__name__)


def load_qgis_project(project_file: str) -> QgsApplication:
    logger.info("Initializing QGIS...")
    qgs = QgsApplication([], False)
    qgs.initQgis()

    project_path = Path(project_file)
    if not project_path.is_file():
        raise FileNotFoundError(f'Project file does not exist: "{project_file}"')

    qgs_project = QgsProject.instance()
    if not qgs_project.read(project_file):
        raise RuntimeError(f'Unable to read project "{project_file}"')

    logger.info(f"Project: {qgs_project.fileName()}")
    return qgs


def run_analysis(param: dict) -> tuple[dict, dict]:
    qgs_project = QgsProject.instance()
    project_folder = os.path.dirname(qgs_project.absoluteFilePath())

    cables_dict, grid, dlist = npw.get_grid_geometry(qgs_project, param)

    grid, cables_dict, has_no_phase, sh = npw.read_spreadsheet(
        project_folder, grid, cables_dict, param["phase_balance_spreadsheet"]
    )

    grid, cables_dict = npw.cumulate_current(grid, cables_dict, dlist, V0, PF)

    phase_balance = 100 * np.std(
        grid["generator"].cum_power / np.mean(grid["generator"].cum_power)
    )

    cables_dict = npw.inspect_cable_layers(
        qgs_project, param["cables_layers_list"], cables_dict
    )
    grid = npw.compute_distro_requirements(grid, cables_dict)

    logger.info("Computing voltage drop...")
    grid, cables_dict = npw.compute_voltage_drop(grid, cables_dict)

    logger.info("Checking inventory...")
    npw.choose_cables_in_inventory(project_folder, cables_dict, param["inventory"])
    npw.choose_distros_in_inventory(project_folder, grid, param["inventory"])

    npw.print_grid_info(grid, cables_dict, phase_balance, has_no_phase, dlist)

    if param["update"]["qgis_layers"]:
        npw.update_1phase_layers(grid, cables_dict, qgs_project)
        npw.update_load_layers(grid, param["loads_layers_list"], qgs_project)

    if param["update"]["phase_balance_spreadsheet"]:
        npw.write_spreadsheet(grid, sh)

    return grid, cables_dict


def main():
    param = npw.get_user_parameters()
    qgs = load_qgis_project(param["project_file"])

    try:
        grid, cables_dict = run_analysis(param)
        logger.info("Nopywer analysis completed :)")
        return grid, cables_dict
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main()
