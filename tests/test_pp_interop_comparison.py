"""Side-by-side comparison: nopywer's tree walk vs pandapower's AC flow
on every existing analyze fixture.

== Why this file exists ==

`test_pp_interop_parity.py` proves that under matched assumptions the
two tools agree exactly. **This file** asks the more interesting
question: when those assumptions are NOT matched (i.e. on real
fixtures with real load distributions), how much do nopywer and
pandapower disagree, and **in which direction**?

The answer turns out to depend on the fixture. Three different
shapes show up, each mapped to a real festival situation:

    1. Low drop, balanced load    →  agreement to within rounding
    2. Unbalanced single-phase    →  nopywer over-states drop
    3. High drop, balanced load   →  nopywer under-states drop

Each test below pins one of these shapes, with both direction-of-
disagreement assertions and pinned numbers (±2 pp tolerance) so
future changes to either tool are visible.

For the underlying physics — why each direction shows up, what the
constant-current-vs-constant-power distinction means, what
max(I_per_phase) does to unbalanced loads — see
[`research/pandapower/08_why_tree_walk_and_ac_disagree.md`](
../research/pandapower/08_why_tree_walk_and_ac_disagree.md).

== Why both directions matter ==

A festival planner reading a single tool's output needs to know
whether it's optimistic or pessimistic in their specific scenario.
The conservative assumption ("trust the worst number") only works
if you know each tool's bias:

- nopywer's max-phase rule is **conservative for sizing decisions**
  on unbalanced single-phase loads (small distros).
- pandapower's iterative AC is **closer to physical truth on
  high-stress balanced loads** (long radial trunks to heavy loads).

These tests document those biases as code so they can't be forgotten.
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
    """**Mechanism 1**: small balanced load — both tools agree.

    What this is comparing
    ----------------------
    Fixture: `analyze_named_generator.geojson` — 1 generator + 1
    unphased 1 kW load through 10 m of 2.5 mm² cable.

    Both views run on the same `PowerGrid`:
        - nopywer: `analyze(grid)` → tree walk → drop reported on
          each `PowerNode.vdrop_percent`.
        - pandapower: `to_pandapower(grid)` → `runpp` → drop derived
          from `res_bus.vm_pu`.

    What this is testing
    --------------------
    That under the most benign conditions both simplifications are
    inactive and the two tools land on essentially the same number:

        - The load is **unphased** (split evenly across L1/L2/L3) →
          balanced → nopywer's `max(I_per_phase)` rule degenerates
          to the right answer.
        - The drop is **tiny** (~0.5 V / 0.2 %) → constant-current
          (nopywer) and constant-power (pandapower) make
          near-identical predictions.

    Pinned within 0.1 V / 0.05 % so a real divergence shows up but
    rounding noise doesn't.

    Real-world scenario
    -------------------
    A small ~1 kW distro (e.g. an info booth, a single PA stack)
    plugged into a 16 A socket near the generator via a short cable.
    Both tools should give the planner the same V/I numbers; if
    they diverge here, something fundamental in the conversion is
    broken.
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
    """**Mechanism 2**: unbalanced single-phase loads — nopywer
    over-states drop relative to pandapower's balanced flow.

    What this is comparing
    ----------------------
    Fixture: `analyze_input.geojson` —

        generator ── cable_0 (20 m) ── load_a (3 kW on L1)
                                    ── cable_1 (22 m) ── load_b (6 kW on L2)

    nopywer's tree walk sees per-phase power vectors:
        cable_1 cum_power = [0, 6 kW, 0]   →  I = [0, 29 A, 0]
        cable_0 cum_power = [3 kW, 6 kW, 0] →  I = [14, 29, 0] A
    and uses **max** of each I to compute each cable's ΔV.

    pandapower's `runpp` (after our converter collapses single-phase
    loads to balanced) sees:
        cable_0 carries 9 kW total → per-phase line I ≈ 14.4 A
        cable_1 carries 6 kW total → per-phase line I ≈ 9.6 A
    and computes balanced ΔV.

    What this is testing
    --------------------
    1. **Direction**: tree walk reports a *bigger* drop than AC at
       the worst-stressed node (load_b). This is nopywer's
       max-phase rule being conservative — it applies the L2 (worst)
       drop to all three phases.
    2. **Magnitude**: ~5 percentage-point gap (8.13 % tree walk vs
       3.12 % AC). Documented in
       `08_why_tree_walk_and_ac_disagree.md`.
    3. **Cable currents**: tree walk's reported I per cable is the
       max-phase value (29 A); pandapower's is the balanced value
       (10–14 A). Test pins `tw_i > ac_i` for both cables.

    Neither number is the physical truth. Truth needs `runpp_3ph`
    with `asymmetric_load` (opportunity §3 in
    `06_extended_opportunities.md`), which would model the actual
    L1/L2/L3 distribution and the neutral conductor.

    Real-world scenario
    -------------------
    A typical small-distro feed: lighting on L1, sound system on L2,
    kitchen tent on L3 — single-phase loads pinned to specific
    phases, deliberately balanced by the planner *across the
    festival* but **unbalanced on any individual cable**.

    nopywer's number tells the planner "the WORST case at any node
    is X % drop" — useful for cable-sizing decisions where you want
    a safety margin. pandapower's number tells them "the AVERAGE
    drop assuming the load is spread out" — useful for sanity-
    checking that the typical user experience is acceptable. Neither
    is wrong; they answer different questions.
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
    """**Mechanism 3**: high-stress balanced load — nopywer
    *under-states* drop because its tree walk doesn't iterate the
    constant-power feedback.

    What this is comparing
    ----------------------
    Fixture: `input_nodes.geojson` — the 2025 Nowhere event, 51 nodes.
    Run `optimize_layout` to produce the 50-cable layout, then run
    `compare_with_tree_walk` on the result.

    nopywer's tree walk computes I = P / V0 / PF **once** at nominal
    voltage and never iterates. ΔV stacks linearly down the tree.
    Reports `glitch` at 26.9 % drop (V = 168 V P-N).

    pandapower's `runpp` iterates: at lower local V, the
    constant-power loads draw more current → more drop → even more
    current → ... converges around `glitch` at 39.1 % drop (V = 140 V).

    What this is testing
    --------------------
    1. **Direction**: AC reports a *bigger* drop than tree walk at
       the worst-stressed node. This is the opposite direction from
       Mechanism 2 — different simplification, different bias.
    2. **Magnitude**: ~12 percentage-point gap (39 % AC vs 27 %
       tree). Captured in `07_optimiser_validation_findings.md` as
       the headline finding; pinned here as a regression check.
    3. **Optimisation stability**: the test uses `optimize_layout`,
       which involves randomness in tie-breaking. The numbers are
       pinned with ±2 pp tolerance to absorb that.

    If anyone "fixes" the tree walk to be more accurate (e.g. by
    iterating to a fixed point), this test will go red and force
    the 07-doc finding to be updated.

    Real-world scenario
    -------------------
    A long radial cable run from the generator to a remote stage
    (or kitchen tent, or ice plant) — heavy balanced load drawn
    through many cable hops. The kind of layout the optimiser
    produces when the geographic spread of the festival forces
    long trunks.

    The headline number (V at glitch = 140 V instead of 168 V) is
    operationally significant: at 140 V, switch-mode PSUs trip,
    motors stall, light bulbs noticeably dim. The tree walk's
    168 V is alarming but understates how bad it actually gets at
    the load. **This is the case where a planner should NOT trust
    nopywer alone** — running the AC validator surfaces a real
    safety issue the tree walk hides.
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
