# `pp_interop` — pandapower interop layer

Optional feature. Install with `uv sync --extra pandapower`. Without
the extra, every public entry point raises a clear `ImportError`
pointing at this command.

Two solver paths live here:

- **Balanced AC power flow** (`to_pandapower` → `compute_power_flow`),
  built on pandapower's `runpp`. One scalar voltage per bus, one
  scalar current per cable. Right model for a well-balanced grid.
- **Asymmetric three-phase power flow** (`to_pandapower_3ph` →
  `compute_power_flow_3ph`), built on `runpp_3ph`. Per-leg voltages
  and currents, plus the neutral-conductor current — the quantity
  no balanced tool and no nopywer tree walk can produce.

A separate `phases/` subpackage synthesises per-load phase
assignments for fixtures that arrive unphased. The asymmetric solver
needs that to be populated; the balanced solver ignores it.

See `research/pandapower/` (docs 10, 10.1, 11, 12) for the modelling
theory and findings behind these choices.

## Code-flow diagram

```
                         ┌─────────────────────────────┐
                         │   GeoJSON FeatureCollection │
                         │  (input or export schema)   │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                    ┌────────────────────────────────────┐
                    │  nopywer.io.load_geojson(path)     │
                    │  → (dict[name, PowerNode],         │
                    │     dict[id,   Cable])             │
                    └──────────────┬─────────────────────┘
                                   │
                          (wrap in PowerGrid / analyze)
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │     PowerGrid        │
                         │  (snapped cables,    │
                         │   phase fields set   │
                         │   per node)          │
                         └────────┬─────────────┘
                                  │
              ┌───────────────────┴─── optional ────────────────┐
              │ phase-planning pass (only for fixtures whose    │
              │ loads arrive `phase=None`)                      │
              │                                                 │
              │   from nopywer.pp_interop import config         │
              │   from nopywer.pp_interop.phases import (       │
              │       assign_greedy, assign_round_robin,        │
              │       apply_assignment)                         │
              │                                                 │
              │   plan = assign_greedy(                         │
              │       grid,                                     │
              │       usage_factor=config.DEFAULT_USAGE_FACTOR) │
              │   apply_assignment(grid, plan)                  │
              └───────────────────┬─────────────────────────────┘
                                  │
                ┌─────────────────┴─────────────────┐
                │                                   │
                ▼                                   ▼
    ┌────────────────────────┐         ┌──────────────────────────────┐
    │ to_pandapower(grid)    │         │ to_pandapower_3ph(grid)      │
    │  (balanced)            │         │  (asymmetric — augments      │
    │                        │         │   the balanced net with      │
    │                        │         │   zero-seq params + swaps    │
    │                        │         │   phased loads for           │
    │                        │         │   asymmetric_loads)          │
    └──────────┬─────────────┘         └────────────────┬─────────────┘
               │                                        │
               ▼                                        ▼
    ┌────────────────────────┐         ┌────────────────────────────┐
    │ compute_power_flow     │         │ compute_power_flow_3ph     │
    │  (runpp, balanced)     │         │  (runpp_3ph)               │
    └──────────┬─────────────┘         └────────────────┬───────────┘
               │                                        │
               ▼                                        ▼
    ┌──────────────────────┐           ┌────────────────────────────┐
    │ PowerFlowResults     │           │ PowerFlow3phResults        │
    │  (scalar per-bus V,  │           │  (per-leg tuples + neutral │
    │   per-line A,        │           │   current, unbalance %)    │
    │   loading %)         │           │                            │
    └──────────────────────┘           └────────────────────────────┘
```

## Inputs

| What | Required form |
|---|---|
| **GeoJSON** | A `FeatureCollection`. Points → `PowerNode`s with `name`, `power` (W), `phase` (`None` / `1` / `2` / `3` / `[1,2]` / `"U"` / `"Y"`), `is_generator`. LineStrings → cables with `id`, `length`/`length_m`, `area`/`area_mm2`, `plugs&sockets`/`plugs_and_sockets_a`. Either the hand-authored or the round-tripped export schema works (aliases handled in `io._EXPORT_KEY_ALIASES`). |
| **Generator** | Exactly one node with `is_generator: true`. Its bus becomes the `ext_grid` slack. |
| **Cable endpoints** | Cables must reference existing node names via `from_node` / `to_node`. The GeoJSON loader populates these by snapping; the converter raises `ValueError` if any are missing. |
| **Per-load phase** | Only required for the **asymmetric** path. For balanced `to_pandapower` it's ignored. For `to_pandapower_3ph`, any load whose `phase` is an `int` or `list` becomes an `asymmetric_load`; `None` stays balanced. Use the `phases` package to synthesise an assignment if your fixture arrives unphased. |
| **`usage_factor`** | **Required, keyword-only**, on every public function in `pp_interop.phases`. There is no default. Use `config.DEFAULT_USAGE_FACTOR` (0.5) as the project-wide reference if you want it. |
| **Modelling constants** | All in `pp_interop/config.py`: generator rating (`GEN_SN_KVA`, `GEN_XDSS_PU`, `GEN_RX`), cable reactance (`X_OHM_PER_KM`), zero-sequence ratios (`R0_OVER_R1`, `X0_OVER_X1`), source earthing (`SOURCE_X0X_MAX`, `SOURCE_R0X0_MAX`), and `DEFAULT_USAGE_FACTOR`. All have working defaults; override via kwargs to `to_pandapower(...)`. |
| **Optional dep** | `uv sync --extra pandapower` — without it, `_import_pandapower` raises a clear `ImportError`. |

