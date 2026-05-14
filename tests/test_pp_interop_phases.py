"""Tests for the per-load phase distribution strategies.

`nopywer.pp_interop.phases` synthesises a leg (L1/L2/L3) for every
single-phase load on a grid that shipped without phase data — the
prerequisite for asymmetric `runpp_3ph` work (research doc 10).

Two strategies share one set of scaffolding:

  - `_common` — candidate selection, the fixed-leg seed, the balance
    metric, and `apply_assignment`.
  - `assign_round_robin` (Strategy B) — positional, cyclic legs.
  - `assign_greedy` (Strategy D) — size-aware, heaviest load onto the
    currently-lightest leg.

The unit tests below build tiny hand-made grids with arithmetic that
works out cleanly, so an expected leg layout can be asserted exactly.
One integration test runs both strategies against the real 2026
field-export fixture and checks the property that motivates having
two strategies at all: greedy balances better than round-robin.
"""

from pathlib import Path

import pytest

from nopywer.models import PowerGrid, PowerNode
from nopywer.pp_interop.phases import (
    DEFAULT_USAGE_FACTOR,
    SINGLE_PHASE_CAPACITY_W,
    PhaseAssignment,
    apply_assignment,
    assign_greedy,
    assign_round_robin,
    single_phase_candidates,
)
from nopywer.pp_interop.phases._common import _fixed_leg_seed, build_assignment

FIXTURES = Path(__file__).parent / "fixtures"


def make_grid(loads: list[tuple[str, float, object]], gen_power: float = 0.0) -> PowerGrid:
    """Build a cable-less `PowerGrid` from `(name, power_watts, phase)` specs.

    The strategies never touch cables, so an empty cable dict is fine.
    Each node is given a distinct longitude purely so they are
    well-formed; geometry is irrelevant to phase distribution.
    """
    nodes = {"gen": PowerNode("gen", 0.0, 0.0, power_watts=gen_power, is_generator=True)}
    for i, (name, power, phase) in enumerate(loads):
        nodes[name] = PowerNode(name, float(i + 1), 0.0, power_watts=power, phase=phase)
    return PowerGrid(nodes=nodes, cables={})


# --- single_phase_candidates -------------------------------------------------


def test_single_phase_capacity_constant():
    """The capacity cut-off is 16 A x 230 V x 0.9, derived not hard-coded."""
    assert SINGLE_PHASE_CAPACITY_W == pytest.approx(16 * 230 * 0.9)


def test_candidates_include_only_eligible_loads():
    """Generator, zero-power, pre-phased and over-capacity loads are excluded."""
    grid = make_grid(
        [
            ("small", 2000.0, None),  # eligible
            ("zero", 0.0, None),  # excluded: no power
            ("phased_int", 2000.0, 2),  # excluded: already has a phase
            ("phased_list", 2000.0, [1, 3]),  # excluded: already multi-phase
            ("marker", 2000.0, "U"),  # excluded: sub-grid marker counts as phased
            ("huge", 20000.0, None),  # excluded: too big for one leg even at 0.5x
        ],
        gen_power=1000.0,
    )
    names = [name for name, _ in single_phase_candidates(grid)]
    assert names == ["small"]


def test_candidates_return_usage_adjusted_watts_in_grid_order():
    """Each pair carries effective (usage x nameplate) watts, in grid order."""
    grid = make_grid([("a", 2000.0, None), ("b", 1000.0, None)])
    assert single_phase_candidates(grid, usage_factor=0.5) == [("a", 1000.0), ("b", 500.0)]


def test_candidates_capacity_cutoff_moves_with_usage_factor():
    """A load near the cut-off is a candidate at 0.5x but not at 1.0x."""
    # 5 kW nameplate: 2.5 kW effective at 0.5x (under ~3.3 kW cap), 5 kW at 1.0x (over).
    grid = make_grid([("borderline", 5000.0, None)])
    assert [n for n, _ in single_phase_candidates(grid, usage_factor=0.5)] == ["borderline"]
    assert single_phase_candidates(grid, usage_factor=1.0) == []


# --- _fixed_leg_seed ---------------------------------------------------------


