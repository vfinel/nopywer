import logging
import os
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from qgis.core import QgsApplication, QgsProject

import nopywer as npw
from nopywer.constants import V0, PF

logger = logging.getLogger(__name__)

app = typer.Typer()


def load_qgis_project(project_file: str) -> QgsApplication:
    logger.info("Initializing QGIS...")
    qgs = QgsApplication([], False)
    qgs.initQgis()

    if not Path(project_file).is_file():
        raise FileNotFoundError(f'Project file does not exist: "{project_file}"')

    qgs_project = QgsProject.instance()
    if not qgs_project.read(project_file):
        raise RuntimeError(f'Unable to read project "{project_file}"')

    logger.info(f"Project: {qgs_project.fileName()}")
    return qgs


def run_analysis(
    *,
    cables_layers_list: list[str],
    loads_layers_list: list[str],
    spreadsheet_name: str,
    spreadsheet_sheet: str,
    inventory: str,
    update_layers: bool,
    update_spreadsheet: bool,
) -> tuple[dict, dict]:
    qgs_project = QgsProject.instance()
    project_folder = os.path.dirname(qgs_project.absoluteFilePath())

    param = {
        "cables_layers_list": cables_layers_list,
        "loads_layers_list": loads_layers_list,
    }
    cables_dict, grid, dlist = npw.get_grid_geometry(qgs_project, param)

    sparam = {"name": spreadsheet_name, "sheet": spreadsheet_sheet, "skiprows": 0}
    grid, cables_dict, has_no_phase, sh = npw.read_spreadsheet(
        project_folder, grid, cables_dict, sparam
    )

    grid, cables_dict = npw.cumulate_current(grid, cables_dict, dlist, V0, PF)

    phase_balance = 100 * np.std(
        grid["generator"].cum_power / np.mean(grid["generator"].cum_power)
    )

    cables_dict = npw.inspect_cable_layers(
        qgs_project, cables_layers_list, cables_dict
    )
    grid = npw.compute_distro_requirements(grid, cables_dict)

    logger.info("Computing voltage drop...")
    grid, cables_dict = npw.compute_voltage_drop(grid, cables_dict)

    logger.info("Checking inventory...")
    npw.choose_cables_in_inventory(project_folder, cables_dict, inventory)
    npw.choose_distros_in_inventory(project_folder, grid, inventory)

    npw.print_grid_info(grid, cables_dict, phase_balance, has_no_phase, dlist)

    if update_layers:
        npw.update_1phase_layers(grid, cables_dict, qgs_project)
        npw.update_load_layers(grid, loads_layers_list, qgs_project)

    if update_spreadsheet:
        npw.write_spreadsheet(grid, sh)

    return grid, cables_dict


@app.command()
def main(
    project: Annotated[
        Path,
        typer.Argument(help="QGIS project file (.qgs)"),
    ],
    cable_layer: Annotated[
        list[str],
        typer.Option(help="QGIS cable layer name (repeat for multiple)"),
    ],
    load_layer: Annotated[
        list[str],
        typer.Option(help="QGIS load/node layer name (repeat for multiple)"),
    ],
    spreadsheet: Annotated[
        Path,
        typer.Option(help="Phase-balance spreadsheet (.ods)"),
    ],
    inventory: Annotated[
        Path,
        typer.Option(help="Equipment inventory spreadsheet (.ods)"),
    ],
    sheet: Annotated[
        str,
        typer.Option(help="Sheet name in the phase-balance spreadsheet"),
    ] = "All",
    update_layers: Annotated[
        bool,
        typer.Option(help="Write results back to QGIS layers"),
    ] = False,
    update_spreadsheet: Annotated[
        bool,
        typer.Option(help="Write results back to the phase-balance spreadsheet"),
    ] = False,
):
    qgs = load_qgis_project(str(project))
    try:
        run_analysis(
            cables_layers_list=cable_layer,
            loads_layers_list=load_layer,
            spreadsheet_name=str(spreadsheet),
            spreadsheet_sheet=sheet,
            inventory=str(inventory),
            update_layers=update_layers,
            update_spreadsheet=update_spreadsheet,
        )
        logger.info("Nopywer analysis completed :)")
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    app()
