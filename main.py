import json
import logging
from pathlib import Path
from typing import Annotated

import typer

import nopywer as npw
from nopywer.constants import PF, V0

logger = logging.getLogger(__name__)

app = typer.Typer()


def run_analysis(grid, cables_dict):
    npw.find_connections(grid, cables_dict)
    npw.get_children("generator", grid, cables_dict)
    dlist = npw.compute_deepness_list(grid)

    for load in grid.keys():
        if load != "generator":
            parent = grid[load].parent
            if parent is not None:
                cable2parent = grid[parent].children[load]["cable"]
                grid[load].cable = cable2parent

    grid, cables_dict = npw.cumulate_current(
        grid, cables_dict, dlist, V0, PF
    )
    npw.compute_distro_requirements(grid, cables_dict)
    grid, cables_dict = npw.compute_voltage_drop(grid, cables_dict)

    return grid, cables_dict


@app.command()
def main(
    input: Annotated[
        Path,
        typer.Argument(help="Input GeoJSON file with nodes and cables"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output GeoJSON file"),
    ] = None,
    inventory: Annotated[
        Path | None,
        typer.Option(help="Equipment inventory spreadsheet (.ods)"),
    ] = None,
    do_update: Annotated[
        bool,
        typer.Option(help="Write results back to the input GeoJSON"),
    ] = False,
):
    nodes, cables_dict = npw.load_grid_geojson(input)
    grid = {n.name: n for n in nodes}

    grid, cables_dict = run_analysis(grid, cables_dict)

    if inventory:
        project_folder = str(input.parent)
        npw.choose_cables_in_inventory(
            project_folder, cables_dict, str(inventory)
        )
        npw.choose_distros_in_inventory(
            project_folder, grid, str(inventory)
        )

    result = npw.analysis_to_geojson(grid, cables_dict)

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
