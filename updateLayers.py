exec(Path('../nopywer/getLayer.py').read_text())

#based on https://gis.stackexchange.com/questions/428973/writing-list-as-attribute-field-in-pyqgis


def updateLayers(grid: dict, cables: dict):

    print('\nupdatingLayers...')
    # print(json.dumps(cables, sort_keys=True, indent=4))

    # write phase (=attribute) for each cable (=feature) of each cable layer
    for cableLayerName in cables.keys():
        if "1phase" in cableLayerName:
            cableLayer = getLayer(cableLayerName)
            if cableLayer.isEditable()==False:
                with edit(cableLayer):
                    for i,cable in enumerate(list(cableLayer.getFeatures())):
                        phase = cables[cableLayerName][i]['phase']
                        cable.setAttribute('phase', f'{phase}')
                        cableLayer.updateFeature(cable)

            else:
                raise ValueError(f'Layer "{cableLayerName}" cannot be edited by nopywer '\
                                 'because it is already in edit mode in QGIS. Please untoggle edit mode.')

    # write nodes' power and cumPower (=attributes) for each nodes (=feature) of load layer

    
    return None