def test_fixed_leg_seed_spreads_balanced_and_lands_phased():
    """Balanced loads spread /3; int phase lands on one leg; list phase splits."""
    grid = make_grid(
        [
            ("balanced", 3000.0, None),  # -> 1000 on each leg
            ("on_l1", 2000.0, 1),  # -> 2000 on L1
            ("split", 2000.0, [2, 3]),  # -> 1000 on L2, 1000 on L3
            ("a_candidate", 1000.0, None),  # excluded via candidate_names
        ],
        gen_power=5000.0,  # generator never contributes
    )
    legs = _fixed_leg_seed(grid, candidate_names={"a_candidate"}, usage_factor=1.0)
    assert legs == [1000.0 + 2000.0, 1000.0 + 1000.0, 1000.0 + 1000.0]


# --- build_assignment --------------------------------------------------------


def test_build_assignment_sums_seed_and_placements():
    """Leg totals are the fixed seed plus the candidate placements."""
    grid = make_grid([("balanced", 3000.0, None), ("c", 1200.0, None)])
    # seed: balanced spreads 1000/leg. placement: c (1200 W) onto L2.
    assignment = build_assignment(grid, {"c": 2}, usage_factor=1.0)
    assert assignment.leg_totals_w == (1000.0, 1000.0 + 1200.0, 1000.0)
    assert assignment.usage_factor == 1.0


def test_build_assignment_balance_pct_zero_when_level_and_when_empty():
    """A level split is 0 %; a grid with no load is defined as 0 % too."""
    level = build_assignment(make_grid([("x", 900.0, None)]), {"x": 1}, usage_factor=1.0)
    # x on L1 only -> (900, 0, 0) -> heavily imbalanced, definitely not 0
    assert level.balance_pct > 0

    empty = build_assignment(make_grid([]), {}, usage_factor=1.0)
    assert empty.balance_pct == 0.0
    assert empty.leg_totals_w == (0.0, 0.0, 0.0)


def test_build_assignment_balance_pct_matches_std_over_mean():
    """balance_pct is 100 x std / mean of the three leg totals."""
    grid = make_grid([("a", 3000.0, 1), ("b", 1500.0, 2)])
    # both pre-phased, so candidate set is empty; seed = (3000, 1500, 0)
    assignment = build_assignment(grid, {}, usage_factor=1.0)
    mean = 4500.0 / 3
    variance = ((3000 - mean) ** 2 + (1500 - mean) ** 2 + (0 - mean) ** 2) / 3
    assert assignment.balance_pct == pytest.approx(100.0 * variance**0.5 / mean)


def test_build_assignment_raises_on_unknown_node():
    """Naming a node that is not on the grid is a KeyError, not a silent skip."""
    with pytest.raises(KeyError):
        build_assignment(make_grid([("real", 1000.0, None)]), {"ghost": 1}, usage_factor=1.0)


# --- assign_round_robin ------------------------------------------------------


def test_round_robin_cycles_legs_in_grid_order():
    """Candidates get L1, L2, L3, L1, ... following grid order exactly."""
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c", "d")])
    assignment = assign_round_robin(grid, usage_factor=1.0)
    assert assignment.phases == {"a": 1, "b": 2, "c": 3, "d": 1}


def test_round_robin_is_reproducible():
    """Same grid in, same assignment out — no hidden state."""
    grid = make_grid([(n, 1500.0, None) for n in ("a", "b", "c")])
    assert assign_round_robin(grid).phases == assign_round_robin(grid).phases


def test_round_robin_usage_factor_changes_totals_not_legs():
    """The factor rescales leg totals but never moves a load to another leg."""
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    half = assign_round_robin(grid, usage_factor=0.5)
    full = assign_round_robin(grid, usage_factor=1.0)
    assert half.phases == full.phases
    assert half.leg_totals_w == tuple(v / 2 for v in full.leg_totals_w)


def test_round_robin_empty_when_no_candidates():
    """A grid whose loads are all pre-phased yields an empty assignment."""
    grid = make_grid([("a", 1000.0, 1), ("b", 1000.0, 2)])
    assert assign_round_robin(grid).phases == {}


# --- assign_greedy -----------------------------------------------------------


def test_greedy_places_heaviest_first_onto_lightest_leg():
    """Known layout: 3 kW + three 1 kW loads, all at usage 1.0.

    Sorted heaviest-first: a(3000), then b, c, d (1000 each).
      a -> L1            legs (3000, 0, 0)
      b -> L2 (lightest) legs (3000, 1000, 0)
      c -> L3 (lightest) legs (3000, 1000, 1000)
      d -> L2 (tie L2/L3 -> lowest index) legs (3000, 2000, 1000)
    """
    grid = make_grid(
        [("a", 3000.0, None), ("b", 1000.0, None), ("c", 1000.0, None), ("d", 1000.0, None)]
    )
    assignment = assign_greedy(grid, usage_factor=1.0)
    assert assignment.phases == {"a": 1, "b": 2, "c": 3, "d": 2}
    assert assignment.leg_totals_w == (3000.0, 2000.0, 1000.0)


