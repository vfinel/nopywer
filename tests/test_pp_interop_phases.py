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
    """The single-phase capacity cut-off is derived, not a magic number.

    What: `SINGLE_PHASE_CAPACITY_W` equals 16 A x 230 V x 0.9.

    Why it matters: this constant decides which loads are eligible to
    sit on one leg. It must be *computed* from the catalogue's 16 A
    rating and the global voltage / power-factor constants — not
    hard-coded as ~3.3 kW — so that if any of those inputs change the
    cut-off tracks them instead of silently going stale.
    """
    assert SINGLE_PHASE_CAPACITY_W == pytest.approx(16 * 230 * 0.9)


def test_candidates_include_only_eligible_loads():
    """`single_phase_candidates` applies all four exclusion rules.

    What: a grid with one of every disqualifying case plus one valid
    load returns only the valid load.

    Why it matters: each excluded category is a distinct bug class if
    it leaked through — a strategy that tried to phase the generator,
    a 0 W transit distro, a load already carrying a `phase`, or a load
    too big for a single 16 A leg would each produce a physically
    wrong or destructive plan. This pins all four guards at once.
    """
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
    """Candidates carry usage-adjusted watts and stay in grid order.

    What: at usage 0.5x, two 2 kW / 1 kW loads come back as 1 kW /
    0.5 kW pairs, in the order they appear in the grid.

    Why it matters: greedy *sorts* on the returned watts, so they must
    already be effective (usage-adjusted), not nameplate — otherwise
    greedy would balance a peak that never happens. Round-robin
    *relies* on grid order for its positional cycling. Both
    contracts are load-bearing, so both are asserted here.
    """
    grid = make_grid([("a", 2000.0, None), ("b", 1000.0, None)])
    assert single_phase_candidates(grid, usage_factor=0.5) == [("a", 1000.0), ("b", 500.0)]


def test_candidates_capacity_cutoff_moves_with_usage_factor():
    """The eligibility cut-off shifts with the usage factor.

    What: a 5 kW nameplate load is a candidate at 0.5x usage (2.5 kW
    effective, under the ~3.3 kW single-leg cap) but not at 1.0x
    (5 kW effective, over it).

    Why it matters: the usage factor is not cosmetic. It changes the
    physical question "can this load sit on one 16 A leg?" — and so
    changes the candidate set itself, not just the reported totals.
    A regression that applied the factor only to reporting would
    pass the round-robin tests but fail here.
    """
    grid = make_grid([("borderline", 5000.0, None)])
    assert [n for n, _ in single_phase_candidates(grid, usage_factor=0.5)] == ["borderline"]
    assert single_phase_candidates(grid, usage_factor=1.0) == []


# --- _fixed_leg_seed ---------------------------------------------------------


def test_fixed_leg_seed_spreads_balanced_and_lands_phased():
    """The fixed-leg seed handles every non-candidate load form correctly.

    What: a balanced load spreads evenly (1/3 per leg), an int-phase
    load lands wholly on its leg, a list-phase load splits evenly
    across its listed legs — while the generator and any name passed
    in `candidate_names` contribute nothing.

    Why it matters: the seed is the leg loading a strategy *starts
    from* — greedy balances around it. If any of the three phase
    forms were mis-handled, every greedy assignment on a grid with
    pre-existing phased loads would be silently skewed, and the bug
    would be invisible on the all-unphased fixtures.
    """
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
    """`build_assignment` adds candidate placements on top of the seed.

    What: with a balanced 3 kW load (seed: 1 kW/leg) and a 1.2 kW
    candidate placed on L2, the leg totals are (1000, 2200, 1000) and
    the usage factor is recorded on the result.

    Why it matters: this is the one place leg totals are computed, so
    every strategy reports them the same way. The test proves the two
    contributions — the fixed seed and the strategy's own placements —
    are both counted, exactly once each.
    """
    grid = make_grid([("balanced", 3000.0, None), ("c", 1200.0, None)])
    # seed: balanced spreads 1000/leg. placement: c (1200 W) onto L2.
    assignment = build_assignment(grid, {"c": 2}, usage_factor=1.0)
    assert assignment.leg_totals_w == (1000.0, 1000.0 + 1200.0, 1000.0)
    assert assignment.usage_factor == 1.0


