# Why nopywer's tree walk and pandapower's AC flow disagree

A walkthrough of the physics behind the divergence captured in
`tests/test_pp_interop_comparison.py` (and quantified in
[`07_optimiser_validation_findings.md`](./07_optimiser_validation_findings.md)).

The headline finding from the comparison tests:

| Fixture | nopywer | pandapower | direction |
|---|---:|---:|---|
| `analyze_named_generator` (small balanced) | 0.22 % | 0.19 % | parity |
| `analyze_input` (unbalanced single-phase) | 8.13 % at load_b | 3.12 % | nopywer **over-states** |
| `input_nodes` optimised (high-stress balanced) | 26.9 % at glitch | 39.1 % | nopywer **under-states** |

The disagreement is **not one-directional**. Two different
simplifications, one in each tool, pull in opposite directions. To
see why, a small amount of power-systems theory is needed.

## Power theory primer — just enough to read the rest

Festival LV is **400 V three-phase, 50 Hz, four-wire**: three phase
conductors L1 / L2 / L3 plus a neutral N.

```
          L1 ────┐
                 │
          L2 ────┼──── 400 V line-to-line  (V_LL)
                 │
          L3 ────┘
                 │
                 │     230 V line-to-neutral  (V_PN)
                 │     ( = V_LL / √3 )
                 │
          N  ────┘
```

One physical wire bundle, two conventions:

- **Single-phase loads** (lighting, sound, sockets) connect L1–N
  (or L2–N or L3–N) and see 230 V. nopywer's `V0 = 230` is this.
- **Three-phase loads** (motors, big distros) connect across all
  three phases and see 400 V between any two of them. pandapower's
  bus voltage `vn_kv = 0.4` is this.

The √3 ratio between them is where almost every interop bug hides.

Three-phase real power for a balanced load:

```
        P  =  √3 · V_LL · I · cos φ
           =   3 · V_PN · I · cos φ
```

Two equivalent forms. `cos φ` is the **power factor** — 1 for a pure
resistor (lights), ~0.7 for inductive loads (motors, transformers),
even lower for switch-mode PSUs. nopywer hardcodes `PF = 0.9`.

Voltage drop across a cable, to first order, is just Ohm's law:

```
        ΔV  =  I · R         (resistive cable, X ≈ 0)
```

That's the equation nopywer's tree walk uses. The full physics has
an `I · X` term too (reactance), and `I` is itself complex
(real + imaginary), so the actual scalar drop is `|I| · |Z|` where
`Z = R + jX`. Pandapower solves the full thing.

## Three load models — the ZIP

A load doesn't have a single "current". The current it draws depends
on the voltage it's currently seeing. Three idealised behaviours:

```
  Constant-Z (impedance):  I = V/Z       like a resistor — V drops, I drops linearly
  Constant-I (current):    I = I_rated   like a current source — I never moves
  Constant-P (power):      I = P/V       like a regulated PSU — V drops, I RISES
```

Real loads are mostly P (electronics with switch-mode PSUs auto-
regulate to maintain power), partly I, partly Z. The ZIP model
mixes all three. Pandapower's `pp.create_load` defaults to
**constant-P**.

**nopywer's tree walk is implicitly a constant-current model.** It
computes `I = P / V0 / PF` once at nominal voltage and uses that
current to derive `ΔV = R · I`. The current never updates when the
local voltage drops. This is one of the two key simplifications.

## What the tree walk actually does

```
Step 1: cumulate power  (leaves → root)
        Each cable's "cumulative power" is the sum of all loads
        downstream of it, kept as a 3-element [P_L1, P_L2, P_L3]
        array.

Step 2: derive current per phase
        I_per_phase = cum_power / V0 / PF
        (uses NOMINAL V0, not the local V — this is the
         constant-I shortcut)

Step 3: voltage drop  (root → leaves)
        For each cable:
            ΔV_cable = R_cable · max(I_per_phase)   ← takes the
                                                      WORST phase
            V_child  = V_parent − ΔV_cable
```

Two shortcuts here.

**Shortcut A — `V0` instead of local V.** Computes current as if
every load saw a perfect 230 V regardless of what's actually
arriving. For loads near the generator with small drops, fine. For
loads downstream where the local voltage has already dropped to
(say) 200 V, the real load draws *more* current to maintain its
rated power, but the tree walk doesn't know.

**Shortcut B — `max(I_per_phase)` for the whole cable.** Even if
only L2 is heavily loaded, nopywer applies the L2 drop to *everyone*
on the cable. This is conservative — overestimates how much voltage
has been lost — but treats the four-wire cable as if all three
phases drop together. In a real four-wire system the lightly-loaded
phases don't drop nearly as much, and downstream loads on those
phases see almost no impact.

Both shortcuts make the tree walk **a single pass** with no
iteration. That's what makes it microsecond-fast — and what creates
the disagreement with AC.

