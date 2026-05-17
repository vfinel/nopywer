# Asymmetric three-phase modelling + per-load phase planning

## What this PR adds

A pandapower-backed **asymmetric three-phase power flow** path for
festival grids, with the **per-load phase planning** needed to feed
it. Five user-facing pieces:

1. **`io.load_geojson`** now accepts the round-tripped export schema
   (`area_mm2`, `length_m`, `plugs_and_sockets_a`) alongside the
   hand-authored input schema, and accepts list-valued `phase` for
   multi-phase loads (e.g. `[1, 2]` for a 2-leg load).
2. **`pp_interop/phases/`** — two phase-distribution strategies
   (greedy + round-robin) and a `phase_geojson` one-call wrapper for
   the `load → plan → apply → write` workflow.
3. **`pp_interop/_powerflow_3ph.py`** — `to_pandapower_3ph` and
   `compute_power_flow_3ph` for `runpp_3ph`. Returns a distinct
   `Pandapower3phGrid` type so the dual `pp.load` / `pp.asymmetric_load`
   layout is encoded in the type, not in a comment. Independent of
   the balanced converter — no shared state, no mutation.
4. **`PowerNode.to_geojson` emits `phase`** when non-`None`, so phase
   plans round-trip through the loader.
5. **Diagnostic logging** in `io` and `pp_interop` — legacy `"U"`/`"Y"`
   string phase markers and unknown-property-key typos now surface
   instead of being silently coerced.

## Why

`research/pandapower/10_three_phase_asymmetric_modelling.md` is the
motivation: nopywer's tree walk and the balanced `runpp` agree on a
balanced grid, but disagree exactly when balance matters (single-
phase loads piling onto one leg). The balanced solve averages the
imbalance away; the tree walk's `max(I_per_phase)` over-states
drop on lightly-loaded legs and under-states it on heavily-loaded
ones. Neither models the neutral conductor at all.

`runpp_3ph` is the right fix. It surfaces two quantities a balanced
solve structurally cannot:

- **per-leg voltage drop**, so loads on the heavy leg of an
  imbalanced grid are sized against the leg they actually sit on;
- **neutral-conductor current**, which decides whether a
  reduced-section-neutral cable (`3G6+½N`) is safe or the run needs
  full-section neutral (`4G6`).

Doc 12 (`12_runpp_3ph_findings.md`) is the first set of numbers from
this on the real 2026 east-grid fixture; the headline is that
balanced `runpp` is optimistic (~2.2× lower worst leg drop than
asymmetric at 0.5× usage), and that `cable_15` carries 20.4 A on its
neutral under the greedy phase plan, which would have been invisible
in any balanced analysis.

## How a reviewer can try it

**Phase a fixture** (load → plan → apply → write, one call):

```bash
uv sync --extra pandapower
uv run python -c '
from nopywer.pp_interop import config
from nopywer.pp_interop.phases import phase_geojson
phase_geojson(
    "tests/fixtures/2026-05-14_martin.geojson",
    "/tmp/martin_phased.geojson",
    usage_factor=config.DEFAULT_USAGE_FACTOR,
    strategy="greedy",
)
'
```

**Run the asymmetric solve** with a printable report:

```bash
# unphased fixture — solves like the balanced one
uv run python scripts/run_asymmetric.py \
    tests/fixtures/2026-05-14_martin_modified.geojson

# with phase planning — actually exercises runpp_3ph
uv run python scripts/run_asymmetric.py \
    tests/fixtures/2026-05-14_martin.geojson \
    --plan greedy --usage-factor 0.5
```

Reads the fixture, snaps cables, optionally plans phases, runs both
the balanced and asymmetric solves side-by-side, and prints the top
worst-leg voltage drops and worst-neutral cables.

## What I want a closer look at

Four modelling assumptions live inline and are operator-tunable. All
documented in `pp_interop/config.py` and `research/pandapower/`, but
worth flagging here:

