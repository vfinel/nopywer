# `runpp_3ph` findings on the 2026 east-grid fixture

The shopping list in [`10`](./10_three_phase_asymmetric_modelling.md)
and the theory in
[`10.1`](./10.1_three_phase_theory.md) said the same thing:
balancing the legs at the generator is *not* the same problem as
sizing the cables, and the asymmetric solver would show us things
the balanced one structurally cannot. This doc is the first run of
that solver on a real fixture and what it actually surfaced.

Same register as
[`07_optimiser_validation_findings.md`](./07_optimiser_validation_findings.md):
numbers, the takeaways they justify, and an explicit list of what
the numbers do *not* support.

## What was run

- **Fixture**: `tests/fixtures/2026-05-14_martin_modified.geojson` —
  2026 east-grid export, with the four cable resizes from
  doc 11 (one 1P 16 A trunk → 3P 125 A, the GoJ feeder → 3P 63 A,
  the other generator trunk → 3P 125 A, the curious-creatures feed
  → 3P 32 A) and the asymmetric `curious creatures` modelled as
  `phase: [1, 2]`.
- **Strategies**: Strategy D (greedy least-loaded leg) and Strategy
  B (round-robin), both from `pp_interop/phases`, applied fresh
  each run.
- **Solvers**: balanced `pp.runpp` (`compute_power_flow`) and
  asymmetric `pp.runpp_3ph` (`compute_power_flow_3ph`), in parallel.
- **Usage factor**: 0.5× is the working assumption (doc 10). The
  scale sweep walks down from full nameplate to expose where each
  solver tips into non-convergence.

The zero-sequence cable and source defaults
(`R0_OVER_R1 = 4`, `X0_OVER_X1 = 4`, `SOURCE_X0X_MAX = 1`,
`SOURCE_R0X0_MAX = 0.1`) are engineering rule-of-thumb, not
measured — anything sensitive to them is a *direction*, not a
calibrated number.

## Convergence sweep

| Strategy | Scale | Balanced `runpp` | Asymmetric `runpp_3ph` |
|---|---:|---|---|
| greedy | 1.0× | converged, worst 21.7 % (`jamhouse`) | **no converge** |
| greedy | 0.7× | converged, worst 13.9 % (`jamhouse`) | converged, worst leg **37.7 %** (`oasis playground` L2) |
| greedy | 0.5× | converged, worst 9.5 % (`jamhouse`) | converged, worst leg **21.1 %** (`oasis playground` L2) |
| greedy | 0.3× | converged, worst 5.5 % (`jamhouse`) | converged, worst leg **11.3 %** (`oasis playground` L2) |
| round-robin | 1.0× | converged, worst 21.7 % (`jamhouse`) | **no converge** |
| round-robin | 0.7× | converged, worst 13.9 % (`jamhouse`) | **no converge** |
| round-robin | 0.5× | converged, worst 9.5 % (`jamhouse`) | converged, worst leg **31.2 %** (`jamhouse` L2) |
| round-robin | 0.3× | converged, worst 5.5 % (`jamhouse`) | converged, worst leg **14.7 %** (`jamhouse` L2) |

Three things to read from this.

### 1. The balanced view is optimistic in a way that hides physical reality

At full nameplate the balanced solve converges on both strategies
and reports a 21.7 % worst-node drop — alarming, but at least a
*finite answer*. The asymmetric solve refuses to converge at all.
The grid as exported, with realistic per-leg loads on its worst
phase, **does not have an AC operating point**. The balanced 21.7 %
is a fiction produced by averaging that load across three legs;
under the real per-leg loading the heaviest phase is past its P–V
nose.

At 0.5× — the working usage factor — the gap is smaller but still
load-bearing: balanced says 9.5 %, asymmetric says **21.1 %**.
Roughly 2.2× higher, and on a *different node* (`oasis playground`,
not `jamhouse`). A planner working from the balanced number would
think they were in the 10 % drop zone and would not order bigger
cable. The asymmetric number is comfortably over the 5 % NF C
15-100 ceiling. The two solvers are answering different questions.

### 2. Strategy choice changes which scale converges

Greedy converges at 0.7×; round-robin does not. Same grid, same
loads, only the phase plan differs. This is the convergence-side
manifestation of what doc 10 already noted: greedy levels the
generator legs to 0.6 % imbalance vs round-robin's 9.5 %, and that
extra margin buys roughly one scale step before the heaviest leg
runs out of voltage. It is not a free lunch — see point 3 — but it
is a real result.

### 3. Strategy choice does **not** rescue voltage drop

At 0.5× both strategies converge, but the worst leg is still 21 %
(greedy) or 31 % (round-robin), far above 5 %. Greedy beats
round-robin here, but neither even approaches spec. This confirms
the doc 10 conclusion from a second angle: phase planning is for
generator-leg balance and convergence margin; it is **not a
substitute for cable sizing**. The cables on `oasis playground`'s
path are 2.5 mm² flex, and no amount of phase shuffling fixes a
cable that is too thin for its load.

## What `runpp_3ph` surfaces that nothing else does

### Per-leg voltage at the worst-affected stalls

The top five buses by worst-leg drop, greedy @ 0.5×:

| Node | L1 % | L2 % | L3 % | Voltage unbalance % |
|---|---:|---:|---:|---:|
| `oasis playground` | 6.7 | **21.1** | 2.2 | 3.1 |
| `desert dessert` | -1.4 | -5.9 | **19.5** | 3.5 |
| `planet pulpo` | 7.6 | **19.1** | 2.4 | 2.7 |
| `mirage` | 8.3 | **17.6** | 2.6 | 2.5 |
| `jamhouse` | **16.5** | 14.0 | -0.1 | 2.7 |

