# Phase-to-neutral nominal voltage — European LV standard (IEC 60038)
V0 = 230  # [V]

# Power factor — typical for mixed resistive/inductive festival loads
# (lighting, fridges, sound systems)
PF = 0.9

# Effective copper resistivity accounting for temperature rise (~70 °C)
# and connector contact resistance. Textbook value at 20 °C is 1/56;
# 1/26 is the de-rated value commonly used for installation sizing.
RHO_COPPER = 1 / 26  # [Ω·mm²/m]

# Max acceptable voltage drop per NF C 15-100 / IEC 60364
VDROP_THRESHOLD_PERCENT = 5.0

# Slack added to straight-line map distance: accounts for routing around
# obstacles, coiling at both ends, and terrain detours
EXTRA_CABLE_LENGTH_M = 10.0  # [m]
