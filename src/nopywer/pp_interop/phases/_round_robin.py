"""Strategy B — round-robin phase distribution.

The simpler of the two strategies: walk the candidate loads in grid
order and assign legs cyclically, `L1, L2, L3, L1, L2, L3, ...`.

This mirrors what a careful electrician does pulling a corridor of
stalls — alternate the leg on each successive drop. It is purely
*positional*: it never looks at how much power a load draws, so a
run of heavy loads landing on consecutive positions can still pile
onto one leg. The upside is that it is trivial, deterministic, and a
reasonable default when load sizes are unknown or roughly uniform.

== When this is the right choice ==

  - load sizes are unknown, unreliable, or genuinely uniform — there
    is nothing for a size-aware strategy to exploit;
  - you want the assignment to be obvious and auditable on site (the
    leg follows position in the list, full stop);
  - it is a baseline: doc 10 uses round-robin as the reference that
    greedy has to beat.

For size-aware balancing see `_greedy.py` (Strategy D), which on
fixtures with varied load sizes typically cuts the imbalance by an
order of magnitude.
"""

from ...models import PowerGrid
from ._common import (
    PhaseAssignment,
    build_assignment,
    single_phase_candidates,
)


def assign_round_robin(grid: PowerGrid, *, usage_factor: float) -> PhaseAssignment:
    """Assign each single-phase candidate a leg, cycling L1 / L2 / L3.

    The i-th candidate (in grid order) gets leg `(i % 3) + 1`, so the
    sequence is `L1, L2, L3, L1, ...`. Candidate selection is done by
    `single_phase_candidates` — generators, zero-power nodes, loads
    already carrying a `phase`, and loads too big for one leg are all
    excluded and left as-is.

    The assignment is **positional, not size-aware**. Three 4 kW
    loads followed by three 1 kW loads would put all the heavy ones
    on L1/L2/L3 and all the light ones on L1/L2/L3 again — balanced
    here only because the counts line up. Reorder the grid and the
    balance changes. That sensitivity is the price of simplicity; it
    is exactly what `assign_greedy` removes.

    Args:
        grid: the grid to plan phases for. Not mutated — pass the
            result to `apply_assignment` to write it back.
        usage_factor: **required**, keyword-only. Assumed fraction
            of nameplate power loads draw together. No default —
            see `DEFAULT_USAGE_FACTOR` (0.5) for the project-wide
            reference figure. Does **not** change *which* leg a
            load gets (this strategy is positional), but it does
            scale the reported `leg_totals_w` and `balance_pct`, and
            it shifts the capacity cut-off in
            `single_phase_candidates` (so a load can move in or out
            of the candidate set as the factor changes).

    Returns:
        A `PhaseAssignment`. Fully reproducible for a given grid and
        usage factor: same grid order in, same legs out. If the grid
        has no single-phase candidates, `phases` is empty and the
        result describes just the fixed (balanced / pre-assigned)
        loads.
    """
    candidates = single_phase_candidates(grid, usage_factor=usage_factor)
    phases = {name: (i % 3) + 1 for i, (name, _) in enumerate(candidates)}
    return build_assignment(grid, phases, usage_factor)
