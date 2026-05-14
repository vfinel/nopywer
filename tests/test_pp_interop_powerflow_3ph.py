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
    """Every form of `PowerNode.phase` maps to the right per-leg power tuple.

    What: `_phase_split` is exercised across all six cases — int legs
    1/2/3, a two-leg list, a full three-leg list, `None`, the `"U"`
    sub-grid marker, and two malformed lists (empty, no valid leg).
    Each must produce the documented per-leg split, and every split
    must conserve power (sum back to the 9 kW input).

    Why it matters: this function is the bridge between nopywer's
    polymorphic `phase` field and pandapower's asymmetric loads. If it
    disagreed with the rule `io.load_geojson` uses, `runpp_3ph` would
    be solving a different grid than the tree walk — the two would be
    silently incomparable. The malformed-input rows pin the
    fall-through-to-balanced behaviour so a bad fixture degrades
    safely instead of crashing the solve.
    """
    result = _phase_split(phase, 9000.0)
    assert result == expected
    assert sum(result) == pytest.approx(9000.0)


# --- to_pandapower_3ph -------------------------------------------------------


def test_to_3ph_swaps_phased_loads_for_asymmetric():
    """A phased load becomes an asymmetric_load; a balanced load stays a pp.load.

    What: a grid with one balanced and one L1 load converts to a net
    with exactly one `pp.load` and one `pp.asymmetric_load`, and
    `load_idx` is pruned down to just the load that stayed balanced.

    Why it matters: `to_pandapower_3ph` builds on the balanced
    converter and *mutates* its output — dropping the balanced
    `pp.load` rows for phased loads and re-adding them as asymmetric.
    Get the swap wrong and a phased load is either counted twice (a
    leftover `pp.load` plus the asymmetric one) or lost entirely. The
    `load_idx` check guards the bookkeeping: it must end up describing
    only the loads that remain plain `pp.load`s, or downstream
    write-back keyed off it would touch the wrong rows.
    """
    grid = _grid([("balanced", 3000.0, None), ("on_l1", 3000.0, 1)])
    pp_grid = to_pandapower_3ph(grid)

    assert len(pp_grid.net.load) == 1  # only the balanced one
    assert len(pp_grid.net.asymmetric_load) == 1  # the phased one
    # load_idx is pruned to the loads that stayed balanced
    assert set(pp_grid.load_idx) == {"balanced"}


def test_to_3ph_sets_zero_sequence_line_params():
    """Every line gets r0 / x0 / c0 derived from the config ratios.

    What: a line's `r0_ohm_per_km` is its positive-sequence
    `r_ohm_per_km` times `R0_OVER_R1`, and likewise for x0; `c0` is
    the configured zero-sequence capacitance.

    Why it matters: `runpp_3ph` cannot solve a line that has no
    zero-sequence parameters — they describe how the cable behaves to
    the imbalance current returning through neutral and earth. This is
    a wiring-regression guard (it asserts the formula the code
    applies), not a physics check: its job is to catch someone
    dropping or rescaling the zero-sequence assignment, which would
    make `runpp_3ph` either fail outright or silently model the wrong
    cable.
    """
    grid = _grid([("load", 3000.0, None)])
    net = to_pandapower_3ph(grid).net
    line = net.line.iloc[0]
    assert line["r0_ohm_per_km"] == pytest.approx(line["r_ohm_per_km"] * config.R0_OVER_R1)
    assert line["x0_ohm_per_km"] == pytest.approx(line["x_ohm_per_km"] * config.X0_OVER_X1)
    assert line["c0_nf_per_km"] == config.C0_NF_PER_KM


def test_to_3ph_sets_source_vector_group():
    """The ext_grid carries the genset's zero-sequence return ratios.

    What: the converted ext_grid has `r0x0_max` and `x0x_max` set to
    the `SOURCE_*` config values.

    Why it matters: these describe whether the source's neutral
    provides a return path for zero-sequence current — a Yn grounded
    genset versus an isolated IT one behave completely differently.
    Without them `runpp_3ph` has no source-side zero-sequence model.
    Like the line-params test this is a wiring-regression guard, not
    a physics check.
    """
    net = to_pandapower_3ph(_grid([("load", 3000.0, None)])).net
    assert net.ext_grid.at[0, "r0x0_max"] == config.SOURCE_R0X0_MAX
    assert net.ext_grid.at[0, "x0x_max"] == config.SOURCE_X0X_MAX


