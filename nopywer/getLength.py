# This sample of code shows how to measure :
#   - distance between two points.
#   - length of a (multi)line 
#
# it could be used to find with nodes is connected to which cable
#
# We'll use the class: QgsDistanceArea, and its methods:
#   - measureLength (argin: geometry)
#   - measureLine (args in : list of points)
#
# Documentation of the class:
# https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html#qgis.core.QgsDistanceArea
#
# Tutorial: "Santa claus is a workaholic and needs a summer break," in:
# https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/geometry.html

print('\n\n=================================================')
print('get length in meters')
print('=================================================')

d = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
d.setEllipsoid('WGS84')

# "layer" must be a Line layer
layer = iface.activeLayer()
print(f"\nlayer is : {layer}")
features = layer.getFeatures() # features is a iterator so needs to be recreated

for feature in features:
    
    # retrieve every feature with its geometry and attributes
    print("\nFeature ID: ", feature.id())
    
    # fetch geometry
    # show some information about the feature geometry
    geom = feature.geometry()
    geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
    
    if geom.type() == QgsWkbTypes.LineGeometry:
        if geomSingleType:
            x = geom.asPolyline()
            print("Line: ", x, "length: ", geom.length())
        else:
            x = geom.asMultiPolyline()
            print("MultiLine: ", x, "length: ", geom.length())
            
    else:
        print("Unknown or invalid geometry")
        
    # measure distance
    start = x[0][0] # <class 'qgis._core.QgsPointXY'>
    stop =  x[0][-1] 
    print("Distance in meters: ", d.measureLine(start, stop))
    print("Distance in meters: ", d.measureLength(geom))