function select_layer_by_name(layer_name):
#layer_name = '3phases'
    layers = QgsProject.instance().mapLayersByName(layer_name)

    if len(layers)==0:
        raise ValueError(f'layer "{layer_name}" does not exists')
        
    elif len(layers)>1:
        #raise ValueError(f'multiple layers have the same name: "{layer_name}" ')
        layer = layers[0] # solution to select only first layer of that name...    
        
    vlayer = iface.activeLayer()
    print(vlayer)
    
    return vlayer