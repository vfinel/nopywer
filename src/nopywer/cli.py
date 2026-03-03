import json
import logging
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

import nopywer

logger = logging.getLogger(__name__)

app = typer.Typer()


def run_analysis(grid, cables_dict):
    nopywer.analysis.find_connections(grid, cables_dict)
    nopywer.analysis.get_children("generator", grid, cables_dict)
    dlist = nopywer.analysis.compute_deepness_list(grid)

    for load in grid:
        if load != "generator":
            parent = grid[load].parent
            if parent is not None:
                cable2parent = grid[parent].children[load]["cable"]
                grid[load].cable = cable2parent

    grid, cables_dict = nopywer.analysis.cumulate_current(
        grid, cables_dict, dlist,
        nopywer.constants.V0, nopywer.constants.PF,
    )
    nopywer.analysis.compute_distro_requirements(grid, cables_dict)
    grid, cables_dict = nopywer.analysis.compute_voltage_drop(
        grid, cables_dict,
    )

    return grid, cables_dict, dlist


@app.command()
def analyze_grid(
    input: Annotated[
        Path,
        typer.Argument(help="Input GeoJSON file with nodes and cables"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output GeoJSON file"),
    ] = None,
    inventory_file: Annotated[
        Path | None,
        typer.Option(
            "--inventory", help="Equipment inventory spreadsheet (.ods)",
        ),
    ] = None,
    do_update: Annotated[
        bool,
        typer.Option(help="Write results back to the input GeoJSON"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print detailed grid info"),
    ] = False,
):
    if verbose:
        logging.basicConfig(level=logging.INFO)

    nodes, cables_dict = nopywer.io.load_grid_geojson(input)
    grid = {n.name: n for n in nodes}

    grid, cables_dict, dlist = run_analysis(grid, cables_dict)

    if verbose:
        cum = grid["generator"].cum_power
        phase_balance = 100 * np.std(cum) / np.mean(cum)
        has_no_phase = [
            name for name, node in grid.items()
            if name != "generator" and node.phase is None
        ]
        nopywer.analysis.print_grid_info(
            grid, cables_dict, phase_balance, has_no_phase, dlist,
        )

    if inventory_file:
        project_folder = str(input.parent)
        nopywer.inventory.choose_cables_in_inventory(
            project_folder, cables_dict, str(inventory_file),
        )
        nopywer.inventory.choose_distros_in_inventory(
            project_folder, grid, str(inventory_file),
        )

    result = nopywer.io.analysis_to_geojson(grid, cables_dict)

    if do_update:
        with open(input, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Input updated in-place: {input}")

    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Results written to {output}")
    elif not do_update:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
