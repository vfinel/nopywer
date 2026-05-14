"""Strategy D — greedy least-loaded-leg phase distribution.

The size-aware counterpart to round-robin. Where Strategy B assigns
legs by *position* in the load list, this assigns by *load size*:

  1. seed the three legs with the loads that are not being
     distributed — balanced loads spread evenly, pre-assigned loads
     on their declared legs (this is `_fixed_leg_seed`);
  2. sort the single-phase candidates heaviest-first;
  3. drop each candidate onto whichever leg is currently lightest.

Heaviest-first matters: placing the big loads while the legs are
still near-empty leaves the small loads to fine-tune the balance at
the end. Do it the other way round and the last (largest) load can
blow a leg that the small loads had carefully levelled. This is the
standard greedy multiway-partition heuristic (the "longest processing
time" rule) — not provably optimal, but in practice it lands far
closer to a level three-way split than round-robin, especially when
load sizes vary a lot.

== Cost of the win ==

Greedy needs trustworthy load sizes — that is the input it exploits.
If the nameplate figures are guesses, its apparent precision is
false and round-robin's positional honesty may be preferable. It is
also less obvious on site: the leg a load ends up on depends on
every heavier load before it, not on a rule you can read off a list.

For the simpler positional strategy see `_round_robin.py` (Strategy B).
"""

from ...models import PowerGrid
from ._common import (
    DEFAULT_USAGE_FACTOR,
    PhaseAssignment,
    _fixed_leg_seed,
    build_assignment,
    single_phase_candidates,
)


def assign_greedy(grid: PowerGrid, usage_factor: float = DEFAULT_USAGE_FACTOR) -> PhaseAssignment:
    """Assign each single-phase candidate to the currently-lightest leg.

    Candidates (from `single_phase_candidates`) are sorted by
    effective power, heaviest first, and placed one at a time onto
    whichever leg has the least load *so far* — where "so far"
    starts from the fixed seed of non-distributed loads, not from
    zero. So greedy balances *around* the balanced and pre-assigned
    loads already on the grid, rather than pretending the grid is
    empty.

    Tie-breaking is deterministic: when two or more legs are equally
    loaded, `min` picks the lowest index (L1 before L2 before L3).
    Combined with the heaviest-first sort, this makes the whole
    result reproducible for a given grid and usage factor.

    This is a heuristic, not an optimiser. It will not always find
    the theoretically most level split (that is NP-hard in general),
    but for festival-shaped inputs — a handful of medium loads and a
    long tail of small ones — it gets very close, and unlike
    round-robin it is insensitive to the order loads appear in the
    grid.

    Args:
        grid: the grid to plan phases for. Not mutated — pass the
            result to `apply_assignment` to write it back.
        usage_factor: assumed fraction of nameplate power loads draw
            together. Unlike round-robin, this **does** affect the
            assignment: both the lightest-leg decision and the
            heaviest-first sort run on usage-adjusted watts, and the
            factor also shifts the candidate capacity cut-off. A
            different factor can therefore produce a genuinely
            different leg layout, not just rescaled totals.

    Returns:
        A `PhaseAssignment` whose `balance_pct` is typically far
        lower than round-robin's on the same grid. If the grid has
        no single-phase candidates, `phases` is empty and the result
        describes just the fixed (balanced / pre-assigned) loads.
    """
    candidates = single_phase_candidates(grid, usage_factor)
    legs = _fixed_leg_seed(grid, {name for name, _ in candidates}, usage_factor)

    phases: dict[str, int] = {}
    for name, effective_w in sorted(candidates, key=lambda c: c[1], reverse=True):
        target = min(range(3), key=lambda i: legs[i])
        legs[target] += effective_w
        phases[name] = target + 1

    return build_assignment(grid, phases, usage_factor)
