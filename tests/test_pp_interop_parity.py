"""Parity tests: nopywer's tree walk and pandapower's AC power flow agree
exactly when their modelling assumptions are matched.

== Why this file exists ==

The wider comparison tests (`test_pp_interop_comparison.py`) show
nopywer and pandapower disagreeing on real fixtures by up to 12
percentage points of voltage drop. Before reading anything into that
divergence, a reviewer needs to know it's not a trivial bug: a unit
error, a √3 mistake, a wrong R formula. This file is the proof.

Under controlled conditions where physics guarantees agreement —
matched load model, no reactance, no constant-power feedback — the
two tools must produce **the same number to within rounding**. That's
the conversion-correctness check. If this file fails, fix the
conversion first; the comparison tests are noise until then.

== What "matched assumptions" means ==

nopywer's tree walk computes `I = P / V0 / PF` once at nominal
voltage and uses that current everywhere. The current never updates
when the local voltage drops. That's a **constant-current load
model** in disguise.

Pandapower's `pp.create_load` defaults to **constant-power** — the
load draws its rated P regardless of voltage, so I rises as V falls.
This is what creates the load-feedback loop and the divergence on
high-stress fixtures.

To get parity, we ask pandapower to use the constant-current model
too: `pp.create_load(..., const_i_p_percent=100)`. Then:

- The current is fixed at `I_rated = P_rated / V_rated`.
- No iteration on load behaviour — the answer falls out in one step.
- The only physics in play is `ΔV = R · I` and `V = V_source - ΔV`,
  exactly what the tree walk computes.

With this matched, both tools land on the same answer.

== Festival mapping ==

This test directly mirrors
`tests/test_analyze.py::test_compute_voltage_drop_uses_phase_voltage_reference`
— Vincent's canonical unit test of the voltage-reference convention.
A festival planner reading either test should see the same fixture
(26 m of 1 mm² carrying 10 A) and the same answer (220 V at the
load, 4.35 % drop).

The 26 / 1 / 10 numbers are chosen so the arithmetic is integer-clean:

    R = RHO_COPPER × L / A = (1/26) × 26 / 1  =  1.0 Ω exactly
    ΔV = R × I = 1 × 10                       = 10.0 V exactly
    V_load = V0 − ΔV = 230 − 10               = 220.0 V
    vdrop_% = 100 × ΔV / V0 = 100 × 10/230    = 4.347…% → 4.35 (rounded)

Pandapower running on the same fixture in const-I mode lands on
220.016 V / 4.341 % — within 0.02 V / 0.01 % of the analytical
answer.
"""

import math

import pytest

pp = pytest.importorskip("pandapower")

from nopywer.analyze import _compute_voltage_drop
from nopywer.constants import V0
from nopywer.models import Cable, PowerGrid, PowerNode
from nopywer.pp_interop import config


