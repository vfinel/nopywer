import numpy as np
import pytest

from nopywer.models import (
    CABLE_TYPES,
    Cable,
    Cable16A,
    Cable32A,
    Cable63A,
    Cable125A,
    PowerGrid,
    PowerNode,
    pick_cable_for,
)


@pytest.mark.parametrize(
    "power_watts, expected_cls",
    [
        (0, Cable16A),
        (1000, Cable16A),
        (3312, Cable16A),
        (3313, Cable32A),
        (10_000, Cable32A),
        (19_872, Cable32A),
        (19_873, Cable63A),
        (39_123, Cable63A),
        (39_124, Cable125A),
        (77_625, Cable125A),
        (100_000, Cable125A),
    ],
)
def test_pick_cable_for(power_watts, expected_cls):
    assert pick_cable_for(power_watts) is expected_cls




def test_cable_to_geojson():
    cable = Cable32A(
        id="c1",
        length_m=25.5,
        from_node="gen",
        to_node="load_a",
        from_coords=(2.35, 48.85),
        to_coords=(2.36, 48.86),
        current_per_phase=[10.5, 10.5, 10.5],
        vdrop_volts=1.23,
    )
    gj = cable.to_geojson()

    assert gj["type"] == "Feature"
    assert gj["geometry"]["type"] == "LineString"
    assert gj["geometry"]["coordinates"] == [[2.35, 48.85], [2.36, 48.86]]

    props = gj["properties"]
    assert props["id"] == "c1"
    assert props["nodes"] == ["gen", "load_a"]
    assert props["from"] == "gen"
    assert props["to"] == "load_a"
    assert props["length_m"] == 25.5
    assert props["area_mm2"] == 6.0
    assert props["plugs_and_sockets_a"] == 32.0
    assert props["cable_type"] == "3P 32A — 6.0mm²"
    assert props["current_a"] == 10.5
    assert props["cum_power_kw"] == 6.52
    assert props["vdrop_volts"] == 1.23


def test_power_node_to_geojson():
    node = PowerNode(
        name="bar_south",
        lon=2.35,
        lat=48.85,
        power_watts=3000.0,
        power_per_phase=np.array([1000.0, 1000.0, 1000.0]),
        cum_power=np.array([2000.0, 2000.0, 2000.0]),
        voltage=228.5,
        vdrop_percent=1.75,
        distro={"in": "3P 32A", "out": {"1P 16A": 2}},
    )
    gj = node.to_geojson()

    assert gj["type"] == "Feature"
    assert gj["geometry"]["type"] == "Point"
    assert gj["geometry"]["coordinates"] == [2.35, 48.85]

    props = gj["properties"]
    assert props["name"] == "bar_south"
    assert props["type"] == "load"
    assert props["power_watts"] == 3000.0
    assert props["cum_power_watts"] == 6000.0
    assert props["voltage"] == 228.5
    assert props["vdrop_percent"] == 1.75
    assert props["distro"] == {"in": "3P 32A", "out": {"1P 16A": 2}}


def test_generator_node_to_geojson():
    node = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    assert node.to_geojson()["properties"]["type"] == "generator"


def test_power_grid_resolves_generator_once():
    generator = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load_a", lon=1.0, lat=1.0)

    grid = PowerGrid(nodes={"generator": generator, "load_a": load}, cables={})

    assert grid.generator is generator


def test_power_grid_to_geojson_includes_nodes_and_cables():
    generator = PowerNode(name="generator", lon=0.0, lat=0.0, is_generator=True)
    load = PowerNode(name="load_a", lon=1.0, lat=1.0)
    cable = Cable(id="c1", length_m=10.0, from_node="generator", to_node="load_a")

    grid = PowerGrid(
        nodes={"generator": generator, "load_a": load},
        cables={"c1": cable},
    )

    geojson = grid.to_geojson()

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 3


def test_cable_rounds_on_set():
    cable = Cable(id="c", length_m=12.3456)
    assert cable.length_m == 12.3

    cable.vdrop_volts = 1.23456
    assert cable.vdrop_volts == 1.23

    cable.current_per_phase = [10.556, 10.556, 10.556]
    assert cable.current_per_phase == [10.56, 10.56, 10.56]


def test_power_node_rounds_on_set():
    node = PowerNode(name="n", lon=0.0, lat=0.0, voltage=228.777)
    assert node.voltage == 228.8

    node.vdrop_percent = 1.23456
    assert node.vdrop_percent == 1.23
