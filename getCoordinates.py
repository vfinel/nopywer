def getCoordinates(feature):
    # this function returns geo-coordinates of a feature
    #
    # Code based on:
    # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/vector.html#iterating-over-vector-layer
    #
    
    print2debug = 0
    
    # fetch geometry
    geom = feature.geometry()
    geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
    if print2debug: print(f"geom.type() = {geom.type()}")
    
    if geom.type() == QgsWkbTypes.PointGeometry: # == 0
        # the geometry type can be of single or multi type
        if geomSingleType:
            x = geom.asPoint()
            if print2debug: print("Point: ", x)
        else:
            x = geom.asMultiPoint()
            if print2debug: print("MultiPoint: ", x)
            
    elif geom.type() == QgsWkbTypes.LineGeometry: # == 1
        if geomSingleType:
            x = geom.asPolyline()
            if print2debug: print("Line: ", x, "length: ", geom.length())
        else:
            x = geom.asMultiPolyline()
            if print2debug: print("MultiLine: ", x, "length: ", geom.length())
            # first point: x[0][0]
            # last point:  x[0][-1]
            
    elif geom.type() == QgsWkbTypes.PolygonGeometry: # == 2
        if geomSingleType:
            x = geom.asPolygon()
            if print2debug: print("Polygon: ", x, "Area: ", geom.area())
        else:
            x = geom.asMultiPolygon()
            if print2debug: print("MultiPolygon: ", x, "Area: ", geom.area())
            
    else:
        raise ValueError("Unknown or invalid geometry. Have a look on the map to see if object is properly defined? ")
        
    
    if len(x)==1:
        # i don't fully understand why i need to do that. Because the layer i work with 
        # are multiline /multipoint layers ?
        x = x[0]
        
    else:
        raise ValueError("why len(x)~=1 ?")
            
            
    return x