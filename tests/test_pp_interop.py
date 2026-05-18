"""Smoke tests for the pp_interop module.

Three groups, each mapped to a real festival concern:

== Conversion tests ==
    Does `to_pandapower` produce a structurally-correct pandapowerNet
    from a `PowerGrid`? Right number of buses, lines, ext_grids; right
    R per km derived from `RHO_COPPER`; right loads with P/Q from PF.

    Festival mapping: any time a planner runs the AC validator or
    short-circuit calc, this is the conversion they're trusting. A
    silent unit/convention bug here would miscompute everything
    downstream.

== Short-circuit tests ==
    Does `compute_short_circuit` give physically-sensible results that
    scale correctly with cable distance and generator size?

    Festival mapping: prospective fault current at every distro is what
    sizes breakers and verifies they'll trip in time on a fault.
    Underestimating Isc means undersized breakers; overestimating means
    paying for breakers you don't need.

== Power-flow + comparison tests ==
    Does `compute_power_flow` converge and return reasonable numbers
    on a trivial grid? Does `compare_with_tree_walk` line up nopywer
    and pandapower views correctly?

    Festival mapping: AC validation runs once after the optimiser
    produces a layout. These tests are the "did the plumbing connect"
    check before the headline-finding tests in
    test_pp_interop_comparison.py.

== Defensive tests ==
    Bad inputs (unconnected cable, no cables, zero-length cable)
    surface useful errors rather than silent garbage.

The fixtures are deliberately tiny (1 generator + 1 load + 1 cable).
For real-world-fixture comparisons see `test_pp_interop_comparison.py`;
for the matched-assumption parity check see `test_pp_interop_parity.py`.
"""

import pytest

pytest.importorskip("pandapower")

from nopywer.constants import RHO_COPPER
from nopywer.models import Cable16A, Cable32A, PowerGrid, PowerNode
from nopywer.pp_interop import (
    PandapowerGrid,
    compare_with_tree_walk,
    compute_power_flow,
    compute_short_circuit,
    to_pandapower,
)


def _simple_grid() -> PowerGrid:
    """Trivial 1-cable grid for smoke tests.

    Generator → 50 m of 6 mm² 32 A cable → 3 kW load. Both nodes
    geographically next to each other (1° of longitude apart) but
    cable length is set explicitly so the geometry doesn't matter.

    Loosely models a stage being fed from a single trunk cable —
    enough to exercise every code path, not enough to reveal
    interesting physics.
    """
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load", lon=0.001, lat=0.0, power_watts=3000.0)
    cable = Cable32A(id="c1", length_m=50.0, from_node="generator", to_node="load")
    return PowerGrid(
        nodes={"generator": gen, "load": load},
        cables={"c1": cable},
    )


# ============================================================
# Conversion tests
# ============================================================


def test_to_pandapower_topology():
    """Pandapower net structure mirrors the PowerGrid one-to-one.

    Asserts: one bus per PowerNode, one line per Cable, exactly one
    ext_grid (the slack reference for the generator), and the
    line's R-per-km / max_i_ka derived correctly from
    `RHO_COPPER * 1000 / area_mm2` and `plugs_and_sockets_a / 1000`.

    What this catches: silent unit errors in the conversion (mm² vs
    m², kA vs A, ohm/km vs ohm/m), missing slack reference,
    duplicate buses.
    """
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)

    assert isinstance(pp_grid, PandapowerGrid)
    assert pp_grid.source is grid
    assert set(pp_grid.bus_idx.keys()) == {"generator", "load"}

    net = pp_grid.net
    assert len(net.bus) == 2
    assert len(net.line) == 1
    assert len(net.ext_grid) == 1
    assert net.ext_grid.at[0, "bus"] == pp_grid.bus_idx["generator"]

    line = net.line.iloc[0]
    assert line["length_km"] == pytest.approx(0.05)
    # r_ohm_per_km = RHO_COPPER * 1000 / area_mm2; tracks the actual
    # constant rather than its legacy 1/26 historical value.
    assert line["r_ohm_per_km"] == pytest.approx(RHO_COPPER * 1000 / 6.0)
    assert line["max_i_ka"] == pytest.approx(0.032)


