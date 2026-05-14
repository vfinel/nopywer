"""Tests for asymmetric (unbalanced three-phase) AC power flow.

`_powerflow_3ph` runs `pp.runpp_3ph` — the solve that, unlike the
balanced `runpp`, sees per-leg voltage drop and neutral-conductor
current. These tests check three things:

  - `_phase_split` turns a `PowerNode.phase` field into a per-leg
    power tuple the same way the rest of nopywer does;
  - `to_pandapower_3ph` augments the balanced net correctly —
    zero-sequence params on lines and ext_grid, asymmetric loads
    swapped in for phased loads;
  - `compute_power_flow_3ph` converges and returns results with the
    physical signatures we expect: a balanced load draws ~no neutral
    current and sags all three legs equally; a single-phase load
    sags its own leg and returns its whole current down the neutral.

Grids are tiny and hand-built so the physics is obvious. For
real-fixture behaviour see the field-export work in research doc 11.
"""

import pytest

pytest.importorskip("pandapower")

from nopywer.models import Cable32A, PowerGrid, PowerNode
from nopywer.pp_interop import (
    PowerFlow3phResults,
    compute_power_flow_3ph,
    config,
    to_pandapower_3ph,
)
from nopywer.pp_interop._powerflow_3ph import _phase_split


def _grid(loads: list[tuple[str, float, object]]) -> PowerGrid:
    """Generator + one 50 m Cable32A per load, `(name, watts, phase)`."""
    nodes = {"generator": PowerNode("generator", 0.0, 0.0, is_generator=True)}
    cables = {}
    for i, (name, watts, phase) in enumerate(loads):
        nodes[name] = PowerNode(name, 0.001 * (i + 1), 0.0, power_watts=watts, phase=phase)
        cables[f"c{i}"] = Cable32A(id=f"c{i}", length_m=50.0, from_node="generator", to_node=name)
    return PowerGrid(nodes=nodes, cables=cables)


# --- _phase_split ------------------------------------------------------------


@pytest.mark.parametrize(
    "phase, expected",
    [
        (1, (9000.0, 0.0, 0.0)),
        (2, (0.0, 9000.0, 0.0)),
        (3, (0.0, 0.0, 9000.0)),
        ([1, 2], (4500.0, 4500.0, 0.0)),
        ([1, 2, 3], (3000.0, 3000.0, 3000.0)),
        (None, (3000.0, 3000.0, 3000.0)),
        ("U", (3000.0, 3000.0, 3000.0)),  # sub-grid marker -> balanced
        ([], (3000.0, 3000.0, 3000.0)),  # empty list -> balanced
        ([9], (3000.0, 3000.0, 3000.0)),  # no valid legs -> balanced
    ],
)
def test_phase_split(phase, expected):
    """Every form of `phase` maps to a per-leg tuple summing to the load."""
    result = _phase_split(phase, 9000.0)
    assert result == expected
    assert sum(result) == pytest.approx(9000.0)


# --- to_pandapower_3ph -------------------------------------------------------


def test_to_3ph_swaps_phased_loads_for_asymmetric():
    """Phased loads become asymmetric_loads; balanced loads stay pp.load."""
    grid = _grid([("balanced", 3000.0, None), ("on_l1", 3000.0, 1)])
    pp_grid = to_pandapower_3ph(grid)

    assert len(pp_grid.net.load) == 1  # only the balanced one
    assert len(pp_grid.net.asymmetric_load) == 1  # the phased one
    # load_idx is pruned to the loads that stayed balanced
    assert set(pp_grid.load_idx) == {"balanced"}


def test_to_3ph_sets_zero_sequence_line_params():
    """r0/x0 are the positive-sequence values times the config ratios."""
    grid = _grid([("load", 3000.0, None)])
    net = to_pandapower_3ph(grid).net
    line = net.line.iloc[0]
    assert line["r0_ohm_per_km"] == pytest.approx(line["r_ohm_per_km"] * config.R0_OVER_R1)
    assert line["x0_ohm_per_km"] == pytest.approx(line["x_ohm_per_km"] * config.X0_OVER_X1)
    assert line["c0_nf_per_km"] == config.C0_NF_PER_KM


