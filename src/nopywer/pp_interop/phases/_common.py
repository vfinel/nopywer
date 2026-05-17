"""Shared scaffolding for per-load phase distribution strategies.

A festival grid that will be solved with pandapower's asymmetric
`runpp_3ph` benefits from every single-phase load declaring which
leg (L1 / L2 / L3) it sits on. The strategies in this package
synthesise that assignment for fixtures that ship unphased or
partially phased.

Everything the individual strategies have in common lives here:

  - **candidate selection** (`single_phase_candidates`) — which
    loads get a single leg vs which stay multi-phase (too big for a
    1-phase connection, or already carrying an explicit `phase`).
  - the **leg-balance metric** (`build_assignment`) — used to score
    and compare strategies.
  - the **write-back** (`apply_assignment`) — the one place a plan
    actually touches the grid.

A strategy is a function
`(PowerGrid, *, usage_factor: float) -> PhaseAssignment`. It does
not mutate the grid; call `apply_assignment` to write the result
back. The `usage_factor` (festival diversity factor — loads rarely
draw nameplate together) is required at every call site; the
project-wide reference value lives in
`pp_interop.config.DEFAULT_USAGE_FACTOR`.

== The data model it bridges ==

`PowerNode.phase` is the field every strategy ultimately drives. It
is deliberately polymorphic (see `nopywer.models`):

  - `None`        — unphased. `io.load_geojson` spreads the load
                    evenly across all three legs (balanced).
  - `1` / `2` / `3` — single-phase: the whole load sits on that leg.
  - `[1, 2]`      — multi-phase: the load is split evenly across the
                    listed legs (a 10 kW load on `[1, 2]` is 5 kW on
                    L1, 5 kW on L2).
  - `"U"` / `"Y"` — sub-grid reporting markers with no electrical
                    meaning; treated here the same as `None`.

A strategy only ever *creates* the single-int form, and only for
loads that arrive as `None`. Loads that already carry a `1/2/3`,
a list, or a string marker are left exactly as they are — the
planner (or a previous run) has spoken.
"""

import logging
from dataclasses import dataclass

from ...constants import PF, V0
from ...models import Cable16A, PowerGrid

logger = logging.getLogger(__name__)

# Most power a single-phase 16 A connection can carry: I x V x PF.
# A load whose effective (usage-adjusted) power exceeds this cannot
# sit on one leg and is left multi-phase. Derived from the catalogue
# (`Cable16A.max_current_a`) and the global voltage / power-factor
# constants so it tracks any change to those rather than hard-coding
# ~3.3 kW.
SINGLE_PHASE_CAPACITY_W = Cable16A.max_current_a * V0 * PF


@dataclass(frozen=True)
class PhaseAssignment:
    """The result of running a phase-distribution strategy.

    Immutable: a strategy returns one of these describing *what it
    would do*; nothing changes on the grid until `apply_assignment`
    is called. This split keeps strategies pure and comparable — you
    can run both `assign_round_robin` and `assign_greedy` on the same
    grid, inspect the two `balance_pct` values, and only then commit
    one.

    Attributes:
        phases: maps `PowerNode.name` to its assigned leg (1, 2 or 3).
            Only single-phase *candidate* loads appear here. Loads
            left multi-phase — balanced (`None`), already carrying an
            explicit `phase`, or too big for one leg — are deliberately
            absent, not present with a sentinel value. So
            `name in assignment.phases` is the precise test for "this
            strategy moved this load".
        usage_factor: the nameplate fraction used for balancing (see
            `config.DEFAULT_USAGE_FACTOR`). Recorded so a `PhaseAssignment`
            is self-describing — the leg totals below only make sense
            against the factor they were computed with.
        leg_totals_w: effective watts on (L1, L2, L3) *after* this
            assignment, including the contribution of loads not in
            `phases`: balanced loads spread evenly across all three
            legs, pre-assigned loads landed on their declared legs.
            This is the whole grid's predicted per-leg loading, not
            just the candidates' — that is what makes it a fair
            balance figure.
        balance_pct: leg imbalance as `100 * std / mean` of
            `leg_totals_w`. 0 % is a perfectly level three-way split;
            higher is worse. Uses the same formula as
            `io.print_grid_info` so the number is directly comparable
            to what the planner already sees in grid summaries. When
            the grid has no load at all the mean is 0 and this is
            defined as 0.0.
    """

    phases: dict[str, int]
    usage_factor: float
    leg_totals_w: tuple[float, float, float]
    balance_pct: float