def test_to_pandapower_creates_load_per_consumer():
    """Each non-generator node with `power_watts > 0` becomes a `pp.load`.

    Asserts: P matches `power_watts / 1e6` (MW), Q derived from
    PF=0.9 via `Q = P * tan(acos(0.9)) ≈ 0.484 * P`. Generator node
    is NOT a load (it's the slack, modelled by ext_grid instead).

    What this catches: P/Q sign errors, PF mis-derivation, generator
    accidentally added as a load (would short the slack).

    Festival mapping: every paying customer of the festival grid is
    a load — stages, kitchens, bars, distros, lights. The Q assumption
    is what determines whether the AC flow reports realistic drops.
    """
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    assert "load" in pp_grid.load_idx
    assert "generator" not in pp_grid.load_idx
    load_row = pp_grid.net.load.iloc[pp_grid.load_idx["load"]]
    assert load_row["p_mw"] == pytest.approx(3000 / 1e6)
    # Q derived from PF=0.9 → tan(acos(0.9)) ≈ 0.4843
    assert load_row["q_mvar"] == pytest.approx(load_row["p_mw"] * 0.484, abs=0.01)


# ============================================================
# Short-circuit tests
# ============================================================


def test_short_circuit_decreases_with_cable_distance():
    """Fault current at the load bus is smaller than at the generator.

    Physics: total impedance from the source to the fault point grows
    with cable length, so `I_sc = c · Un / (√3 · Z_total)` shrinks
    further from the source. Fault current at the generator bus is
    bounded only by the generator's own subtransient impedance.

    What this catches: wrong impedance sign, ext_grid placed on the
    wrong bus, line impedance not contributing to the fault path.

    Festival mapping: a fault at a distro at the back of the field
    will draw less current than a fault at the generator. This is
    why breaker selectivity matters — the breaker nearest the fault
    should trip before the breaker upstream, and that's only
    possible if the local fault current still exceeds the local
    breaker's instantaneous trip threshold. Short-circuit calc is
    the input to that selectivity analysis.
    """
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    results = compute_short_circuit(pp_grid)

    assert set(results.keys()) == {"generator", "load"}
    assert results["generator"] > results["load"] > 0.0
    assert grid.nodes["generator"].i_sc_ka == pytest.approx(results["generator"], abs=1e-4)
    assert grid.nodes["load"].i_sc_ka == pytest.approx(results["load"], abs=1e-4)


def test_short_circuit_higher_for_smaller_source_impedance():
    """A bigger generator (more kVA, lower X''d) produces more fault current.

    Physics: `s_sc_max_mva = (S_n / 1000) / X''d`. Doubling S_n
    halves the source impedance Z_source and roughly doubles I_sc
    at the generator bus.

    What this catches: source-impedance derivation off by a factor
    of √3 or 1000, or applied to the wrong element.

    Festival mapping: the choice of generator (50 kVA hire vs 500
    kVA hire) directly affects what breakers are safe to install
    downstream. Breakers must cope with the WORST-case prospective
    fault current — under-sizing the breaker breaking-capacity is
    a fire risk. Conversely, an under-rated generator might not
    deliver enough fault current to trip the breaker at all,
    leaving a fault unisolated.
    """
    pp_small = to_pandapower(_simple_grid(), gen_sn_kva=50.0)
    pp_big = to_pandapower(_simple_grid(), gen_sn_kva=500.0)

    r_small = compute_short_circuit(pp_small)
    r_big = compute_short_circuit(pp_big)

    assert r_big["generator"] > r_small["generator"]


# ============================================================
# Power-flow + comparison tests
# ============================================================


def test_compute_power_flow_balanced_case():
    """`runpp` converges and returns volts P-N / amps in the right ranges.

    On the trivial 1-cable 3 kW grid: generator bus near 230 V P-N,
    load bus below it (positive drop), cable carries non-zero current.

    What this catches: runpp not running, vm_pu → V_PN conversion
    wrong (the √3 trap), result reading from the wrong dataframe.

    Festival mapping: this is the same call that the AC validator
    runs on real fixtures. If this test passes and the comparison
    tests still show divergence, the divergence is real physics
    (not solver failure).
    """
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    res = compute_power_flow(pp_grid)
    assert res.converged
    assert res.bus_voltage_v["generator"] == pytest.approx(230.0, abs=0.5)
    # Load bus volts below generator bus volts.
    assert res.bus_voltage_v["load"] < res.bus_voltage_v["generator"]
    assert res.bus_vdrop_percent["load"] > 0.0
    assert res.line_current_a["c1"] > 0.0