def test_to_3ph_sets_source_vector_group():
    """The ext_grid carries the genset's zero-sequence return ratios."""
    net = to_pandapower_3ph(_grid([("load", 3000.0, None)])).net
    assert net.ext_grid.at[0, "r0x0_max"] == config.SOURCE_R0X0_MAX
    assert net.ext_grid.at[0, "x0x_max"] == config.SOURCE_X0X_MAX


def test_to_3ph_all_balanced_grid_has_no_asymmetric_loads():
    """A grid with no phased loads needs no asymmetric_load table entries."""
    grid = _grid([("a", 3000.0, None), ("b", 2000.0, None)])
    pp_grid = to_pandapower_3ph(grid)
    assert len(pp_grid.net.asymmetric_load) == 0
    assert len(pp_grid.net.load) == 2


# --- compute_power_flow_3ph --------------------------------------------------


def test_balanced_load_sags_all_legs_equally_with_no_neutral_current():
    """A balanced load is the symmetric case: equal legs, ~zero neutral."""
    grid = _grid([("load", 6000.0, None)])
    res = compute_power_flow_3ph(to_pandapower_3ph(grid))

    assert res.converged
    v_l1, v_l2, v_l3 = res.bus_voltage_v["load"]
    assert v_l1 == pytest.approx(v_l2, abs=0.1)
    assert v_l2 == pytest.approx(v_l3, abs=0.1)
    # the imbalance return is essentially nothing
    assert res.line_neutral_current_a["c0"] == pytest.approx(0.0, abs=0.5)
    # and there is a real drop — the load is being fed, not idle
    assert res.bus_vdrop_percent["load"][0] > 0


def test_single_phase_load_sags_its_own_leg_and_loads_the_neutral():
    """A single-phase load: its own leg sags, only it draws current, and
    the whole current returns on the neutral.

    Physics check — for a purely single-phase draw the return current
    has nowhere to go but the neutral, so the cable's neutral current
    must match its loaded-phase current. Note the two *unloaded* legs
    do NOT sit at equal voltage: L2 and L3 couple differently to L1's
    current through the line impedances, so a single-phase load makes
    the bus genuinely asymmetric — which is the whole reason a
    `runpp_3ph` solve exists.
    """
    grid = _grid([("on_l1", 6000.0, 1)])
    res = compute_power_flow_3ph(to_pandapower_3ph(grid))

    assert res.converged
    v_l1, v_l2, v_l3 = res.bus_voltage_v["on_l1"]
    # L1 carries the load and sags hardest of the three
    assert v_l1 < v_l2
    assert v_l1 < v_l3
    assert res.bus_vdrop_percent["on_l1"][0] > 5  # a real, sizeable sag

    i_l1, i_l2, i_l3 = res.line_current_a["c0"]
    assert i_l1 > 0
    assert i_l2 == pytest.approx(0.0, abs=0.5)
    assert i_l3 == pytest.approx(0.0, abs=0.5)
    # the whole phase current returns on the neutral
    assert res.line_neutral_current_a["c0"] == pytest.approx(i_l1, rel=0.05)


def test_results_helpers_find_worst_leg_and_neutral():
    """worst_phase_vdrop / worst_neutral_current pick out the right extremes."""
    # two single-phase loads, the heavier one on L2
    grid = _grid([("light_l1", 2000.0, 1), ("heavy_l2", 6000.0, 2)])
    res = compute_power_flow_3ph(to_pandapower_3ph(grid))

    worst = res.worst_phase_vdrop()
    assert worst is not None
    name, leg, drop = worst
    assert name == "heavy_l2"
    assert leg == 2
    assert drop == max(d for legs in res.bus_vdrop_percent.values() for d in legs)

    worst_n = res.worst_neutral_current()
    assert worst_n is not None
    cid, current = worst_n
    # heavy_l2's feeder carries the most neutral current
    assert cid == "c1"
    assert current == max(res.line_neutral_current_a.values())


def test_results_helpers_return_none_on_empty():
    """The helpers degrade gracefully rather than raising on empty results."""
    empty = PowerFlow3phResults(
        bus_voltage_v={},
        bus_vdrop_percent={},
        bus_unbalance_percent={},
        line_current_a={},
        line_neutral_current_a={},
        line_loading_percent={},
        converged=True,
    )
    assert empty.worst_phase_vdrop() is None
    assert empty.worst_neutral_current() is None
