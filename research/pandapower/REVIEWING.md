# Reviewing this branch

A short guide for whoever picks this up. Reading the docs in order
takes ~25 minutes. Reading the code takes ~15 more.

## What changed at a glance

| Area | Files | Lines | Risk |
|---|---|---:|---|
| **Research notes** (read these first) | `research/pandapower/*.md` | +1125 | none — docs only |
| **Optional dep + extras** | `pyproject.toml`, `uv.lock` | +29 / +562 | medium — dep floors lowered, see §packaging below |
| **PowerNode schema** | `src/nopywer/models.py` | +4 | low — additive `i_sc_ka` field |
| **New module** | `src/nopywer/pp_interop/` | +474 | low — opt-in, lazy import |
| **Tests** | `tests/test_pp_interop.py` | +160 | none — only new tests, all 44 pass |
| **End-to-end runner** | `scripts/validate_optimiser_with_runpp.py` | +77 | none — script, not imported |

Total: 6 new docs, 6 new code files, 2 modified files.

## Reading order

**Skip nothing.** The docs build on each other.

1. [`research/pandapower/README.md`](./README.md) — TL;DR, sets the
   context for why this branch exists. **2 min.**
2. [`02_nopywer_power_calculations.md`](./02_nopywer_power_calculations.md)
   — what nopywer's tree walk actually does. Skim if you're
   already familiar with `analyze.py`. **5 min.**
3. [`03_intersection.md`](./03_intersection.md) — concept-by-concept
   mapping nopywer ↔ pandapower. Useful to understand the choices
   in the conversion layer. **5 min.**
4. [`06_extended_opportunities.md`](./06_extended_opportunities.md) —
   the menu of pandapower-able calculations. Reading this first
   makes the next doc make sense. **5 min.**
5. [`07_optimiser_validation_findings.md`](./07_optimiser_validation_findings.md)
   — what was actually built (opportunity §1) and what running it on
   the 2025 fixture revealed. Has the diagrams. **8 min.**

After that, read the code in this order:

6. `src/nopywer/pp_interop/config.py` — every assumption / default
   in one file with explanations. **3 min.**
7. `src/nopywer/pp_interop/_conversion.py` — the only file that
   touches pandapower's `create_*` API. Worth scrutinising. **5 min.**
8. `src/nopywer/pp_interop/_powerflow.py` and `_shortcircuit.py`
   — thin wrappers over `runpp` and `calc_sc`. **3 min each.**
9. `tests/test_pp_interop.py` — exercises the public API. **3 min.**
10. `scripts/validate_optimiser_with_runpp.py` — end-to-end runner;
    its output is the headline finding. **2 min.**

Skip on first pass: `__init__.py` (re-exports only), older research
docs `01`, `04`, `05` (background; not required to review the
code).

## Run it yourself

```bash
# Reproduce the test suite (44 tests, ~7 s with pandapower installed)
uv sync --extra pandapower
uv run pytest

# Reproduce the headline finding on the 2025 event fixture
uv run python scripts/validate_optimiser_with_runpp.py
```

The script's output is what `07_optimiser_validation_findings.md`
quotes. You should see the same numbers (within solver tolerance).

If you want the build *without* pandapower (smaller dep tree,
modern pandas/numpy), use:

```bash
uv sync --extra modern    # pandas>=3.0, numpy>=2.4, no pandapower
```

The two extras are declared as conflicting in `[tool.uv]` because
pandapower 3.4.0 caps pandas at `<3` and numpy at `<2.4`. Either
extra alone resolves cleanly; you cannot have both.

## Decisions worth pushing back on

These are the choices most likely to provoke a reviewer comment.
I've laid out the reasoning so you can disagree on the substance.

### 1. `pandapower` extra pinned to a git commit, not a release

```toml
"pandapower @ git+https://github.com/e2nIEE/pandapower.git@472d8294…"
```

