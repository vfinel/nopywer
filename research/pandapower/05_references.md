# References

## Official pandapower

- [pandapower.org](https://www.pandapower.org/) — homepage.
- [About pandapower](https://www.pandapower.org/about/) — scope, design,
  positioning vs commercial tools.
- [Getting Started](https://www.pandapower.org/start/) — install, minimal
  3-bus example, notebooks list.
- [pandapower 3.4.0 docs](https://pandapower.readthedocs.io/en/latest/) —
  current stable.
- [Change Log](https://pandapower.readthedocs.io/en/latest/about/changelog.html)
  — pandapower 3.4.0 was released 9 Feb 2026.
- [GitHub: e2nIEE/pandapower](https://github.com/e2nIEE/pandapower) —
  source, releases, issues.
- [PyPI page](https://pypi.org/project/pandapower/).

## Documentation pages most relevant to nopywer

- [Power Flow (`runpp`)](https://pandapower.readthedocs.io/en/latest/powerflow/ac.html)
  — balanced AC Newton-Raphson and other solvers.
- [Asymmetric / Three-Phase Power Flow (`runpp_3ph`)](https://pandapower.readthedocs.io/en/latest/powerflow/ac_3ph.html)
  — sequence-frame method, transformer constraints, per-phase results.
- [Line element](https://pandapower.readthedocs.io/en/latest/elements/line.html)
  — `r_ohm_per_km`, `x_ohm_per_km`, `c_nf_per_km`, `max_i_ka`, zero-sequence
  parameters.
- [External Grid (`ext_grid`)](https://pandapower.readthedocs.io/en/latest/elements/ext_grid.html)
  — slack reference; analogue to nopywer's generator.
- [Asymmetric load](https://pandapower.readthedocs.io/en/latest/elements/asymmetric_load.html)
  — per-phase loads for `runpp_3ph`.
- [Topology module — create_nxgraph](https://pandapower.readthedocs.io/en/latest/topology/create_graph.html)
  — converting a `pandapowerNet` to a NetworkX graph.
- [Standard types](https://pandapower.readthedocs.io/en/latest/std_types.html)
  — predefined cable / line / transformer types.

## Tutorials worth reading first

- [tutorials/minimal_example.ipynb](https://github.com/e2nIEE/pandapower/blob/develop/tutorials/minimal_example.ipynb)
  — smallest possible network with `runpp`.
- [tutorials/create_simple.ipynb](https://github.com/e2nIEE/pandapower/blob/develop/tutorials/create_simple.ipynb)
  — building a network from scratch with `create_*` helpers.
- [tutorials/topology.ipynb](https://github.com/e2nIEE/pandapower/blob/master/tutorials/topology.ipynb)
  — graph searches, connectivity, component analysis.

## Recent third-party guides (≤ 12 months old)

Checking publication dates is awkward via search; these are the freshest
secondary references located in April 2026:

- [N. G. Tech, "1 Introducing pandapower"](https://medium.com/@brownebc/1-introducing-pandapower-4b18bcd78f1e)
  — Medium article, dated Feb 2026. High-level introduction. Useful for a
  reader new to pandapower's mental model. (Not deeply technical.)
- [Sustainable Power Systems Lab — "Pandapower-Based Modeling of Distribution Networks"](https://sps-lab.org/courses/student-projects/pandapower-modeling-dn/)
  — student-project framing of using pandapower to model distribution
  networks, more applied than the official tutorials.

The pandapower ecosystem skews academic; most "guides" are conference
papers, MDPI / Energies articles, or repository tutorials rather than
blog posts. The tutorials in the repo are the most reliable starting
point.

## Foundational papers

- [L. Thurner et al., "Pandapower — An Open-Source Python Tool for
  Convenient Modeling, Analysis, and Optimization of Electric Power
  Systems" (IEEE Transactions on Power Systems, 2018)](https://ieeexplore.ieee.org/document/8344496)
  — the canonical citation. Open-access PDF on
  [arXiv](https://arxiv.org/abs/1709.06743).

## Related libraries to be aware of

- [PYPOWER](https://github.com/rwl/PYPOWER) — pandapower's underlying solver.
- [lightsim2grid](https://lightsim2grid.readthedocs.io/) — fast C++ NR solver
  pandapower can offload to.
- [PowerGridModel](https://github.com/PowerGridModel/power-grid-model) —
  alternative C++ solver with pandapower bindings.
- [PowerModels.jl](https://lanl-ansi.github.io/PowerModels.jl/) — Julia OPF
  toolbox; pandapower can call it for advanced OPF.
- [andes](https://docs.andes.app/) — dynamic / RMS simulation, complementary
  to pandapower's static analysis. Mentioned only because nopywer's domain
  is static and andes is *not* relevant for festival sizing.

## Standards referenced (relevant to both libraries)

- IEC 60038 — standard voltages, where 230 V phase-to-neutral originates.
- IEC 60364 / NF C 15-100 — low-voltage installation rules and the 5 %
  voltage-drop threshold nopywer enforces.
- IEC 60909 — short-circuit calculation method pandapower implements.