def single_phase_candidates(
    grid: PowerGrid, *, usage_factor: float
) -> list[tuple[str, float]]:
    """Loads eligible for a single-leg assignment.

    A load is a candidate only when *all* of the following hold:

      1. it draws power — `power_watts > 0`. Zero-power transit nodes
         (distros, junctions) have no leg to balance and are skipped.
      2. it is not the generator — the source is not a load.
      3. it has no explicit `phase` yet — `phase is None`. A load
         already carrying `1/2/3`, a `[...]` list, or a `"U"/"Y"`
         marker has been decided elsewhere and is left untouched.
      4. it fits on one leg — its *effective* power
         (`power_watts * usage_factor`) is within
         `SINGLE_PHASE_CAPACITY_W`. A load bigger than a single 16 A
         connection can carry must stay multi-phase; forcing it onto
         one leg would be a connection that cannot physically exist.

    Loads failing (4) are intentionally *not* returned and so are
    never single-phased by a strategy — they remain `None` (balanced)
    and the planner is expected to wire them three-phase.

    Args:
        grid: the grid to inspect. Not mutated.
        usage_factor: **required**, keyword-only. Assumed fraction of
            nameplate power loads draw together. Has no safe default
            because the right value is event-specific (audio shows
            with simultaneous peaks differ from food courts with
            spread loads); see `config.DEFAULT_USAGE_FACTOR` for the
            project-wide reference figure (0.5) callers can adopt
            explicitly. Scales the effective power used for the
            capacity test in (4): at 0.5x a 6 kW nameplate load is
            treated as 3 kW and so *is* a single-phase candidate; at
            1.0x the same load is 6 kW and is not.

    Returns:
        `(name, effective_watts)` pairs in grid iteration order.
        `effective_watts` is already usage-adjusted, so callers can
        sum or sort on it directly without re-applying the factor.
        Order is grid order; strategies that care about size (greedy)
        re-sort, strategies that care about position (round-robin)
        rely on it.
    """
    candidates: list[tuple[str, float]] = []
    for name, node in grid.nodes.items():
        if node.is_generator or node.power_watts <= 0:
            continue
        if node.phase is not None:
            continue
        effective_w = node.power_watts * usage_factor
        if effective_w <= SINGLE_PHASE_CAPACITY_W:
            candidates.append((name, effective_w))
    return candidates


def _fixed_leg_seed(grid: PowerGrid, candidate_names: set[str], usage_factor: float) -> list[float]:
    """Per-leg watts contributed by loads that are *not* being distributed.

    Before a strategy places its candidates it needs to know the leg
    loading it is starting from — the grid is rarely a blank slate.
    Three kinds of load contribute to this seed:

      - **balanced / unphased** (`phase is None`, but excluded from
        the candidate set because it is too big for one leg): spread
        evenly, `effective_w / 3` onto each of L1, L2, L3.
      - **explicit single phase** (`phase` is an int 1-3): the whole
        `effective_w` lands on that one leg.
      - **explicit multi-phase** (`phase` is a list, e.g. `[1, 2]`):
        `effective_w` split evenly across the listed legs.

    Generators, zero-power nodes, and anything in `candidate_names`
    are skipped — candidates are the strategy's job, not the seed's.
    A `"U"` / `"Y"` string marker falls through to the balanced
    branch (it has no electrical meaning).

    This is private: it is an implementation detail shared by the
    strategies and `build_assignment`, not part of the package API.

    Args:
        grid: the grid to inspect. Not mutated.
        candidate_names: names the caller intends to assign itself;
            excluded from the seed so they are not double-counted.
        usage_factor: nameplate fraction, applied to every load's
            `power_watts` before it is added to a leg.

    Returns:
        A fresh 3-element list `[L1, L2, L3]` of effective watts.
        Always a new list — callers mutate it freely.
    """
    legs = [0.0, 0.0, 0.0]
    for name, node in grid.nodes.items():
        if node.is_generator or node.power_watts <= 0 or name in candidate_names:
            continue
        effective_w = node.power_watts * usage_factor
        phase = node.phase
        if isinstance(phase, int) and 1 <= phase <= 3:
            legs[phase - 1] += effective_w
        elif isinstance(phase, list) and phase:
            legs_used = [p for p in phase if isinstance(p, int) and 1 <= p <= 3]
            for leg in legs_used:
                legs[leg - 1] += effective_w / len(legs_used)
        else:
            # balanced / unphased / string marker — spread evenly
            if isinstance(phase, str):
                logger.warning(
                    "Node %r carries legacy string phase marker %r; treating "
                    "as unphased (balanced across L1/L2/L3) in the leg seed.",
                    name,
                    phase,
                )
            for i in range(3):
                legs[i] += effective_w / 3
    return legs


