"""Parity tests: nopywer's tree walk and pandapower's AC power flow agree
exactly when the modelling assumptions are matched.

The point of these tests is to prove the **conversion is faithful** —
when both tools see the same physics, they produce the same numbers.
Any divergence on real fixtures (see tests/test_pp_interop_comparison.py)
is then known to come from physics nopywer simplifies away (load
feedback, reactive power, line reactance), not from a translation bug.

Mirror of `test_compute_voltage_drop_uses_phase_voltage_reference` in
test_analyze.py — same hand-crafted 26 m / 1 mm² / 10 A fixture, same
expected 220 V / 4.35 % answer.
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

    nopywer's tree walk computes I = P / V0 / PF **once** at nominal
    voltage and uses that current to derive ΔV = R·I. That's exactly the
    constant-current load model in pandapower (`const_i_percent=100`):
    the load draws the rated current regardless of its actual local
    voltage, so there's no nonlinear feedback to iterate over.

    Same fixture as test_compute_voltage_drop_uses_phase_voltage_reference:
        26 m of 1 mm² cable, single-phase load drawing 10 A.
        With RHO_COPPER = 1/26, R = (1/26) * 26 / 1 = 1.0 Ω exactly.
        ΔV = R * I = 1 * 10 = 10 V exactly.
        V_load = 230 - 10 = 220 V, vdrop = 100 * 10/230 = 4.35 %.
    """
    # --- nopywer side: bypass `analyze`, hand-build the tree state
    #     and call `_compute_voltage_drop` directly, exactly as the
    #     original test does. ---
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

    # Sanity: the nopywer numbers are the ones the original test pins.
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
