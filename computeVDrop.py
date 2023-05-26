import numpy as np 
V0 = 230
th_percent = 5
PF = 0.9 # todo: USE !!!
rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area

def getWireArea(cable): 
    # cable must be a grid[load]['cable'] dictionnary 
    # return area in mm²

    if ('nodes' in cable.keys()) and (('generator' in cable['nodes']) and (('werkhaus' in cable['nodes']) or ('malfaretotal' in cable['nodes']))):
        wireArea = 16
    
    elif cable['layer'] == '3phases_norg':
        wireArea = 6
    
    elif cable['layer'] == '1phase_norg':
        wireArea = 2.5
    
    else:
        raise ValueError("unable to determine wireArea of this cable")

    return wireArea


def computeVDrop(grid,load=None):
    # load is supposed to be a string 

    if load==None: # first call of the function. no vdrop at generator
        load = 'generator'
        grid[load]['voltage'] = V0
        grid[load]['vdrop_percent'] = 0
        
    else: # compute vdrop at load 
        parent = grid[load]['parent']
        cableArea = getWireArea(grid[load]['cable'])
        
        r = rho*grid[load]['cable']['length']/cableArea
        i = np.mean(grid[load]['cumPower'])/V0/PF # todo: think about maths !!!!!
        grid[load]['vdrop_volts'] = r*i
        grid[load]['voltage'] = grid[parent]['voltage'] - grid[load]['vdrop_volts']
        grid[load]['vdrop_percent'] = 100*(V0-grid[load]['voltage'])/V0/np.sqrt(3) # todo: l2l voltage or not ??

        # /!\ bug for isolation: why grid['isolation']['cable'] has not length, even if cabesDict['1phase_norg'][2] en a une ?
        # ---> pourquoi grid['isolation']['cable]l['length'] n'a pas été updatée ?
        print(f'\npropagating vdrop to {load}')
        print(f"cable: length {grid[load]['cable']['length']:.0f}m, area: {cableArea:.1f}mm²")
        print(f"grid[parent]['voltage']: {grid[parent]['voltage']:.0f}V")
        print(f"grid[load]['voltage']: {grid[load]['voltage']:.0f}V")
        print(f"grid[load]['vdrop_percent']: {grid[load]['vdrop_percent']:.1f}%")
        
        
        if grid[load]['vdrop_percent']>th_percent:
            print(f"/!\ {load} has a vdrop of {grid[load]['vdrop_percent']:.1f} percent!")

    # recursive call
    children = grid[load]['children'].keys()
    for child in children:
        grid = computeVDrop(grid, child)

    return grid