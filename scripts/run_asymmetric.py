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

============================================================
The single user-facing knob — `--load-factor`
============================================================

`--load-factor` is **one** multiplier on nameplate that drives the
entire analysis. The default (0.5) is the project-wide festival
diversity assumption: "festival loads draw ~50 % of nameplate on
average". The number says, *for this run*, what fraction of
nameplate we are modelling.

It has two consistent effects:

  1. **Planning (`--plan`)** — `assign_greedy` / `assign_round_robin`
     balance the legs against `power_watts × load_factor`. A
     borderline-large load shifts in or out of the "fits on one leg"
     category, and greedy's heaviest-first pack order is computed on
     scaled values.
  2. **Solve (`runpp` and `runpp_3ph`)** — every load's
     `power_watts` is multiplied by `load_factor` before conversion,
     so both solvers see the same scaled demand the planner assumed.

The two effects use the **same number** on purpose. Plan-then-stress-
test (plan at 0.5, solve at 1.0) is a separate diagnostic workflow,
not a knob on this script — if you genuinely need it, run the
script twice or write a 5-line scripted sweep.

What changing it does, intuitively:

  - `--load-factor 1.0` — model worst case: every load peaks
    simultaneously. The most conservative answer. Often won't
    converge on real fixtures (the grid is past voltage collapse).
  - `--load-factor 0.5` (default) — model the festival diversity
    assumption. The number doc 12's findings use.
  - `--load-factor 0.2` — model a deep quiet period. Usually
    converges with plenty of headroom; useful for sanity-checking
    that the topology is sensible.

============================================================
Other notes
============================================================

  - `runpp_3ph` will refuse to converge on grids past voltage collapse
    (the P-V nose). This is a *physical* result, not a script bug —
    see research/pandapower/11_field_export_fixture_walkthrough.md.
  - Phase planning is **optional**. Without `--plan`, unphased loads
    stay `phase=None`, become balanced `pp.load`s under `runpp_3ph`,
    and the asymmetric solver behaves much like the balanced one
    (because the grid genuinely *is* balanced then). Pass
    `--plan greedy` to actually exercise the asymmetric machinery.

============================================================
Order of operations
============================================================

    load  ->  snap  ->  plan (sees power_watts × load_factor)
          ->  apply  ->  scale (multiply power_watts by load_factor)
          ->  convert  ->  solve (balanced and asymmetric)

The scale step happens *after* planning so the planner can use the
unmodified `node.power_watts` field to compute candidates and the
scaling is the one place that mutates the grid.
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


def _positive_float(raw: str) -> float:
    """argparse type — reject zero, negative, and absurd factors."""
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"--load-factor must be > 0, got {value!r}")
    if value > 5:
        raise argparse.ArgumentTypeError(
            f"--load-factor {value!r} is implausibly large (> 5x nameplate). "
            "If you really mean this, override the bound in scripts/run_asymmetric.py."
        )
    return value


_STRATEGIES = {"greedy": assign_greedy, "round_robin": assign_round_robin}


def _nameplate_total_w(grid: PowerGrid) -> float:
    """Sum of nameplate power across non-generator loads, in watts."""
    return sum(n.power_watts for n in grid.nodes.values() if not n.is_generator)


