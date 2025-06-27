from qgis.core import QgsWkbTypes
from .logger_config import logger


def get_coordinates(feature):
    # this function returns geo-coordinates of a feature
    #
    # Code based on:
    # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/vector.html#iterating-over-vector-layer
    #

    # fetch geometry
    geom = feature.geometry()
    geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
    logger.trace(f"{geom.type() = }, {geom.wkbType():}")

    if geom.type() == QgsWkbTypes.PointGeometry:  # == 0
        # the geometry type can be of single or multi type
        if geomSingleType:
            x = geom.asPoint()
            logger.trace(f"Point: {x}")

        else:
            x = geom.asMultiPoint()
            logger.trace(f"MultiPoint: {x}")

    elif geom.type() == QgsWkbTypes.LineGeometry:  # == 1
        if geomSingleType:
            x = geom.asPolyline()
            logger.trace(f"Line:  {x}, length: {geom.length()}")

        else:
            x = geom.asMultiPolyline()
            logger.trace(f"MultiLine:  {x}, length: {geom.length()}")
            # first point: x[0][0]
            # last point:  x[0][-1]

    elif geom.type() == QgsWkbTypes.PolygonGeometry:  # == 2
        if geomSingleType:
            x = geom.asPolygon()
            logger.trace(f"Polygon: {x}, Area: {geom.area()}")

        else:
            x = geom.asMultiPolygon()
            logger.trace(f"MultiPolygon: {x}, Area: {geom.area()}")

    else:
        raise ValueError(
            f"Unknown or invalid geometry. Have a look on the map to see if object is properly defined? \n geom: {geom} "
        )

    if not geomSingleType:
        if len(x) == 1:
            # extract first point (the only one)
            x = x[0]

        else:
            logger.info(f"geom {geom.type()}")
            logger.info(f"x: {x}, x[0]={x[0]}, x[1]={x[1]}")
            raise ValueError(
                "geometry 'x' has multiple objects in it ? it is unexpected."
            )

    return x
