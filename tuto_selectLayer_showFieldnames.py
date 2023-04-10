# example made from https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis-101-viewing-vector-layer-attributes/

print('\n===================================================================\n')

# ------ How to select a layer. 
print('how to select a layer:')

# First possibility: select it on the GUI
#layer = iface.activeLayer()

# Second possibility: select by name (from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
layer_name = 'power usage' #
#layer_name = '3phases_norg'
layers = QgsProject.instance().mapLayersByName(layer_name)

if len(layers)==0:
    raise ValueError(f'layer "{layer_name}" does not exists')
    
elif len(layers)>1:
    raise ValueError(f'multiple layers have the same name: "{layer_name}" ')
    layer = layers[0] # solution to select only first layer of that name...    
    
print(layer)

# ------ End of "How to select a layer." 


# layer = iface.activeLayer() # get selected layer 

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
    #print(feature["watts"]) # print watts usage
    fname = feature['name']
    fload = feature['watts']
    print(f"\t{fname} uses {fload} kW")


