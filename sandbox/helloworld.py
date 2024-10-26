print('lets go')
from qgis.core import QgsProject

layer = QgsProject.instance().mapLayersByName("1phase")[0]
# layer is an object. access its methods with dir(layer)
# to know what type of object: layer.fskjgd and read error message

iface.setActiveLayer(layer)

if gPnt.wkbType() == QgsWkbTypes.Point:
  print(gPnt.wkbType())
  # output: 1 for Point

if gLine.wkbType() == QgsWkbTypes.LineString:
  print(gLine.wkbType())
  # output: 2 for LineString

if gPolygon.wkbType() == QgsWkbTypes.Polygon:
  print(gPolygon.wkbType())

  # output: 3 for Polygon
  
## Point layer
#for f in layer.getFeatures():
#    geom = f.geometry()
#    print ('%f, %f' % (geom.asPoint().y(), geom.asPoint().x()))