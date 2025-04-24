# this code show how to get:
# - features of a layer
# - geometry of a feature
#
# It works for both Point layers and (multiple)line layers.
# Note that in the case of a multiple line, you may have more than 2 points,
# even if the line looks like having only 2 points (it depends on how you clicked)
#
#
# Code based on:
# https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/vector.html#iterating-over-vector-layer
#

from qgis.core import QgsApplication

if QgsApplication.instance() is not None:
    # "layer" is a QgsVectorLayer instance
    layer = iface.activeLayer()
    print(f"layer is : {layer}")
    features = layer.getFeatures()  # features is a iterator so needs to be recreated

    for feature in features:
        # retrieve every feature with its geometry and attributes
        print("\nFeature ID: ", feature.id())

        # fetch geometry
        # show some information about the feature geometry
        geom = feature.geometry()
        geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())

        if geom.type() == QgsWkbTypes.PointGeometry:
            # the geometry type can be of single or multi type
            if geomSingleType:
                x = geom.asPoint()
                print("Point: ", x)
            else:
                x = geom.asMultiPoint()
                print("MultiPoint: ", x)

        elif geom.type() == QgsWkbTypes.LineGeometry:
            if geomSingleType:
                x = geom.asPolyline()
                print("Line: ", x, "length: ", geom.length())
            else:
                x = geom.asMultiPolyline()
                print("MultiLine: ", x, "length: ", geom.length())
                # first point: x[0][0]
                # last point:  x[0][-1]

        elif geom.type() == QgsWkbTypes.PolygonGeometry:
            if geomSingleType:
                x = geom.asPolygon()
                print("Polygon: ", x, "Area: ", geom.area())
            else:
                x = geom.asMultiPolygon()
                print("MultiPolygon: ", x, "Area: ", geom.area())

        else:
            print("Unknown or invalid geometry")

        # fetch attributes
        attrs = feature.attributes()
        # attrs is a list. It contains all the attribute values of this feature
        print(attrs)

else:
    print("This code is an example code meant to be ran from pyQGIS console only.")
