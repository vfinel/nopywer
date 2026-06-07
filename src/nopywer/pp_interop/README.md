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
assignments for fixtures that arrive unphased or partially phased.
The balanced solver always ignores `phase`. The asymmetric solver
*uses* it where it's set and falls back to a balanced draw where
it isn't — so phase planning is an enhancement to the 3ph path,
not a prerequisite.

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
    │  → PandapowerGrid      │         │  → Pandapower3phGrid         │
    │  (balanced loads in    │         │  (independent net; loads     │
    │   net.load)            │         │   split across net.load and  │
    │                        │         │   net.asymmetric_load by     │
    │                        │         │   node.phase)                │
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
| **GeoJSON** | A `FeatureCollection`. Points → `PowerNode`s with `name`, `power` (W), `phase` (`None` / `1` / `2` / `3` / `[1,2]`), `is_generator`. LineStrings → cables with `id`, `length`/`length_m`, `area`/`area_mm2`, `plugs&sockets`/`plugs_and_sockets_a`. Either the hand-authored or the round-tripped export schema works (aliases handled in `io._EXPORT_KEY_ALIASES`). |
| **Generator** | Exactly one node with `is_generator: true`. Its bus becomes the `ext_grid` slack. |
| **Cable endpoints** | Cables must reference existing node names via `from_node` / `to_node`. The GeoJSON loader populates these by snapping; the converter raises `ValueError` if any are missing. |
| **Per-load phase** | Only required for the **asymmetric** path. For balanced `to_pandapower` it's ignored. For `to_pandapower_3ph`, any load whose `phase` is an `int` or `list` becomes an `asymmetric_load`; `None` stays balanced. Use the `phases` package to synthesise an assignment if your fixture arrives unphased. |
| **`usage_factor`** | **Required, keyword-only**, on every public function in `pp_interop.phases`. There is no default. Use `config.DEFAULT_USAGE_FACTOR` (0.5) as the project-wide reference if you want it. |
| **Modelling constants** | All in `pp_interop/config.py`: generator rating (`GEN_SN_KVA`, `GEN_XDSS_PU`, `GEN_RX`), cable reactance (`X_OHM_PER_KM`), zero-sequence ratios (`R0_OVER_R1`, `X0_OVER_X1`), source earthing (`SOURCE_X0X_MAX`, `SOURCE_R0X0_MAX`), and `DEFAULT_USAGE_FACTOR`. All have working defaults. Generator and cable values are also exposed as kwargs on `to_pandapower(...)` / `to_pandapower_3ph(...)` for per-call overrides; zero-sequence and source-earthing values are read directly from `config` at conversion time and must be changed there. |
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

**Phase a fixture and write it out** — for the common workflow,
use the `phase_geojson` one-call wrapper:

```python
from nopywer.pp_interop import config
from nopywer.pp_interop.phases import phase_geojson

plan = phase_geojson(
    "tests/fixtures/2026-05-14_martin.geojson",
    "2026-05-14_martin_phased.geojson",
    usage_factor=config.DEFAULT_USAGE_FACTOR,
    strategy="greedy",          # or "round_robin"
)
print(plan.balance_pct)
```

`phase_geojson` loads the input, runs the chosen strategy, applies
the assignment, and writes a pretty-printed GeoJSON to the output
path. `usage_factor` is required (no default — the right value is
event-specific). The source fixture is never modified in place.

The same workflow done by hand — useful when you want to inspect
or compare plans before writing, or to use the strategies from
inside larger pipelines:

```python
import json
from nopywer.io import load_geojson
from nopywer.models import PowerGrid
from nopywer.pp_interop import config
from nopywer.pp_interop.phases import assign_greedy, apply_assignment

nodes, cables = load_geojson("tests/fixtures/2026-05-14_martin.geojson")
grid = PowerGrid(nodes=nodes, cables=cables)

plan = assign_greedy(grid, usage_factor=config.DEFAULT_USAGE_FACTOR)
apply_assignment(grid, plan)                # writes plan.phases onto the grid

with open("2026-05-14_martin_phased.geojson", "w") as f:
    json.dump(grid.to_geojson(), f, indent=2)
```

`PowerNode.to_geojson` emits `phase` whenever it is non-`None` and
omits it otherwise, so the export stays clean for fully-balanced
fixtures and round-trips faithfully for planned ones. Reload the
written file with `load_geojson` and the assignment is in place —
`assign_greedy` will then treat those loads as pre-assigned and
leave them alone. The existing `python -m nopywer <in> -o <out>`
CLI uses the same `grid.to_geojson()` and so picks up the phase
field automatically.

**Asymmetric power flow from the command line** — for a quick run
without writing code, `scripts/run_asymmetric.py` wraps the whole
pipeline behind a single `--load-factor` knob that drives both
planning and solve consistently. See `scripts/run_asymmetric.py`'s
module docstring for the rationale behind the one-knob design and
the implications of each value.