## Outputs

| Solver | Returns | Key fields |
|---|---|---|
| `compute_power_flow` | `PowerFlowResults` | `bus_voltage_v[node]` (scalar V_PN), `bus_vdrop_percent[node]`, `line_current_a[cable]`, `line_loading_percent[cable]`, `converged` |
| `compute_power_flow_3ph` | `PowerFlow3phResults` | `bus_voltage_v[node]` (3-tuple per leg), `bus_vdrop_percent[node]` (3-tuple), `bus_unbalance_percent[node]`, `line_current_a[cable]` (3-tuple), **`line_neutral_current_a[cable]`** (the headline number), `line_loading_percent[cable]`, helpers `worst_phase_vdrop()` / `worst_neutral_current()` |
| `compare_with_tree_walk` | `TreeWalkVsAcDiff` | Side-by-side of nopywer's tree walk and balanced `runpp` on the same grid, with per-bus / per-line diffs and helper `worst_*_disagreement` methods. |

## Minimal runnable examples

**Balanced power flow** — exactly the shape `tests/test_pp_interop.py`
uses:

```python
from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.pp_interop import to_pandapower, compute_power_flow

nodes, cables = load_geojson("tests/fixtures/2026-05-14_martin_modified.geojson")
grid = PowerGrid(nodes=nodes, cables=cables)
pp_grid = to_pandapower(grid)                # → PandapowerGrid
results = compute_power_flow(pp_grid)        # → PowerFlowResults
print(results.bus_vdrop_percent["jamhouse"])
```

**Asymmetric power flow with phase planning** — the full doc 12
pipeline:

```python
from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.pp_interop import (
    config,
    to_pandapower_3ph,
    compute_power_flow_3ph,
)
from nopywer.pp_interop.phases import assign_greedy, apply_assignment

nodes, cables = load_geojson("tests/fixtures/2026-05-14_martin_modified.geojson")
grid = PowerGrid(nodes=nodes, cables=cables)

# 1. plan phases (only if the fixture has unphased loads)
plan = assign_greedy(grid, usage_factor=config.DEFAULT_USAGE_FACTOR)
apply_assignment(grid, plan)

# 2. convert + solve asymmetric
pp_grid_3ph = to_pandapower_3ph(grid)
results = compute_power_flow_3ph(pp_grid_3ph)

print(results.worst_phase_vdrop())      # ('jamhouse', 2, 13.7)
print(results.worst_neutral_current())  # ('cable_15', 20.4)
```

## Things to remember

- `to_pandapower_3ph` **augments and mutates** the balanced net
  produced by `to_pandapower` (pops phased loads out of `net.load`,
  adds them to `net.asymmetric_load`). Don't reuse the same
  `PandapowerGrid` for both balanced and asymmetric solves — convert
  fresh each time.
- `usage_factor` is required everywhere in `pp_interop.phases`.
  Forgetting it is a `TypeError`, by design — the right value is
  event-specific and we don't want it disappearing into a default.
- Voltages are reported in nopywer-native phase-to-neutral volts
  (≈ 230 V nominal), not pandapower's line-to-line per-unit.
- For real-cable safety calls the headline number from the
  asymmetric path is `line_neutral_current_a` — it's the one no
  balanced solve can give you and the one that decides
  reduced-vs-full-section neutral cable choice.
- Multi-phase loads (`phase=[1, 2]`) split power **evenly** across
  the listed legs. This is a modelling assumption — see
  `research/pandapower/10_three_phase_asymmetric_modelling.md`
  ("Modelling assumption — multi-phase loads self-balance evenly")
  for when it holds and when it doesn't.
