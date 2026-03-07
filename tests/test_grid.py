from nopywer.grid import PowerGrid
from nopywer.models import Cable, PowerNode


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

    grid._compute_voltage_drop("generator")

    assert cable.vdrop_volts == 10.0
    assert load.voltage == 220.0
    assert load.vdrop_percent == 4.35