def test_build_assignment_balance_pct_zero_when_level_and_when_empty():
    """`balance_pct` is well-defined at both ends of the range.

    What: a single load dumped entirely on L1 gives a clearly
    non-zero imbalance; a grid with no load at all gives exactly 0.0
    and zeroed leg totals.

    Why it matters: the empty-grid case is the div-by-zero trap —
    `mean` is 0, and the metric must be *defined* as 0.0 there rather
    than raising or producing NaN. Without this guard, calling a
    strategy on a load-free sub-grid would crash.
    """
    level = build_assignment(make_grid([("x", 900.0, None)]), {"x": 1}, usage_factor=1.0)
    # x on L1 only -> (900, 0, 0) -> heavily imbalanced, definitely not 0
    assert level.balance_pct > 0

    empty = build_assignment(make_grid([]), {}, usage_factor=1.0)
    assert empty.balance_pct == 0.0
    assert empty.leg_totals_w == (0.0, 0.0, 0.0)


def test_build_assignment_balance_pct_matches_std_over_mean():
    """`balance_pct` is exactly 100 x std / mean of the three leg totals.

    What: for a known imbalanced seed (3000, 1500, 0), the metric
    matches the std/mean formula computed independently in the test.

    Why it matters: this formula is deliberately the same one
    `io.print_grid_info` already uses for its "phase balance" line.
    Keeping them identical means a strategy's `balance_pct` is
    directly comparable to the number a planner already sees in grid
    summaries — a divergence here would make the two silently
    incomparable.
    """
    grid = make_grid([("a", 3000.0, 1), ("b", 1500.0, 2)])
    # both pre-phased, so candidate set is empty; seed = (3000, 1500, 0)
    assignment = build_assignment(grid, {}, usage_factor=1.0)
    mean = 4500.0 / 3
    variance = ((3000 - mean) ** 2 + (1500 - mean) ** 2 + (0 - mean) ** 2) / 3
    assert assignment.balance_pct == pytest.approx(100.0 * variance**0.5 / mean)


def test_build_assignment_raises_on_unknown_node():
    """Naming a node that is not on the grid fails loud, not silent.

    What: `build_assignment` with a `phases` mapping referencing a
    non-existent node raises `KeyError`.

    Why it matters: the usual cause is an assignment computed against
    a different grid object. Silently skipping the unknown name would
    produce a plausible-looking but wrong result; a hard `KeyError`
    surfaces the mistake immediately.
    """
    with pytest.raises(KeyError):
        build_assignment(make_grid([("real", 1000.0, None)]), {"ghost": 1}, usage_factor=1.0)


# --- assign_round_robin ------------------------------------------------------


def test_round_robin_cycles_legs_in_grid_order():
    """Round-robin assigns L1, L2, L3, L1, ... down the grid order.

    What: four equal loads `a, b, c, d` get legs 1, 2, 3, 1.

    Why it matters: this *is* Strategy B — purely positional cycling.
    The test pins the exact sequence so a change to the cycling rule
    (off-by-one, wrong modulus, wrong iteration order) can't slip
    through.
    """
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c", "d")])
    assignment = assign_round_robin(grid, usage_factor=1.0)
    assert assignment.phases == {"a": 1, "b": 2, "c": 3, "d": 1}


def test_round_robin_is_reproducible():
    """Round-robin is a pure function — same grid in, same plan out.

    What: two calls on the same grid produce identical `phases`.

    Why it matters: phase plans get committed to fixtures and acted on
    in the field. Any hidden state or non-determinism would make the
    fixture and a re-run disagree, which is exactly the kind of drift
    that erodes trust in a planning tool.
    """
    grid = make_grid([(n, 1500.0, None) for n in ("a", "b", "c")])
    assert assign_round_robin(grid).phases == assign_round_robin(grid).phases


