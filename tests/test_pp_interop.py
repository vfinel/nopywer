import pytest

pytest.importorskip("pandapower")

from nopywer.models import Cable16A, Cable32A, PowerGrid, PowerNode
from nopywer.pp_interop import PandapowerGrid, compute_short_circuit, to_pandapower


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
