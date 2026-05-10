"""Topology comparison tests: how the tree-walk-vs-AC gap changes with
grid SHAPE.

The fixtures in `test_pp_interop_comparison.py` cover three real
festival layouts but vary on multiple axes at once (size, phase
distribution, load magnitude). This file holds load type and config
defaults constant and varies only the topology, so each test isolates
**one geometric effect**.

== The three shapes ==

A festival planner regularly sketches one of three patterns:

    1. Deep linear chain     gen ─→ A ─→ B ─→ C ─→ D
       Common for back-of-house corridors: generator at the gate,
       then kitchen → dressing room → green room → workshop, each
       distro tapping its load and passing the rest through.

    2. Wide star             gen ─┬─→ stage 1
                                  ├─→ stage 2
                                  ├─→ stage 3
                                  ├─→ stage 4
                                  └─→ stage 5
       Common when a central distro hub feeds independent areas in
       different directions. Each branch carries its own load with
       no compounding from siblings.

    3. Bottleneck            gen ─→ [thin cable] ─→ distro ─┬─→ load
                                                            ├─→ load
                                                            └─→ load
       Common when a planner has the wrong-tier cable on hand or
       wants to reuse an existing run. The thin section limits every
       downstream load even if their own cables are ample.

== What each test isolates ==

Deep chain  → tests **constant-power feedback compounding** with
              depth. Each cable's drop nudges the next iteration's
              current. AC-vs-tree-walk gap should grow with depth.

Wide star   → tests **branch independence**. No chaining = no
              compounding feedback. AC and tree walk should agree
              closely on every leaf.

Bottleneck  → tests **drop attribution**. Even when the magnitudes
              diverge, both tools should agree that the thin cable
              dominates the total drop.

For the underlying physics, see
[`research/pandapower/08_why_tree_walk_and_ac_disagree.md`](
../research/pandapower/08_why_tree_walk_and_ac_disagree.md).
"""

import pytest

pytest.importorskip("pandapower")

from nopywer.models import Cable, PowerGrid, PowerNode
from nopywer.pp_interop import compare_with_tree_walk


def _node(name: str, lon: float, power_kw: float = 0.0, *, generator: bool = False) -> PowerNode:
    """Helper: build a PowerNode at given longitude (lat=0).

    Power is in kW for readability — converted to W internally.
    Loads are unphased (split balanced across L1/L2/L3) so we isolate
    topology effects from phase imbalance. We populate `power_per_phase`
    here because `io.load_geojson` does that step (the dataclass
    default leaves it as zeros), and the tree walk reads it directly.
    """
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
    """Helper: build a snapped Cable between two named nodes."""
    return Cable(
        id=cid,
        length_m=length_m,
        area_mm2=area_mm2,
        plugs_and_sockets_a=ps_a,
        from_node=frm,
        to_node=to,
    )


def test_deep_linear_chain_compounds_drop_with_depth():
    """**Deep chain**: gen → A → B → C → D, each distro tapping 5 kW.

    Topology
    --------
    Five nodes in a line, four cables. 50 m between each, 32 A
    cables (6 mm²) — within rating throughout but stressed enough
    to make the constant-power feedback bite.

        gen ─[50 m]→ A(5kW) ─[50 m]→ B(5kW) ─[50 m]→ C(5kW) ─[50 m]→ D(5kW)

    Cumulative power on each cable, leaves → root:
        cable_d: 5 kW
        cable_c: 10 kW
        cable_b: 15 kW
        cable_a: 20 kW

    What this is testing
    --------------------
    1. **Direction**: AC drop at every depth ≥ tree-walk drop. The
       constant-current shortcut in nopywer always under-states in
       this regime.
    2. **Compounding**: the AC-vs-tree gap **grows monotonically
       with depth**. A is barely off; D shows the biggest gap.
       This is the signature of feedback compounding — each level
       deeper, the iteration has done one more round of "lower V →
       more I → more drop".

    Real-world scenario
    -------------------
    A row of distros down a back-of-house corridor: kitchen (A) →
    dressing room (B) → green room (C) → tech workshop (D). The
    planner's tree walk says D will be at, say, V_tw V. The AC
    truth is **lower** — and the gap matters more the deeper you
    go. This is the case where a planner reading nopywer's output
    might think "5% drop at D, fine" when AC would say "8% drop,
    light bulbs visibly dim".
    """
    nodes = {
        "gen": _node("gen", 0.0, generator=True),
        "a": _node("a", 0.001, 5.0),
        "b": _node("b", 0.002, 5.0),
        "c": _node("c", 0.003, 5.0),
        "d": _node("d", 0.004, 5.0),
    }
    cables = {
        "cable_a": _cable("cable_a", "gen", "a", 50.0, area_mm2=6.0, ps_a=32.0),
        "cable_b": _cable("cable_b", "a", "b", 50.0, area_mm2=6.0, ps_a=32.0),
        "cable_c": _cable("cable_c", "b", "c", 50.0, area_mm2=6.0, ps_a=32.0),
        "cable_d": _cable("cable_d", "c", "d", 50.0, area_mm2=6.0, ps_a=32.0),
    }
    grid = PowerGrid(nodes=nodes, cables=cables)

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    # Direction: AC drop ≥ tree walk drop at every node downstream
    # of the generator.
    for name in ("a", "b", "c", "d"):
        tw_pct, ac_pct, _ = diff.bus_vdrop_percent[name]
        assert ac_pct >= tw_pct - 0.05, (
            f"{name}: expected AC drop ≥ tree-walk drop, got "
            f"AC={ac_pct:.2f} % vs tree={tw_pct:.2f} %"
        )

    # Compounding: the gap at depth 4 (d) is strictly bigger than
    # the gap at depth 1 (a). This is the signature of constant-P
    # feedback compounding.
    _, _, gap_a = diff.bus_vdrop_percent["a"]
    _, _, gap_d = diff.bus_vdrop_percent["d"]
    assert gap_d > gap_a, (
        f"expected gap to grow with depth, got "
        f"gap@a={gap_a:.3f} %, gap@d={gap_d:.3f} %"
    )


