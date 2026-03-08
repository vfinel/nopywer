import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from . import inventory
from .analyze import analyze
from .io import print_grid_info
from .models import PowerGrid
from .optimize_milp import optimize_layout_to_files

logger = logging.getLogger(__name__)

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
    analyze(grid)

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
        logger.info(f"Results written to {output}")
    elif not do_update:
        print(json.dumps(result, indent=2))


@app.command("optimize-milp")
def optimize_grid_milp(
    input_geojson: Annotated[
        Path,
        typer.Argument(help="Input GeoJSON with point nodes.", envvar="NOPYWER_INPUT"),
    ],
    output_geojson: Annotated[
        Path,
        typer.Option("--output-geojson", help="Where to write optimized layout GeoJSON."),
    ] = Path("milp_layout.geojson"),
    plot_html: Annotated[
        Path | None,
        typer.Option(
            "--plot-html",
            help="Optional HTML path for an interactive pyvis network plot.",
        ),
    ] = None,
    candidate_k: Annotated[
        int,
        typer.Option(
            "--candidate-k",
            help="Nearest-neighbor candidate arcs per node (0 for full graph).",
        ),
    ] = 12,
    time_limit_s: Annotated[
        int,
        typer.Option("--time-limit-s", help="MILP solver time limit in seconds."),
    ] = 60,
    extra_cable_m: Annotated[
        float,
        typer.Option("--extra-cable-m", help="Extra slack added to each selected cable length."),
    ] = 10.0,
    solver_msg: Annotated[
        bool,
        typer.Option("--solver-msg", help="Enable CBC solver output."),
    ] = False,
    weight_cost: Annotated[
        float,
        typer.Option("--weight-cost", help="Objective weight for cable-tier cost term."),
    ] = 1.0,
    weight_length: Annotated[
        float,
        typer.Option("--weight-length", help="Objective weight for pure cable-length term."),
    ] = 0.0,
    weight_power_distance: Annotated[
        float,
        typer.Option(
            "--weight-power-distance",
            help="Objective weight for distance-weighted power-routing term.",
        ),
    ] = 0.0,
    weight_voltage_drop: Annotated[
        float,
        typer.Option(
            "--weight-voltage-drop",
            help="Objective weight for linearized voltage-drop term.",
        ),
    ] = 0.0,
    weight_cumulative_voltage_drop: Annotated[
        float,
        typer.Option(
            "--weight-cumulative-voltage-drop",
            help="Objective weight for cumulative source-to-node voltage drop at load nodes.",
        ),
    ] = 0.0,
    max_voltage_drop_percent: Annotated[
        float | None,
        typer.Option(
            "--max-voltage-drop-percent",
            help=(
                "Optional hard cap on cumulative voltage drop for each load node, "
                "as percent of nominal voltage V0."
            ),
        ),
    ] = None,
):
    optimize_layout_to_files(
        input_geojson=input_geojson,
        output_geojson=output_geojson,
        plot_html=plot_html,
        candidate_k=candidate_k,
        time_limit_s=time_limit_s,
        extra_cable_m=extra_cable_m,
        solver_msg=solver_msg,
        weight_cost=weight_cost,
        weight_length=weight_length,
        weight_power_distance=weight_power_distance,
        weight_voltage_drop=weight_voltage_drop,
        weight_cumulative_voltage_drop=weight_cumulative_voltage_drop,
        max_voltage_drop_percent=max_voltage_drop_percent,
    )


if __name__ == "__main__":
    app()
