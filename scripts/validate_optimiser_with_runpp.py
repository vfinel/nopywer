"""End-to-end validation of nopywer's optimiser against pandapower runpp.

Loads the 2025 event fixture, optimises layout, then compares the
tree-walk result against pandapower's AC power flow on the same grid.

Run with:
    uv run python scripts/validate_optimiser_with_runpp.py
"""

import json
import time
from pathlib import Path

from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.optimize import optimize_layout
from nopywer.pp_interop import compare_with_tree_walk

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "input_nodes.geojson"


def main() -> None:
    with open(FIXTURE) as f:
        nodes_geojson = json.load(f)

    nodes, _ = load_geojson(nodes_geojson)
    print(f"Loaded {len(nodes)} nodes from {FIXTURE.name}")

    start = time.time()
    grid = optimize_layout(PowerGrid(nodes=nodes, cables={}))
    optim_duration = time.time() - start
    print(f"Optimised ({optim_duration :.2f} s): ",
          f"{len(grid.cables)} cables, "
          f"{sum(c.length_m for c in grid.cables.values()):.0f} m total")

    diff = compare_with_tree_walk(grid)
    print(f"AC converged: {diff.converged}")

    print("\n=== Voltage drop comparison (% at each node) ===")
    print(f"{'node':<32} {'tree':>8} {'AC':>8} {'Δ':>8}")
    rows = sorted(
        diff.bus_vdrop_percent.items(), key=lambda kv: kv[1][1], reverse=True
    )
    for name, (tw, ac, delta) in rows[:15]:
        print(f"{name[:32]:<32} {tw:>8.2f} {ac:>8.2f} {delta:>+8.3f}")

    print("\n=== Worst voltage disagreement ===")
    worst = diff.worst_voltage_disagreement()
    if worst:
        name, delta = worst
        tw, ac, _ = diff.bus_voltage_v[name]
        print(f"{name}: tree-walk {tw:.1f} V, AC {ac:.1f} V, Δ {delta:+.2f} V")

    print("\n=== Cable current comparison (top 10 by AC current) ===")
    print(f"{'cable':<14} {'tree_max_A':>12} {'ac_A':>10} {'Δ A':>8}")
    rows = sorted(
        diff.line_current_a.items(), key=lambda kv: kv[1][1], reverse=True
    )
    for cid, (tw, ac, delta) in rows[:10]:
        print(f"{cid[:14]:<14} {tw:>12.1f} {ac:>10.1f} {delta:>+8.2f}")

    print("\n=== Worst current disagreement ===")
    worst = diff.worst_current_disagreement()
    if worst:
        cid, delta = worst
        tw, ac, _ = diff.line_current_a[cid]
        print(f"{cid}: tree-walk {tw:.1f} A, AC {ac:.1f} A, Δ {delta:+.2f} A")

    print("\n=== Execution time ===")
    print(f"tree walk: {diff.time_diff[0]:.3f} ms")
    print(f"AC: {diff.time_diff[1]:.3f} ms")
    print(f"diff: {abs(diff.time_diff[2]):.3f} ms")



    print("\n=== Summary ===")
    voltage_deltas = [d for _, _, d in diff.bus_voltage_v.values()]
    current_deltas = [d for _, _, d in diff.line_current_a.values()]
    if voltage_deltas:
        print(f"Voltage Δ: max |Δ| = {max(abs(d) for d in voltage_deltas):.2f} V, "
              f"mean |Δ| = {sum(abs(d) for d in voltage_deltas) / len(voltage_deltas):.3f} V")
    if current_deltas:
        print(f"Current Δ: max |Δ| = {max(abs(d) for d in current_deltas):.2f} A, "
              f"mean |Δ| = {sum(abs(d) for d in current_deltas) / len(current_deltas):.3f} A")


if __name__ == "__main__":
    main()