def test_wide_star_branches_are_independent():
    """**Wide star**: gen → 5 parallel 5 kW loads, no chaining.

    Topology
    --------
    Five branches off the generator, each a single 80 m / 32 A
    cable to one 5 kW load. No depth, no chaining, no compounding
    feedback between branches.

        gen ─┬─[80m]→ stage_1 (5 kW)
             ├─[80m]→ stage_2 (5 kW)
             ├─[80m]→ stage_3 (5 kW)
             ├─[80m]→ stage_4 (5 kW)
             └─[80m]→ stage_5 (5 kW)

    Total cumulative power at the generator: 25 kW. Each cable
    independently carries 5 kW.

    What this is testing
    --------------------
    1. **Symmetry**: every branch should report the same drop —
       no branch sees the others' currents.
    2. **Branch independence**: AC and tree walk agree closely on
       every leaf. Without depth, the constant-P feedback only
       runs one iteration deep, so the gap stays small (<0.5 pp).
    3. **Sanity**: this should look like 5 copies of a single
       1-cable case, not like a deep tree.

    Real-world scenario
    -------------------
    A central distribution hub feeding multiple stages or zones
    radially. The planner uses nopywer to design the layout; for
    this shape, **the tree walk and AC truth are nearly the same**
    and the planner can trust nopywer's numbers without worrying
    about the iterative AC validation.

    Contrast with `test_deep_linear_chain_compounds_drop_with_depth`
    — same total power (20–25 kW), same cable tier — but a wide
    layout instead of deep, and the gap collapses.
    """
    nodes = {"gen": _node("gen", 0.0, generator=True)}
    cables: dict[str, Cable] = {}
    for i in range(5):
        name = f"stage_{i + 1}"
        # Lay branches at slightly different lon to keep nodes distinct.
        nodes[name] = _node(name, 0.001 * (i + 1), 5.0)
        cables[f"cable_{i + 1}"] = _cable(
            f"cable_{i + 1}", "gen", name, 80.0, area_mm2=6.0, ps_a=32.0
        )
    grid = PowerGrid(nodes=nodes, cables=cables)

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    # All branches symmetric: every leaf reports the same drop.
    leaf_drops_tw = [diff.bus_vdrop_percent[f"stage_{i + 1}"][0] for i in range(5)]
    leaf_drops_ac = [diff.bus_vdrop_percent[f"stage_{i + 1}"][1] for i in range(5)]
    assert max(leaf_drops_tw) - min(leaf_drops_tw) < 0.05, (
        f"tree walk should report identical drops on symmetric branches; "
        f"got {leaf_drops_tw}"
    )
    assert max(leaf_drops_ac) - min(leaf_drops_ac) < 0.05, (
        f"AC should report identical drops on symmetric branches; "
        f"got {leaf_drops_ac}"
    )

    # Branch independence: AC and tree walk agree to within 0.5 pp on
    # every leaf. Without depth there's no feedback compounding.
    for i in range(5):
        name = f"stage_{i + 1}"
        tw_pct, ac_pct, gap = diff.bus_vdrop_percent[name]
        assert abs(gap) < 0.5, (
            f"{name}: expected near-parity (|gap| < 0.5 pp) on a wide "
            f"star branch, got tree={tw_pct:.2f} %, AC={ac_pct:.2f} %, "
            f"gap={gap:+.2f} pp"
        )


