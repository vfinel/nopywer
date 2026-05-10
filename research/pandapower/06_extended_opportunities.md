# Extended pandapower opportunities

A wider survey beyond the IEC 60909 short-circuit module that already
exists. Each entry is sized in rough value-for-effort order. No code
changes are proposed here — this is a thinking aid for what to build
next on top of the conversion layer.

## 1. AC validation of the optimiser (highest value)

**Problem.** Both the heuristic optimiser (`optimize.py`) and the MILP
optimiser added in PR #5 (`optimize_milp.py`) end by calling
`analyze(grid)`. `analyze` is a tree-walk that linearises:
`I ≈ P / (phases · V₀ · PF)` and `V_drop ≈ I · R`. The MILP
solver's own docstring flags this and tells callers to
"validate critical layouts with a detailed power-flow check".

**Pandapower angle.** `to_pandapower(grid)` already converts the
topology. Adding loads to the converted net (`pp.create_load` with
`p_mw`, `q_mvar` from `PF = 0.9`) lets `runpp(net)` produce true AC
voltages and currents that include reactance and reactive power. We
then diff them against the tree-walk numbers and flag nodes where
the linearisation disagrees beyond a threshold.

**Why it's a clean fit.**
- Reuses the conversion layer already built. New code is a single
  calc function `compute_power_flow(pp_grid)` taking the same
  `PandapowerGrid` handle.
- Closes a loop the MILP author already documented as needing
  closure.
- Cost is one `runpp` call per layout — fractions of a second on a
  50-node festival grid.
- Doesn't replace `analyze.py`. The tree walk stays for fast inner
  loops; pandapower validates after optimisation completes.

**What it surfaces.**
- Voltage drop from reactance, especially at low PF. The tree walk
  underestimates by 1–5 % depending on PF.
- Voltage interaction with reactive power on long cables — the tree
  walk treats current as a function of `cum_power / V₀`, which is
  exact only at the source bus. AC flow accounts for the voltage
  the current actually sees.
- Whether the MILP's `weight_voltage_drop` and
  `max_voltage_drop_percent` constraints are actually being honoured
  in physical reality.

**Open questions.**
- What threshold counts as "disagreement"? Voltage to 0.5 V, current
  to 0.5 A is consistent with the tree-walk's existing rounding. Tighter
  than that is noise; looser hides real divergence.
- Should the validator log warnings inside `analyze` or be a
  separate CLI step? Probably separate — a hard pandapower
  dependency in `analyze.py` would force the optional extra to
  become required.

## 2. Reactive power per load type

**Problem.** `constants.py` bakes `PF = 0.9` once for every load. Real
festival loads cluster very differently:
- LED lighting and most electronics: PF ≈ 1.0
- Sound systems, amplifiers under load: PF ≈ 0.7
- Motors, chillers, coffee carts, ice machines: PF ≈ 0.6
- Switch-mode PSUs: highly current-distorting, effective PF can be
  ≈ 0.5 with significant harmonic content.

Collapsing all of this into a single 0.9 multiplier loses
information that voltage drop and cable sizing actually depend on.

**Pandapower angle.** `net.load` accepts `p_mw` and `q_mvar` per load.
A small enum on `PowerNode` (`load_type ∈ {"linear", "audio",
"motor", "smps"}`) feeds a per-load `q_mvar = p · tan(acos(PF_type))`.
For unbalanced single-phase loads, `net.asymmetric_load` allows a
different P/Q per phase.

**Why it's worth it.**
- Festivals routinely undersize cables to motor-heavy loads (kitchens,
  ice machines). A type-aware Q makes that visible.
- Costs nothing in topology — just a metadata field on `PowerNode`.

**What it costs.**
- A new GeoJSON property (`load_type`) that loaders, fixtures, and
  the frontend would need to learn about.
- A migration: existing fixtures default to `linear` or `mixed`.

## 3. Neutral conductor sizing via runpp_3ph

**Problem.** Nopywer reports phase imbalance as a single
percentage (`io.py:101`) but never sizes the neutral conductor.
For a 32 A 3-phase cable carrying mostly single-phase load on
phase 1, the neutral can carry close to 32 A. A `4G6` cable (4 cores
all 6 mm²) handles that; a `3G6+½N` (reduced-section neutral) does
not. Nopywer is silent on the distinction.

**Pandapower angle.** `runpp_3ph` returns per-phase line currents
including neutral residual. Converting `PowerNode.phase ∈ {1,2,3}`
loads into `net.asymmetric_load` with `p_a_mw / p_b_mw / p_c_mw` and
running the asymmetric solver gives realistic neutral currents.

**Why it's worth it.**
- Real safety gap. If anyone deploys a reduced-neutral cable
  (common in fixed installations, less so in flex) under heavy
  single-phase loading, nopywer's current "5% imbalance warning" is
  not the right diagnostic.
- Festival distros are usually 4-pole, but the cable feeding them
  may not be.

**What it costs.**
- Zero-sequence parameters on every cable. For LV flex these are
  not in pandapower's standard library — a documented assumption,
  similar to the existing `x_ohm_per_km = 0.08` decision, would
  cover it (typical `r0/r1 ≈ 4`, `x0/x1 ≈ 4` for 4-core cable).
