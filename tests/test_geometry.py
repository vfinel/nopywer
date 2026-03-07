import pytest

from nopywer.geometry import DISTANCE_CRS, geodesic_distance_m


def test_geodesic_distance_uses_epsg_32630():
    assert DISTANCE_CRS == "EPSG:32630"
    assert geodesic_distance_m(-3.7038, 40.4168, -3.7030, 40.4176) == pytest.approx(
        111.77061893324682
    )


def test_geodesic_distance_is_zero_for_identical_points():
    assert geodesic_distance_m(-3.7038, 40.4168, -3.7038, 40.4168) == 0.0