def build_assignment(
    grid: PowerGrid, phases: dict[str, int], usage_factor: float
) -> PhaseAssignment:
    """Wrap a raw `{name: leg}` mapping into a scored `PhaseAssignment`.

    The single place leg totals and the balance metric are computed,
    so every strategy reports them identically. A strategy's only job
    is to decide `phases`; this function does the bookkeeping.

    The leg totals are the sum of two parts:

      - the **fixed seed** — every load *not* in `phases`, via
        `_fixed_leg_seed` (balanced loads spread, pre-assigned loads
        on their legs);
      - the **candidate placements** — each `name -> leg` in `phases`,
        adding that load's effective power to the chosen leg.

    `balance_pct` is then `100 * std / mean` over the three totals,
    matching `io.print_grid_info`. A grid with no load anywhere has
    `mean == 0`; balance is defined as 0.0 there rather than dividing
    by zero.

    Args:
        grid: the grid the mapping was computed for. Not mutated.
            Names in `phases` must exist in `grid.nodes`.
        phases: the strategy's decision — `name -> leg (1/2/3)`. May
            be empty (e.g. a grid whose every load is already phased
            or too big to single-phase); the result is then just the
            seed.
        usage_factor: nameplate fraction; must match what the
            strategy used to pick `phases`, and is stored verbatim on
            the result.

    Returns:
        A fully populated, immutable `PhaseAssignment`.

    Raises:
        KeyError: if `phases` names a node not present in `grid`.
    """
    legs = _fixed_leg_seed(grid, set(phases), usage_factor)
    for name, leg in phases.items():
        legs[leg - 1] += grid.nodes[name].power_watts * usage_factor

    mean = sum(legs) / 3
    if mean > 0:
        variance = sum((leg - mean) ** 2 for leg in legs) / 3
        balance_pct = 100.0 * variance**0.5 / mean
    else:
        balance_pct = 0.0

    return PhaseAssignment(
        phases=phases,
        usage_factor=usage_factor,
        leg_totals_w=(legs[0], legs[1], legs[2]),
        balance_pct=balance_pct,
    )


def apply_assignment(grid: PowerGrid, assignment: PhaseAssignment) -> None:
    """Write an assignment back onto the grid, mutating `PowerNode.phase`.

    The one place a strategy's plan actually touches the grid. Kept
    separate from the strategies so that planning is free of side
    effects: you can compute, compare, and discard `PhaseAssignment`s
    without ever changing the grid, then commit exactly one.

    Only the candidate loads in `assignment.phases` are touched —
    each has its `phase` set to the assigned int leg. Multi-phase
    loads, pre-assigned loads, the generator, and zero-power nodes
    are never in `phases` and so are left exactly as they were.

    Idempotent: applying the same assignment twice is a no-op the
    second time. Applying it does *not* recompute `power_per_phase`
    — that happens when the grid is next loaded or analysed.

    Args:
        grid: the grid to mutate. Must contain every node named in
            `assignment.phases`.
        assignment: the plan to commit, typically straight from
            `assign_round_robin` or `assign_greedy`.

    Raises:
        KeyError: if the assignment names a node not in `grid`
            (e.g. the assignment was computed against a different
            grid).
    """
    for name, leg in assignment.phases.items():
        grid.nodes[name].phase = leg
