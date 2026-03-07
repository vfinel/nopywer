# Phase-to-neutral nominal voltage — European LV standard (IEC 60038)
V0 = 230  # [V]

# Power factor — typical for mixed resistive/inductive festival loads
# (lighting, fridges, sound systems)
PF = 0.9

# Conservative resistance coefficient for field cable sizing.
# This intentionally overestimates copper-only resistance to provide margin
# under real-world deployment conditions. Has been found in Rich's old notes,
# probably comes from measurements they did.
# For reference, physical value is 1 / 58 ^^
RHO_COPPER = 1 / 26  # [Ω·mm²/m]

# Max acceptable voltage drop per NF C 15-100 / IEC 60364
VDROP_THRESHOLD_PERCENT = 5.0

# Slack added to straight-line map distance: accounts for routing around
# obstacles, coiling at both ends, and terrain detours
EXTRA_CABLE_LENGTH_M = 10.0  # [m]

# Max distance to snap a cable endpoint to a node
CONNECTION_THRESHOLD_M = 5.0  # [m]
