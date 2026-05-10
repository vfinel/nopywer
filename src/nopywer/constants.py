# Phase-to-neutral nominal voltage — European LV standard (IEC 60038)
V0 = 230  # [V]

# Power factor — typical for mixed resistive/inductive festival loads
# (lighting, fridges, sound systems)
PF = 0.9

# === Effective copper resistivity for field cable sizing ===
#
# Conservative resistance coefficient. Intentionally overestimates
# copper-only resistance to provide margin under real-world deployment
# conditions. Historically a single opaque constant (`RHO_COPPER = 1/26`)
# documented as "from Rich's old notes — probably from measurements
# they did". The textbook physical value for annealed copper at 20 °C
# is ~1/58, so the historical 1/26 figure represents ≈ 2.2× textbook.
#
# Now decomposed into three independently-overridable components so the
# 2.2× inflation is traceable rather than opaque:
#
#     RHO_COPPER  =  RHO_COPPER_20C  ×  k_temp(COPPER_TEMP_C)  ×  FIELD_MARGIN
#                 ≈      (1/58)      ×        1.197             ×    1.864
#                 ≈   0.01724        ×        1.197             ×    1.864
#                 ≈   0.0385  ≈  1/26
#
# The product at the defaults reproduces the legacy 1/26 value to
# within 0.02 % — well below modelling noise — so test fixtures
# pinned to the old value continue to pass.
#
# Each component is independently overridable for sensitivity analysis
# or per-event tuning:
#
#   - `RHO_COPPER_20C` is annealed copper at 20 °C (IACS standard).
#     Not really tunable — physics.
#   - `COPPER_TEMP_C` is the assumed steady-state conductor
#     temperature under festival load. Lower for a known cool event;
#     raise for a coiled-drum-in-the-sun scenario.
#   - `FIELD_MARGIN` is a catch-all for connector contact resistance,
#     bundling derating, ageing, strand breakage, and other real-world
#     effects not modelled directly. Empirically calibrated; could be
#     refined from measurement (e.g. PR #12 telemetry).

# Annealed copper resistivity at 20 °C (IACS standard).
RHO_COPPER_20C = 1 / 58  # [Ω·mm²/m]

# Temperature coefficient of copper at 20 °C.
ALPHA_COPPER = 0.00393  # [1/°C]

# Assumed steady-state conductor temperature under festival load.
# 70 °C is reasonable for HO7RN-F flex under sustained near-rated
# current with ambient 20–30 °C. Coiled cables in direct sun can
# reach 90 °C and warrant overriding upward.
COPPER_TEMP_C = 70.0  # [°C]

# Empirical field-margin multiplier on top of temperature-adjusted
# physics. Captures connector contact resistance, bundling, ageing,
# and other real-world effects not modelled directly. Calibrated to
# match the legacy "Rich's notes" RHO_COPPER = 1/26 at default
# COPPER_TEMP_C — independent measurement could refine this.
FIELD_MARGIN = 1.864

# Effective resistance coefficient — derived from physics + assumptions.
# Numerically ≈ 1/26 at the defaults (within 0.02 %); varies if a
# caller overrides COPPER_TEMP_C or FIELD_MARGIN.
RHO_COPPER = (
    RHO_COPPER_20C * (1 + ALPHA_COPPER * (COPPER_TEMP_C - 20)) * FIELD_MARGIN
)  # [Ω·mm²/m]

# Max acceptable voltage drop per NF C 15-100 / IEC 60364
VDROP_THRESHOLD_PERCENT = 5.0

# Slack added to straight-line map distance: accounts for routing around
# obstacles, coiling at both ends, and terrain detours
EXTRA_CABLE_LENGTH_M = 10.0  # [m]

# Max distance to snap a cable endpoint to a node
CONNECTION_THRESHOLD_M = 5.0  # [m]
