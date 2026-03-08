from pathlib import Path

import pytest

from nopywer.analyze import _compute_voltage_drop, analyze
from nopywer.io import print_grid_info
from nopywer.models import Cable, PowerGrid, PowerNode

FIXTURES = Path(__file__).parent / "fixtures"


def test_analyze_nominal_case_logs_grid_info(caplog):
    input_file = FIXTURES / "analyze_input.geojson"
    grid = PowerGrid.from_geojson(input_file)

    caplog.set_level("INFO")
    analyze(grid)
    print_grid_info(grid.nodes, grid.cables, grid.tree, grid.generator)

    assert "total power: 9kW" in caplog.text
    assert "phase balance:" in caplog.text
    assert "village generator" in caplog.text
    assert "load a" in caplog.text
    assert "load b" in caplog.text

    output_geojson = grid.to_geojson()
    point_features = [
        feature for feature in output_geojson["features"] if feature["geometry"]["type"] == "Point"
    ]
    assert len(point_features) == 3
    assert any(
        feature["properties"]["name"] == "village generator"
        and feature["properties"]["cum_power_watts"] == 9000.0
        for feature in point_features
    )


def test_analyze_uses_detected_generator_name_from_geojson():
    input_file = FIXTURES / "analyze_named_generator.geojson"
    grid = PowerGrid.from_geojson(input_file)

    analyze(grid)

    assert grid.generator.name == "smurf village generator"
    assert grid.tree == [["smurf village generator"], ["load a"]]
    assert grid.nodes["load a"].parent == "smurf village generator"


def test_analyze_raises_when_multiple_generators_are_present():
    input_file = FIXTURES / "analyze_multiple_generators.geojson"
    with pytest.raises(ValueError, match="Only one generator is supported for now"):
        PowerGrid.from_geojson(input_file)


def test_analyze_raises_when_no_cables_are_present():
    input_file = FIXTURES / "analyze_no_cables.geojson"
    grid = PowerGrid.from_geojson(input_file)

    with pytest.raises(ValueError, match="At least one cable is required"):
        analyze(grid)


def test_compute_voltage_drop_uses_phase_voltage_reference():
    generator = PowerNode(
        name="generator",
        lon=0.0,
        lat=0.0,
        is_generator=True,
        children={"load_a": "c1"},
        voltage=230.0,
    )
    load = PowerNode(
        name="load_a",
        lon=0.0,
        lat=0.0,
        parent="generator",
        cable_to_parent="c1",
    )
    cable = Cable(
        id="c1",
        length_m=26.0,
        area_mm2=1.0,
        from_node="generator",
        to_node="load_a",
        current_per_phase=[10.0],
    )
    grid = PowerGrid(
        nodes={"generator": generator, "load_a": load},
        cables={"c1": cable},
    )

    _compute_voltage_drop(grid)

    assert cable.vdrop_volts == 10.0
    assert load.voltage == 220.0
    assert load.vdrop_percent == 4.35
