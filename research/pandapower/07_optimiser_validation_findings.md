# Optimiser AC validation — implementation and findings

This doc records what was built for opportunity §1 in
[`06_extended_opportunities.md`](./06_extended_opportunities.md) and
what running it on the 2025 fixture revealed. The tone is the same
as the rest of this folder: research notes, not a how-to.

## What was built

A second calc function on top of the existing `to_pandapower(grid)`
conversion layer. The same `PandapowerGrid` handle now feeds two
analyses, and a third helper diffs the legacy tree-walk against
pandapower's AC power flow side-by-side.

```
                       ┌─────────────────────────────────────────┐
                       │  src/nopywer/pp_interop/                │
                       │                                         │
  PowerGrid ──────────►│  to_pandapower(grid, ...)               │
  (your domain         │       │                                 │
   model: nodes,       │       ▼                                 │
   cables, generator)  │  ┌──────────────────────┐               │
                       │  │  PandapowerGrid      │               │
                       │  │  ─────────────────   │               │
                       │  │  net      (pp.Net)   │ ◄──── reused
                       │  │  bus_idx  {name:int} │       across
                       │  │  load_idx {name:int} │       all calc
                       │  │  source   PowerGrid  │       functions
                       │  └──────────────────────┘               │
                       │       │                                 │
                       │       ├──► compute_short_circuit  →  i_sc_ka per node
                       │       │       (calc_sc, fault=3ph, max)
                       │       │
                       │       ├──► compute_power_flow     →  PowerFlowResults
                       │       │       (runpp; AC NR)            (V, I per bus/line)
                       │       │
                       │       └──► compare_with_tree_walk →  TreeWalkVsAcDiff
                       │               (analyze + runpp,           (tree, ac, Δ)
                       │                side by side)
                       └─────────────────────────────────────────┘
```

The conversion layer was extended to populate `net.load` for every
non-generator node with `power_watts > 0`. P comes from the node's
power; Q is derived from the project-level `PF = 0.9` constant
(`q_mvar = p_mw · tan(acos(PF))`). Loads are needed by `runpp` and
are harmless for `calc_sc`'s IEC 60909 max-case (which standardly
ignores prefault load).

## Tree-walk vs AC — what each algorithm actually does

The two analyses solve overlapping problems with very different
machinery. On a 1-cable example (generator → 50 m of 6 mm² → 3 kW
load) they look like this:

```
TREE WALK (analyze.py)                    AC POWER FLOW (runpp)
─────────────────────                     ──────────────────────

Step 1: cumulate power leaves → root      Step 1: build admittance matrix Y
                                                  for the whole network
   load.power_per_phase = [1, 1, 1] kW
   gen.cum_power        = [1, 1, 1] kW    Step 2: guess voltages V₀ = 1.0 p.u.
                                                  everywhere

Step 2: derive cable current               Step 3: NEWTON-RAPHSON LOOP
                                                  ┌────────────────────┐
   I = cum_power / V₀ / PF                        │ given V, compute   │
     = 1000 / 230 / 0.9                           │ S = V · (Y·V)*    │
     = 4.83 A   (per phase)                       │                    │
                                                  │ residual = S - S_set
   Note: V₀ is NOMINAL (230 V), not                │                    │
   the voltage actually present at                │ Δ = J⁻¹ · residual │
   the load.                                      │ V ← V + Δ          │
                                                  └────────────────────┘
Step 3: voltage drop, top → down                            ▲
                                                            │ iterate
   R = ρ·L/A = (1/26)·50/6 = 0.32 Ω                         │ until
   ΔV = R · I_max = 0.32 · 4.83                             │ |Δ| < tol
      = 1.55 V                                              ▼
                                          Step 4: read V at each bus,
   load.voltage = 230 - 1.55 = 228.5 V            I in each line
   load.vdrop_percent = 0.67%

   ───  ONE PASS, NO ITERATION  ───      ───  ITERATES TO EQUILIBRIUM  ───
```

The tree walk runs in microseconds and is exact in the limit of
zero voltage drop. AC is slower but solves the full nonlinear system
including reactive power, line reactance, and the load's response
to its actual local voltage.

## Why the two diverge — the constant-power feedback loop

The tree walk's blind spot is exactly what AC iterates to find. A
constant-power load at lower-than-nominal voltage draws more current
to deliver the same P. The extra current causes more drop, which
lowers the voltage further:

```
          ┌─────────────────────────────────────────────────┐
          │                                                 │
          ▼                                                 │
   cable drop ↑                                             │
          │                                                 │
          ▼                                                 │
   V at load ↓ ── (V is lower than V₀)                      │
          │                                                 │
          ▼                                                 │
   Load is constant-power: P = V · I = const                │
          │                                                 │
          ▼                                                 │
   I must rise to hold P                                    │
          │                                                 │
          ▼                                                 │
   more I × same R = more drop ────────────────────────────►┘
          (positive feedback — converges to equilibrium
           at the AC operating point)
```

The tree walk computes `I` at nominal `V₀` and stops there. It
never sees the feedback. So at high drop it reports too little
current, and therefore too little drop.

The conservative `RHO_COPPER = 1/26` (≈ 2.2× textbook copper) was
intended to overstate `R` and hide some of this gap — but the
missing physics is the load-feedback loop, not the resistance
value, and the margin doesn't compensate.

