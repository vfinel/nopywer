# Three-phase asymmetric modelling — what would it take?

The single biggest source of disagreement between nopywer's tree
walk and our pandapower converter is **mechanism 2**: unbalanced
single-phase loads. Captured in detail in
[`08_why_tree_walk_and_ac_disagree.md`](./08_why_tree_walk_and_ac_disagree.md);
the short version is that nopywer's `max(I_per_phase)` rule
*over*-states drop on lightly-loaded phases, and our converter's
balanced-load collapse *under*-states it on heavily-loaded ones.
Both are wrong, in opposite directions. Neither tool models the
neutral conductor at all.

The right fix is `pp.runpp_3ph` with `pp.create_asymmetric_load`,
listed as opportunity §3 in
[`06_extended_opportunities.md`](./06_extended_opportunities.md).
This doc is the detailed shopping list for that fix: what data
pandapower needs, what's already in the existing fixtures, what's
missing, and how much work it is to bridge the gap.

## What pandapower's `runpp_3ph` needs

Three categories of input that the current converter either
discards or doesn't see at all.

### 1. Per-load phase assignment

Each single-phase load needs to declare which of L1, L2, L3 it
connects to. Three cases pandapower distinguishes:

```python
# Single-phase on L1 only:
pp.create_asymmetric_load(
    net, bus=..., p_a_mw=p, p_b_mw=0, p_c_mw=0,
)

# Three-phase balanced (motor, 3P distro):
pp.create_load(net, bus=..., p_mw=p)        # what we use today

# Three-phase unbalanced (rare in practice):
pp.create_asymmetric_load(
    net, bus=..., p_a_mw=p1, p_b_mw=p2, p_c_mw=p3,
)
```

nopywer's `PowerNode.phase` already carries this:

- `1`, `2`, `3` → single-phase load on L1/L2/L3
- `None` → balanced (or "to be assigned later")
- non-numeric values → legacy annotations with no pandapower equivalent;
  treat them as unassigned for three-phase modelling

So the per-load phase information **already exists in nopywer's
data model**. The question is whether it's populated in the
fixtures we want to validate against.

### 2. Per-cable zero-sequence parameters

Pandapower's `r_ohm_per_km`, `x_ohm_per_km`, `c_nf_per_km` are
**positive-sequence** values — they describe what current sees in
the symmetric balanced case. Asymmetric flow also needs
**zero-sequence** equivalents:

```python
pp.create_line_from_parameters(
    net, ...,
    r_ohm_per_km=...,    r0_ohm_per_km=...,   # zero-sequence R
    x_ohm_per_km=...,    x0_ohm_per_km=...,   # zero-sequence X
    c_nf_per_km=...,     c0_nf_per_km=...,    # zero-sequence C
)
```

The zero-sequence params describe how the cable behaves to **the
imbalance current returning through the neutral and earth**. They
have no nopywer analogue (the tree walk doesn't model neutral at
all) and aren't on cable spec sheets for festival flex (HO7RN-F,
Titanex). Engineering rule-of-thumb defaults for 4-core LV flex
with full-section neutral:

```
   r0 / r1  ≈  3 to 5     (neutral-and-earth return path R is ~4× phase R)
   x0 / x1  ≈  3 to 5     (loop area of zero-sequence path is bigger)
```

