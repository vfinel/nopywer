from qgis.core import QgsDistanceArea
exec(Path('../nopywer/getLayer.py').read_text())

dClass = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
dClass.setEllipsoid('WGS84')


def getWireArea(cableInfo, cablesDict): 
    # cable must be a cablesGrid['layerName'][idx] dictionnary 
    # return area in mm²
    cable = cablesDict[cableInfo['layer']][cableInfo['idx']]

    toMalfare = any('malfare' in nodes for nodes in cable['nodes']) # takes into account 'malfareNode'
    fromGenerator = ('generator' in cable['nodes'])
    is16smm = ('nodes' in cable.keys()) and (fromGenerator and toMalfare)
    if is16smm:
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
    rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area
    tot1P = 0
    tot3P = 0
    currentOverloads = ''

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

            # --- compute resistance of cable 
            cableDict['r'] = rho*cableDict['length']/cableDict['area']
            
            # --- check current 
            if (cableDict['current']!=None) and (cableDict['plugsAndsockets']!=None):
                if max(cableDict['current']) >= 0.9*(cableDict['plugsAndsockets']):
                    currentStr = [ '%2.0f' % elem for elem in cableDict['current'] ]
                    a = f"\t /!\ cable {cableDict['nodes']} overload:"
                    b = f"{currentStr}A (plugs&sockets: {cableDict['plugsAndsockets']}A) \n"
                    currentOverloads += f"{a:60} {b}"

        if "1phase" in cableLayerName:
            tot1P += totLayer
        elif "3phases" in cableLayerName:
            tot3P += totLayer
        
        print(f'\t total length of {cableLayerName}: {totLayer:.0f} meters')

    print(f'\t total length of 1P cables: {tot1P:.0f} meters (inventory: {inventory_1P}m)')
    print(f'\t total length of 3P cables: {tot3P:.0f} meters (inventory: {inventory_3P}m)')

    if (tot1P>0.9*inventory_1P) or (tot3P>0.9*inventory_3P):
        raise ValueError("You are running too short on cables (see above)")
    
    if len(currentOverloads)>0:
        print(f'\n{currentOverloads}')
    else:
        print(f'\t no overloaded cables')

    return cablesDict 

    