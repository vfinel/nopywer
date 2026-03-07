import json
from pathlib import Path

from fastapi.testclient import TestClient

from nopywer.api import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_geojson(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _frontend_power_nodes() -> dict:
    sample_nodes_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "nopywer"
        / "frontend"
        / "data"
        / "power-nodes.geojson"
    )
    return json.loads(sample_nodes_path.read_text())


def test_optimize_returns_400_when_geojson_has_no_valid_nodes():
    response = client.post(
        "/api/v1/optimize",
        json={"nodes_geojson": _fixture_geojson("api_empty.geojson")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "No valid nodes found in GeoJSON"}


def test_optimize_returns_400_when_no_generator_is_provided():
    response = client.post(
        "/api/v1/optimize",
        json={"nodes_geojson": _fixture_geojson("api_no_generator.geojson")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "At least one generator is required"}


def test_optimize_returns_400_when_no_load_is_provided():
    response = client.post(
        "/api/v1/optimize",
        json={"nodes_geojson": _fixture_geojson("api_only_generator.geojson")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "At least one load is required"}


def test_optimize_returns_layout_for_bundled_frontend_power_nodes():
    response = client.post(
        "/api/v1/optimize",
        json={"nodes_geojson": _frontend_power_nodes()},
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["total_cable_length_m"] > 0
    assert payload["num_cables"] > 0


def test_frontend_companion_is_served_from_root():
    response = client.get("/")

    assert response.status_code == 200
    assert "Frontend for development only" in response.text
    assert "Optimize power layout" in response.text
