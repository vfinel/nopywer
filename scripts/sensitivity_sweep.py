"""Sensitivity sweep over the high-impact `pp_interop/config.py` defaults.

Probes how the AC vs tree-walk gap responds to small changes around
each default. Three sweeps:

  1. Cable reactance `X_OHM_PER_KM`     default 0.08 Ω/km
       → range 0.05 .. 0.12 in 0.01 steps
       → reads: AC drop at the deepest node of a 4-deep chain

  2. Load power factor `PF`             default 0.9
       → range 0.80 .. 1.00 in 0.025 steps
       → reads: AC drop at the deepest node of a 4-deep chain

  3. Generator subtransient reactance `GEN_XDSS_PU`   default 0.12 pu
       → range 0.08 .. 0.18 in 0.01 steps
       → reads: short-circuit current at the generator bus

Each sweep prints a table:

    parameter value | tree-walk metric | AC metric | gap (AC − tree)
                                                     pp / kA / etc.

Run with:
    uv run python scripts/sensitivity_sweep.py
"""

from nopywer.models import Cable, PowerGrid, PowerNode
from nopywer.pp_interop import compare_with_tree_walk, compute_short_circuit, to_pandapower


def _node(name: str, lon: float, power_kw: float = 0.0, *, generator: bool = False) -> PowerNode:
    node = PowerNode(
        name=name,
        lon=lon,
        lat=0.0,
        power_watts=power_kw * 1000.0,
        is_generator=generator,
    )
    if not generator and power_kw > 0:
        node.power_per_phase += (power_kw * 1000.0) / 3
    return node


def _cable(cid: str, frm: str, to: str, length_m: float, area_mm2: float, ps_a: float) -> Cable:
    return Cable(
        id=cid,
        length_m=length_m,
        area_mm2=area_mm2,
        plugs_and_sockets_a=ps_a,
        from_node=frm,
        to_node=to,
    )


def deep_chain_grid() -> PowerGrid:
    """5 nodes in a chain, 5 kW each, 50 m / 32 A cables.

    Same fixture as `tests/test_pp_interop_topology.py` deep-chain
    test. Stressed enough that the AC vs tree-walk gap is non-zero
    but not extreme. Rebuild for each sweep value because `analyze`
    mutates state.
    """
    return PowerGrid(
        nodes={
            "gen": _node("gen", 0.0, generator=True),
            "a": _node("a", 0.001, 5.0),
            "b": _node("b", 0.002, 5.0),
            "c": _node("c", 0.003, 5.0),
            "d": _node("d", 0.004, 5.0),
        },
        cables={
            "cable_a": _cable("cable_a", "gen", "a", 50.0, area_mm2=6.0, ps_a=32.0),
            "cable_b": _cable("cable_b", "a", "b", 50.0, area_mm2=6.0, ps_a=32.0),
            "cable_c": _cable("cable_c", "b", "c", 50.0, area_mm2=6.0, ps_a=32.0),
            "cable_d": _cable("cable_d", "c", "d", 50.0, area_mm2=6.0, ps_a=32.0),
        },
    )


def one_cable_grid() -> PowerGrid:
    """Trivial 1-cable grid for the short-circuit sweep.

    A single 3 kW load through 50 m of 32 A cable. For Isc the
    fixture topology barely matters; we want the simplest possible
    grid so the source-impedance term dominates the result.
    """
    return PowerGrid(
        nodes={
            "gen": _node("gen", 0.0, generator=True),
            "load": _node("load", 0.001, 3.0),
        },
        cables={
            "c1": _cable("c1", "gen", "load", 50.0, area_mm2=6.0, ps_a=32.0),
        },
    )


def _frange(start: float, stop: float, step: float) -> list[float]:
    """Inclusive float range that doesn't drift due to repeated addition."""
    out = []
    n = 0
    while True:
        v = start + n * step
        if v > stop + 1e-9:
            break
        out.append(round(v, 6))
        n += 1
    return out


