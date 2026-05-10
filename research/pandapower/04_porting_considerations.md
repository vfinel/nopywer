# Porting considerations

Three plausible strategies, with the tradeoffs honestly named. **No
recommendation is given here** — this is a thinking aid.

## Strategy A — Replace `analyze.py` with pandapower

Use pandapower as the core power-flow engine. Keep `optimize.py`,
`inventory.py`, `io.py` (GeoJSON), and the cable-tier model. Build a thin
adapter that converts a `PowerGrid` to a `pandapowerNet` and back.

**Pros**
- Industrially validated solver. Voltage drops include reactance and
  reactive-power effects "for free".
- Future-proofs for non-radial grids (loops), multiple generators, and
  battery / inverter integration without rewriting the analyzer.
- Opens the door to short-circuit calculations and OPF.
- A single dependency replaces a hand-written tree walk.

**Cons**
- Hard dependency on pandapower (and its tail: scipy, pypower, optionally
  numba, lightsim2grid). nopywer's current dependency footprint is small
  and chosen intentionally.
- The current `analyze.py` is ~170 lines; the equivalent adapter to and
  from pandapower (with phase mapping, line parameter generation, result
  unpacking) is plausibly the same size with less domain readability.
- All test fixtures pin specific volts / amps / percents to two decimals.
  Switching to a different solver shifts every number — every fixture
  needs regenerating with documented physical justification.
- The 2.2× ρ-copper margin and PF = 0.9 baking are values learned from
  field experience and would need to be re-expressed (probably as
  per-line `r_ohm_per_km` and per-load `q_mvar`). Risk of silently losing
  the conservative margin.
- For a strictly radial single-generator tree with no Q, NR is overkill —
  pandapower will iterate to convergence on a problem that admits a
  closed-form sweep. Performance matters less than correctness here, but
  the conceptual mismatch is real.

**Open questions**
- Does pandapower converge cleanly on tree topologies with extremely short
  lines (10–30 m at LV)? Festival cables are short and impedance is small.
  Pandapower's docs warn about convergence on low-impedance lines.
- How do flexible / rubber-jacketed festival cables (HO7RN-F etc.) compare
  to the standard-type library entries (NAYY series)? Likely no direct
  match; custom `create_line_from_parameters` calls per cable are needed.

## Strategy B — Add pandapower as a parallel analyzer

Keep `analyze.py` as the default fast path. Add an optional
`analyze_pandapower(grid)` (e.g. behind a CLI flag `--solver pandapower`)
for cases where iterative AC, reactive power, or per-phase asymmetric flow
is wanted.

**Pros**
- No regression risk for existing users / tests.
- pandapower becomes an opt-in dependency rather than a hard one
  (declared as an extra: `pip install nopywer[pandapower]`).
- Useful as a verification harness — running both solvers and diffing
  their results would surface modelling assumptions and build confidence.
- Allows incremental adoption: phase 1 = verification, phase 2 = port
  short-circuit / unbalanced features only, phase 3 = consider full
  replacement.

**Cons**
- Two analyzers to maintain. Nopywer's domain logic ends up duplicated,
  particularly the per-phase mapping and the voltage-drop reporting.
- API drift risk: result formats from the two solvers will not match
  exactly; downstream consumers (GeoJSON, frontend) would need a single
  canonical format.
- Confusing to users: which solver do they want, and why?

**Open questions**
- Where does the pandapower-only feature surface live? A new module under
  `src/nopywer/pp/`, or deeper integration into `models.py`?
- Are there *any* current users for whom NR / Q / unbalanced matters? If
  not, this strategy adds optionality nobody uses.

## Strategy C — Use pandapower only for export

Don't compute with pandapower. Use it solely as a serialisation /
interchange layer: convert nopywer grids to `pandapowerNet`, then export
to PYPOWER, MATPOWER, OpenDSS, CIM, etc. via pandapower's converters.

**Pros**
- Smallest blast radius. `analyze.py` and `optimize.py` are unchanged.
- Festival-power data becomes consumable by the wider power-engineering
  ecosystem — useful for academic collaborations or formal grid studies.
- Zero risk of changing user-facing numbers.

**Cons**
- Weakest justification for taking on the dependency. If the use case is
  only "export this once", a hand-rolled MATPOWER writer might be lighter.
- Doesn't deliver any of pandapower's analytical value.

**Open questions**
- Is there demonstrated demand for export-to-other-tools? The README
  doesn't mention any.

## Cross-cutting risks

These apply regardless of strategy.

- **Test-fixture churn.** Every numerical test in `test_analyze.py`,
  `test_optimize.py`, and `test_models.py` pins values rounded to 1–2 dp.
  Any solver change that touches voltages or currents (even by 0.1 V)
  invalidates fixtures. Decide upfront whether tests assert physics or
  assert behaviour-of-current-implementation.
- **The `1/26` ρ_copper.** This is field-validated tribal knowledge with
  no upstream traceable source ("Rich's old notes"). Whatever path is
  chosen, this number must be carried forward visibly, with a comment, or
  explicitly retired with a justified replacement.
- **The "phase" property.** nopywer accepts `phase ∈ {1, 2, 3, "U", "Y",
  None}`. Phases 1/2/3 map to pandapower's a/b/c. "U" / "Y" are sub-grid
  labels with no electrical meaning in `analyze.py` (they appear only in
  the reporting in `print_grid_info`). They have no pandapower equivalent
  and would need to be threaded around any pandapower path.
- **Performance and packaging.** pandapower with numba is not pip-friendly
  on every platform (Apple Silicon, NixOS, Alpine). Without numba it is
  slower but portable. For a CLI that may run on a laptop in a field,
  this matters.

## Things to test before committing to anything

1. Build a one-bus, one-line, one-load pandapower model that mirrors the
   `test_compute_voltage_drop_uses_phase_voltage_reference` fixture
   (10 A through 26 m of 1 mm² → 10 V drop) and confirm it reproduces
   the nopywer result with `r_ohm_per_km = 1000/26`, `x = 0`, `c = 0`,
   `cos φ = 1`.
2. Run the same setup on the bigger `test_optimization_summary` fixture
   (50-cable 2025 event) end-to-end. Compare voltage drops, currents,
   and phase imbalance against nopywer's output.
3. Try `runpp_3ph` on a grid with mixed single-phase / three-phase loads
   to confirm the per-phase asymmetric model gives sensible neutral
   currents.
4. Measure cold-start cost of `import pandapower as pp` and a single
   `runpp` call on a 50-node tree. The CLI's existing startup is
   dominated by `pyproj` and `pandas`; pandapower would add measurably
   to that.

None of those are in scope for this research folder. They are listed so
that whoever picks this up next knows where to start.

## Things explicitly *not* to port

- The MST + tier-cost local-search optimizer (`optimize.py`). It solves a
  layout-planning problem pandapower does not address.
- The Excel inventory matcher (`inventory.py`). Out of scope for any
  power-flow library.
- The GeoJSON I/O (`io.py`). Pandapower's `bus_geodata` is for plotting,
  not for round-tripping to GIS tools.
- The plug-and-socket-rating-keyed cable tiers in `models.py`. They
  encode a domain (festival hire) that pandapower has no vocabulary for.
