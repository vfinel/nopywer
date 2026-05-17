"""End-to-end asymmetric three-phase analysis on a GeoJSON fixture.

Loads the fixture, snaps cables, optionally plans phases for unphased
loads, runs `runpp_3ph`, and prints a per-leg / per-cable report. The
companion to `phase_geojson` for the *solve* side: nothing here that
you couldn't assemble from `pp_interop` primitives in 30 lines of
Python, but assembled so a reviewer can run

    uv run python scripts/run_asymmetric.py tests/fixtures/<name>.geojson

and see what the asymmetric solver makes of the grid without writing
any code.

The balanced `runpp` is also run for comparison so you can read the
"balanced says X, asymmetric says Y" gap that doc 12 documents.

Notes:
  - `runpp_3ph` will refuse to converge on grids past voltage collapse
    (the P-V nose). This is a *physical* result, not a script bug —
    see research/pandapower/11_field_export_fixture_walkthrough.md.
  - Phase planning is **optional**. If you pass `--plan greedy` (or
    `round_robin`), unphased loads get a synthesised assignment first;
    without it, unphased loads stay `phase=None`. An unphased load
    becomes a balanced `pp.load` under `runpp_3ph` (three-phase even
    draw, zero neutral current — `pp.load` *is* the balanced-draw
    primitive), so the asymmetric solver behaves much like the
    balanced one. Pass `--plan` to actually exercise the asymmetric
    machinery.
"""

import argparse
import logging
import sys
from pathlib import Path

from nopywer.analyze import _snap_cables_to_nodes
from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.pp_interop import (
    compute_power_flow,
    compute_power_flow_3ph,
    config,
    to_pandapower,
    to_pandapower_3ph,
)
from nopywer.pp_interop.phases import (
    apply_assignment,
    assign_greedy,
    assign_round_robin,
)

_STRATEGIES = {"greedy": assign_greedy, "round_robin": assign_round_robin}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Asymmetric 3-phase analysis on a nopywer GeoJSON fixture.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("fixture", type=Path, help="Input GeoJSON file.")
    parser.add_argument(
        "--plan",
        choices=("none", "greedy", "round_robin"),
        default="none",
        help="Synthesise phase assignments for unphased loads before solving.",
    )
    parser.add_argument(
        "--usage-factor",
        type=float,
        default=config.DEFAULT_USAGE_FACTOR,
        help="Festival diversity factor used by --plan.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="How many worst-leg buses / worst-neutral cables to print.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show DEBUG-level log records from nopywer modules.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)-45s %(message)s",
    )
    logging.getLogger("pandapower").setLevel(logging.WARNING)
    logging.getLogger("numba").setLevel(logging.WARNING)

    if not args.fixture.exists():
        print(f"fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    # --- load + snap -------------------------------------------------
    nodes, cables = load_geojson(args.fixture)
    grid = PowerGrid(nodes=nodes, cables=cables)
    _snap_cables_to_nodes(grid)
    print(f"loaded {len(grid.nodes)} nodes, {len(grid.cables)} cables "
          f"from {args.fixture}")

    # --- optional phase planning ------------------------------------
    if args.plan != "none":
        plan = _STRATEGIES[args.plan](grid, usage_factor=args.usage_factor)
        apply_assignment(grid, plan)
        print(f"\nphase plan ({args.plan}, usage_factor={args.usage_factor}):")
        print(f"  loads assigned:  {len(plan.phases)}")
        print(f"  balance:         {plan.balance_pct:.2f}%")
        print(f"  leg totals (W):  "
              f"L1={plan.leg_totals_w[0]:.0f}, "
              f"L2={plan.leg_totals_w[1]:.0f}, "
              f"L3={plan.leg_totals_w[2]:.0f}")

    # --- balanced runpp (reference) ---------------------------------
    print("\n=== balanced runpp (for comparison) ===")
    pp_balanced = to_pandapower(grid)
    try:
        bal = compute_power_flow(pp_balanced)
        worst_bus, worst_drop = max(
            bal.bus_vdrop_percent.items(), key=lambda kv: kv[1]
        )
        print(f"  converged: {bal.converged}")
        print(f"  worst bus drop: {worst_bus!r} = {worst_drop:.2f}%")
    except Exception as exc:
        print(f"  did NOT converge: {type(exc).__name__}: {exc}")
        print("  (grid is past voltage collapse — runpp_3ph will fail too)")

    # --- asymmetric runpp_3ph ---------------------------------------
    print("\n=== runpp_3ph (asymmetric) ===")
    pp_3ph = to_pandapower_3ph(grid)
    print(f"  loads (balanced):    {len(pp_3ph.balanced_load_idx)}")
    print(f"  loads (asymmetric):  {len(pp_3ph.asymmetric_load_idx)}")

    try:
        res = compute_power_flow_3ph(pp_3ph)
    except Exception as exc:
        print(f"  did NOT converge: {type(exc).__name__}: {exc}")
        return 1

    print(f"  converged: {res.converged}")

    worst_vdrop = sorted(
        ((name, leg + 1, drop)
         for name, legs in res.bus_vdrop_percent.items()
         for leg, drop in enumerate(legs)),
        key=lambda t: -t[2],
    )[: args.top]
    print(f"\n  top {args.top} worst per-leg voltage drops:")
    for name, leg, drop in worst_vdrop:
        print(f"    {name!r:30s} L{leg}  {drop:6.2f} %")

    worst_neutral = sorted(
        res.line_neutral_current_a.items(), key=lambda kv: -kv[1]
    )[: args.top]
    print(f"\n  top {args.top} cables by neutral current:")
    for cable_id, i_n in worst_neutral:
        print(f"    {cable_id!r:20s}  {i_n:6.2f} A")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