def _scale_loads_in_place(grid: PowerGrid, factor: float) -> None:
    """Multiply every non-generator load's nameplate power by `factor`.

    Mutates `node.power_watts` directly. Done after planning so the
    planner sees unmodified nameplate; done before conversion so the
    solver sees the scaled values.
    """
    for node in grid.nodes.values():
        if not node.is_generator:
            node.power_watts *= factor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Asymmetric 3-phase analysis on a nopywer GeoJSON fixture. "
            "See the module docstring for what --load-factor does."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("fixture", type=Path, help="Input GeoJSON file.")
    parser.add_argument(
        "--plan",
        choices=("none", "greedy", "round_robin"),
        default="none",
        help=(
            "Synthesise phase assignments for unphased loads before "
            "solving. Without this, runpp_3ph treats unphased loads "
            "as balanced and behaves like runpp."
        ),
    )
    parser.add_argument(
        "--load-factor",
        type=_positive_float,
        default=config.DEFAULT_USAGE_FACTOR,
        help=(
            "Single multiplier on nameplate applied to BOTH phase "
            "planning AND the solver inputs. 1.0 = model worst-case "
            "(everyone peaks); 0.5 (default) = festival diversity "
            "assumption; 0.2 = deep quiet period. See module docstring."
        ),
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

    nameplate_w = _nameplate_total_w(grid)
    effective_w = nameplate_w * args.load_factor

    # --- pre-flight summary — print what assumptions are in play ----
    print("=" * 64)
    print(f"fixture:         {args.fixture}")
    print(f"loaded:          {len(grid.nodes)} nodes, {len(grid.cables)} cables")
    print(f"nameplate total: {nameplate_w / 1e3:7.2f} kW (sum of all loads)")
    print(f"load factor:     {args.load_factor:7.2f}   (applied to BOTH planning and solve)")
    print(f"effective total: {effective_w / 1e3:7.2f} kW (what the solvers will see)")
    print(f"plan strategy:   {args.plan}")
    print("=" * 64)

    # --- optional phase planning (sees nameplate × load_factor) -----
    if args.plan != "none":
        plan = _STRATEGIES[args.plan](grid, usage_factor=args.load_factor)
        apply_assignment(grid, plan)
        print(f"\nphase plan ({args.plan}):")
        print(f"  loads assigned:  {len(plan.phases)}")
        print(
            f"  balance:         {plan.balance_pct:.2f}%  (0 % = perfectly level; lower is better)"
        )
        print(
            f"  per-leg totals:  "
            f"L1={plan.leg_totals_w[0] / 1e3:.2f} kW, "
            f"L2={plan.leg_totals_w[1] / 1e3:.2f} kW, "
            f"L3={plan.leg_totals_w[2] / 1e3:.2f} kW"
        )

    # --- scale loads in place before conversion ---------------------
    if args.load_factor != 1.0:
        _scale_loads_in_place(grid, args.load_factor)

    # --- balanced runpp (reference) ---------------------------------
    print("\n=== balanced runpp (for comparison) ===")
    pp_balanced = to_pandapower(grid)
    try:
        bal = compute_power_flow(pp_balanced)
        worst_bus, worst_drop = max(bal.bus_vdrop_percent.items(), key=lambda kv: kv[1])
        print(f"  converged:        {bal.converged}")
        print(f"  worst bus drop:   {worst_bus!r} = {worst_drop:.2f}%")
    except Exception as exc:
        print(f"  did NOT converge: {type(exc).__name__}: {exc}")
        print("  (grid past voltage collapse — try a lower --load-factor)")

    # --- asymmetric runpp_3ph ---------------------------------------
    print("\n=== runpp_3ph (asymmetric) ===")
    pp_3ph = to_pandapower_3ph(grid)
    n_bal = len(pp_3ph.balanced_load_idx)
    n_asym = len(pp_3ph.asymmetric_load_idx)
    print(f"  loads in net.load            (balanced):   {n_bal:3d}")
    print(f"  loads in net.asymmetric_load (per-leg):    {n_asym:3d}")

    try:
        res = compute_power_flow_3ph(pp_3ph)
    except Exception as exc:
        print(f"  did NOT converge: {type(exc).__name__}: {exc}")
        print("  (grid past voltage collapse — try a lower --load-factor)")
        return 1

    print(f"  converged:        {res.converged}")

    worst_vdrop = sorted(
        (
            (name, leg + 1, drop)
            for name, legs in res.bus_vdrop_percent.items()
            for leg, drop in enumerate(legs)
        ),
        key=lambda t: -t[2],
    )[: args.top]
    print(f"\n  top {args.top} worst per-leg voltage drops:")
    for name, leg, drop in worst_vdrop:
        print(f"    {name!r:30s} L{leg}  {drop:6.2f} %")

    worst_neutral = sorted(res.line_neutral_current_a.items(), key=lambda kv: -kv[1])[: args.top]
    print(f"\n  top {args.top} cables by neutral current:")
    for cable_id, i_n in worst_neutral:
        print(f"    {cable_id!r:20s}  {i_n:6.2f} A")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
