import qgis.core
from qgis.core import (
  QgsGeometry,
  QgsGeometryCollection,
  QgsPoint,
  QgsPointXY,
  QgsWkbTypes,
  QgsProject,
  QgsFeatureRequest,
  QgsVectorLayer,
  QgsDistanceArea,
  QgsUnitTypes,
  QgsCoordinateTransform,
  QgsCoordinateReferenceSystem
)

# example made from https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis-101-viewing-vector-layer-attributes/

#  How to select a layer. 

# First possibility: select it on the GUI

# Second possibility: select by name (from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
layer_name = 'power usage' #'3phases'
layers = QgsProject.instance().mapLayersByName(layer_name)

if len(layers)==0:
    raise ValueError(f'layer "{layer_name}" does not exists')
    
elif len(layers)>1:
    #raise ValueError(f'multiple layers have the same name: "{layer_name}" ')
    layer = layers[0] # solution to select only first layer of that name...    
    
vlayer = iface.activeLayer()
print(vlayer)

# End of "How to select a layer." 


vlayer = iface.activeLayer() # get selected layer 

print("\nvlayer is: ")
print(vlayer)

# the command below is not super useful as it opens attributes in a GUI 
# iface.showAttributeTable(vlayer)

# get fieldnames of the selected layer
print("\nfieldnames of the selected layer are:")
for field in vlayer.fields():
    print(field.name())
    
# get values of one fieldname 
print("\n Some of the attributes of that layer:")
for feature in vlayer.getFeatures():
    #print(feature["power"]) # print watts usage
    fname = feature['name']
    fload = feature['power']
    print(f"\t{fname} uses {fload} kW")


