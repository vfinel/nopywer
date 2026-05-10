# Sensitivity to pp_interop config assumptions

The `pp_interop/config.py` defaults are documented as "industry
typical" but until now we had no measurement of how much each
assumption actually moves the planner-facing numbers.
`scripts/sensitivity_sweep.py` runs three tight sweeps around each
default on a deep-chain fixture (4 cables × 50 m, 5 kW × 4 loads —
representative of a back-of-house corridor). This doc captures what
the sweeps revealed and what each finding means for a planner.

## TL;DR

| Knob | Default | Tested range | Impact at festival scales | Verdict |
|---|---:|---|---|---|
| `X_OHM_PER_KM` | 0.08 | 0.05 – 0.12 | AC drop moves **0.06 pp** across the full range | Negligible — leave as-is |
| `PF` (load) | 0.9 | 0.80 – 1.00 | AC drop moves **0.39 pp**; sign of gap flips at PF ≈ 0.97 | Modest, but the most useful per-load knob if `load_type` ever lands |
| `GEN_XDSS_PU` | 0.12 | 0.08 – 0.18 | Isc moves **2.2×** (1.81 kA → 0.81 kA at the gen bus) | **Biggest lever**. Worth overriding per-event for breaker sizing |

## Sweep 1 — Cable reactance `X_OHM_PER_KM`

Default: 0.08 Ω/km. Tested: 0.05 → 0.12 in 0.01 steps.

```
    X Ω/km    tree d %      AC d %      gap pp
----------------------------------------------
     0.050      11.220      11.312      +0.092
     0.060      11.220      11.321      +0.101
     0.070      11.220      11.330      +0.110
     0.080      11.220      11.339      +0.119  ← default
     0.090      11.220      11.347      +0.127
     0.100      11.220      11.356      +0.136
     0.110      11.220      11.365      +0.145
     0.120      11.220      11.373      +0.153
```

**What it shows.** Tree walk is invariant (it ignores X). AC drop
grows linearly with X, but the slope is ~0.7 pp per Ω/km. Across
the full ±50 % swing around the default, the AC answer moves only
0.06 pp.

**Why.** The reactive component of voltage drop is `I · X · sin φ`.
At PF = 0.9, sin φ = 0.435. With per-cable I ≈ 32 A and total
length ≈ 200 m, the X contribution to each cable's drop is small
relative to the resistive `I · R · cos φ` term. Festival cables
are short and resistive — exactly the regime where X is a
second-order effect.

**Implication for the planner.** The 0.08 default is fine. Even if
a particular cable spec sheet quotes 0.07 or 0.10, the impact on
the AC validator's output is below the rounding the tree walk
already does. **No need to expose this as a per-cable parameter
unless someone runs validators on > 1 km of cable.**

## Sweep 2 — Load power factor `PF`

Default: 0.9. Tested: 0.80 → 1.00 in 0.025 steps.

```
      PF    tree d %      AC d %      gap pp
--------------------------------------------
   0.800      11.220      11.543      +0.323
   0.825      11.220      11.486      +0.266
   0.850      11.220      11.433      +0.213
   0.875      11.220      11.384      +0.164
   0.900      11.220      11.339      +0.119  ← default
   0.925      11.220      11.295      +0.075
   0.950      11.220      11.253      +0.033
   0.975      11.220      11.210      -0.010
   1.000      11.220      11.151      -0.069
```

**What it shows.** Tree walk is invariant — `PF` is hardcoded in
`nopywer.constants.PF`. Only the AC side moves. Lower PF →
bigger AC drop. The gap **changes sign around PF ≈ 0.97**: above
that, AC reports *less* drop than tree walk; below, more.

**Why.** Lower PF = more reactive current to deliver the same P =
more total current = more drop. At PF = 1.0 there's no Q at all
and the constant-power feedback loop barely runs (no voltage-
sensitive Q to amplify), so AC is actually slightly *under* the
tree walk's conservative single-pass answer.

**Implication for the planner.** The default 0.9 is a reasonable
festival average. But:

- A real **kitchen tent** at PF ≈ 0.7 (motors, fridges) would push
  the AC gap further open: extrapolating linearly, AC drop would
  be roughly +0.5 pp above tree walk on this fixture. Not
  catastrophic, but visible.
