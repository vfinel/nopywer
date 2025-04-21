from qgis.core import edit, QgsProject
from .get_layer import get_layer
from .get_grid_geometry import get_load_name

#based on https://gis.stackexchange.com/questions/428973/writing-list-as-attribute-field-in-pyqgis


def update1PhaseLayers(grid: dict, cables: dict, project: QgsProject):
    verbose = 0
    
    print('\nupdating 1-phase layers with phase label...')
    
    # write phase (=attribute) for each cable (=feature) of each cable layer
    for cable_layer_name in cables.keys():
        if "1phase" in cable_layer_name:
            if verbose: print(f'\t cable layer {cable_layer_name}')
            cableLayer = get_layer(project, cable_layer_name)
            if cableLayer.isEditable()==False:
                with edit(cableLayer):
                    for i,cable in enumerate(list(cableLayer.getFeatures())):
                        if cables[cable_layer_name][i]['current'] != None: # don't update not connecte cables
                            phase = cables[cable_layer_name][i]['phase']                        
                            if phase==None:
                                phase = 0
                            
                            if verbose: print(f'\t\t cable idx {i} on phase {phase} (type: {type(phase)})')
                            if phase == 'T':
                                raise ValueError(f'cable idx {i} cannot be on phase "{phase}" because it is in a single phase layer.')

                            cable.setAttribute('phase', f'{phase}')
                            try:
                                cableLayer.updateFeature(cable)

                            except ValueError as err:
                                print(f'problem found in {cable_layer_name} while updating cable idx {i} with phase info "{phase}":')
                                print(err.args)
                                raise ValueError(err.args)
                                                

            else:
                raise ValueError(f'Layer "{cable_layer_name}" cannot be edited by nopywer '\
                                 'because it is already in edit mode in QGIS. Please untoggle edit mode.')
 
    return None


def updateLoadLayers(grid: dict, loadLayersList: list, project: QgsProject):
    # write nodes' power and cumPower (=attributes) for each nodes (=feature) of load layer
    print('\nupdating load layers with power usage and cumulated power...')
    for loadLayerName in loadLayersList:
        layer = get_layer(project, loadLayerName)
        if layer.isEditable()==False:
            with edit(layer):
                for load in list(layer.getFeatures()):
                    loadName = get_load_name(load)
                    
                    if loadName in grid.keys():
                        field = 'power'
                        assert field in load.fields().names(), f'layer "{loadLayerName} does not have a field "{field}"'
                        load.setAttribute(field, f"{1e-3*grid[loadName]['power'].sum()}")
                        
                        field = 'cumPower'
                        if type(grid[loadName][field])!=type(None): # this can be False if load is not connected
                            assert field in load.fields().names(), f'layer "{loadLayerName}" does not have a field "{field}"'
                            load.setAttribute(field, f"{1e-3*sum(grid[loadName]['cumPower'])}")
                        
                        layer.updateFeature(load)
            
        else:
            raise ValueError(f'Layer "{loadName}" cannot be edited by nopywer '\
                                'because it is already in edit mode in QGIS. Please untoggle edit mode.')
            
    return None