## What pandapower's `runpp` does

```
Build admittance matrix Y for the full network
Guess voltages V₀ = 1.0 p.u. everywhere
Newton-Raphson loop:
    given V, compute power injections   S = V · (Y·V)*
    residual = S − S_specified_by_loads_and_generators
    Δ = J⁻¹ · residual            (J = Jacobian)
    V ← V + Δ
    iterate until |Δ| < tol
```

It iterates to a self-consistent equilibrium where every load is
drawing **its specified P at its actual local V**. No shortcuts. The
constant-P load model means current rises as V falls, the falling V
makes more current, more current makes more drop — and the NR
iteration finds the fixed point.

For balanced 3-phase, `runpp` does this in the positive-sequence
per-phase frame — one phase per bus, the other two assumed
symmetric. That's faster than the full three-phase asymmetric solve
(`runpp_3ph`) but loses the imbalance information. **Our
`to_pandapower` collapses unbalanced single-phase loads to balanced**
— an L1-only 3 kW load becomes 1 kW on each of L1, L2, L3. This is
the matching simplification on the pandapower side.

## Mechanism 1 — small balanced load: tree walk and AC agree

`analyze_named_generator.geojson`: 1 kW unphased load, 10 m of
2.5 mm² cable.

In numbers:
- power split balanced → `power_per_phase = [333, 333, 333]` W
- per-phase current: `333 / 230 / 0.9 ≈ 1.61 A`
- cable R: `(1/26) × 20 / 2.5 ≈ 0.31 Ω` (length includes 10 m
  `EXTRA_CABLE_LENGTH_M` slack)
- ΔV: `0.31 × 1.61 ≈ 0.5 V`

Both shortcuts are inactive:

- **Constant-current vs constant-power doesn't matter at 0.5 V drop.**
  V at the load is 229.5 V vs nominal 230 V. The constant-P load
  wants 333 W, so its current is `333 / 229.5 / 0.9 ≈ 1.611 A` vs
  the tree walk's `333 / 230 / 0.9 ≈ 1.610 A`. Difference at the 4th
  decimal. Negligible.
- **Max-phase doesn't matter for balanced loads.** All three phases
  carry the same current, so `max(I_per_phase) == mean(I_per_phase)`.
  The tree walk's "worst phase" rule degenerates to the right answer.

Result: tree walk says 0.22 %, AC says 0.19 %, Δ = 0.03 %. Both
tools agree because **the regime is too benign to expose any of
the simplifications**.

This test is the **conversion-correctness check**. A real bug in
`to_pandapower` (wrong voltage convention, wrong R formula, wrong
unit anywhere) would show up here. It passes — so we know the
conversion is faithful, and any divergence elsewhere is real
physics.

## Mechanism 2 — unbalanced single-phase: tree walk over-states

`analyze_input.geojson`:

```
generator ── cable_0 (20 m, 2.5 mm²) ── load_a (3 kW on L1)
                                     ── cable_1 (22 m) ── load_b (6 kW on L2)
```

**What nopywer sees** — power_per_phase cumulates as a 3-vector,
keeping the phase assignment:

```
load_a:    [3000,    0,    0]
load_b:    [   0, 6000,    0]
cable_1:   [   0, 6000,    0]   →  I = [   0, 28.99,    0] A   →  max = 28.99 A
cable_0:   [3000, 6000,    0]   →  I = [14.49, 28.99,    0] A   →  max = 28.99 A

ΔV cable_0:  R × max(I) = 0.308 × 28.99 ≈ 8.93 V
ΔV cable_1:                0.339 × 28.99 ≈ 9.83 V

V at load_b = 230 − 8.93 − 9.83 = 211.24 V    →  drop 8.13 %
```

In nopywer's world, load_b is at 211 V — way past the 5 %
NF C 15-100 limit. Conservative by design.

**What pandapower sees** — single-phase loads collapsed to balanced:

```
9 kW total, balanced → 3 kW on each of L1, L2, L3

cable_0: 9 kW total → per-phase line current = 9000 / (√3 × 400 × 0.9) ≈ 14.4 A
cable_1: 6 kW       → ~ 9.6 A
                                 ↑
                  (NB: √3·V_LL not V_PN because pandapower works in L-L)

ΔV per phase at cable_0:  0.308 × 14.4 ≈ 4.4 V    (per phase P-N)
V at load_b ≈ 230 − 4.4 − 3.3 ≈ 222.3 V          →  drop 3.12 %
```

Pandapower says load_b is at 222 V — comfortably under the 5 %
limit.

**Why so different?** Two opposing effects:

1. nopywer's `max(I_per_phase)` **overstates** the drop on the
   lightly-loaded phases. In the real four-wire cable, L2 carries
   29 A and drops a lot, L1 carries 14 A and drops half as much,
   L3 carries nothing and drops nothing. nopywer paints all three
   with the L2 brush.