- **`R0_OVER_R1 = X0_OVER_X1 = 4.0`** — rule-of-thumb default for
  4-/5-core LV flex with full-section neutral, TN-S earthing
  (genset star-point bond only). Every neutral-current number in
  doc 12 moves linearly with this. Multi-point N-PE bonding would
  drop it to ~2.5. See `config.py` and `research/pandapower/10.1` §
  "Picking `R0/R1` and `X0/X1` — what the ratios really mean".
- **`SOURCE_X0X_MAX = 1.0`, `SOURCE_R0X0_MAX = 0.1`** — assumes
  TN-S genset with solidly-grounded star point (Yn). An
  isolated-neutral (IT) genset would have no zero-sequence return
  at all and these need overriding.
- **`DEFAULT_USAGE_FACTOR = 0.5`** — single conservative festival
  diversity factor. Required at every `phases` call site (no
  function default — the choice is event-specific and we don't
  want it disappearing into a default).
- **`phase = [1, 2]` splits power evenly across the listed legs** —
  the multi-phase-loads-self-balance-evenly assumption. Documented
  in `research/pandapower/10.md` under "Modelling assumption —
  multi-phase loads self-balance evenly". Currently only matters
  for `curious creatures` in the 2026 fixture; flagged for any
  future genuinely-asymmetric multi-phase load.

Also worth a second pair of eyes:

- The **modified fixture** `tests/fixtures/2026-05-14_martin_modified.geojson`
  was hand-edited to upsize four cables so the grid converges. The
  resize sweep is in `research/pandapower/11`; the original raw export
  is preserved as `2026-05-14_martin.geojson`.
- The **`phase = None` semantics** are explicit and important — `None`
  is the modelling choice "balanced three-phase draw", not "missing
  data". `pp.load` under `runpp_3ph` *is* the balanced-draw primitive,
  so unphased loads need no special handling and don't contribute to
  neutral current. Full per-layer behaviour table in
  `src/nopywer/pp_interop/README.md` § "What `phase = None` means at
  each layer".

## Required reading for the technical reviewer

- `src/nopywer/pp_interop/README.md` — API surface, runnable examples,
  the balanced/asymmetric type distinction, logging surface.
- `research/pandapower/10_three_phase_asymmetric_modelling.md` — what
  the work was and the shopping list it came from.
- `research/pandapower/10.1_three_phase_theory.md` — physics of why
  single-phase loads unbalance the *other* two legs and how the
  zero-sequence parameters get picked.
- `research/pandapower/11_field_export_fixture_walkthrough.md` — the
  real-fixture work that produced the modified fixture.
- `research/pandapower/12_runpp_3ph_findings.md` — first numerical
  findings from `runpp_3ph` on the modified fixture.

## Test count

101 tests; all pass. Notable additions:

- `tests/test_pp_interop_phases.py` — strategies, candidate selection,
  apply, the round-trip through GeoJSON, the `phase_geojson` wrapper.
- `tests/test_pp_interop_powerflow_3ph.py` — `_phase_split`
  parametrised across every `phase` form; per-physics tests for
  balanced and single-phase loads under `runpp_3ph`.
- `tests/test_io_logging.py` — `caplog`-pinned warnings for the
  string-marker and unknown-key paths.

## Not in this PR (deliberately)

- A `compare_3ph_with_tree_walk`. The tree walk collapses each node
  to a single scalar voltage; there is nothing to line up against
  `runpp_3ph`'s three per-leg voltages. The findings doc (12) is the
  honest comparison.
- A CLI subcommand. `scripts/run_asymmetric.py` is a thin standalone
  script; adding it to `python -m nopywer` would convert the existing
  no-subcommand CLI into a subcommand layout (a breaking UX change).
  Out of scope for this PR.
- A sensitivity sweep over the zero-sequence ratios. Listed as
  remaining work in doc 10; would belong in `scripts/sensitivity_sweep.py`.