These would live as **global defaults in `pp_interop/config.py`**,
the same way `X_OHM_PER_KM = 0.08` is today. Future per-cable
overrides could come from telemetry calibration (PR #12 work) or
direct measurement.

### 3. Source vector group and zero-sequence impedance

The festival generator's neutral handling determines whether the
zero-sequence current can flow back through the source:

```python
# Today (balanced runpp):
pp.create_ext_grid(
    net, bus=..., vm_pu=1.0, s_sc_max_mva=..., rx_max=...,
)

# For runpp_3ph, additionally:
pp.create_ext_grid(
    net, bus=..., ...,
    x0x_max=...,      # ratio X0 / X1 for source
    r0x0_max=...,     # ratio R0 / X0 for source
)
```

Most festival diesel gen-sets are **TN-S star with grounded
neutral** (Yn). The neutral provides a return path for
zero-sequence current. Typical defaults:

```
   x0x_max  ≈  1.0
   r0x0_max ≈  0.1
```

Some hire kit is **IT** (isolated neutral) — no zero-sequence
return at all, very different fault behaviour. A
`SOURCE_NEUTRAL_GROUNDING` flag in config would let the planner
override.

## Does the existing fixture contain the info?

Two production fixtures, two stories.

### `tests/fixtures/input_nodes.geojson` — the 2025 production fixture

**Probed it directly:**

```
Total features: 54
Property keys observed: ['name', 'power', 'type']
Phase histogram:
  phase=None      n=54
```

Every node has `phase=None`. `io.load_geojson` then splits each
load evenly across the three phases (`power_per_phase += power/3`),
making every load **balanced by default**.

So the 2025 fixture is **modelled balanced not because the festival
was balanced** but because **the design document was created
before phase assignment was decided**. In reality those 51 loads
would each be wired to one specific phase at deployment.

**Implication**: validating runpp_3ph against this fixture as-is
would tell us nothing new — every load is balanced, so the
asymmetric and balanced solvers should agree. The fixture has to
be enriched (see below) before it can exercise the asymmetric
path meaningfully.

### `tests/fixtures/analyze_input.geojson` — the small synthetic

**Phase info is there:**

```json
{ "name": "Load A", "power": 3000.0, "phase": 1 }
{ "name": "Load B", "power": 6000.0, "phase": 2 }
```

This fixture could be modelled three-phase **directly today**.
It's exactly the fixture that exposed mechanism 2 (the unbalanced
single-phase divergence in
[`08_why_tree_walk_and_ac_disagree.md`](./08_why_tree_walk_and_ac_disagree.md))
and is the natural first target for `runpp_3ph` validation.

### What's in NO fixture

- Zero-sequence cable parameters. None of the GeoJSON properties
  carry cable type beyond `area` and `plugs&sockets`.
- Source vector group / earthing scheme. The generator is just
  a Point with `power=0`.
- Per-load *measured* phase (vs *designed* phase). Festival
  electricians sometimes deviate from the plan based on what's
  available on site.

These gaps are filled by **assumed defaults in
`pp_interop/config.py`** rather than per-feature properties.
Same pattern as `X_OHM_PER_KM = 0.08` today — global, configurable,
documented.

## Filling in the missing per-load phase

The 2025 fixture has 54 nodes with no phase assignment. Three
strategies for adding phase data, ordered from realistic to
worst-case:

### Strategy A — historical reconstruction

Go back to the 2025 event records (deployed phase plan, electrician's
notes, distro labels) and add `phase: 1`/`2`/`3` to each load.
Most realistic — captures what the real grid looked like — but
requires field knowledge that lives outside the codebase.

### Strategy B — round-robin synthesis

Assign phase by node order: `phase = (i % 3) + 1`. Sequence the
54 loads cyclically across L1, L2, L3. Approximates what a
careful planner would do (alternate phases as you go down a
corridor) and produces a roughly balanced grid.

```python
for i, (name, node) in enumerate(grid.nodes.items()):
    if not node.is_generator:
        node.phase = (i % 3) + 1
```

Realistic enough for testing; fully reproducible. **My
recommendation as the default.**

### Strategy C — worst-case stress

Assign every load to `phase=1`. Maximises imbalance — useful as
a stress test for the solver and for showing "this is what bad
phase planning looks like". A planner who runs this on a real
fixture and sees catastrophic neutral currents has empirical
evidence for why phase balancing matters.

## Implementation shopping list

Rough estimate of the work, in three layers:

### Layer 1 — Data / fixtures

- `analyze_input.geojson` — already has `phase` on each load. **No work.**
- `input_nodes.geojson` — needs phase assignment. **Strategy B (round-robin)
  via a one-shot script** is the cheapest realistic option. ~5 lines.
- New synthetic fixtures specifically for asymmetric stress (e.g. all
  loads on L1) could live alongside the existing tests. ~30 lines per
  fixture.

### Layer 2 — Config defaults

Add to `pp_interop/config.py`:

```python
# === Three-phase asymmetric flow ===

# Zero-sequence cable parameter ratios. Typical for 4-core LV flex
# with full-section neutral.
R0_OVER_R1 = 4.0
X0_OVER_X1 = 4.0

# Source neutral grounding. Most festival diesel gen-sets are
# TN-S with solidly grounded star (Yn).
SOURCE_X0X_MAX = 1.0
SOURCE_R0X0_MAX = 0.1
```

### Layer 3 — Code

In `pp_interop/_conversion.py`, branch on `node.phase`:

