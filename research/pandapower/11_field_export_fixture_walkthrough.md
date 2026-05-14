# Plugging a field-export GeoJSON into the pandapower code

[`10_three_phase_asymmetric_modelling.md`](./10_three_phase_asymmetric_modelling.md)
ended on an open question: would `runpp_3ph` even converge on a
2025-scale fixture, and is round-robin phase synthesis meaningful
enough to compare against? Before we can answer that we need a
real grid to point it at. Martin supplied one —
[`tests/fixtures/2026-05-14_martin.geojson`](../../tests/fixtures/2026-05-14_martin.geojson),
"this year's east grid with some loads made up, some real" — and
asked the obvious question: **how do I plug this into the existing
pandapower code to run it?**

This doc answers that. It turns out there are two gaps in the way,
one trivial and one not.

## What the file actually is

It is a **plugin *export*, not a plugin *input*.** 52 features:
26 loads, 1 generator, 25 cables. Every feature already carries
*computed* fields — `current_a`, `cum_power_kw`, `vdrop_volts` on
cables; `voltage`, `vdrop_percent`, `cum_power`, `distro` on
points. Those are nopywer outputs written back into the GeoJSON,
not inputs.

That matters because the export schema and the input schema
`io.load_geojson` expects are **not the same**:

| Quantity        | Export key (this file) | `io.load_geojson` reads |
|-----------------|------------------------|-------------------------|
| Cable CSA       | `area_mm2`             | `area`                  |
| Plug rating     | `plugs_and_sockets_a`  | `plugs&sockets`         |
| Cable length    | `length_m`             | `length`                |
| Load power      | `power`                | `power` ✓               |
| Node name       | `name`                 | `name` ✓                |
| Phase           | *(absent)*             | `phase`                 |

`io.load_geojson` does not error on the unknown keys — it just
falls back to defaults. Probed directly:

```
load_geojson('2026-05-14_martin.geojson')
  -> 27 nodes, 25 cables
  sample cable: area_mm2 = 2.5   (default — real value 6.0 ignored)
                plugs    = 16.0  (default — real value 32.0 ignored)
```

So the file **loads silently and wrongly**: every cable comes in
as 2.5 mm² / 16 A regardless of what the export says. The cable
topology, on the other hand, survives fine — `io.load_geojson`
ignores the export's explicit `from`/`to`/`nodes` and snaps by
coordinate proximity instead (`analyze._snap_cables_to_nodes`,
within `CONNECTION_THRESHOLD_M`). All 25 cables snap to two nodes;
`analyze` builds the tree without complaint and reports 88.3 kW at
the generator.

### Gap 1 — schema translation (trivial)

Either rename the keys on the way in, or teach `io.load_geojson`
to accept both spellings. A one-shot remap is five lines:

```python
fc = json.load(open("2026-05-14_martin.geojson"))
for f in fc["features"]:
    p = f["properties"]
    for export_key, input_key in (
        ("area_mm2", "area"),
        ("plugs_and_sockets_a", "plugs&sockets"),
        ("length_m", "length"),
    ):
        if export_key in p:
            p[input_key] = p[export_key]
nodes, cables = load_geojson(fc)   # load_geojson accepts a dict
```

The cleaner fix is to make `io.load_geojson` read `props.get("area")
or props.get("area_mm2")` etc., so a round-tripped export loads
correctly without a pre-pass. That belongs in `io.py`, not in
every caller. Worth doing — exports round-tripping back as inputs
is going to keep happening.

## Gap 2 — the grid does not have an AC solution

With the schema fixed (real 6 mm² / 32 A cables), the balanced
path is exactly what doc 06/07 already built:

```python
from nopywer import analyze, pp_interop
grid = PowerGrid(nodes=nodes, cables=cables)
analyze._snap_cables_to_nodes(grid)
analyze.analyze(grid)
ppg = pp_interop.to_pandapower(grid)
res = pp_interop.compute_power_flow(ppg)          # <-- LoadflowNotConverged
diff = pp_interop.compare_with_tree_walk(grid)
```