2. pandapower's balanced collapse **understates** the drop on the
   heavily-loaded phase. By averaging the 6 kW load across three
   phases, the L2 wire only "sees" 1/3 of its real burden.

**Neither model is fully right.** The truth is in between, and
you'd need `runpp_3ph` with `asymmetric_load` to get it. For now:

- nopywer's number is the **safe** one for sizing decisions (it's
  conservative on the worst phase).
- pandapower's number is a useful sanity check for "will the
  average node be near nominal", but understates risk on the
  loaded phase.

This is the regime where nopywer's festival heuristic actually
beats pandapower's standard balanced flow, *if* you accept the
conservatism.

## Mechanism 3 — high-drop balanced: tree walk under-states

The optimised 2025 fixture: 51 nodes, the worst-stressed node
`glitch` is many cables deep from the generator. Loads are mixed
but the optimiser produces a layout where each cable carries near
its tier capacity.

**What nopywer sees** — cable currents computed at nominal V0
(= 230 V) **once**. ΔV stacks linearly from generator to leaf.
Reports 26.9 % drop at glitch — meaning V_glitch = `230 × 0.731 =
168 V`.

**What pandapower sees** — same topology, same cable resistances,
but it **iterates**:

```
Iteration 0: assume V = 1.0 p.u. everywhere. Compute currents.
             Compute drops. New V at glitch ≈ 0.73 p.u. (≈ tree walk).

Iteration 1: at V = 0.73 p.u., the constant-P load at glitch wants
             1/0.73 = 1.37× more current to maintain its rated P.
             More current → more drop everywhere upstream.
             New V at glitch drops to ≈ 0.65 p.u.

Iteration 2: at V = 0.65 p.u., even more current, even more drop.
             V drops to ≈ 0.62 p.u.

...converges around V = 0.609 p.u. = 140 V    →  drop 39 %.
```

Pandapower says glitch is at 140 V — light bulbs flicker, motors
stall, switch-mode PSUs trip. The tree walk reported 168 V —
already alarming but understating the actual situation.

**This is the load-feedback loop:**

```
       V at load drops below nominal
                  ↓
       Constant-P load: P = V · I = const
                  ↓
       I must rise to keep P
                  ↓
       More I × same R = more upstream drop
                  ↓
       V at load drops further ──────┐
                  ↑                  │
                  └──────────────────┘
```

The tree walk is blind to this because it computes I once and
stops. It reports the *first iteration* answer, which is always
optimistic in the high-drop regime.

The conservative `RHO_COPPER = 1/26` (≈ 2.2× textbook copper)
doesn't compensate, because the missing physics is not the
resistance value — it's the missing iteration.

## Why the two errors pull opposite ways

```
                tree walk      pandapower    physical truth
                              (balanced
                               collapse)
                ────────       ──────────    ──────────────
unbalanced
single-phase    HIGH drop      LOW drop      somewhere between
                (max-phase     (averages
                 rule)          load)

high-stress
balanced        LOW drop       HIGH drop     pandapower's right
                (constant-I    (constant-P    (loads really do
                 shortcut)      iteration)     pull more current
                                               at low V)
```

The two simplifications happen at different layers:

- **Max-phase** is a conservative *phase-frame* approximation —
  captures the safety-of-sizing concern but ignores that the
  four-wire cable doesn't drop uniformly across phases.
- **Constant-I** is an optimistic *load-model* approximation —
  captures the simple-Ohm's-law concern but ignores that real
  loads regulate themselves in response to voltage.

For a small balanced load (mechanism 1), neither bites and they
agree. For unbalanced single-phase loads (mechanism 2), max-phase
dominates and tree walk over-states. For high-stress balanced
loads (mechanism 3), constant-I dominates and tree walk
under-states.

## Practical takeaway

The tree walk is the **right tool** when:

- many small single-phase loads (typical at the small-distro level),
- and you want a **conservative** cable-sizing estimate.

It's the **wrong tool** when:

- a long radial trunk feeds heavy balanced loads (sound stage,
  kitchen tent, ice plant),
- and the drop is large enough that constant-power feedback matters.

The 2025 fixture is the second case — and the AC validation is
what reveals it.

## The right long-term fix

`runpp_3ph` with `asymmetric_load` — opportunity §3 in
[`06_extended_opportunities.md`](./06_extended_opportunities.md).
That solver:

- Models unbalanced single-phase loads as their actual single-phase
  selves on L1/L2/L3 with a separate neutral conductor.
- Iterates the constant-P feedback so high-drop nodes converge to
  the true equilibrium V.

Both errors would go away, in both directions, simultaneously. The
conversion already exists; it's the load-creation step that needs
an asymmetric variant. The cost is having to populate
zero-sequence cable parameters (typical defaults documented in
config), and `runpp_3ph` is more sensitive to convergence than
balanced `runpp`.
