from qgis.core import edit, QgsProject
from getLayer import getLayer
from getGridGeometry import getLoadName

#based on https://gis.stackexchange.com/questions/428973/writing-list-as-attribute-field-in-pyqgis


def update1PhaseLayers(grid: dict, cables: dict, project: QgsProject):
    print('\nupdating 1-phase layers with phase label...')

    # write phase (=attribute) for each cable (=feature) of each cable layer
    for cableLayerName in cables.keys():
        if "1phase" in cableLayerName:
            cableLayer = getLayer(project, cableLayerName)
            if cableLayer.isEditable()==False:
                with edit(cableLayer):
                    for i,cable in enumerate(list(cableLayer.getFeatures())):
                        phase = cables[cableLayerName][i]['phase']
                        cable.setAttribute('phase', f'{phase}')
                        cableLayer.updateFeature(cable)

            else:
                raise ValueError(f'Layer "{cableLayerName}" cannot be edited by nopywer '\
                                 'because it is already in edit mode in QGIS. Please untoggle edit mode.')
 
    return None


def updateLoadLayers(grid: dict, loadLayersList: list, project: QgsProject):
    # write nodes' power and cumPower (=attributes) for each nodes (=feature) of load layer
    print('\nupdating load layers with with power usage and cumulated power...')
    for loadLayerName in loadLayersList:
        layer = getLayer(project, loadLayerName)
        if layer.isEditable()==False:
            with edit(layer):
                for load in list(layer.getFeatures()):
                    loadName = getLoadName(load)
                    
                    field = 'power'
                    assert field in load.fields().names(), f'layer "{loadLayerName} does not have a field "{field}"'
                    load.setAttribute(field, f"{1e-3*sum(grid[loadName]['power'])}")
                    
                    if type(grid[loadName]['cumPower'])!=type(None): # this can be False if load is not connected
                        field = 'cumPower'
                        assert field in load.fields().names(), f'layer "{loadLayerName} does not have a field "{field}"'
                        load.setAttribute(field, f"{1e-3*sum(grid[loadName]['cumPower'])}")
                    
                    layer.updateFeature(load)
            
        else:
            raise ValueError(f'Layer "{loadName}" cannot be edited by nopywer '\
                                'because it is already in edit mode in QGIS. Please untoggle edit mode.')
            
    return None
