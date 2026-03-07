from pathlib import Path

import pandas as pd

from nopywer.inventory import (
    choose_cables_in_inventory,
    choose_distros_in_inventory,
)
from nopywer.models import Cable32A, PowerNode


def _write_ods(path: Path, sheet_name: str, data: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="odf") as writer:
        data.to_excel(writer, sheet_name=sheet_name, index=False)


def test_choose_cables_in_inventory_nominal_case(tmp_path, caplog):
    inventory_file = tmp_path / "cables_inventory.ods"
    _write_ods(
        inventory_file,
        "cables",
        pd.DataFrame(
            [
                {
                    "number of phases": 3,
                    "plugs&sockets [A]": 32.0,
                    "section [mm2]": 6.0,
                    "quantity": 1,
                    "length [m]": 11.0,  # algo is only happy if inventory has a lil bit more
                }
            ]
        ),
    )

    cables = {
        "c1": Cable32A(
            id="c1",
            length_m=10.0,
            from_node="generator",
            to_node="load_a",
        )
    }

    caplog.set_level("INFO", logger="nopywer.inventory")
    choose_cables_in_inventory(str(inventory_file), cables)

    assert "Reading cables inventory" in caplog.text
    assert "generator-load_a" not in caplog.text


def test_choose_distros_in_inventory_nominal_case(tmp_path):
    inventory_file = tmp_path / "distros_inventory.ods"
    _write_ods(
        inventory_file,
        "distros",
        pd.DataFrame(
            [
                {
                    "input - type": "3P",
                    "input - current [A]": 63.0,
                    "3P output - current [A]": 32.0,
                    "3P output - quantity": 1.0,
                    "3P 2nd output - current [A]": None,
                    "3P 2nd output - quantity": None,
                    "1P output - current [A]": None,
                    "1P output - quantity": None,
                    "how many distros": 1,
                }
            ]
        ),
    )

    grid = {
        "load_a": PowerNode(
            name="load_a",
            lon=0.0,
            lat=0.0,
            distro={"in": "3P 63A", "out": {"3P 32A": 1}},
        )
    }

    updated_grid = choose_distros_in_inventory(str(inventory_file), grid)

    assert updated_grid["load_a"].distro_chosen == {
        "in": "3P - 63A",
        "out": ["3P - 32A (x1)"],
    }
