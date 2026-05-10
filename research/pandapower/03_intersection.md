# Where nopywer and pandapower meet

A concept-by-concept mapping. The aim here is to be honest about which
nopywer concepts have a direct pandapower analogue and which do not.

## Concept mapping

| nopywer concept | pandapower analogue | Notes / friction |
|---|---|---|
| `PowerNode` (load) | `net.load` (balanced) or `net.asymmetric_load` (per-phase) | Loads with `phase ∈ {1,2,3}` would need `asymmetric_load` with `p_a_mw / p_b_mw / p_c_mw`. nopywer's "U" / "Y" sub-grid markers have no pandapower analogue. |
| `PowerNode` (generator) | `net.ext_grid` (slack bus) | Pandapower needs a slack reference. The generator has no internal impedance in nopywer — would map to a `vm_pu = 1.0` `ext_grid` on a dedicated bus. |
| `Cable` | `net.line` | The bridge requires R, X, C, max-I per km — see "Cable model gap" below. |
| `Cable.length_m` | `line.length_km` | Straight conversion `× 1e-3`. Pandapower forbids zero-length lines. |
| `Cable.area_mm2` | implicit in `r_ohm_per_km` and `max_i_ka` | Pandapower has no field for cross-section; a tier table would have to translate area → impedance + ampacity. Standard types like `NAYY 4×50 SE` exist for fixed-installation cables, not festival flex cables. |
| `Cable.plugs_and_sockets_a` | `line.max_i_ka` (or none) | Plug-and-socket rating is a connector-side limit, not a thermal-cable limit; pandapower has no concept of it. |
| `cable.resistance` (ρ·L/A) | `line.r_ohm_per_km × length_km` | Different formulation, same result if ρ is matched. |
| `node.voltage`, `vdrop_percent` | `res_bus.vm_pu` (× nominal kV) | Pandapower returns per-unit on `vn_kv`. Nopywer reports volts and percent. |
| `cable.current_per_phase` | `res_line_3ph.i_a_ka / i_b_ka / i_c_ka` (3ph) or `res_line.i_ka` (1ph) | Per-phase output is only available with `runpp_3ph`. |
| `phase balance` (% std/mean) | none built-in | Would need a post-processing step over the per-phase current results. |
| `tree`, `parent`, `children`, `deepness` | `pp.topology.create_nxgraph(net)` + NetworkX BFS | Pandapower can produce a NetworkX graph; depth labelling is the caller's job. |
| `_snap_cables_to_nodes` | none | Pandapower assumes pre-resolved bus IDs. The snap is an I/O concern, not a flow concern. |
| `optimize_layout` (MST + rewire) | none | Pandapower has topology *analysis* (radiality check, connected components) but no layout *planner*. The `optimize.py` algorithm has no equivalent and would stay. |
| `Cable16A / 32A / 63A / 125A` tiers + `tier_cost` | none | Pandapower's standard type library is keyed by cable name (e.g. `NAYY 4×50 SE`), not plug rating, and has no cost concept. The festival tier model would stay. |
| `inventory.py` (Excel match) | none | Outside pandapower's domain. Stays. |
| `distro_in / distro_out` strings | none | Outside pandapower's domain. Stays. |
| GeoJSON I/O | `net.bus_geodata`, `net.line_geodata` (display only) | Pandapower stores geodata for plotting but does not use it for distance or impedance. The GeoJSON layer stays as a translation boundary. |

## The cable-model gap

This is the single biggest mismatch and worth its own section.

nopywer's cable is **resistance-only**, derived from cross-section and a
single conservative ρ:

```
R = (1 / 26) * length_m / area_mm2     # Ω
```

Pandapower's line is a full π-section: `r_ohm_per_km`, `x_ohm_per_km`,
`c_nf_per_km`. For balanced LV festival cables of typical length (< 1 km),
`x` and `c` produce a small but non-zero correction:

- `x / r` for flexible LV cables in the 2.5–35 mm² range is roughly
  0.05–0.15. So ignoring `x` underestimates impedance magnitude by < 1 %
  at PF ≈ 1 and up to ~5 % at PF = 0.7.
- Capacitive charging current at LV / 50 Hz over < 1 km is negligible.

The implication is that pandapower **can** reproduce nopywer's voltage
drops with `x = 0`, `c = 0`, and a matched `r_ohm_per_km` derived from
`ρ_copper / area_mm2`. With non-zero X and Q, the answers diverge from
nopywer's current behaviour — which may be desirable (more physical) or
undesirable (changes test fixtures). The 2.2× ρ factor would still need
to be carried explicitly to keep field margin.

## The voltage-convention gap

- nopywer treats `V0 = 230 V` as the generator terminal voltage. There is
  no separate concept of phase-to-neutral vs line-to-line; everything is a
  single number.
- Pandapower's `bus.vn_kv` is line-to-line. A European LV bus is `vn_kv =
  0.4`, and `runpp_3ph` returns per-phase voltages relative to that.
  Mapping back to nopywer's "node voltage in volts (P-N)" requires a
  ÷ √3 conversion.

This is not a hard problem, but it is a translation that needs to live
somewhere if pandapower were used.

## The single-generator-vs-slack gap

nopywer's generator is implicitly a perfect 230 V source — no impedance,
no `Z_source`, no synchronisation. Pandapower's `ext_grid` plays the same
role (PV / Slack with `vm_pu = 1.0`, `s_sc_max_mva` optional for
short-circuit). One-to-one mapping.

If, in future, multiple generators were modelled, pandapower has the right
machinery (multiple `ext_grid`s of different priorities, or `gen` with
voltage-control). nopywer currently raises on > 1 generator.

## What pandapower would add that nopywer does not have today

- **Iterative AC power flow** with reactive power, voltage-dependent loads,
  and convergence diagnostics. Required only if Q starts to matter
  (e.g. inverter-fed loads, large motors).
- **True three-phase asymmetric flow** via `runpp_3ph`, which models neutral
  current, zero-sequence impedance, and per-phase voltage on every bus.
  nopywer's current per-phase tracking is an approximation of this.
- **IEC 60909 short-circuit calculation**. Useful for sizing breakers and
  RCDs at festivals, currently out of scope for nopywer.
- **State estimation** if real-time metering is ever added.
- **OPF / generation dispatch** for hybrid generator-plus-battery setups.
- **Standardised export formats** (PYPOWER `.mat`, MATPOWER, CIM,
  PowerModels.jl) via pandapower's converters.

## What nopywer keeps regardless

- GeoJSON in/out and `geometry.py` (geodesic distance from lon/lat).
- Cable-tier model with plug-and-socket-rating-as-primary-key.
- MST + tier-cost local-search layout optimiser.
- Inventory matching against an Excel spreadsheet.
- Distro requirement summarisation.
- Phase-balance reporting.
- The 5 % `VDROP_THRESHOLD_PERCENT` check (per NF C 15-100).
- The 10 m cable slack and 5 m snap threshold.

These are festival-domain concerns and have no pandapower equivalent.
