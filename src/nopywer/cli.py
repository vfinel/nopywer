import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from . import inventory
from .analyze import analyze
from .io import print_grid_info
from .models import PowerGrid
from .pp_interop import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = typer.Typer()


@app.command()
def analyze_grid(
    input: Annotated[
        Path,
        typer.Argument(help="Input GeoJSON file with nodes and cables", envvar="NOPYWER_INPUT"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output GeoJSON file", envvar="NOPYWER_OUTPUT"),
    ] = None,
    engine: Annotated[
        str,
        typer.Option("--engine", "-e", help="Analysis engine to use (tree_walk, pandapower, asymmetric)"),
    ] = "tree_walk",
    load_factor: Annotated[
        float,
        typer.Option(
            "--load-factor",
            "-l",
            help="Multiplier on nameplate power for AC solves (e.g. 0.5 for festival diversity)",
        ),
    ] = config.DEFAULT_USAGE_FACTOR,
    inventory_file: Annotated[
        str | None,
        typer.Option(
            "--inventory",
            help="Equipment inventory spreadsheet",
            envvar="NOPYWER_INVENTORY",
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

    grid = PowerGrid.from_geojson(input)

    # Scale loads in place if load_factor is provided and engine is AC-based
    if engine in ("pandapower", "asymmetric") and load_factor != 1.0:
        for node in grid.nodes.values():
            if not node.is_generator:
                node.power_watts *= load_factor
        logger.info(f" Scaled loads by factor {load_factor}")

    analyze(grid, engine=engine)

    if verbose:
        print_grid_info(grid.nodes, grid.cables, grid.tree, grid.generator)

    if inventory_file:
        inventory.choose_cables(inventory_file, grid.cables)
        inventory.choose_distros(inventory_file, grid.nodes)

    result = grid.to_geojson()

    if do_update:
        with open(input, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Input updated in-place: {input}")

    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        print(' ')
        logger.info(f" Results written to {output}")
    elif not do_update:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