def test_round_robin_usage_factor_changes_totals_not_legs():
    """For round-robin the usage factor rescales totals but never moves a load.

    What: running at 0.5x and 1.0x gives identical `phases` but
    leg totals that differ by exactly the 2x factor.

    Why it matters: round-robin is positional *by design* — the
    factor must not leak into the leg choice. This is the property
    that distinguishes B from D (where the factor genuinely changes
    the assignment), so it is worth pinning explicitly.
    """
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    half = assign_round_robin(grid, usage_factor=0.5)
    full = assign_round_robin(grid, usage_factor=1.0)
    assert half.phases == full.phases
    assert half.leg_totals_w == tuple(v / 2 for v in full.leg_totals_w)


def test_round_robin_empty_when_no_candidates():
    """Round-robin produces an empty plan when nothing is eligible.

    What: a grid whose every load already carries a `phase` yields
    `phases == {}`.

    Why it matters: a strategy must be a no-op on an already-phased
    grid, not re-phase loads the planner has deliberately set. The
    empty result is also what lets `build_assignment` describe a grid
    that is fully fixed — it should not error or invent placements.
    """
    grid = make_grid([("a", 1000.0, 1), ("b", 1000.0, 2)])
    assert assign_round_robin(grid).phases == {}


# --- assign_greedy -----------------------------------------------------------


def test_greedy_places_heaviest_first_onto_lightest_leg():
    """Greedy follows the longest-processing-time rule, step by step.

    What: a 3 kW load plus three 1 kW loads, all eligible at usage
    1.0. Hand-traced:
      sorted heaviest-first: a(3000), then b, c, d (1000 each)
      a -> L1            legs (3000, 0, 0)
      b -> L2 (lightest) legs (3000, 1000, 0)
      c -> L3 (lightest) legs (3000, 1000, 1000)
      d -> L2 (tie L2/L3 -> lowest index) legs (3000, 2000, 1000)

    Why it matters: this pins the whole heuristic — the heaviest-first
    sort, the lightest-leg pick, and the lowest-index tie-break — to
    one fully-worked example. Any single piece breaking changes the
    expected `phases` or `leg_totals_w`.
    """
    grid = make_grid(
        [("a", 3000.0, None), ("b", 1000.0, None), ("c", 1000.0, None), ("d", 1000.0, None)]
    )
    assignment = assign_greedy(grid, usage_factor=1.0)
    assert assignment.phases == {"a": 1, "b": 2, "c": 3, "d": 2}
    assert assignment.leg_totals_w == (3000.0, 2000.0, 1000.0)


def test_greedy_beats_round_robin_on_uneven_load_sizes():
    """Greedy produces a lower imbalance than round-robin — the reason it exists.

    What: on a grid that interleaves one heavy load among light ones —
    round-robin's worst case, since position and size are unrelated —
    greedy's `balance_pct` is strictly lower.

    Why it matters: this is the entire justification for having a
    second, size-aware strategy. If greedy ever failed to beat
    round-robin on uneven sizes it would not be worth its extra
    complexity, and doc 10's recommendation would be wrong.
    """
    # Grid order interleaves one heavy load among light ones — the worst
    # case for round-robin's positional assignment.
    grid = make_grid(
        [("a", 3000.0, None), ("b", 1000.0, None), ("c", 1000.0, None), ("d", 1000.0, None)]
    )
    rr = assign_round_robin(grid, usage_factor=1.0)
    greedy = assign_greedy(grid, usage_factor=1.0)
    assert greedy.balance_pct < rr.balance_pct


