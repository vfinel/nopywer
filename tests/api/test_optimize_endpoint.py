import pytest
from fastapi import HTTPException

from nopywer.api import OptimizeRequest, optimize


def _point_feature(name: str, lon: float, lat: float, power_watts: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "power": power_watts},
    }


def _feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def test_optimize_endpoint_rejects_empty_geojson():
    req = OptimizeRequest(nodes_geojson=_feature_collection([]))
    with pytest.raises(HTTPException) as exc:
        optimize(req)
    assert exc.value.status_code == 400
    assert "No valid nodes" in str(exc.value.detail)


def test_optimize_endpoint_requires_generator():
    req = OptimizeRequest(
        nodes_geojson=_feature_collection([_point_feature("load_a", 0.0, 0.0, 1000)]),
    )
    with pytest.raises(HTTPException) as exc:
        optimize(req)
    assert exc.value.status_code == 400
    assert "At least one generator is required" in str(exc.value.detail)


def test_optimize_endpoint_requires_loads():
    req = OptimizeRequest(
        nodes_geojson=_feature_collection([_point_feature("generator", 0.0, 0.0, 0)]),
    )
    with pytest.raises(HTTPException) as exc:
        optimize(req)
    assert exc.value.status_code == 400
    assert "At least one load is required" in str(exc.value.detail)


def test_optimize_endpoint_returns_cables_for_valid_input():
    req = OptimizeRequest(
        nodes_geojson=_feature_collection(
            [
                _point_feature("generator", 0.0, 0.0, 0),
                _point_feature("load_a", 0.001, 0.0, 1200),
                _point_feature("load_b", 0.0, 0.001, 1800),
            ]
        ),
        extra_cable_m=0.0,
    )
    resp = optimize(req)

    assert resp.num_cables == 2
    assert resp.total_cable_length_m > 0
    assert resp.cables_geojson["type"] == "FeatureCollection"

    line_features = [
        f for f in resp.cables_geojson["features"] if f.get("geometry", {}).get("type") == "LineString"
    ]
    assert len(line_features) == 2