def test_compare_with_tree_walk_returns_aligned_diff():
    """`compare_with_tree_walk` returns matching keys for nopywer and AC views.

    Asserts the diff dict has both views populated for every node and
    every cable, and the `worst_*` helpers actually surface entries.

    What this catches: keying mismatches between bus_idx and
    PowerNode.name, or one of the views silently empty.

    Festival mapping: this is the public diff API a planner would
    call after running the optimiser. Their downstream tooling
    (logging, GeoJSON enrichment, alert thresholds) depends on the
    diff being structurally complete.
    """
    grid = _simple_grid()
    diff = compare_with_tree_walk(grid)
    assert diff.converged
    # Both views populated for every node.
    assert set(diff.bus_voltage_v.keys()) == {"generator", "load"}
    assert set(diff.line_current_a.keys()) == {"c1"}
    # Tree-walk and AC agree at the slack bus to within rounding.
    tw_v, ac_v, _ = diff.bus_voltage_v["generator"]
    assert abs(tw_v - ac_v) < 1.0
    # The "worst disagreement" helper returns one of the entries.
    worst = diff.worst_voltage_disagreement()
    assert worst is not None
    assert worst[0] in {"generator", "load"}


def test_compare_with_tree_walk_after_explicit_analyze():
    """Calling `compare_with_tree_walk` after the user already ran `analyze`
    is a no-op, not an error.

    `analyze.py:43-49` raises if `node.children` is already populated
    (cycle-detection guard). Naive double-invocation would trip this.
    `compare_with_tree_walk` skips the analyze step when `grid.tree`
    is non-empty.

    What this catches: regression of the idempotence guard.

    Festival mapping: the typical CLI flow already runs `analyze`
    inside the optimiser, then a planner separately invokes the
    validator on the same grid. Without this guard, that workflow
    would crash.
    """
    from nopywer.analyze import analyze

    grid = _simple_grid()
    analyze(grid)
    # Second call would hit `_assign_children`'s cycle-detection guard if
    # we re-ran analyze. Should succeed silently.
    diff = compare_with_tree_walk(grid)
    assert diff.converged


# ============================================================
# Reusability + defensive tests
# ============================================================


def test_pandapower_grid_reusable():
    """The `PandapowerGrid` handle survives multiple calc calls.

    Calling `compute_short_circuit` twice on the same handle gives
    the same answer. The first call writes into `net.res_bus_sc`;
    the second call overwrites it without state leakage.

    What this catches: hidden mutation of the input net during a
    calc, or one-shot guards that prevent re-running.

    Festival mapping: a planner exploring different fault types or
    different generator-impedance assumptions should be able to
    iterate quickly without re-converting the grid each time.
    """
    pp_grid = to_pandapower(_simple_grid())
    r1 = compute_short_circuit(pp_grid)
    # Mutating net.res_bus_sc, calling again still works and gives same answer.
    r2 = compute_short_circuit(pp_grid)
    assert r1 == r2


def test_zero_length_cable_clamped():
    """A 0 m cable doesn't crash pandapower (gets clamped to MIN_LENGTH_M).

    Pandapower forbids zero-length lines (divide-by-zero in the
    solver). The conversion clamps `length_m` to 1 m before
    dividing by 1000.

    What this catches: regression of the clamp.

    Festival mapping: GeoJSON input where two nodes coincide
    (e.g. a distro split right next to a generator) would otherwise
    crash the validator. The clamp lets it run, accepting that the
    1 m floor is conservative for ultra-short connections.
    """
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load", lon=0.0, lat=0.0, power_watts=1000.0)
    cable = Cable16A(id="c1", length_m=0.0, from_node="generator", to_node="load")
    grid = PowerGrid(
        nodes={"generator": gen, "load": load},
        cables={"c1": cable},
    )
    results = compute_short_circuit(to_pandapower(grid))
    assert results["load"] > 0.0


def test_unconnected_cable_raises():
    """A cable with empty `from_node` / `to_node` raises a clear error.

    Festival mapping: GeoJSON where a cable LineString endpoint
    isn't within `CONNECTION_THRESHOLD_M` (5 m) of any node. The
    user typically wants the loader (`io.load_geojson`) or
    `analyze._snap_cables_to_nodes` to fix this; if the conversion
    is hit with an unsnapped cable, the error message tells them.
    """
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load", lon=0.001, lat=0.0, power_watts=1000.0)
    cable = Cable16A(id="c1", length_m=50.0)
    grid = PowerGrid(
        nodes={"generator": gen, "load": load},
        cables={"c1": cable},
    )
    with pytest.raises(ValueError, match="not connected"):
        to_pandapower(grid)


def test_no_cables_raises():
    """An empty cables dict raises a clear error.

    Festival mapping: a GeoJSON with only points and no line
    features — caught by the conversion before pandapower
    encounters an isolated bus and produces obscure singular-matrix
    errors.
    """
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    grid = PowerGrid(nodes={"generator": gen}, cables={})
    with pytest.raises(ValueError, match="At least one cable"):
        to_pandapower(grid)
