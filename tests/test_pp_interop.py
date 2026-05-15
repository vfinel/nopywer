import pytest

pytest.importorskip("pandapower")

from nopywer.models import Cable16A, Cable32A, PowerGrid, PowerNode
from nopywer.pp_interop import (
    PandapowerGrid,
    compare_with_tree_walk,
    compute_power_flow,
    compute_short_circuit,
    to_pandapower,
)


def _simple_grid() -> PowerGrid:
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load", lon=0.001, lat=0.0, power_watts=3000.0)
    cable = Cable32A(id="c1", length_m=50.0, from_node="generator", to_node="load")
    return PowerGrid(
        nodes={"generator": gen, "load": load},
        cables={"c1": cable},
    )


def test_to_pandapower_topology():
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
    assert line["r_ohm_per_km"] == pytest.approx(1000 / 26 / 6.0)
    assert line["max_i_ka"] == pytest.approx(0.032)


def test_short_circuit_decreases_with_cable_distance():
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    results = compute_short_circuit(pp_grid)

    assert set(results.keys()) == {"generator", "load"}
    assert results["generator"] > results["load"] > 0.0
    assert grid.nodes["generator"].i_sc_ka == pytest.approx(results["generator"], abs=1e-4)
    assert grid.nodes["load"].i_sc_ka == pytest.approx(results["load"], abs=1e-4)


def test_short_circuit_higher_for_smaller_source_impedance():
    pp_small = to_pandapower(_simple_grid(), gen_sn_kva=50.0)
    pp_big = to_pandapower(_simple_grid(), gen_sn_kva=500.0)

    r_small = compute_short_circuit(pp_small)
    r_big = compute_short_circuit(pp_big)

    assert r_big["generator"] > r_small["generator"]


def test_zero_length_cable_clamped():
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
    gen = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    grid = PowerGrid(nodes={"generator": gen}, cables={})
    with pytest.raises(ValueError, match="At least one cable"):
        to_pandapower(grid)


def test_pandapower_grid_reusable():
    """The same PandapowerGrid can be inspected and passed to multiple calls."""
    pp_grid = to_pandapower(_simple_grid())
    r1 = compute_short_circuit(pp_grid)
    # Mutating net.res_bus_sc, calling again still works and gives same answer.
    r2 = compute_short_circuit(pp_grid)
    assert r1 == r2


def test_to_pandapower_creates_load_per_consumer():
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    assert "load" in pp_grid.load_idx
    assert "generator" not in pp_grid.load_idx
    load_row = pp_grid.net.load.iloc[pp_grid.load_idx["load"]]
    assert load_row["p_mw"] == pytest.approx(3000 / 1e6)
    # Q derived from PF=0.9 → tan(acos(0.9)) ≈ 0.4843
    assert load_row["q_mvar"] == pytest.approx(load_row["p_mw"] * 0.484, abs=0.01)


def test_compute_power_flow_balanced_case():
    grid = _simple_grid()
    pp_grid = to_pandapower(grid)
    res = compute_power_flow(pp_grid)
    assert res.converged
    assert res.bus_voltage_v["generator"] == pytest.approx(230.0, abs=0.5)
    # Load bus volts below generator bus volts.
    assert res.bus_voltage_v["load"] < res.bus_voltage_v["generator"]
    assert res.bus_vdrop_percent["load"] > 0.0
    assert res.line_current_a["c1"] > 0.0


def test_compare_with_tree_walk_after_explicit_analyze():
    """Caller may have already run analyze; we must not re-run it."""
    from nopywer.analyze import analyze

    grid = _simple_grid()
    analyze(grid)
    # Second call would hit `_assign_children`'s cycle-detection guard if
    # we re-ran analyze. Should succeed silently.
    diff = compare_with_tree_walk(grid)
    assert diff.converged


def test_compare_with_tree_walk_returns_aligned_diff():
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