def test_voltage_drop_matches_pandapower_with_constant_current_load():
    """nopywer == pandapower when the load is modelled as constant-current.

    What this is comparing
    ----------------------
    nopywer side: bypasses `analyze`, hand-builds the tree state, and
        calls `_compute_voltage_drop` directly — exactly as the
        canonical test in `tests/test_analyze.py` does.

    pandapower side: builds the same scenario from scratch (NOT via
        `to_pandapower`, to keep the test transparent and
        self-contained) using:
            - `vn_kv` = 0.3984 kV (the L-L equivalent of 230 V P-N
              that our converter uses).
            - `r_ohm_per_km` = (1/26) × 1000 / 1 = 38.46 Ω/km, so
              R over 26 m = 1.0 Ω.
            - `x_ohm_per_km` = 1e-9 (nopywer assumes 0; pandapower's
              solver init divides by x to compute susceptance and
              chokes on 0, so we use a negligible non-zero value).
            - A constant-current load drawing 10 A per phase line:
              `p_mw = 10 × √3 × V_LL = 6.9 kW`, `const_i_p_percent=100`.

    What this is testing
    --------------------
    1. The R formula in `to_pandapower` matches `analyze.py`'s — both
       give 1.0 Ω for the canonical fixture. (If R diverges the rest
       can't agree.)
    2. The voltage-reference convention is right: pandapower returns
       per-unit on `vn_kv` (L-L), and our `compute_power_flow`
       converts that back to volts P-N via `× vn_kv × 1000 / √3`.
       Both ends agree on what "230 V" means.
    3. The load model is the **only** semantic difference between
       `_compute_voltage_drop` and `runpp` in this regime. Forcing
       pandapower to constant-I removes that difference and proves
       agreement.

    Real-world scenario
    -------------------
    Imagine a single 230 V single-phase load (e.g. a small distro
    feeding a couple of 16 A sockets, drawing 2300 W) at the end of
    26 m of 1 mm² cable. Both tools must report:

        V at the load                 = 220.0 V
        voltage drop                  = 10 V (4.35 %)
        cable current per phase       = 10 A

    A festival electrician working from either nopywer's report or
    pandapower's runpp output should see the same number — and that
    number should match what they'd compute by hand.
    """
    # --- nopywer side: bypass `analyze`, hand-build the tree state
    #     and call `_compute_voltage_drop` directly, exactly as the
    #     canonical test does. ---
    generator = PowerNode(
        name="generator",
        lon=0.0,
        lat=0.0,
        is_generator=True,
        children={"load_a": "c1"},
        voltage=V0,
    )
    load = PowerNode(
        name="load_a",
        lon=0.0,
        lat=0.0,
        parent="generator",
        cable_to_parent="c1",
    )
    cable = Cable(
        id="c1",
        length_m=26.0,
        area_mm2=1.0,
        from_node="generator",
        to_node="load_a",
        current_per_phase=[10.0],
    )
    grid = PowerGrid(
        nodes={"generator": generator, "load_a": load},
        cables={"c1": cable},
    )
    _compute_voltage_drop(grid)

    # Sanity: the nopywer numbers are the ones the canonical test pins.
    assert cable.vdrop_volts == 10.0
    assert load.voltage == 220.0
    assert load.vdrop_percent == 4.35

    # --- pandapower side: build the same scenario from scratch using
    #     the same conventions our converter uses (vn_kv L-L equivalent
    #     of 230 V P-N), and a constant-current load drawing 10 A per
    #     phase. ---
    vn_kv_ll = config.VN_KV_LL  # 0.3984 kV — exactly 230 V P-N

    net = pp.create_empty_network(sn_mva=1.0, f_hz=50.0)
    b_gen = pp.create_bus(net, vn_kv=vn_kv_ll, name="generator")
    b_load = pp.create_bus(net, vn_kv=vn_kv_ll, name="load_a")
    pp.create_ext_grid(net, bus=b_gen, vm_pu=1.0)

    # R = 1 Ω over 26 m means r_per_km = 1 / 0.026 ≈ 38.46.
    # Equivalently RHO_COPPER * 1000 / area_mm2 = (1/26)*1000/1 = same.
    pp.create_line_from_parameters(
        net,
        from_bus=b_gen,
        to_bus=b_load,
        length_km=0.026,
        r_ohm_per_km=(1.0 / 26.0) * 1000.0 / 1.0,
        # Negligible (1 nΩ/km) but non-zero — pandapower's solver init
        # divides by x to compute susceptance and chokes on x = 0.
        x_ohm_per_km=1e-9,
        c_nf_per_km=0.0,
        max_i_ka=0.016,
    )

    # Constant-current load drawing 10 A per phase line.
    # 3-phase line current: I = P / (sqrt(3) * V_LL * PF)
    # ⇒ P = I * sqrt(3) * V_LL = 10 * sqrt(3) * 398.4 ≈ 6900 W.
    p_mw = 10.0 * math.sqrt(3) * vn_kv_ll * 1000.0 / 1e6
    pp.create_load(
        net,
        bus=b_load,
        p_mw=p_mw,
        q_mvar=0.0,
        const_i_p_percent=100.0,
        const_z_p_percent=0.0,
    )

    pp.runpp(net)

    pn_v_at_nominal = vn_kv_ll * 1000.0 / math.sqrt(3)  # ≈ 230 V
    vm_pu = float(net.res_bus.at[b_load, "vm_pu"])
    pp_v_pn = vm_pu * pn_v_at_nominal
    pp_vdrop_percent = 100.0 * (V0 - pp_v_pn) / V0

    # --- compare: pandapower lands on 220.016 V / 4.341 % — within
    #     0.05 V / 0.02 % of nopywer's analytical 220 / 4.35.
    #     Any larger gap would indicate a conversion bug. ---
    assert pp_v_pn == pytest.approx(220.0, abs=0.05)
    assert pp_vdrop_percent == pytest.approx(4.35, abs=0.02)