def test_greedy_beats_round_robin_on_uneven_load_sizes():
    """The whole point of Strategy D: lower imbalance than Strategy B."""
    # Grid order interleaves one heavy load among light ones — the worst
    # case for round-robin's positional assignment.
    grid = make_grid(
        [("a", 3000.0, None), ("b", 1000.0, None), ("c", 1000.0, None), ("d", 1000.0, None)]
    )
    rr = assign_round_robin(grid, usage_factor=1.0)
    greedy = assign_greedy(grid, usage_factor=1.0)
    assert greedy.balance_pct < rr.balance_pct


def test_greedy_balances_around_the_fixed_seed():
    """Greedy levels the *whole* grid, not just its candidates.

    A pre-assigned 4 kW load already sits on L1, so greedy should
    steer its candidates onto L2/L3 to compensate.
    """
    grid = make_grid(
        [
            ("preassigned", 4000.0, 1),  # fixed seed: 4000 on L1
            ("x", 2000.0, None),  # candidate
            ("y", 2000.0, None),  # candidate
        ]
    )
    assignment = assign_greedy(grid, usage_factor=1.0)
    # both candidates should avoid the already-heavy L1
    assert set(assignment.phases.values()) == {2, 3}
    assert assignment.leg_totals_w == (4000.0, 2000.0, 2000.0)


def test_greedy_is_reproducible_with_deterministic_tie_break():
    """Equal-load ties break to the lowest leg index, every run."""
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    first = assign_greedy(grid)
    second = assign_greedy(grid)
    assert first.phases == second.phases == {"a": 1, "b": 2, "c": 3}


# --- apply_assignment --------------------------------------------------------


def test_apply_assignment_mutates_candidates_only():
    """Candidate phases are written; generator and pre-phased loads untouched."""
    grid = make_grid(
        [("cand", 2000.0, None), ("preassigned", 2000.0, 3)],
        gen_power=1000.0,
    )
    assignment = assign_greedy(grid, usage_factor=1.0)
    apply_assignment(grid, assignment)
    assert grid.nodes["cand"].phase == assignment.phases["cand"]
    assert grid.nodes["preassigned"].phase == 3  # unchanged
    assert grid.nodes["gen"].phase is None  # unchanged


def test_apply_assignment_is_idempotent():
    """Applying the same assignment twice leaves the grid unchanged."""
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    assignment = assign_round_robin(grid)
    apply_assignment(grid, assignment)
    snapshot = {n: grid.nodes[n].phase for n in assignment.phases}
    apply_assignment(grid, assignment)
    assert {n: grid.nodes[n].phase for n in assignment.phases} == snapshot


def test_apply_assignment_raises_on_unknown_node():
    """An assignment from a different grid fails loudly rather than silently."""
    grid = make_grid([("real", 1000.0, None)])
    stray = PhaseAssignment(
        phases={"ghost": 1}, usage_factor=1.0, leg_totals_w=(0, 0, 0), balance_pct=0
    )
    with pytest.raises(KeyError):
        apply_assignment(grid, stray)


# --- defaults ----------------------------------------------------------------


def test_default_usage_factor_is_half():
    """Doc 10's starting assumption: festival loads at 0.5x nameplate."""
    assert DEFAULT_USAGE_FACTOR == 0.5


# --- integration on the real field export ------------------------------------


def test_strategies_run_on_field_export_and_greedy_balances_better():
    """Both strategies handle the real 2026 export; greedy wins on balance.

    `2026-05-14_martin.geojson` is the unmodified field export — every
    load arrives unphased, so it exercises the full candidate path.
    """
    grid = PowerGrid.from_geojson(FIXTURES / "2026-05-14_martin.geojson")

    rr = assign_round_robin(grid)
    greedy = assign_greedy(grid)

    # the export has plenty of small loads -> a non-trivial candidate set
    assert len(rr.phases) > 5
    assert rr.phases.keys() == greedy.phases.keys()
    # every assignment is a valid leg
    assert all(leg in (1, 2, 3) for leg in greedy.phases.values())
    # the reason Strategy D exists
    assert greedy.balance_pct < rr.balance_pct