def test_to_3ph_all_balanced_grid_has_no_asymmetric_loads():
    """A grid with no phased loads produces no asymmetric_load entries.

    What: when every load is balanced (`phase` is `None`), the
    converted net has an empty `asymmetric_load` table and keeps every
    load as a plain `pp.load`.

    Why it matters: the converter must only swap loads that actually
    carry a phase. A bug that asymmetric-ised balanced loads would
    work numerically — three equal legs is still balanced — but would
    bloat the net and, more importantly, mean the swap logic was
    triggering on the wrong condition. This is the negative case that
    pins it: no phases in, no asymmetric loads out.
    """
    grid = _grid([("a", 3000.0, None), ("b", 2000.0, None)])
    pp_grid = to_pandapower_3ph(grid)
    assert len(pp_grid.net.asymmetric_load) == 0
    assert len(pp_grid.net.load) == 2


# --- compute_power_flow_3ph --------------------------------------------------


def test_balanced_load_sags_all_legs_equally_with_no_neutral_current():
    """A balanced load is the symmetric case: equal legs, ~zero neutral.

    What: a single balanced 6 kW load converges, sits at the same
    voltage on all three legs, draws essentially no neutral current,
    and still shows a real (non-zero) voltage drop.

    Why it matters: this is the physics sanity floor for the
    asymmetric solver — when the load *is* balanced, `runpp_3ph` must
    reproduce the symmetric result: no negative- or zero-sequence
    component, so nothing in the neutral and no per-leg spread. The
    "drop > 0" check rules out the degenerate pass where the solver
    returns a flat nominal grid because the load was silently
    dropped. (Cross-checked against the balanced `runpp` separately:
    both land on 227.17 V.)
    """
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
    """A single-phase load sags its own leg and returns its whole current
    on the neutral.

    What: a single 6 kW load on L1 converges; L1 is the lowest of the
    three legs and drops more than 5 %; L2 and L3 draw essentially no
    current; and the cable's neutral current equals its L1 current.

    Why it matters: this is the asymmetric case the whole module
    exists for — the one a balanced `runpp` structurally cannot show.
    Two independent physics facts are pinned: (1) a purely
    single-phase draw has no return path *but* the neutral, so
    `i_neutral == i_L1` is a hard identity, not a fitted number; (2)
    the loaded leg must sag hardest. The `> 5 %` bound is deliberately
    loose — hand arithmetic puts the real drop near 9 % (R per
    conductor ~0.32 ohm, ~32 A, P-N drop ~20 V) — so it tests the
    sign and scale without over-fitting to the solver's exact output.

    Note the two *unloaded* legs do NOT sit at equal voltage: L2 and
    L3 couple differently to L1's current through the line
    impedances, so a single-phase load makes the bus genuinely
    asymmetric. That asymmetry is precisely why a `runpp_3ph` solve
    is needed at all — which is why this test does not assert
    L2 == L3 (an earlier version did, and it was wrong physics).
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
    """The result helpers pick out the genuinely worst leg and cable.

    What: with a light 2 kW load on L1 and a heavy 6 kW load on L2,
    `worst_phase_vdrop` returns `heavy_l2`'s L2 (and that drop is the
    max over every node and leg), and `worst_neutral_current` returns
    `heavy_l2`'s feeder cable (and that current is the max over every
    cable).

    Why it matters: these helpers are what a planner actually reads —
    "where is the grid worst?" The test confirms they search across
    *all* nodes/legs/cables rather than, say, returning the first or
    last entry. The heavier single-phase load must sag its own leg
    most and load its own feeder's neutral most, so the expected
    answers are derivable by hand, not read off the solver.
    """
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
    """The result helpers return None on empty results instead of raising.

    What: a `PowerFlow3phResults` with empty dicts yields `None` from
    both `worst_phase_vdrop` and `worst_neutral_current`.

    Why it matters: the helpers use `max(...)`, which raises
    `ValueError` on an empty iterable. An empty result is a real
    possibility — a grid with no lines, or a caller inspecting a
    partially-built result — and the helpers must degrade to a clean
    `None` the caller can branch on, not blow up.
    """
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