```python
for name, node in grid.nodes.items():
    if node.is_generator or node.power_watts <= 0:
        continue
    p_mw = node.power_watts / 1e6
    q_mvar = p_mw * tan_phi

    if isinstance(node.phase, int) and 1 <= node.phase <= 3:
        # Asymmetric: all power on one phase
        p_a, p_b, p_c = (p_mw if node.phase == i + 1 else 0.0 for i in range(3))
        q_a, q_b, q_c = (q_mvar if node.phase == i + 1 else 0.0 for i in range(3))
        pp.create_asymmetric_load(
            net, bus=..., p_a_mw=p_a, p_b_mw=p_b, p_c_mw=p_c,
            q_a_mvar=q_a, q_b_mvar=q_b, q_c_mvar=q_c,
        )
    else:
        # Truly balanced (or unphased — assumed balanced)
        pp.create_load(net, bus=..., p_mw=p_mw, q_mvar=q_mvar)
```

Plus the `r0/x0` params on every line, `x0x_max/r0x0_max` on the
ext_grid, and a new entry point `compute_power_flow_3ph(pp_grid)`
that calls `pp.runpp_3ph` instead of `runpp`.

### Scope summary

| Layer | Lines |
|---|---:|
| Add phase to `analyze_input.geojson` (already done) | 0 |
| Round-robin phase synthesis script for `input_nodes.geojson` | ~5 |
| New config defaults (zero-sequence + source vector group) | ~10 |
| Branch on phase in `_conversion.py` | ~30 |
| New `compute_power_flow_3ph` function | ~50 |
| Tests (parity + comparison + topology), mirroring the existing balanced suite | ~150 |
| Findings doc (`11_runpp_3ph_findings.md`) | ~200 |

The biggest unknown is whether `runpp_3ph` converges cleanly on
the 2025-scale fixture (51 nodes) given its documented sensitivity,
and whether round-robin phase synthesis produces results meaningful
enough to compare against the historical balanced answer.

## What this would tell us

Three things we currently don't know:

### 1. The real shape of mechanism 2 at scale

On `analyze_input` (2 loads, 1 cable per load) it's a ~5 pp gap.
On `input_nodes` (51 loads, optimised tree) it could be anywhere
— and the gap shape is exactly what Vincent's been asking about
indirectly. Today we report only the balanced-flow numbers; the
asymmetric numbers might be very different.

### 2. Neutral currents per cable

Critical for **cable-spec decisions**: a `4G6` cable (4 cores
all 6 mm²) handles a fully-loaded neutral; a `3G6+½N` (reduced-
section neutral) does not. Currently no festival design tool I'm
aware of surfaces this. If round-robin phase synthesis + runpp_3ph
shows the worst neutral current is < 50 % of the worst phase
current, reduced-N cables are fine. If it shows neutral ≈ phase,
the planner needs full-section-N specs.

### 3. Whether nopywer's max-phase rule is actually conservative

The current assumption is "max-phase always over-states the worst
phase". For symmetric distributions and simple topologies that
holds. For specific bad phase distributions it might *under*-state
— if all the constant-power loads on the heavy phase pull each
other's voltage down through compounding feedback, the actual
worst-phase drop could exceed nopywer's first-pass estimate. The
only way to know is to measure with `runpp_3ph`.

## What this would NOT tell us

- **Whether the 2025 grid was actually unbalanced.** The fixture
  has no phase data. Round-robin synthesis is a *plausible*
  reconstruction, not a measurement.
- **What real zero-sequence cable parameters are.** The defaults
  are engineering rule-of-thumb; calibration would need
  measured-vs-modelled telemetry from a deployed event.
- **Whether the source neutral is actually grounded.** That's a
  hire-contract / electrician question, not a model question. The
  default assumption (`Yn`) covers most cases but isn't universal.

## Where it slots in

If pursued, this work would land as:

- A new branch off `feat/pandapower-comparison-tests` (the current
  PR stack head): `feat/pandapower-runpp-3ph`.
- A new module file `pp_interop/_powerflow_3ph.py` mirroring
  `_powerflow.py`'s shape.
- A new findings doc `11_runpp_3ph_findings.md` capturing the
  numbers — same register as
  [`07_optimiser_validation_findings.md`](./07_optimiser_validation_findings.md).
- Extension of `scripts/sensitivity_sweep.py` to add a fourth
  sweep over the new zero-sequence ratio defaults.

The conversion layer (`to_pandapower`) and short-circuit module
stay backward-compatible — `runpp_3ph` is purely additive.
