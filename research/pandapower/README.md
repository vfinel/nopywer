# pandapower research

High-level research on whether and how the [pandapower](https://www.pandapower.org/)
library could be used to replace or augment the power calculations in nopywer.

This folder contains **research only** — no code, no migration plan, no
recommended implementation. The aim is to document understanding so that a
later decision can be made with eyes open.

Date of research: April 2026. Pandapower latest at time of writing: **3.4.0**
(released 9 Feb 2026).

## Contents

1. [`01_pandapower_overview.md`](01_pandapower_overview.md) — what pandapower
   is, what it computes, what it depends on.
2. [`02_nopywer_power_calculations.md`](02_nopywer_power_calculations.md) —
   what nopywer currently does for the power-side maths and where its
   simplifying assumptions lie.
3. [`03_intersection.md`](03_intersection.md) — concept-by-concept mapping
   between the two domain models, where they overlap, where they diverge.
4. [`04_porting_considerations.md`](04_porting_considerations.md) — high-level
   tradeoffs of replacing nopywer's analyzer with pandapower, retaining it,
   or running them side-by-side. Risks, gaps, and open questions.
5. [`05_references.md`](05_references.md) — pandapower docs, recent (≤ 12 mo)
   guides, papers, and tutorials worth following up on.
6. [`06_extended_opportunities.md`](06_extended_opportunities.md) — wider survey
   of pandapower-able calculations beyond short-circuit (AC validation,
   reactive power per load type, neutral sizing, breaker coordination, OPF,
   state estimation), in rough value-for-effort order.
7. [`07_optimiser_validation_findings.md`](07_optimiser_validation_findings.md) —
   what was built for opportunity §1 (AC validation of the optimiser) and
   what running it on the 2025 fixture revealed: tree walk under-reports
   voltage drop by up to 12 percentage points at high-stress nodes.
8. [`08_why_tree_walk_and_ac_disagree.md`](08_why_tree_walk_and_ac_disagree.md) —
   power-systems theory walkthrough of why nopywer and pandapower
   disagree, and why the disagreement runs in opposite directions on
   different fixtures (max-phase rule vs constant-power feedback).
9. [`09_sensitivity_to_config_assumptions.md`](09_sensitivity_to_config_assumptions.md) —
   how much each `pp_interop/config.py` default actually moves the
   numbers. Three sweeps (`X_OHM_PER_KM`, `PF`, `GEN_XDSS_PU`) with
   tables and per-knob takeaways. Headline: X is negligible, PF is
   modest, but X″d moves Isc by 2.2× across realistic generator
   choices — worth overriding per-event.
10. [`10_three_phase_asymmetric_modelling.md`](10_three_phase_asymmetric_modelling.md) —
    detailed shopping list for moving from balanced `runpp` to
    asymmetric `runpp_3ph`. Covers what pandapower needs (per-load
    phase, zero-sequence cable params, source vector group), what
    the existing fixtures contain (the 2025 fixture has no phase
    data; the small synthetic does), four strategies for
    synthesising phase data (B round-robin and D greedy now
    implemented in `pp_interop/phases`), and a per-layer scope
    breakdown. Key finding: phase balancing and voltage-drop relief
    are decoupled levers — greedy cuts leg imbalance 9.5 %→0.6 % but
    leaves the worst node's drop unchanged.
11. [`11_field_export_fixture_walkthrough.md`](11_field_export_fixture_walkthrough.md) —
    how to plug Martin's `2026-05-14_martin.geojson` field export into
    the pandapower code. Two gaps: a trivial schema mismatch (export
    keys `area_mm2`/`plugs_and_sockets_a` vs input keys
    `area`/`plugs&sockets`, loads silently to defaults), and a real
    one — at full load the grid is past voltage collapse and `runpp`
    will not converge. The non-convergence is itself the finding.
12. [`13_cable_costs.md`](13_cable_costs.md) — EU web research on finished
    CEE extension-lead costs for nopywer's four cable tiers. Fits each tier
    as `a + b * length_m` from complete H07RN-F leads rather than raw cable
    plus separate connector parts, and compares the fitted slopes with the
    current `tier_cost` heuristic.

## TL;DR

- **Yes, pandapower can in principle compute everything nopywer's `analyze.py`
  computes today**, plus more (reactive power, three-phase unbalanced flow
  via `runpp_3ph`, short-circuit per IEC 60909, state estimation).
- **Pandapower will not replace `optimize.py`, `inventory.py`, the GeoJSON
  I/O, the distro-requirement logic, or the cable-tier-cost MST heuristic** —
  those are festival-specific and have no equivalent in pandapower's domain.
- **The biggest modelling mismatches** are: (a) nopywer's resistance-only
  cable model versus pandapower's full R+X+C model; (b) nopywer's implicit
  230 V phase-to-neutral generator versus pandapower's `ext_grid` + line-to-line
  bus voltage convention; (c) nopywer's per-load single-phase assignment
  versus pandapower's `asymmetric_load` table.
- **The biggest practical questions** are whether the festival domain
  actually *needs* a full Newton-Raphson AC solver (it currently doesn't),
  and what the cost is of taking on pandapower (and its dependency tree:
  pypower, scipy, numba) as a hard dependency.
