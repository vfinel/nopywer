# pandapower at a glance

## What it is

Pandapower is a Python toolkit for static and quasi-static analysis and
optimization of balanced (and, optionally, three-phase asymmetric) power
systems. It was first published in 2017 (Thurner et al., IEEE Transactions on
Power Systems) and is maintained by the Fraunhofer IEE / e2nIEE group on
GitHub. It is BSD-licensed.

The library positions itself as the bridge between commercial tools like
DIgSILENT PowerFactory and the open-source MATPOWER / PYPOWER stack, with
its component models validated against commercial software.

## Core abstractions

A pandapower network (`pandapowerNet`) is a collection of pandas DataFrames,
one per element type:

| DataFrame | Represents |
|---|---|
| `net.bus` | Buses (nodes), with nominal voltage `vn_kv` (line-to-line for 3-phase) |
| `net.line` | Distribution / transmission lines and cables |
| `net.trafo`, `net.trafo3w` | Two- and three-winding transformers |
| `net.ext_grid` | Slack / external grid connection (sets reference voltage and angle) |
| `net.gen`, `net.sgen` | Synchronous and static (PV / PQ) generators |
| `net.load`, `net.asymmetric_load` | Symmetric and per-phase loads |
| `net.switch` | Switches between buses or on lines |
| `net.shunt`, `net.impedance`, `net.ward`, `net.xward` | Equivalent impedances |

Results from a power flow are written into parallel `net.res_*` DataFrames
(`res_bus`, `res_line`, `res_trafo`, …).

## Calculations supported

| Function | Purpose |
|---|---|
| `runpp(net)` | Balanced AC power flow. Newton-Raphson by default; PYPOWER, lightsim2grid, or PowerGridModel solvers also pluggable. |
| `runpp_3ph(net)` | Asymmetric three-phase power flow using the sequence-frame method (NR for positive sequence, current injection for zero/negative). Requires zero-sequence line parameters. |
| `rundcpp(net)` | DC approximation. |
| `runopp(net)` / `rundcopp(net)` | AC / DC optimal power flow via PYPOWER or PowerModels.jl. |
| `estimate(net)` | Weighted-least-squares state estimation with bad-data detection. |
| `pp.shortcircuit.calc_sc(net)` | IEC 60909 short-circuit calculation, including converter-fed networks. |
| `pp.topology.create_nxgraph(net)` | Convert the net to a NetworkX (Multi)Graph for connectivity / radiality / cycle / component searches. |

## Line / cable model

`pandapower.create_line_from_parameters(net, from_bus, to_bus, length_km,
r_ohm_per_km, x_ohm_per_km, c_nf_per_km, max_i_ka, …)`

Required electrical parameters per line:

- `r_ohm_per_km` — resistance.
- `x_ohm_per_km` — reactance.
- `c_nf_per_km` — line-to-earth capacitance.
- `max_i_ka` — thermal current limit, used for loading-percent reporting.
- For 3-phase asymmetric flow: zero-sequence equivalents `r0_ohm_per_km`,
  `x0_ohm_per_km`, `c0_nf_per_km`.

Constraints worth knowing:

- `length_km` must be > 0 (zero leads to division-by-zero in the solver).
- Very low impedance can cause Newton-Raphson convergence problems — pandapower
  recommends bridging via `net.switch` or `net.impedance` instead of an
  artificially short line.
- Pandapower ships a **standard-type library** (e.g. the `NAYY 4×50 SE` LV
  cable) that auto-fills all parameters from a name string.

## Voltage convention

- Bus voltage `vn_kv` is **line-to-line** for three-phase systems
  (European LV → 0.4 kV, not 0.23 kV).
- Per-unit results in `res_bus.vm_pu` are referenced to the bus's `vn_kv`.
- For runpp_3ph, results are reported per phase (a, b, c).

## Three-phase asymmetric flow specifics

`runpp_3ph` is the relevant entry point for any unbalanced LV analysis.
Constraints to be aware of:

- Only earthed transformer vector groups are supported: Dyn, Yyn, YNyn, Yzn.
- Loads need to live in `net.asymmetric_load` (with `p_a_mw`, `p_b_mw`,
  `p_c_mw`, etc.) for true per-phase modelling.
- Voltage-dependent loads, Q-limit enforcement, and temperature-dependent
  resistance are **not** confirmed-tested in the 3-phase path.
- Lines need their zero-sequence parameters populated.

## Dependencies

Core: `numpy`, `scipy`, `pandas`, `networkx`, `packaging`, `tqdm`, `deepdiff`.
Optional: `numba` (JIT, big speedup for `runpp`), `lightsim2grid`,
`PowerGridModel`, `PowerModels.jl` (Julia, for OPF / advanced features),
`matplotlib` / `plotly` (plotting).

Installation footprint with `pip install pandapower[all]` is non-trivial
(numba pulls in LLVM). The minimum core is moderate.

## Version 3.4.0 highlights (Feb 2026)

- `enforce_p_lims` argument on `runpp` for `gen` / `sgen` active-power limits.
- New toolbox helper `get_all_elements()` returning every element table as a
  combined DataFrame.
- Renamed `tap_dependent_impedance` → `tap_dependency_table` for transformers.
- Build moved from `setup.py` to `pyproject.toml`.

## What pandapower is *not*

- Not a transient / dynamic simulator. For RMS / EMT, use packages like
  `andes`, `dynawo`, `assimulo`, or commercial tools.
- Not a cable-routing / layout / planning tool — it has no concept of
  geographic distance, cable-tier cost, plug standards, or inventory.
- Not designed around radial-only networks; it can solve them, but it
  doesn't know that "radial" is a special case worth optimising for.
- Not a North American distribution tool — pandapower's three-phase model
  assumes European-style symmetric connections and cannot represent the
  asymmetric feeder-with-neutral patterns used in NA distribution. (This is
  not a constraint nopywer cares about.)