- Vector group on the source — `runpp_3ph` requires earthed
  transformer or specific ext_grid configuration.
- More sensitive to convergence than balanced `runpp`.

## 4. Breaker / RCD coordination using existing i_sc_ka

**Problem.** The short-circuit module computes `i_sc_ka` per node but
nothing currently consumes it. Distro selection in `inventory.py`
matches breakers and panels by physical attributes only.

**Pandapower angle.** None directly — pandapower's job ends with
`calc_sc`. But the result feeds two safety checks:
1. Breaking capacity: `i_sc_ka < breaker.icu` at every bus where a
   breaker sits, otherwise the breaker can't safely interrupt the
   fault.
2. Disconnection time: per IEC 60364 §411, fault current must
   exceed the breaker's instantaneous magnetic threshold (typically
   5–10× rated for B-curve, 10–20× for C-curve, 10–50× for D-curve)
   to ensure trip times under 0.4 s on TN systems. Below that, the
   breaker only times out on overload — too slow for fault
   isolation.

**Why it's worth it.**
- IEC 60364 compliance is a formal requirement for permanent
  installations and increasingly for festivals under local
  jurisdictions.
- Catches a class of error invisible today: undersized breakers
  that "work" until they need to clear an actual fault.

## 5. Min-case earth-fault current

**Problem.** `compute_short_circuit` runs `case="max"` only. RCD
sensitivity verification needs *minimum* prospective single-line-
to-earth fault current — the current that flows for an L-PE fault
with all cables at maximum service temperature.

**Pandapower angle.** `calc_sc(net, fault="1ph", case="min")` once
zero-sequence parameters are populated. Same conversion layer.

**Why it's lower priority than 1–4.**
- Useful but additive. The breaker-coordination check (§4) covers
  most of the safety value with the data already on hand.
- Same zero-sequence-parameters dependency as §3 — if §3 lands,
  this is essentially free.

## 6. OPF for hybrid generator + battery

**Problem.** `models.py:177–183` raises if there is more than one
generator. Hybrid setups (diesel gen + battery + small PV array)
are increasingly common at events targeting low fuel use.

**Pandapower angle.** `runopp(net)` minimises generation cost
subject to V/I constraints. Multiple `ext_grid` or `gen` elements
with priority dispatch handle the hybrid case.

**Why it's lower priority.**
- Speculative; not a stated near-term need.
- Requires removing the >1 generator restriction and rewriting
  the cumulative-power tree walk to handle multiple sources.
- Big surface change for uncertain payoff.

## 7. State estimation against telemetry

**Problem.** PR #12 adds a telemetry visualiser that ingests real
per-phase Wh measurements. Today these are reported but not used
to calibrate the model.

**Pandapower angle.** `pp.estimate(net)` does WLS state estimation
with bad-data detection. Given measurements at the generator and a
few distros, it can reconstruct the actual node powers and flag
loads that don't match nameplate.

**Why it's interesting.**
- Calibration target for `RHO_COPPER = 1/26`. If measured drops
  match modelled drops with `RHO_COPPER = 1/X`, that's empirical
  evidence for X — would resolve the "Rich's old notes" provenance
  question.
- Catches unmodelled loads ("this distro reads 30 A but the model
  says 12 A").

**Why it's lower priority.**
- Telemetry pipeline isn't yet routine; PR #12 is a one-off
  visualiser.

## 8. Loop topologies

**Problem.** `analyze.py:43–49` raises on cycles. Some larger sites
deliberately run a closed ring with normally-open points for
fast reroute on cable failure.

**Pandapower angle.** Native — pandapower is mesh-capable.

**Why it's lowest priority.**
- Not a typical festival pattern.
- Would also need to redesign `optimize.py` (MST is radial-by-
  construction).

## What was considered and rejected

- **Standard-type cable library substitution.** Pandapower's
  `NAYY 4×50 SE` etc. are fixed-installation cables, not festival
  flex (HO7RN-F, Titanex, Type W). No fit.
- **`bus_geodata` as round-trip GIS.** Pure plotting metadata in
  pandapower, not used for distance or impedance. The GeoJSON
  layer stays as the geographic boundary.
- **DC approximation `rundcpp`.** Designed for transmission scale.
  Festival LV cables are too short and resistive to benefit.
- **MATPOWER / PYPOWER / CIM export.** Strategy C from
  `04_porting_considerations.md`. Useful only for academic
  collaboration, no demonstrated demand.

## Architectural fit

All of §1, §3, §5, §6, §7 take a `PandapowerGrid` and add new
calc functions. The conversion layer in `shortcircuit/_core.py`
is the foothold. The pattern is: `to_pandapower(grid)` once, then
pass the handle to whichever combination of calc functions the
caller cares about. No global state, no required coupling between
features.

§2 is the only entry that changes the `PowerNode` schema (new
`load_type` field). §4 is the only one that touches
`inventory.py` (consumes `i_sc_ka` for distro coordination).
Everything else is additive in a new module.
