"""Side-by-side comparison: nopywer's tree walk vs pandapower's AC flow.

These tests pin the divergence between the two tools on each existing
analyze fixture, so future changes to either side get caught.

The divergence is **not one-directional** — three different shapes show
up depending on the fixture:

1. Low drop, balanced load
   → tree walk and AC agree to within rounding.

2. Unbalanced single-phase loads
   → nopywer's `max(current_per_phase)` rule is conservative and
     **over-states** voltage drop relative to pandapower's balanced
     runpp (which our converter currently uses — runpp_3ph is
     opportunity §3 in 06_extended_opportunities.md).

3. High drop, balanced load
   → constant-power feedback at low local voltage means more current,
     more drop. The tree walk computes I at nominal V0 once and never
     iterates, so it **under-states** voltage drop.

Numbers come from running compare_with_tree_walk() against each
fixture; pinned with ±0.5 V / ±0.5 % tolerance to absorb minor
numerical noise but tight enough to catch real changes.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("pandapower")

from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.optimize import optimize_layout
from nopywer.pp_interop import compare_with_tree_walk

FIXTURES = Path(__file__).parent / "fixtures"


def test_named_generator_fixture_low_drop_parity():
    """Small balanced load — tree walk and AC agree to within rounding.

    1 generator + 1 unphased 1 kW load through 10 m cable. Because the
    load is unphased, io.load_geojson splits it evenly across phases
    (333 W per phase, balanced). At ~1.6 A per phase through 20 m of
    2.5 mm² (~ 0.31 Ω), drop is well under 1 V — far too small for
    constant-power feedback to matter. Both tools land within 0.1 V.
    """
    nodes, cables = load_geojson(FIXTURES / "analyze_named_generator.geojson")
    grid = PowerGrid(nodes=nodes, cables=cables)

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    tw_v, ac_v, delta_v = diff.bus_voltage_v["load a"]
    assert tw_v == pytest.approx(229.5, abs=0.1)
    assert ac_v == pytest.approx(229.6, abs=0.1)
    assert abs(delta_v) < 0.1  # rounding-level agreement

    tw_pct, ac_pct, delta_pct = diff.bus_vdrop_percent["load a"]
    assert tw_pct == pytest.approx(0.22, abs=0.05)
    assert ac_pct == pytest.approx(0.19, abs=0.05)
    assert abs(delta_pct) < 0.1

    tw_i, ac_i, delta_i = diff.line_current_a["cable_0"]
    assert tw_i == pytest.approx(1.61, abs=0.05)
    assert ac_i == pytest.approx(1.61, abs=0.05)


def test_analyze_input_fixture_unbalanced_max_phase_overstates_drop():
    """Unbalanced single-phase loads — nopywer's max-phase rule pushes
    the tree walk's reported drop **above** pandapower's balanced flow.

    Fixture:
      generator → cable_0 (20 m) → load_a (3 kW on phase 1)
                                 → cable_1 (22 m) → load_b (6 kW on phase 2)

    nopywer cumulates power per phase: cable_0 sees [3 kW, 6 kW, 0],
    so current_per_phase = [14.5, 29.0, 0] A. ΔV is then computed
    against `max(current_per_phase) = 29.0 A` — the worst-phase
    estimate, conservative by design.

    Our `to_pandapower` collapses single-phase loads to balanced
    3-phase loads (runpp_3ph is opportunity §3). So pandapower sees
    9 kW total, balanced, with per-phase line current ~14.5 A.
    Result: pandapower reports a smaller drop than the tree walk.

    This is **not a bug in either tool** — it's two different physical
    models. The test pins the gap so future changes to either side
    are visible.
    """
    nodes, cables = load_geojson(FIXTURES / "analyze_input.geojson")
    grid = PowerGrid(nodes=nodes, cables=cables)

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    # Worst-stressed node: load_b. Tree walk says 8.1 %; AC says 3.1 %.
    tw_pct, ac_pct, delta_pct = diff.bus_vdrop_percent["load b"]
    assert tw_pct == pytest.approx(8.13, abs=0.1)
    assert ac_pct == pytest.approx(3.12, abs=0.1)
    # Direction: tree walk overstates by ~5 pp.
    assert tw_pct > ac_pct
    assert (tw_pct - ac_pct) == pytest.approx(5.0, abs=0.5)

    # Cable currents: tree walk's max-phase rule reports the phase 2
    # current (29 A), AC reports the balanced equivalent (~10–15 A).
    for cable_id in ("cable_0", "cable_1"):
        tw_i, ac_i, _ = diff.line_current_a[cable_id]
        assert tw_i > ac_i, f"{cable_id}: expected tree walk I > AC I"


def test_optimised_input_nodes_fixture_high_drop_understates_drop():
    """High-stress balanced case — constant-power feedback makes
    pandapower's AC drop **larger** than the tree walk's.

    This is the headline finding from
    research/pandapower/07_optimiser_validation_findings.md, captured
    here as a regression check: at the worst-stressed node `glitch`,
    the tree walk reports ~27 % drop and AC reports ~39 %.

    If anyone "fixes" the tree walk to be more accurate (e.g. by
    iterating to fixed-point), this test goes red and forces the
    07-doc finding to be updated.
    """
    with open(FIXTURES / "input_nodes.geojson") as f:
        nodes_geojson = json.load(f)
    nodes, _ = load_geojson(nodes_geojson)
    grid = optimize_layout(PowerGrid(nodes=nodes, cables={}))

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    # `glitch` was the worst node in the 07 findings doc.
    assert "glitch" in diff.bus_vdrop_percent, (
        "fixture changed: 'glitch' no longer in optimised layout — "
        "update test and 07_optimiser_validation_findings.md"
    )
    tw_pct, ac_pct, delta_pct = diff.bus_vdrop_percent["glitch"]

    # Pin both numbers loosely. Optimisation has some non-determinism
    # via floats but the answer is stable to ~1 pp.
    assert tw_pct == pytest.approx(27.0, abs=2.0)
    assert ac_pct == pytest.approx(39.0, abs=2.0)
    # Direction: AC overstates the tree walk by ~12 pp at this node.
    assert ac_pct > tw_pct, "expected AC drop > tree-walk drop at high stress"
    assert (ac_pct - tw_pct) == pytest.approx(12.0, abs=2.0)
