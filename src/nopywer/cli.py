import json
import logging
from pathlib import Path
from typing import Annotated

import typer

import nopywer

logger = logging.getLogger(__name__)

app = typer.Typer()


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
        str | None,
        typer.Option(
            "--inventory",
            help="Equipment inventory spreadsheet",
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

    grid = nopywer.grid.PowerGrid.from_geojson(input)
    grid.analyze()

    if verbose:
        nopywer.io.print_grid_info(grid.nodes, grid.cables, grid.tree)

    if inventory_file:
        nopywer.inventory.choose_cables_in_inventory(inventory_file, grid.cables)
        nopywer.inventory.choose_distros_in_inventory(inventory_file, grid.nodes)

    result = nopywer.io.to_geojson(grid.nodes, grid.cables)

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
