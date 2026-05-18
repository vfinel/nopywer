# What nopywer's power calculations actually do

Read of `src/nopywer/analyze.py`, `models.py`, `optimize.py`, and `constants.py`
as of commit on branch `develop` (April 2026).

## Domain

Festival / event temporary power distribution. European LV (230 V phase-to-neutral,
50 Hz implicit), single generator, radial cable layout, IEC plug-and-socket
form factors (16 A / 32 A / 63 A / 125 A).

## Inputs

A GeoJSON FeatureCollection containing:

- **Point features** → loads or the generator. Properties: `name`, `power`
  (watts), `phase` (1, 2, 3, or null). The generator is identified
  by the substring `"generator"` in its name.
- **LineString features** → cables with the two coordinate endpoints.
  Properties: `length` (m, optional — geodesic distance is used otherwise),
  `area` (mm², default 2.5), `plugs&sockets` (A, default 16), `phase`.

There is **no** transformer, no shunt capacitance, no reactive component, no
external grid, no impedance element, no switch, and no concept of
line-to-line voltage. Everything is single-stage radial.

## Power flow algorithm (`analyze.py`)

The algorithm is not a Newton-Raphson AC power flow. It is a four-pass
tree walk:

1. **`_snap_cables_to_nodes`** — Snap any unattached cable endpoint to the
   nearest node within `CONNECTION_THRESHOLD_M = 5 m`.
2. **`_build_tree`** — Recursively assign a parent / children / depth to each
   node using a simple DFS rooted at the generator. Cycles raise an error.
3. **`_cumulate_current`** — Walk the tree from leaves back to the root,
   accumulating `power_per_phase` (a length-3 numpy array) into each
   ancestor. The cable to a node's parent gets
   `current_per_phase = cum_power / V0 / PF`. There is **no Kirchhoff /
   Newton iteration** — the answer is obtained in a single bottom-up sweep
   because the graph is a tree.
4. **`_compute_voltage_drop`** — Walk the tree top-down. For each child cable:

   ```
   cable.vdrop_volts = cable.resistance * max(cable.current_per_phase)
   node.voltage      = parent.voltage - cable.vdrop_volts
   ```

   `cable.resistance` is `RHO_COPPER * length_m / area_mm2`.

   `RHO_COPPER = 1/26 Ω·mm²/m`, deliberately ~2.2× the textbook copper
   resistivity (1/58). The constant comes from "Rich's old notes" and is a
   conservative field-margin factor.

## What this model captures

- Per-phase real-power balance through any tree topology.
- Single-phase loads pinned to one specific phase (1, 2, or 3) cause that
  phase to carry more cumulative current upstream.
- Voltage drop is approximately correct for resistive cables with PF = 0.9.
- Phase imbalance is reported as `100 * std(cum_power_per_phase) / mean(...)`
  at the generator.

## What this model elides

| Effect | Treated as |
|---|---|
| Cable reactance (X) | Zero. Festival cables have `X / R` in the 0.05–0.15 range, so this is a few-percent error in voltage drop magnitude. |
| Cable capacitance (C) | Zero. Acceptable at festival scales (km-class capacitance is irrelevant under 1 km of LV cable). |
| Reactive power (Q) | Power factor is folded into `PF = 0.9` once at conversion. There is no concept of `Q` per load. |
| Voltage-dependent load | All loads are constant-power. |
| Line-to-line vs line-to-neutral | The generator output is treated as 230 V phase-to-neutral always; there is no Δ vs Y wiring. |
| Neutral / earth current | Not modelled. Per-phase imbalance produces neutral current in reality; nopywer reports imbalance but does not size the neutral. |
| Mutual coupling between phases | Not modelled. |
| Loop topologies | Forbidden — `_assign_children` raises if a cycle is detected. |
| Multiple generators | Forbidden — `PowerGrid.__post_init__` raises if `len(generators) > 1`. |
| Solver convergence | N/A — the tree walk is direct, so there is nothing to converge. |

## Sizing logic (`models.py`)

Four hardcoded `Cable` subclasses:

| Class | Phases | Max current (A) | Cross-section (mm²) | Tier cost |
|---|---|---|---|---|
| `Cable16A` | 1 | 16 | 2.5 | 1.0 |
| `Cable32A` | 3 | 32 | 6.0 | 3.0 |
| `Cable63A` | 3 | 63 | 16.0 | 8.0 |
| `Cable125A` | 3 | 125 | 35.0 | 20.0 |

`pick_cable_for(power_watts)` picks the smallest tier such that
`power / (num_phases * V0 * PF) ≤ max_current_a`.

The thresholds (3 313 W, 19 873 W, 39 124 W) are pinned in
`tests/test_models.py`.

## Layout optimization (`optimize.py`)

Independent of `analyze.py`. Steps:

1. Build a complete distance graph between all node pairs (geodesic distance
   via projection to EPSG:32630).
2. Compute the NetworkX MST → minimum-total-length tree.
3. Root by BFS at the generator.
4. **`_reduce_cable_cost`** — local-search rewires: for each non-root node,
   try the 15 nearest neighbours, the generator, and a few ancestors as
   candidate parents. Accept any rewire that drops total
   `Σ length × pick_cable_for(cum_power).tier_cost` by ≥ 1 %.
5. Convert the final tree into typed cables and recompute power flow.

This is a domain-specific layout planner. There is no equivalent in
pandapower.

## Other supporting logic

- **`inventory.py`** — Match required cables / distros against an Excel
  inventory using a greedy combinatorial search over available cable
  lengths. Pure pandas + itertools.
- **`api.py`** — Single FastAPI endpoint `/api/v1/optimize` that takes a
  nodes GeoJSON and returns the optimized layout as cables GeoJSON.
- **`io.py`** — GeoJSON ↔ `PowerGrid` round-trip plus a `print_grid_info`
  reporter that prints per-depth tabular grid info to logs.

## Key numbers to keep in mind

- `V0 = 230 V` (phase-to-neutral)
- `PF = 0.9`
- `RHO_COPPER = 1/26 Ω·mm²/m` (conservative)
- `VDROP_THRESHOLD_PERCENT = 5 %` (NF C 15-100 / IEC 60364)
- `EXTRA_CABLE_LENGTH_M = 10 m` (slack added to every cable)
- `CONNECTION_THRESHOLD_M = 5 m` (snap distance)
