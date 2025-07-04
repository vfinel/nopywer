from qgis.core import QgsProject


def get_layer(project, layer_name: str):
    # from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
    layers = project.mapLayersByName(layer_name)
    if len(layers) == 0:
        names = [layer.name() for layer in project.mapLayers().values()]
        print("\n".join(names))
        raise ValueError(
            f'layer "{layer_name}" does not exists. Existing layers are \n {names}'
        )

    elif len(layers) > 1:
        raise ValueError(f'multiple layers have the same name: "{layer_name}" ')
        layer = layers[0]  # solution to select only first layer of that name...

    # layer = iface.activeLayer() # to get selected layer on the GUI
    layer = layers[0]
    return layer