def sweep_x_ohm_per_km() -> None:
    """X reactance sweep, 0.05–0.12 Ω/km in 0.01 steps. Default 0.08.

    Tree walk ignores X entirely. Pandapower includes the X·sin φ term
    in voltage drop. Larger X → larger AC drop. Tree-walk drop is
    constant across the sweep.
    """
    print("== X_OHM_PER_KM sweep (default 0.08, ±range 0.05–0.12) ==")
    print("fixture: deep chain, 4 cables × 50 m, 5 kW load at each leaf")
    print(f"{'X Ω/km':>10}  {'tree d %':>10}  {'AC d %':>10}  {'gap pp':>10}")
    print("-" * 46)
    base_x = 0.08
    for x in _frange(0.05, 0.12, 0.01):
        diff = compare_with_tree_walk(deep_chain_grid(), x_ohm_per_km=x)
        tw, ac, gap = diff.bus_vdrop_percent["d"]
        marker = "  ← default" if abs(x - base_x) < 1e-6 else ""
        print(f"{x:>10.3f}  {tw:>10.3f}  {ac:>10.3f}  {gap:>+10.3f}{marker}")
    print()


def sweep_pf() -> None:
    """Load PF sweep, 0.80–1.00 in 0.025 steps. Default 0.9.

    nopywer's PF is hardcoded in `nopywer.constants`, so the tree-walk
    drop is constant across the sweep — only pandapower's Q-mvar moves.
    Lower PF → more reactive current → bigger AC drop.

    Reading the gap: at PF = 0.9 the two tools share an assumption,
    so the gap is the "topology + load-feedback" gap. At PF ≠ 0.9 the
    gap also includes "the load is more/less reactive than nopywer
    assumed".
    """
    print("== PF sweep (default 0.9, ±range 0.80–1.00) ==")
    print("fixture: deep chain (same as X sweep)")
    print("note: nopywer's PF is fixed at 0.9; only AC side moves")
    print(f"{'PF':>8}  {'tree d %':>10}  {'AC d %':>10}  {'gap pp':>10}")
    print("-" * 44)
    base_pf = 0.9
    for pf in _frange(0.80, 1.00, 0.025):
        diff = compare_with_tree_walk(deep_chain_grid(), load_pf=pf)
        tw, ac, gap = diff.bus_vdrop_percent["d"]
        marker = "  ← default" if abs(pf - base_pf) < 1e-6 else ""
        print(f"{pf:>8.3f}  {tw:>10.3f}  {ac:>10.3f}  {gap:>+10.3f}{marker}")
    print()


def sweep_gen_xdss_pu() -> None:
    """Generator X''d sweep, 0.08–0.18 pu in 0.01 steps. Default 0.12.

    Affects short-circuit only. `s_sc_max_mva = (S_n / 1000) / X''d`,
    so smaller X''d → bigger source MVA → bigger Isc.
    """
    print("== GEN_XDSS_PU sweep (default 0.12, ±range 0.08–0.18) ==")
    print("fixture: 1 cable, 50 m / 32 A, 3 kW load")
    print("metric: Isc at the generator bus, IEC 60909 3-phase max-case")
    print(f"{'X''d pu':>10}  {'Isc gen kA':>12}  {'Isc load kA':>13}")
    print("-" * 39)
    base_xdss = 0.12
    for xdss in _frange(0.08, 0.18, 0.01):
        pp_grid = to_pandapower(one_cable_grid(), gen_xdss_pu=xdss)
        results = compute_short_circuit(pp_grid)
        marker = "  ← default" if abs(xdss - base_xdss) < 1e-6 else ""
        print(f"{xdss:>10.3f}  {results['gen']:>12.4f}  {results['load']:>13.4f}{marker}")
    print()


def main() -> None:
    sweep_x_ohm_per_km()
    sweep_pf()
    sweep_gen_xdss_pu()


if __name__ == "__main__":
    main()
