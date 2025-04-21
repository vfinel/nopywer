from qgis.core import QgsDistanceArea, QgsUnitTypes
from .get_layer import get_layer


def inspect_cable_layers(project, cablesLayersList, cables_dict):
    print('\n inspect cable layer:')
    verbose = 0
    inventory_3P = 785 # todo: smarter thing
    inventory_1P = 2340
    rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area
    tot1P = 0   # [m] total length of 1P cables 
    tot3P = 0   # [m] total length of 3P cables 
    n1P = 0     # total number of 1P cables
    n3P = 0     # total number of 3P cables
    currentOverloads = ''

    for cableLayerName in cablesLayersList:
        cableLayer = get_layer(project, cableLayerName)
        cables = cableLayer.getFeatures() # is an interator, so needs to be reset after each load
        totLayer = 0

        for cableIdx, cable in enumerate(cables):
            cableDict = cables_dict[cableLayerName][cableIdx]

            # --- get length 
            totLayer += cableDict["length"]
            msg = f'\t\tcable layer {cableLayerName} idx {cableIdx} has length {cableDict["length"]:.1f}m'
            if cableDict["length"] < 5:
                raise ValueError(msg)
            
            elif verbose:
                print(msg)

            # --- get cable area and plugs&sockets type 
            cableInfo = {"layer": cableLayerName, "idx": cableIdx}

            # --- compute resistance of cable 
            cableDict['r'] = rho*cableDict['length']/cableDict['area']
            
            # --- check current 
            if (cableDict['current']!=None) and (cableDict['plugsAndsockets']!=None):
                if max(cableDict['current']) >= 0.9*(cableDict['plugsAndsockets']):
                    currentStr = [ '%2.0f' % elem for elem in cableDict['current'] ]
                    a = f"\t /!\ cable {cableDict['nodes']} overload:"
                    b = f"{currentStr}A (plugs&sockets: {cableDict['plugsAndsockets']}A) \n"
                    currentOverloads += f"{a:60} {b}"

        nCablesInLayer = cableIdx+1
        if "1phase" in cableLayerName:
            tot1P += totLayer
            n1P += nCablesInLayer

        elif "3phases" in cableLayerName:
            tot3P += totLayer
            n3P += nCablesInLayer

        print(f'\t total length of {cableLayerName}: {totLayer:.0f} meters - {nCablesInLayer} cables')

    print(f'\t total length of 1P cables: {tot1P:.0f} meters (inventory: {inventory_1P}m) - {n1P} cables')
    print(f'\t total length of 3P cables: {tot3P:.0f} meters (inventory: {inventory_3P}m) - {n3P} cables')

    if (tot1P>0.95*inventory_1P) or (tot3P>0.95*inventory_3P):
        raise ValueError("You are running too short on cables (see above)")
    
    if len(currentOverloads)>0:
        print(f'\n{currentOverloads}')
    
    else:
        print(f'\t no overloaded cables')

    return cables_dict 

    