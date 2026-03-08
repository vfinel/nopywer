from math import hypot

from pyproj import Transformer

DISTANCE_CRS = "EPSG:32630"  # valid in spain ! https://epsg.io/32630

_transformer = Transformer.from_crs("EPSG:4326", DISTANCE_CRS, always_xy=True)


def geodesic_distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """Return distance in metres after projecting lon/lat to the sizing CRS."""
    x1, y1 = _transformer.transform(lon1, lat1)
    x2, y2 = _transformer.transform(lon2, lat2)
    return hypot(x2 - x1, y2 - y1)
