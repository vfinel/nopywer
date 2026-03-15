import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nopywer.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_optimize_network_writes_output_geojson(tmp_path):
    output_geojson = tmp_path / "network_layout.geojson"

    result = runner.invoke(
        app,
        [
            "optimize-network",
            str(FIXTURES / "input_nodes.geojson"),
            "--output-geojson",
            str(output_geojson),
            "--extra-cable-m",
            "0",
        ],
    )

    assert result.exit_code == 0
    assert output_geojson.exists()

    payload = json.loads(output_geojson.read_text())
    line_features = [
        feature
        for feature in payload["features"]
        if feature.get("geometry", {}).get("type") == "LineString"
    ]

    assert payload["type"] == "FeatureCollection"
    assert line_features