`pp.runpp` **does not converge** on this fixture — not with the
defaulted cables, and not with the corrected ones either. This is
not a bug in the converter. It is the constant-power feedback
mechanism from
[`08_why_tree_walk_and_ac_disagree.md`](./08_why_tree_walk_and_ac_disagree.md)
taken to its limit: the fixture's own exported `vdrop_percent`
values run as high as **56 %** (nodes sitting at ~101 V on a 230 V
nominal). A constant-power load draws *more* current as its
voltage sags, which sags it further. Past the nose of the P–V
curve there is simply no fixed point for Newton-Raphson to find.

Scaling every load down confirms it is load-magnitude driven, not
numerical:

| Load scale | Generator total | `runpp` result        | min bus voltage |
|-----------:|----------------:|-----------------------|----------------:|
| 1.0        | 88.3 kW         | **did not converge**  | —               |
| 0.5        | 44.1 kW         | converged             | 0.66 pu         |
| 0.3        | 26.5 kW         | converged             | 0.84 pu         |
| 0.2        | 17.7 kW         | converged             | 0.90 pu         |

Even at half load the worst bus is at 0.66 pu — a 34 % drop, well
past anything a real festival grid would tolerate. The grid as
exported is not a borderline case; it is deep in the
non-physical region.

This is itself a **finding**, and arguably the most useful one for
Martin and Vincent:

- **nopywer's tree walk still produces numbers here** (88.3 kW,
  vdrops up to 56 %) because it is an explicit forward pass — it
  never has to converge anything. It will happily report a grid
  that cannot physically exist.
- **pandapower refusing to converge is the correct answer.** "No
  AC solution" is real information: this grid needs bigger cable,
  shorter runs, or a closer generator before any phase-balancing
  question is even worth asking.
- It also re-frames doc 10's open question. Running `runpp_3ph` on
  *this* fixture as-is is pointless — if the balanced solver can't
  find a fixed point, the asymmetric one certainly won't. The
  3-phase work needs a fixture that converges balanced first.

## So: how to plug it in

For Martin, concretely:

1. **Translate the schema.** Five-line key remap above, or the
   `io.py` fix. Without this the cables are silently wrong.
2. **Run the balanced path first** — `to_pandapower` →
   `compute_power_flow`. On this fixture it will raise
   `LoadflowNotConverged`. That is the headline result, not an
   error to work around.
3. **To get past non-convergence**, the grid has to be made
   physical first: scale the made-up loads down to realistic
   values, or fix the under-sized cable runs. At ~0.2× it
   converges with sane voltages and `compare_with_tree_walk`
   becomes meaningful.
4. **Phase assignment is still absent.** Every node in this export
   has `phase = None` — Martin's note that the phase work went
   "without great results" is borne out; none of it made it into
   the file. So the asymmetric `runpp_3ph` path from doc 10 has no
   real data to chew on here either. Round-robin synthesis
   (Strategy B) remains the only option, and only once the grid
   converges balanced.

## Worked example: making the grid converge

`tests/fixtures/2026-05-14_martin_modified.geojson` is an editable
copy used to test the "fix the under-sized runs" path from step 3
above. The exercise: resize cables one at a time and watch where
the bottleneck moves.

**Tracing the worst bus.** At 0.5× load (where the original
converges), the worst bus is `jamhouse` at 0.66 pu. Walking its
path back to the generator, one cable dominates: `cable_23`, the
`generator → distro1` trunk — 2.5 mm² flex (16 A rated) carrying
45 A, ~55 V of drop on that segment alone. It feeds the entire
`distro1` subtree: 15 loads, 38.8 kW, with `curious creatures`
(10 kW) the single biggest lump. The trunk is on the *thinnest*
cable type in nopywer's catalogue while carrying a third of the
grid.

**Resizing, one cable at a time.** nopywer's catalogue has exactly
one single-phase type (`Cable16A`, 2.5 mm²); everything bigger
(32/63/125 A) is three-phase. So any trunk fix is also a
1-phase → 3-phase change. Iterating on the modified fixture at
*full* load:

| Change | Result |
|---|---|
| baseline (export as-is) | no AC solution |
| `cable_23` trunk → 125 A 3P | still no solution; converges at 0.6–0.7× |
| `cable_3` (GoJ feed) → 32 A 3P | **converges**, vmin 0.576 (`garden of joy`) |
| `cable_3` → 63 A 3P | vmin 0.707, worst bus → `desert dessert` |
| `cable_1` (other gen trunk) → 125 A 3P | vmin 0.779, worst bus → `jamhouse` |
| `cable_2` (CC feed) → 32 A 3P | vmin 0.783, two cables left ~1.0× rating |

