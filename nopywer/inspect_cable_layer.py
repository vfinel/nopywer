from qgis.core import QgsDistanceArea, QgsUnitTypes
from .get_layer import get_layer


def inspect_cable_layers(project, cables_layers_list, cables_dict):
    print('\n inspect cable layer:')
    verbose = 0
    inventory_3P = 785 # todo: smarter thing
    inventory_1P = 2340
    rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area
    tot1P = 0   # [m] total length of 1P cables 
    tot3P = 0   # [m] total length of 3P cables 
    n1P = 0     # total number of 1P cables
    n3P = 0     # total number of 3P cables
    current_overloads = ''

    for cable_layer_name in cables_layers_list:
        cable_layer = get_layer(project, cable_layer_name)
        cables = cable_layer.getFeatures() # is an interator, so needs to be reset after each load
        totLayer = 0

        for cable_idx, cable in enumerate(cables):
            cableDict = cables_dict[cable_layer_name][cable_idx]

            # --- get length 
            totLayer += cableDict["length"]
            msg = f'\t\tcable layer {cable_layer_name} idx {cable_idx} has length {cableDict["length"]:.1f}m'
            if cableDict["length"] < 5:
                raise ValueError(msg)
            
            elif verbose:
                print(msg)

            # --- get cable area and plugs&sockets type 
            cable_info = {"layer": cable_layer_name, "idx": cable_idx}

            # --- compute resistance of cable 
            cableDict['r'] = rho*cableDict['length']/cableDict['area']
            
            # --- check current 
            if (cableDict['current']!=None) and (cableDict['plugsAndsockets']!=None):
                if max(cableDict['current']) >= 0.9*(cableDict['plugsAndsockets']):
                    current_str = [ '%2.0f' % elem for elem in cableDict['current'] ]
                    a = f"\t /!\ cable {cableDict['nodes']} overload:"
                    b = f"{current_str}A (plugs&sockets: {cableDict['plugsAndsockets']}A) \n"
                    current_overloads += f"{a:60} {b}"

        n_cables_in_layer = cable_idx+1
        if "1phase" in cable_layer_name:
            tot1P += totLayer
            n1P += n_cables_in_layer

        elif "3phases" in cable_layer_name:
            tot3P += totLayer
            n3P += n_cables_in_layer

        print(f'\t total length of {cable_layer_name}: {totLayer:.0f} meters - {n_cables_in_layer} cables')

    print(f'\t total length of 1P cables: {tot1P:.0f} meters (inventory: {inventory_1P}m) - {n1P} cables')
    print(f'\t total length of 3P cables: {tot3P:.0f} meters (inventory: {inventory_3P}m) - {n3P} cables')

    if (tot1P>0.95*inventory_1P) or (tot3P>0.95*inventory_3P):
        raise ValueError("You are running too short on cables (see above)")
    
    if len(current_overloads)>0:
        print(f'\n{current_overloads}')
    
    else:
        print(f'\t no overloaded cables')

    return cables_dict 

    