Pandapower 3.4.0 (the latest release on PyPI) ships a bug
([#2860](https://github.com/e2nIEE/pandapower/pull/2860)) that breaks
`runpp` under pandas ≥ 2.3 with read-only numpy buffers. The fix
merged 2026-02-10 — one day after the 3.4.0 release. There is no
3.4.1 yet. Without this pin, `compute_power_flow` does not work at
all; only `compute_short_circuit` works (`calc_sc` doesn't traverse
the buggy path).

**Alternative considered:** wait for 3.4.1. Unknown ETA. Held the
work back too long.

**TODO** when 3.4.1 ships: replace the git URL with `pandapower>=3.4.1`.
Search for the PR link in `pyproject.toml` to find the spot.

### 2. Dependency floors lowered

Was: `pandas>=3.0`, `numpy>=2.4`.
Now: `pandas>=2.3`, `numpy>=1.26`.

Pandapower 3.4 declares `pandas~=2.3` and `numpy<2.4`, so the floors
had to come down for the extra to install. The `modern` extra
restores the higher floors for users who don't want pandapower:

```toml
[project.optional-dependencies]
modern = ["pandas>=3.0", "numpy>=2.4"]
```

Existing pandas usage (`inventory.py` only) is read_excel — works
on both floors. Numpy usage is array/dot-product, also fine.

**Alternative considered:** keep base floors high and document
that the `pandapower` extra forces a downgrade. Confusing — uv
won't tell you why your install regressed.

### 3. New module name: `pp_interop`

Trading off:
- `pp` — convention is `import pandapower as pp`. Shadowing it
  inside our own module would be confusing.
- `pandapower` — conflicts with the third-party package import.
- `shortcircuit` — accurate when we only had `calc_sc`, no longer
  fits with `compute_power_flow` added.
- `pp_interop` — what landed. Boring, unambiguous, descriptive.

### 4. `PowerNode.i_sc_ka` is always emitted in `to_geojson`

Default 0.0 means downstream consumers will see
`"i_sc_ka": 0.0` for every node — even when short-circuit was never
computed.

**Alternative:** emit only when > 0. Would make the GeoJSON schema
data-dependent, harder for the frontend to reason about. The
chosen approach matches how `voltage` and `vdrop_percent` work
(also default 0, also always emitted).

### 5. `to_pandapower` always creates loads, even for short-circuit

IEC 60909 max-case standardly ignores prefault load, so the loads
are inert when only `compute_short_circuit` runs. We could gate
load creation on a flag. The reasoning for not gating:
- One conversion path is simpler than two.
- The `PandapowerGrid` handle is meant to be reused across calc
  functions. Gating on which calc you'll run breaks that.
- `calc_sc` ignores the loads, so the cost is one extra
  `pp.create_load` call per node — negligible.

### 6. `compare_with_tree_walk` skips `analyze` if the tree is already built

`analyze.py:43–49` raises if `node.children` is already populated
(cycle-detection guard). Calling `analyze` twice on the same grid
trips this. The branch:

```python
if not grid.tree:
    analyze(grid)
```

…makes the helper safe to call after the user has already run
`analyze` themselves (a normal flow). There's a test for this
(`test_compare_with_tree_walk_after_explicit_analyze`).

### 7. Default `gen_sn_kva = 100`

Fictional. The shape of the divergence on the 2025 fixture is
insensitive to this (cable impedance ≫ source impedance for
realistic festival kVA), but absolute Isc numbers are not. Real
deployments should pass the rated kVA explicitly. Documented in
`config.py`.

### 8. Documentation lives in `research/pandapower/`

Six docs totalling ~1000 lines. Reasoning:
- Not in `docs/` — there is no `docs/` and adding one for one
  feature is overkill.
- Not in code comments — these are design / context docs,
  not API docs.
- `research/` is already a folder pattern (created by an earlier
  research request) and signals "thinking aid, not production
  documentation".

## What's *not* in this branch

Listed so you don't go looking for them.

- **No CLI flag.** Validation runs through the script. Folding
  into `nopywer-analyze` is a thin wrapper, deliberately deferred.
- **No frontend changes.** GeoJSON gains an `i_sc_ka` field that
  `app.js` ignores.
- **No optimiser changes.** Validation runs *after* the optimiser,
  doesn't feed back into it. Closing that loop is a separate piece
  of work tracked in `06_extended_opportunities.md`.
- **No `runpp_3ph`** (per-phase asymmetric flow). The balanced
  `runpp` is enough to demonstrate the linearisation gap. Asymmetric
  is opportunity §3.
- **No min-case fault current** (`fault="1ph", case="min"`). Needs
  zero-sequence params on cables. Opportunity §5.

## Sanity checklist for the reviewer

- [ ] `uv sync --extra pandapower && uv run pytest` — 44/44 pass
- [ ] `uv run python scripts/validate_optimiser_with_runpp.py` —
      reports "AC converged: True" and shows divergence at high-drop
      nodes
- [ ] `uv sync --extra modern` — installs without pandapower, gives
      pandas 3.x / numpy 2.4+
- [ ] `import nopywer` works without the `pandapower` extra
      installed (lazy import)
- [ ] No existing test was modified — only added
- [ ] `git diff develop -- src/nopywer/` is small (only models.py,
      plus the new module)