**Worst voltage drop across both axes.** Sweeping each cable
config against the reduced-power scales gives the full picture —
each cell is the max bus voltage drop (`1 − vmin`); "—" is no AC
solution at all:

| Cable config | 1× | 0.7× | 0.6× | 0.5× | 0.3× |
|---|---|---|---|---|---|
| S0  original (most 2.5 mm²)     | — | —    | —    | 34 % | 16 % |
| S1  +`cable_23`→125 A           | — | 44 % | 30 % | 23 % | 12 % |
| S2  +`cable_3`→32 A             | 42 % | 22 % | 18 % | 14 % | 8 % |
| S3  `cable_3`→63 A              | 29 % | 18 % | 15 % | 12 % | 7 % |
| S4  +`cable_1`→125 A            | 22 % | 14 % | 12 % | 10 % | 5 % |
| S5  +`cable_2`→32 A             | 22 % | 14 % | 12 % | 10 % | 5 % |

Two things stand out. First, **cable resizing and load reduction
buy roughly the same thing** — S1 at 0.5× and S0 at 0.3× both land
near a 12–16 % drop; you can trade one for the other. Second,
**even the fully-resized grid (S5) only reaches 22 % drop at full
load** — better than "no solution", still 4× over the 5 % NF C
15-100 threshold. Convergence is a low bar; spec compliance is a
much higher one, and these five cable swaps do not clear it. S5
only meets 5 % at 0.3× load. (S5 matches S4 because `cable_2` was
never the binding constraint — that swap was a *type* correction,
not a capacity one; see below.)

The pattern is the whole point: **every fix exposes the
next-thinnest segment.** The worst bus hops `garden of joy` →
`desert dessert` → `jamhouse` as each bottleneck is cleared. This
is not a one-cable problem — 21 of the 25 cables are 2.5 mm². Going
from "no solution" to "converges, two cables marginally over" took
four targeted resizes, and getting fully within the 5 % drop
threshold would need a systematic `pick_cable_for`-against-actual-
current pass over every cable, not worst-bus whack-a-mole.

**Asymmetric loads need multi-core cable.** `curious creatures`
was re-modelled as a genuine two-phase load (5 kW on L1, 5 kW on
L2) via the new list-valued `phase` support — `phase: [1, 2]`
splits power evenly across the listed legs. That immediately
surfaced a modelling error the balanced view hid: its feed
`cable_2` was a *1-phase* cable, which physically cannot carry two
phases regardless of rating. It is not "underrated", it is the
wrong type. The fix is the smallest 3-phase cable
(`Cable32A`, 6 mm²) — each live leg pulls ~24 A, under the 32 A
rating, with the unused L3 core idle. The lesson for the doc 10
`runpp_3ph` work: per-load phase assignment and cable *type* are
coupled — assigning phases can invalidate the cable feeding the
load.

## What this changes upstream

Carrying back into the codebase rather than leaving as research
notes:

- **`io.load_geojson` now accepts the export schema** (done —
  `_EXPORT_KEY_ALIASES` maps `area_mm2`/`plugs_and_sockets_a`/
  `length_m` onto the input-schema keys) **and list-valued
  `phase`** for multi-phase loads. Exports round-tripping as
  inputs is a normal workflow; the old silent-default behaviour
  was a trap.
- **The `LoadflowNotConverged` path needs a deliberate story.**
  Right now `compute_power_flow` lets pandapower's exception
  propagate raw. For a planning tool, "this grid has no AC
  solution — your worst node is past voltage collapse" is a
  *result* worth surfacing cleanly, not a stack trace. This is a
  natural companion to the doc 10 work, not a blocker for it.

## Where it slots in

Same branch story as doc 10 (`feat/pandapower-runpp-3ph` off the
current PR stack). The `io.py` schema fix is independent and
small enough to land on its own. The non-convergence handling
belongs alongside `_powerflow.py`. None of it touches the
converter or the short-circuit module.
