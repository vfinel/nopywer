"""Tests for the diagnostic logging emitted by `nopywer.io.load_geojson`.

The loader is the project's front door for fixture data and silently
coerces a number of borderline inputs (unknown property keys).
This module pins the warnings/diagnostics that surface those
coercions so they cannot regress to silent behaviour.
"""

import logging

from nopywer.io import load_geojson


def _point_feature(name: str, **extra_props) -> dict:
    """A minimal valid Point feature with whatever extra properties given."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        "properties": {"name": name, "power": 1000.0, **extra_props},
    }


def _fc(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def test_int_phase_emits_no_warning(caplog):
    """A well-formed integer phase does not trigger any warnings.

    What: loading a Point feature with `phase: 2` produces no
    `WARNING`-level log records.
    """
    caplog.set_level(logging.WARNING, logger="nopywer.io")
    load_geojson(_fc(_point_feature("ok", phase=2)))
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_unknown_property_key_logs_a_debug_diagnostic(caplog):
    """An unrecognised property key surfaces at DEBUG level.

    What: loading a Point feature with a property key not in the
    known set (here, the typo `powr` for `power`) produces a
    `logging.DEBUG` record naming the feature and the unknown key.

    Why it matters: `load_geojson` silently ignores unknown keys —
    a typo for a known key (`powr` instead of `power`) would
    otherwise load with the default value and never get flagged.
    DEBUG (not WARNING) because legitimate exports also carry keys
    we don't read; this is a "if you suspect a typo, turn on DEBUG"
    aid, not a noisy default.
    """
    caplog.set_level(logging.DEBUG, logger="nopywer.io")
    load_geojson(_fc(_point_feature("typo_stage", powr=2000.0)))

    debug_records = [
        r for r in caplog.records if r.levelno == logging.DEBUG and "powr" in r.getMessage()
    ]
    assert len(debug_records) == 1
    assert "typo_stage" in debug_records[0].getMessage()


def test_recognised_export_keys_do_not_log(caplog):
    """Computed fields from a round-tripped nopywer export are silent.

    What: loading a Point feature with the full set of computed
    export keys (`voltage`, `vdrop_percent`, `cum_power_watts`,
    `distro`, ...) produces no DEBUG-level records about unknown
    keys.

    Why it matters: round-tripping an export back into the loader
    is the canonical workflow (see doc 11). If the loader warned on
    every computed field, the DEBUG channel would be useless noise
    every time someone reloads their own previous output.
    """
    caplog.set_level(logging.DEBUG, logger="nopywer.io")
    load_geojson(
        _fc(
            _point_feature(
                "exported",
                voltage=228.5,
                vdrop_percent=1.75,
                cum_power_watts=3000.0,
                distro={"in": "3P 32A", "out": {}},
                i_sc_ka=2.5,
                type="load",
            )
        )
    )
    unknown_debugs = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "not used by load_geojson" in r.getMessage()
    ]
    assert unknown_debugs == []
