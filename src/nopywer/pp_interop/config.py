"""Configuration for the pandapower interop module.

All tunable constants and modelling assumptions live here so they are
discoverable in one place. Calc functions accept these as keyword
arguments with these values as defaults.

== Key assumptions ==

Voltage / frequency
- 50 Hz European LV. Every bus is `vn_kv = VN_KV_LL` (line-to-line of
  230 V P-N). Mixing MV / different frequencies is out of scope.

Generator (the only source)
- Modelled as a Thevenin `ext_grid`, not a `pp.gen` with explicit
  subtransient parameters. Sufficient for worst-case three-phase fault
  current; not sufficient for transient/dynamic studies.
- Default rated apparent power 100 kVA, X''d = 0.12 pu, R/X = 0.1
  (typical diesel gen). All three configurable.
- Generator terminal voltage fixed at vm_pu = 1.0.

Cables
- Resistance per km derived from `RHO_COPPER = 1/26` Ω·mm²/m — preserves
  nopywer's conservative field-margin convention. Slightly overstates R
  (≈ 2.2× textbook copper). Implication: under-estimates Isc, which is
  cautious for "will my breaker trip in time?" but optimistic for
  breaking capacity sizing.
- Reactance defaults to 0.08 Ω/km for all cables (LV multi-core flex
  typical). Single hardcoded value; real flex spans roughly 0.07–0.10.
- Capacitance is zero (negligible at < 1 km LV).
- Length is clamped at `MIN_LENGTH_M` minimum (pandapower forbids
  zero-length lines).
- `max_i_ka` is taken from the plug-and-socket rating, not a thermal
  rating of the conductor itself.

Loads
- Not modelled at all. IEC 60909 short-circuit current is the source
  contribution; loads vanish during a bolted fault.
- `PowerNode.phase` (1/2/3/"U"/"Y") is ignored. Three-phase symmetric
  fault by definition balances all phases.

Topology
- Only the generator-rooted radial tree implied by `from_node`/`to_node`
  is converted. Cables must already be snapped (run `analyze` first or
  rely on the GeoJSON loader having populated endpoints).

Fault model
- `compute_short_circuit` runs `fault="3ph", case="max"`. Worst case for
  breaker breaking capacity. Phase-to-earth and phase-to-phase faults
  need zero-sequence line parameters and a vector-grouped transformer.
"""

from ..constants import V0

# === Network ===

# European LV line-to-line nominal voltage in kV (= V0 * sqrt(3) / 1000,
# 230 * 1.732 ≈ 400 V → 0.4 kV).
VN_KV_LL: float = round(V0 * 3**0.5 / 1000, 4)

# Pandapower per-unit base apparent power. 1 MVA is conventional for LV.
NET_SN_MVA: float = 1.0

# Grid frequency.
F_HZ: float = 50.0


# === Generator (festival diesel default) ===

# Rated generator apparent power in kVA.
GEN_SN_KVA: float = 100.0

# Generator subtransient reactance in per unit.
GEN_XDSS_PU: float = 0.12

# Generator resistance-to-reactance ratio.
GEN_RX: float = 0.1

# Generator/slack bus voltage set point in per unit.
GEN_VM_PU: float = 1.0


# === Cables ===

# Reactance per km for LV multi-core flex. Industry typical; not
# measured per-cable.
X_OHM_PER_KM: float = 0.08

# Capacitance per km. Negligible under 1 km of LV cable.
C_NF_PER_KM: float = 0.0

# Minimum cable length to feed pandapower (forbids zero-length lines).
MIN_LENGTH_M: float = 1.0


# === Fault calculation ===

# IEC 60909 fault type: balanced three-phase short circuit.
FAULT_TYPE: str = "3ph"

# IEC 60909 case: maximum prospective short-circuit current.
FAULT_CASE: str = "max"
