from qgis.core import QgsDistanceArea
exec(Path('../nopywer/getLayer.py').read_text())

dClass = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
dClass.setEllipsoid('WGS84')


def getWireArea(cableInfo, cablesDict): 
    # cable must be a cablesGrid['layerName'][idx] dictionnary 
    # return area in mm²
    cable = cablesDict[cableInfo['layer']][cableInfo['idx']]

    goingToMalfare = any('malfare' in nodes for nodes in cable['nodes']) # to take into account 'malfareNode'
    if ('nodes' in cable.keys()) and (('generator' in cable['nodes']) and (('werkhaus' in cable['nodes']) or goingToMalfare or ('kunsthaus' in cable['nodes']))):
        wireArea = 16
        plugsAndSockets = 63

    elif '3phases' in cableInfo['layer']:
        wireArea = 6
        plugsAndSockets = 32

    elif '1phase' in cableInfo['layer']:
        wireArea = 2.5
        plugsAndSockets = 16
    
    else:
        raise ValueError(f"unable to determine wireArea of cable: {cable}")

    cable['area'] = wireArea
    cable['plugsAndsockets'] = plugsAndSockets

    return cablesDict


def inspectCableLayers(cablesLayersList, cablesDict):
    print('\n inspect cable layer:')
    verbose = 0
    inventory_3P = 845
    inventory_1P = 2020
    tot1P = 0
    tot3P = 0
    currentOverload = ''

    for cableLayerName in cablesLayersList:
        cableLayer = getLayer(cableLayerName)
        cables = cableLayer.getFeatures() # is an interator, so needs to be reset after each load
        totLayer = 0

        for cableIdx, cable in enumerate(cables):
            cableDict = cablesDict[cableLayerName][cableIdx]

            # --- get length 
            geom = cable.geometry()
            length = dClass.measureLength(geom)
            totLayer += length 
            msg = f"\t\tcable layer {cableLayerName} idx {cableIdx} has length {length:.1f}m"
            if length < 5:
                raise ValueError(msg)
            elif verbose:
                print(msg)

            # --- get cable area and plugs&sockets type 
            cableInfo = {"layer": cableLayerName, "idx": cableIdx}
            cablesDict = getWireArea(cableInfo, cablesDict)
            
            # --- check current 
            if (cableDict['current']!=None) and (cableDict['plugsAndsockets']!=None):
                if max(cableDict['current']) >= 0.9*(cableDict['plugsAndsockets']):
                    currentStr = [ '%.0f' % elem for elem in cableDict['current'] ]
                    currentOverload += f"\t cable between {cableDict['nodes']} is overloaded: {currentStr}A (plugs&sockets: {cableDict['plugsAndsockets']}A) \n"

            

            if verbose:
                print(f"cable: {cablesDict[cableLayerName][cableIdx]}")


        if "1phase" in cableLayerName:
            tot1P += totLayer
        elif "3phases" in cableLayerName:
            tot3P += totLayer
        
        print(f'\t total length of {cableLayerName}: {totLayer:.0f} meters')

    print(f'\t total length of 1P cables: {tot1P:.0f} meters (inventory: {inventory_1P}m)')
    print(f'\t total length of 3P cables: {tot3P:.0f} meters (inventory: {inventory_3P}m)')

    if (tot1P>0.9*inventory_1P) or (tot3P>0.9*inventory_3P):
        raise ValueError("You are running too short on cables (see above)")
    
    if len(currentOverload)>0:
        print(f'\n{currentOverload}')
    else:
        print(f'\t no overloaded cables')

    return cablesDict 

    