"""Per-load phase distribution strategies.

Fixtures exported before phase planning was decided ship with every
load unphased. Pandapower's asymmetric `runpp_3ph` (and nopywer's own
per-phase tree walk) need each single-phase load to declare a leg.
This package synthesises that assignment.

Two strategies, deliberately kept in separate modules:

  - `assign_round_robin` (Strategy B, `_round_robin.py`) — cyclic
    L1/L2/L3 down the load list. Positional, ignores load size.
  - `assign_greedy` (Strategy D, `_greedy.py`) — size-aware; each
    load goes to whichever leg is currently lightest.

Both return a `PhaseAssignment` and do not mutate the grid; call
`apply_assignment` to write the chosen plan back. All modelling
assumptions (usage factor, single-phase capacity) live in `_common`.

For the common "load a fixture, phase it, write it out" workflow
see `phase_geojson` (`_export.py`) — a single-call wrapper around
the whole pipeline aimed at scripts and the CLI. Internal callers
should keep using the individual primitives so every step is
visible at the call site.
"""

from ..config import DEFAULT_USAGE_FACTOR
from ._common import (
    SINGLE_PHASE_CAPACITY_W,
    PhaseAssignment,
    apply_assignment,
    single_phase_candidates,
)
from ._export import phase_geojson
from ._greedy import assign_greedy
from ._round_robin import assign_round_robin

__all__ = [
    "DEFAULT_USAGE_FACTOR",
    "SINGLE_PHASE_CAPACITY_W",
    "PhaseAssignment",
    "apply_assignment",
    "assign_greedy",
    "assign_round_robin",
    "phase_geojson",
    "single_phase_candidates",
]