def test_greedy_balances_around_the_fixed_seed():
    """Greedy levels the whole grid, including loads it did not place.

    What: a pre-assigned 4 kW load already sits on L1; greedy's two
    2 kW candidates both go to L2 and L3, never piling onto the
    already-heavy L1. Final legs: (4000, 2000, 2000).

    Why it matters: greedy seeds its leg tally from `_fixed_leg_seed`,
    not from zero. If it ignored the seed it would treat the grid as
    empty and could stack candidates straight onto L1 — making a grid
    that was already lopsided worse. This proves it balances around
    what is already there.
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
    """Greedy is deterministic — equal-load ties always break to the lowest leg.

    What: three equal loads land on L1, L2, L3 (each step ties across
    the remaining empty legs and picks the lowest index), and two
    runs produce identical `phases`.

    Why it matters: `min` over equal values is only deterministic if
    the tie-break is defined. Without a stable rule, greedy could
    return different plans on different runs or platforms — the same
    drift trap as the round-robin reproducibility test, and just as
    corrosive to a committed fixture.
    """
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    first = assign_greedy(grid)
    second = assign_greedy(grid)
    assert first.phases == second.phases == {"a": 1, "b": 2, "c": 3}


# --- apply_assignment --------------------------------------------------------


def test_apply_assignment_mutates_candidates_only():
    """`apply_assignment` writes only the candidate loads, nothing else.

    What: after applying, a candidate has its assigned phase; a
    pre-phased load keeps its original phase; the generator stays
    `None`.

    Why it matters: applying a plan must not clobber loads the planner
    deliberately phased, nor invent a phase for the generator or a
    transit node. The blast radius of a write-back is exactly the
    candidate set — this proves it.
    """
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
    """Applying the same plan twice is identical to applying it once.

    What: a snapshot of node phases after one apply equals the state
    after a second apply.

    Why it matters: idempotence means `apply_assignment` has no
    accumulating side effect — re-running a pipeline that applies a
    plan can't corrupt the grid. It also documents that apply is a
    plain write, not a toggle or an increment.
    """
    grid = make_grid([(n, 1000.0, None) for n in ("a", "b", "c")])
    assignment = assign_round_robin(grid)
    apply_assignment(grid, assignment)
    snapshot = {n: grid.nodes[n].phase for n in assignment.phases}
    apply_assignment(grid, assignment)
    assert {n: grid.nodes[n].phase for n in assignment.phases} == snapshot


def test_apply_assignment_raises_on_unknown_node():
    """Applying a plan built for a different grid fails loud.

    What: an assignment naming a node absent from the grid raises
    `KeyError` on apply.

    Why it matters: same failure mode as the `build_assignment`
    version — mixing up grid objects is an easy mistake, and a hard
    error at the write-back catches it before a bogus plan is
    committed to a fixture.
    """
    grid = make_grid([("real", 1000.0, None)])
    stray = PhaseAssignment(
        phases={"ghost": 1}, usage_factor=1.0, leg_totals_w=(0, 0, 0), balance_pct=0
    )
    with pytest.raises(KeyError):
        apply_assignment(grid, stray)


# --- defaults ----------------------------------------------------------------


def test_default_usage_factor_is_half():
    """The default usage factor is 0.5x.

    What: `DEFAULT_USAGE_FACTOR == 0.5`.

    Why it matters: 0.5x is doc 10's stated starting assumption —
    festival loads rarely draw nameplate together. Pinning it here
    means a change to that assumption has to be deliberate (and shows
    up as a failing test) rather than drifting in unnoticed.
    """
    assert DEFAULT_USAGE_FACTOR == 0.5


# --- integration on the real field export ------------------------------------


def test_strategies_run_on_field_export_and_greedy_balances_better():
    """Both strategies handle the real 2026 export; greedy wins on balance.

    What: loaded from the unmodified `2026-05-14_martin.geojson`
    field export — every load arrives unphased, so the full candidate
    path runs — both strategies produce a non-trivial assignment over
    the same set of loads, every leg is valid (1/2/3), and greedy's
    `balance_pct` beats round-robin's.

    Why it matters: the unit tests above use tidy synthetic grids; this
    is the proof the strategies survive a real fixture's messiness
    (mixed load sizes, multi-phase loads already present, zero-power
    distros). The greedy-beats-round-robin check is the same property
    as the synthetic test, but confirmed on production-shaped data —
    which is what doc 10's recommendation actually rests on.
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
