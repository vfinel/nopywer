# from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879

layer_name = "3phases_norg"
layers = QgsProject.instance().mapLayersByName(layer_name)

if len(layers) == 0:
    raise ValueError(f'layer "{layer_name}" does not exists')

elif len(layers) > 1:
    raise ValueError(f'multiple layers have the same name: "{layer_name}" ')
    layer = layers[0]  # solution to select only first layer of that name...

# layer = iface.activeLayer() # to get selected layer on the GUI
layer = layers
print(layer)