- A real **LED-only stage** at PF ≈ 1.0 would have AC reporting
  *less* drop than tree walk. Tree walk over-states by ~0.07 pp.

The interesting consequence: **nopywer's tree walk is roughly
right when the load mix really does average 0.9 PF**, but it
silently over-estimates drop for resistive loads and under-
estimates for inductive ones. A future per-load `load_type`
field (opportunity §2 in
[`06_extended_opportunities.md`](./06_extended_opportunities.md))
would let `to_pandapower` pass per-load Q values and capture this
properly.

## Sweep 3 — Generator subtransient reactance `GEN_XDSS_PU`

Default: 0.12 pu (typical diesel). Tested: 0.08 → 0.18 in 0.01 steps.

```
     X''d pu    Isc gen kA    Isc load kA
-----------------------------------------
       0.080        1.8115         0.6957
       0.090        1.6102         0.6794
       0.100        1.4492         0.6627
       0.110        1.3174         0.6460
       0.120        1.2076         0.6293  ← default
       0.130        1.1147         0.6127
       0.140        1.0351         0.5963
       0.150        0.9661         0.5803
       0.160        0.9057         0.5646
       0.170        0.8525         0.5493
       0.180        0.8051         0.5345
```

**What it shows.** Isc at the generator bus moves from 1.81 kA at
X″d = 0.08 down to 0.81 kA at 0.18 — a **2.2× range** across the
realistic 0.08 – 0.18 sweep. At the load bus (50 m of 32 A cable
downstream), the cable impedance dominates and the response is
much weaker (0.70 → 0.53 kA, 1.3× range).

**Why.** Source short-circuit power is `S_sc = S_n / X''d`. Halve
X″d and you double the available fault current at the gen bus.
Cable impedance attenuates this further downstream, so the lever
is biggest where there's no cable in the way.

**Implication for the planner.** This is the single most
important assumption to **override per-event**. Real festivals
hire one of:

- A large **salient-pole synchronous machine** (X″d ≈ 0.08) →
  high Isc, breakers must have ≥ 2 kA breaking capacity.
- A typical **diesel gen-set** (X″d ≈ 0.12, the default) →
  ~1.2 kA Isc. Most 6 kA breakers are over-rated for this.
- A **gas turbine** or smaller-frame machine (X″d ≈ 0.18) →
  ~0.8 kA Isc. Standard breakers fine, but worth checking the
  *minimum* fault current for RCD trip.

A planner running `compute_short_circuit` without overriding
`gen_xdss_pu` for the actual hired machine could get the breaker
selection wrong by a factor of 2. **Worth flagging in the CLI
output** — "computed assuming X″d = 0.12 pu (typical diesel);
override via gen_xdss_pu= for the actual machine".

## Cross-cutting observations

**The two power-flow knobs (X, PF) are second-order at festival
scales.** Even varying them simultaneously to their pessimistic
ends (X = 0.12, PF = 0.80) only moves AC drop by ~0.4 pp from the
default. The tree walk and AC flow are **dominated by the cable
R and the topology**, not by these per-cable / per-load constants.

**The fault-calc knob (X″d) is first-order.** Source impedance is
the only meaningful contributor to fault current at the gen bus,
and changing it by a factor of 2.25 changes Isc by exactly that.
A planner who ignores this is making a real safety error.

**What we are NOT measuring.** This sweep holds the fixture
constant and varies one parameter at a time. We don't measure:

- **Compounding effects** between knobs (e.g. low PF + high X
  combined). The expectation is that they superpose linearly at
  these scales, but it's untested.
- **Sensitivity to `RHO_COPPER`**. Both tools share that constant,
  so it shifts both views equally and the *gap* is invariant — but
  the absolute numbers both produce would scale linearly with any
  change. Worth flagging if telemetry from PR #12 ever provides
  a basis for re-deriving the 1/26 figure.
- **Sensitivity to fixture topology**. A wider star or a deeper
  chain would shift the absolute drops; the qualitative findings
  about each knob's leverage should hold but the magnitudes would
  change.

## How to reproduce

```bash
uv run python scripts/sensitivity_sweep.py
```

Output is deterministic. Re-run after any change to `pp_interop/
config.py`'s defaults to refresh the numbers in this doc.
