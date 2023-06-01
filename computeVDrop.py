import numpy as np 
V0 = 230
th_percent = 5
PF = 0.9 # todo: USE !!!
rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area

def getWireArea(cable): 
    # cable must be a grid[load]['cable'] dictionnary 
    # return area in mm²
    
    goingToMalfare = any('malfare' in nodes for nodes in cable['nodes']) # to take into account 'malfareNode'
    if ('nodes' in cable.keys()) and (('generator' in cable['nodes']) and (('werkhaus' in cable['nodes']) or goingToMalfare or ('kunsthaus' in cable['nodes']))):
        wireArea = 16
    
    elif '3phases' in cable['layer']:
        wireArea = 6
    
    elif '1phase' in cable['layer']:
        wireArea = 2.5
    
    else:
        raise ValueError(f"unable to determine wireArea of cable: {cable}")

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
        i = np.max(grid[load]['cumPower'])/V0/PF # todo: think about maths !!!!!
        grid[load]['cable']['vdrop_volts'] = np.sqrt(3)*r*i # todo: change coef for 1-phase vs 3-phase https://drive.google.com/file/d/14_rlY05iPmopzXP5nSGixhvf_KH9mJ0p/view
        grid[load]['voltage'] = grid[parent]['voltage'] - grid[load]['cable']['vdrop_volts']
        grid[load]['vdrop_percent'] = 100*(V0-grid[load]['voltage'])/V0

        # /!\ bug for isolation: why grid['isolation']['cable'] has not length, even if cabesDict['1phase_norg'][2] en a une ?
        # ---> pourquoi grid['isolation']['cable]l['length'] n'a pas été updatée ?
        print(f'\npropagating vdrop to {load}')
        print(f"\tcable: length {grid[load]['cable']['length']:.0f}m, area: {cableArea:.1f}mm²")
        print(f"\tgrid[parent]['voltage']: {grid[parent]['voltage']:.0f}V")
        print(f"\tgrid[load]['voltage']: {grid[load]['voltage']:.0f}V")
        print(f"\tgrid[load]['vdrop_percent']: {grid[load]['vdrop_percent']:.1f}%")
        
        
        if grid[load]['vdrop_percent']>th_percent:
            print(f"/!\ {load} has a vdrop of {grid[load]['vdrop_percent']:.1f} percent!")

    # recursive call
    children = grid[load]['children'].keys()
    for child in children:
        grid = computeVDrop(grid, child)

    return grid