```bash
uv run python scripts/run_asymmetric.py \
    tests/fixtures/2026-05-14_martin_modified.geojson \
    --load-factor 0.5
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

## Two converters, two grid types

`to_pandapower` and `to_pandapower_3ph` return **distinct dataclasses**
and produce **independent** `pandapowerNet` objects. They share a
private skeleton builder (buses, lines, ext_grid), but neither
mutates the other's output. Converting the same `PowerGrid` for
both flows is a no-shared-state operation.

| Converter | Return type | Loads in net |
|---|---|---|
| `to_pandapower(grid)` | `PandapowerGrid` | Every load in `net.load`; one `load_idx` map. |
| `to_pandapower_3ph(grid)` | `Pandapower3phGrid` | Loads split across `net.load` and `net.asymmetric_load`; **two** index maps: `balanced_load_idx` and `asymmetric_load_idx`. |

### Why the 3ph grid splits loads into two tables

The split is not an implementation quirk — it tracks a real
distinction in the source data:

- **`phase is None`** → load goes to `net.load`, keyed in
  `balanced_load_idx`. The planner has not declared a leg; nopywer
  treats this as an even three-phase draw, which is exactly what
  pandapower's `pp.load` means under `runpp_3ph`. Using `pp.load`
  here is not a shortcut — it's the right primitive.
- **`phase` is an `int` or `list`** → load goes to
  `net.asymmetric_load`, keyed in `asymmetric_load_idx`. The
  planner has nailed the load to specific legs. Only
  `pp.asymmetric_load` lets us tell pandapower "8 kW on L1, 0 on
  L2, 0 on L3" or "5 kW on L1, 5 kW on L2, 0 on L3".

A load name appears in **at most one** map. The split is decided at
conversion time from `node.phase` and is fixed for the lifetime of
the `Pandapower3phGrid`.

### What `phase = None` means at each layer

`None` is not "missing data" — it is the explicit modelling choice
"balanced three-phase draw". Each layer treats it consistently with
that meaning:

| Layer | Behaviour on `phase is None` |
|---|---|
| `io.load_geojson` | Sets `node.power_per_phase = [P/3, P/3, P/3]` for any tree-walk analysis downstream. |
| `PowerNode.to_geojson` | **Omits** the `"phase"` key (not emitted as `null`). Reload is symmetric: missing key → `None`. |
| `phases.single_phase_candidates` | `None` is the marker for "eligible to be planned". Any other `phase` (int / list) is treated as already-decided and left alone. |
| `phases.apply_assignment` | When a plan assigns a leg, sets `node.phase = 1\|2\|3`. Does **not** recompute `power_per_phase` — that derived cache is stale until the grid is reloaded. The `phase` field is authoritative. |
| `to_pandapower` (balanced) | Ignores `phase` entirely; every load is a balanced `pp.load`. |
| `to_pandapower_3ph` (asymmetric) | `None` → `pp.load` in `balanced_load_idx`. `pp.runpp_3ph` treats `pp.load` as an even three-phase draw, so this is the correct primitive for unphased loads, not a workaround. |
| `compute_power_flow_3ph` | An unphased load sags its three legs equally and contributes zero to neutral current (its three currents cancel in the return). Indistinguishable from a balanced motor. |

The takeaway: a fully-unphased grid solves through `runpp_3ph` just
fine — it'll just look very similar to the balanced solve, because
that's what an all-balanced grid genuinely is.

### What this means for you

- **Convert once per flow.** Build a `PandapowerGrid` for the
  balanced solve; build a separate `Pandapower3phGrid` for the
  asymmetric solve. The two are independent — modifying one does
  not affect the other.
- **`compute_power_flow_3ph` requires `Pandapower3phGrid`.** The
  type-checker will catch "I passed the balanced grid to the 3ph
  solver" at the call site rather than letting it fail at runtime
  with a cryptic pandapower error.
- **To check whether a specific load has been planned**, look at
  `pp_grid_3ph.asymmetric_load_idx` (or equivalently
  `name in pp_grid_3ph.balanced_load_idx`). You do not need to
  inspect `net` directly — the type surfaces the planning state.
- **A fully-planned fixture leaves `balanced_load_idx` empty.** Same
  code path; no special handling. Likewise, a fully-unphased fixture
  leaves `asymmetric_load_idx` empty and `runpp_3ph` solves a
  balanced grid (the same one `runpp` would solve, plus the
  zero-sequence overhead).
- **Write-back keyed on names is safe.** Iterating
  `pp_grid_3ph.bus_idx` reaches every node exactly once regardless
  of the load split.

## Logging

Two silent data coercions emit log records so they cannot regress
to silent behaviour. Configure the standard `logging` module to see
them (`logging.basicConfig(level=logging.DEBUG)` for everything;
`level=logging.WARNING` for just the loud ones).

| Logger | Level | When it fires |
|---|---|---|
| `nopywer.io` | `DEBUG` | A feature carries property keys outside the known set — useful for catching typos (`powr` for `power`) without being noisy on legitimate computed export fields. |

## Things to remember

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