## Findings on the 2025 event fixture

`tests/fixtures/input_nodes.geojson` — 51 nodes, 50 cables after
optimisation, 2480 m total. AC converged. The voltage-drop
disagreement at the worst nodes:

```
Voltage at the worst nodes (% drop from 230 V P-N):

            tree walk          AC truth
           (analyze.py)         (runpp)
                │                  │
glitch       ───┤ 26.9 ────────────┤ 39.1   ← 12.2 pp worse than reported
oasis_pg     ───┤ 26.5 ────────────┤ 38.5
belly_town   ───┤ 26.2 ────────────┤ 37.9
curious_cr   ───┤ 25.9 ────────────┤ 37.6
distro10     ───┤ 25.8 ────────────┤ 37.4
prueba       ───┤ 25.4 ────────────┤ 36.7
distro2      ───┤ 24.7 ────────────┤ 35.8
distro9      ───┤ 24.6 ────────────┤ 35.6
distro4      ───┤ 24.3 ────────────┤ 35.2
why_do_…     ───┤ 22.2 ─────┤ 26.6              ← divergence shrinks
wonderever   ───┤ 21.8 ─────┤ 26.2                where drop is smaller
…
                │                  │
              0─5─────15────25─────35────45 % drop
                │                  │
              IEC 60364
              5% threshold
              (NF C 15-100)
                │
                ▼
              both views
              already over
              the limit
```

Two things to take away.

1. **The optimiser is producing layouts where even the tree walk
   reports 25–27 % drop** — already 5× over the 5 % NF C 15-100
   threshold. That is an existing issue. AC didn't create it; AC
   just made it visible. Whether this fixture represents a real
   shipped event or is a stress test worth checking.

2. **The gap is bigger at higher drops.** The first 9 nodes
   diverge by 11–12 pp; the lower-stress nodes diverge by ~4 pp.
   This matches the feedback-loop intuition: the deeper the drop,
   the more the constant-power loads compound it.

Aggregate numbers across all 51 buses and 50 cables:
- Voltage Δ: max 28.0 V at `glitch`, mean |Δ| = 7.8 V
- Cable current Δ: max 38.8 A on `optim_0`, mean |Δ| = 4.2 A

## Workflow change

```
Today:                                    With AC validation:
─────                                     ──────────────────────────

GeoJSON                                    GeoJSON
   │                                          │
   ▼                                          ▼
load_geojson()                             load_geojson()
   │                                          │
   ▼                                          ▼
optimize_layout()                          optimize_layout()
   │                                          │
   ▼                                          ▼
analyze()  ◄── tree walk only              analyze()
   │                                          │
   ▼                                          ▼
print + GeoJSON out                        compare_with_tree_walk()
                                              │  ┌── tree walk (fast inner loop)
                                              │  └── runpp     (AC validation)
                                              ▼
                                           print + Δ report + GeoJSON out
```

The tree walk stays for the inner loop of the optimiser — it must
run thousands of times during local-search rewires and it is the
right tool for that scale. Pandapower runs **once at the end** as a
validator on the converged layout.

## What this enables that wasn't possible before

- **Threshold-based escalation.** "Re-optimise if AC vdrop > 5 %
  even when tree walk passes" is now expressible. Today the
  optimiser can produce layouts that the tree walk reports as 4.8 %
  while AC truth is 9 %.
- **Quantifying the linearisation cost.** PR #5's MILP optimiser
  carries an explicit caveat: *validate critical layouts with a
  detailed power-flow check*. That validator now exists. The
  numbers above tell us the caveat was understating the issue.
- **Calibration target for `RHO_COPPER`.** The 1/26 constant comes
  from "Rich's old notes". With AC validation in place, fixtures
  with measured voltages (PR #12 telemetry) can be back-fitted to
  reveal the empirical ρ that matches reality.

## What it does *not* do yet

- The validation does not feed back into the optimiser. It runs
  once after the layout is fixed. Closing that loop (re-optimise
  on AC failure) is a separate piece of work.
- Loads are modelled as balanced. Single-phase loads pinned to a
  specific phase (`PowerNode.phase ∈ {1,2,3}`) are aggregated as
  P/3 across all phases for `runpp`. Per-phase asymmetric flow
  needs `runpp_3ph` and is opportunity §3 in
  `06_extended_opportunities.md`.
- The default `gen_sn_kva = 100` is fictional. For real per-event
  numbers the caller passes the rated kVA explicitly. The
  shape of the divergence is insensitive to this — generator
  source impedance is small compared to the cable impedance for
  any realistic festival kVA — but absolute Isc numbers are not.
- No CLI flag yet. The validation runs through
  `scripts/validate_optimiser_with_runpp.py`. Folding into
  `nopywer-analyze` is a thin wrapper.

## Packaging note

Pandapower 3.4.0 (the latest release) ships a bug in its `runpp`
result-extraction path that fails under pandas ≥ 2.3 with read-only
numpy buffers. The fix is in
[e2nIEE/pandapower#2860](https://github.com/e2nIEE/pandapower/pull/2860),
merged 2026-02-10 — one day after the 3.4.0 release. The
`pyproject.toml` `pandapower` extra is therefore pinned to that
merge commit until 3.4.1 ships. `compute_short_circuit` is
unaffected because `calc_sc` doesn't traverse the buggy code path.
