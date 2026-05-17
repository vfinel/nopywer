"""One-call helper to phase a GeoJSON fixture and write the result.

The building blocks (`assign_greedy` / `assign_round_robin`,
`apply_assignment`, `PowerGrid.to_geojson`) compose into a single
common workflow: load a fixture, plan phases, commit them, write
the phased fixture back out. `phase_geojson` is that workflow as a
single function, intended for scripts and the CLI rather than for
internal callers (which should keep using the individual primitives
so the call site shows every step).
"""

import json
from pathlib import Path
from typing import Literal

from ...io import load_geojson
from ...models import PowerGrid
from ._common import PhaseAssignment, apply_assignment
from ._greedy import assign_greedy
from ._round_robin import assign_round_robin

Strategy = Literal["greedy", "round_robin"]

_STRATEGIES = {
    "greedy": assign_greedy,
    "round_robin": assign_round_robin,
}


def phase_geojson(
    input_path: Path | str,
    output_path: Path | str,
    *,
    usage_factor: float,
    strategy: Strategy = "greedy",
) -> PhaseAssignment:
    """Load a GeoJSON, plan and apply phases, write the result out.

    The one-call convenience wrapper around the full
    `load_geojson → assign_* → apply_assignment → to_geojson → write`
    pipeline. Input and output paths are kept distinct so the source
    fixture is never modified in place.

    Args:
        input_path: GeoJSON file to read. May be in either the
            hand-authored input schema or the round-tripped export
            schema — `load_geojson` handles both.
        output_path: GeoJSON file to write. Will be overwritten if it
            exists. Pretty-printed with `indent=2` for diff-friendly
            commits to fixtures.
        usage_factor: **required**, keyword-only. Assumed fraction of
            nameplate power loads draw together. No default — see
            `config.DEFAULT_USAGE_FACTOR` (0.5) for the project-wide
            reference figure callers can adopt explicitly.
        strategy: which phase-assignment strategy to use. `"greedy"`
            (size-aware, doc 10's Strategy D, recommended default)
            or `"round_robin"` (positional, Strategy B, useful as a
            baseline). New strategies should land here as new string
            keys; the literal type is deliberately closed.

    Returns:
        The `PhaseAssignment` that was applied. Useful for logging
        the `balance_pct` or diffing two strategy runs without
        having to reload the written file.

    Raises:
        ValueError: if `strategy` is not one of the known names.
        FileNotFoundError: if `input_path` does not exist.
    """
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"unknown strategy {strategy!r}; "
            f"expected one of {sorted(_STRATEGIES)}"
        )

    nodes, cables = load_geojson(input_path)
    grid = PowerGrid(nodes=nodes, cables=cables)

    plan = _STRATEGIES[strategy](grid, usage_factor=usage_factor)
    apply_assignment(grid, plan)

    with open(output_path, "w") as f:
        json.dump(grid.to_geojson(), f, indent=2)

    return plan