Three things to notice. The worst-leg drop varies by node by 5+
percentage points within the same fixture. The *quietest* leg at a
bus can sit slightly above nominal (`oasis playground` L3 at -1.4 V,
i.e. 230 V + tiny). And the voltage-unbalance factor at downstream
buses (2.5-3.5 %) is far higher than the 0.05 % the *generator*
sees — a single number for the whole grid would have hidden every
one of these.

### Neutral currents per cable — the cable-spec result

Top five cables by neutral current, greedy @ 0.5×:

| Cable | Spec | Phases (A) | Neutral (A) | Notes |
|---|---|---|---:|---|
| `cable_23` | 3P 125 A trunk | 50.8 / 40.7 / 15.3 | 29.5 | within rating |
| `cable_21` | 3P 63 A | 45.6 / 33.0 / 15.3 | 24.7 | within rating |
| **`cable_15`** | **1P 16 A, 2.5 mm²** | 0 / 0 / 20.4 | **20.4** | **neutral over rating** |
| `cable_1` | 3P 125 A trunk | 27.1 / 35.6 / 45.6 | 16.0 | within rating |
| `cable_22` | 3P 63 A | 26.0 / 33.0 / 15.3 | 13.4 | within rating |

`cable_15` (zaz → `desert dessert`) carries 20.4 A on a 2.5 mm² / 16
A flex — over rating, **on the neutral specifically**. A balanced
solve cannot see this: in its world the neutral carries nothing.
Reduced-section-neutral cables (`3G6+½N`) would fare worse still on
this branch.

This is the cable-spec result we hoped for. It will not be alarming
on every fixture, but it does say "neutral sizing is *not* free" —
a worst-case neutral approaching the worst-phase current can show
up on a real grid, not just on a stress fixture.

### Strategy comparison under `runpp_3ph` (not just tree-walk)

Doc 10 measured strategy quality with nopywer's tree walk (max-phase
rule). With `runpp_3ph` we can measure it under the real AC solve:

| Metric @ 0.5× | Greedy | Round-robin |
|---|---:|---:|
| Worst leg vdrop | **21.1 %** | 31.2 % |
| Worst leg location | `oasis playground` L2 | `jamhouse` L2 |
| Worst neutral current | 29.5 A | 24.0 A |
| Worst node unbalance | ~3.5 % | (similar order) |
| Lowest converging scale | 0.7× | 0.5× |

Greedy wins on convergence margin and on worst-leg drop. Round-robin
is marginally better on worst-neutral. The neutral-current ordering
is a nuance worth flagging: greedy concentrates more of its
imbalance onto the upstream trunk (`cable_23`) where the path is
heaviest, while round-robin's positional cycling spreads things
more uniformly across cables. Greedy's lower *generator* imbalance
does not propagate as lower *per-cable* neutral everywhere.

## Generator-balanced is not grid-balanced

Greedy at 0.5× gives a generator-bus voltage unbalance of **0.05 %**
— effectively perfect. Three nodes downstream of the same generator
sit at **3+ %** unbalance. That is the asymmetric reality the
balanced view cannot represent at all: the balance metric reported
by `print_grid_info` and used by the strategy itself is a
generator-side quantity, and it does not predict what individual
stalls actually see at their socket. Same lesson as doc 10's
worst-vdrop result, but now in the dimension of voltage unbalance
rather than per-leg drop.

## What this does *not* show

- **Real zero-sequence parameters.** The 4× rule for `r0`/`x0` and
  the `Yn` source defaults are engineering rules of thumb. The
  numbers above will shift if a particular event uses an isolated
  (IT) genset or differently-built flex; the *directions* (greedy
  > round-robin, balanced < asymmetric on worst-drop, some cables
  see meaningful neutral current) are robust, the absolute values
  are not calibrated.
- **What the 2026 grid was actually wired as.** The greedy plan we
  ran is a synthetic phase assignment, not a measurement. It is a
  *plausible* assignment with the right structure to expose the
  mechanisms; it is not a reconstruction of what the
  electricians did. A historical reconstruction (doc 10
  Strategy A) would replace it.
- **A spec verdict on `cable_15`.** It is over rating *on the
  neutral* under this phase plan at 0.5× usage. That is enough to
  flag, not enough to condemn the cable — a different plan, or a
  measurement of actual usage at the load, could put it back inside
  rating. The point is that without `runpp_3ph` the question was
  invisible.

## Headlines

1. **Balanced `runpp` is optimistic, sometimes catastrophically so.**
   On this fixture at full nameplate it converges to 21.7 % worst
   drop; the asymmetric solve says the grid has no operating point
   at all. At 0.5× it under-states the worst drop by ~2.2×.
2. **Phase strategy matters for convergence, not for drop.** Greedy
   wins one scale step of margin over round-robin and lower worst
   drops, but neither comes close to 5 %. Cable sizing is the only
   lever that does (doc 11).
3. **Neutral current can put a cable over rating even when its phase
   loading is fine.** `cable_15` is the first concrete example we
   have of the cable-spec question doc 10 raised. The number that
   answers it does not exist in any other tool we have.
4. **Generator-leg balance is decoupled from downstream unbalance.**
   Greedy gets the generator to 0.05 % unbalance; individual loads
   downstream see 3+ %. Reporting only the generator number would
   misrepresent what the grid does at the socket.