def test_bottleneck_thin_cable_dominates_drop_attribution():
    """**Bottleneck**: a thin 16 A trunk feeding three 32 A spurs.

    Topology
    --------
    A thin (2.5 mm² / 16 A) trunk runs 100 m from the generator to
    a central distro. From there, three 30 m / 6 mm² / 32 A spurs
    fan out to three 3 kW loads.

        gen ─[100 m, 2.5 mm²]→ distro ─┬─[30 m, 6 mm²]→ load_1 (3 kW)
                                        ├─[30 m, 6 mm²]→ load_2 (3 kW)
                                        └─[30 m, 6 mm²]→ load_3 (3 kW)

    Total downstream power: 9 kW, balanced across phases.
    Per-phase line current on the trunk: ~14.5 A (under 16 A).
    Per-phase line current on each spur: ~4.8 A (well under 32 A).

    The trunk is the bottleneck:
        R_trunk = (1/26) × 100 / 2.5 ≈ 1.54 Ω
        R_spur  = (1/26) × 30 / 6.0  ≈ 0.19 Ω

    Trunk R is ~8× spur R. Even at 1/3 the current, the trunk
    dominates total drop.

    What this is testing
    --------------------
    1. **Attribution**: both tools agree that the trunk carries
       the bulk of the drop (>75 % of the total path loss to any
       leaf). Even if magnitudes diverge, the **shape** of the
       drop along the path should match.
    2. **Symmetry**: the three downstream loads see identical
       drops (their spurs are symmetric).
    3. **Both tools surface the bottleneck**: tree walk and AC
       both report the largest cable current on the trunk, not
       on a spur.

    Real-world scenario
    -------------------
    A planner reuses an existing 100 m run of 2.5 mm² flex from
    the gen to a central area, then fans out with proper 32 A
    cables. The thin trunk **looks fine on paper** (14.5 A < 16 A
    rating) but its high R per metre dominates voltage drop. Both
    nopywer and pandapower should make this obvious in their
    output — the planner who reads either report should see "the
    drop is in the trunk, the spurs are negligible" and consider
    upgrading the trunk to a 32 A or 63 A cable.
    """
    nodes = {
        "gen": _node("gen", 0.0, generator=True),
        "distro": _node("distro", 0.001),
        "load_1": _node("load_1", 0.002, 3.0),
        "load_2": _node("load_2", 0.0021, 3.0),
        "load_3": _node("load_3", 0.0022, 3.0),
    }
    # Ensure distinct lat so nodes don't coincide with the trunk endpoint.
    nodes["load_1"].lat = 0.0001
    nodes["load_2"].lat = 0.0002
    nodes["load_3"].lat = 0.0003
    cables = {
        "trunk": _cable("trunk", "gen", "distro", 100.0, area_mm2=2.5, ps_a=16.0),
        "spur_1": _cable("spur_1", "distro", "load_1", 30.0, area_mm2=6.0, ps_a=32.0),
        "spur_2": _cable("spur_2", "distro", "load_2", 30.0, area_mm2=6.0, ps_a=32.0),
        "spur_3": _cable("spur_3", "distro", "load_3", 30.0, area_mm2=6.0, ps_a=32.0),
    }
    grid = PowerGrid(nodes=nodes, cables=cables)

    diff = compare_with_tree_walk(grid)
    assert diff.converged

    # Both tools agree the trunk carries the highest current.
    tw_currents = {cid: diff.line_current_a[cid][0] for cid in diff.line_current_a}
    ac_currents = {cid: diff.line_current_a[cid][1] for cid in diff.line_current_a}
    assert max(tw_currents, key=tw_currents.get) == "trunk", (
        f"tree walk should surface the trunk as highest-current; got {tw_currents}"
    )
    assert max(ac_currents, key=ac_currents.get) == "trunk", (
        f"AC should surface the trunk as highest-current; got {ac_currents}"
    )

    # Attribution: most of the drop to any load is in the trunk.
    # Compute per-cable ΔV from tree-walk side.
    distro_drop_tw = diff.bus_vdrop_percent["distro"][0]
    leaf_drop_tw = diff.bus_vdrop_percent["load_1"][0]
    trunk_share_tw = distro_drop_tw / leaf_drop_tw if leaf_drop_tw > 0 else 0
    assert trunk_share_tw > 0.75, (
        f"tree walk: trunk should carry >75 % of drop to leaf; got "
        f"trunk drop={distro_drop_tw:.2f} % vs leaf drop={leaf_drop_tw:.2f} % "
        f"(share={trunk_share_tw:.0%})"
    )

    # Same attribution check on the AC side.
    distro_drop_ac = diff.bus_vdrop_percent["distro"][1]
    leaf_drop_ac = diff.bus_vdrop_percent["load_1"][1]
    trunk_share_ac = distro_drop_ac / leaf_drop_ac if leaf_drop_ac > 0 else 0
    assert trunk_share_ac > 0.75, (
        f"AC: trunk should carry >75 % of drop to leaf; got "
        f"trunk drop={distro_drop_ac:.2f} % vs leaf drop={leaf_drop_ac:.2f} % "
        f"(share={trunk_share_ac:.0%})"
    )

    # Symmetry: the three spurs see identical drops in each tool.
    spur_drops_tw = [diff.bus_vdrop_percent[n][0] for n in ("load_1", "load_2", "load_3")]
    spur_drops_ac = [diff.bus_vdrop_percent[n][1] for n in ("load_1", "load_2", "load_3")]
    assert max(spur_drops_tw) - min(spur_drops_tw) < 0.05
    assert max(spur_drops_ac) - min(spur_drops_ac) < 0.05
