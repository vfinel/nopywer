from pyproj import Geod

_geod = Geod(ellps="WGS84")


def geodesic_distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    _, _, dist = _geod.inv(lon1, lat1, lon2, lat2)
    return dist
