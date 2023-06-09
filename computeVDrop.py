import numpy as np 

# --- constant data 
V0 = 230
th_percent = 5
PF = 0.9 # todo: USE !!!
rho = 1/26 # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area

# --- parameters
vdrop_ref = np.sqrt(3)*V0
vdrop_coef = 1 #np.sqrt(3) # todo: change coef for 1-phase vs 3-phase https://drive.google.com/file/d/14_rlY05iPmopzXP5nSGixhvf_KH9mJ0p/view

verbose = 0


def computeVDrop(grid: dict, cablesDict: dict,load=None):
    # load is supposed to be a string
    verbose = 0
    if verbose: print(f'\n\t propagating vdrop to {load}')

    if load==None: # first call of the function. no vdrop at generator
        load = 'generator'
        grid[load]['voltage'] = V0
        grid[load]['vdrop_percent'] = 0
        
    else: # compute vdrop at load 
        parent = grid[load]['parent']
        cable = cablesDict[grid[load]['cable']['layer']][grid[load]['cable']['idx']]
        
        r = rho*cable['length']/cable['area']
        i = grid[load]['cumPower']/V0/PF # todo: constant power or constant voltage ?
        cable['vdrop_volts'] = vdrop_coef*r*np.max(i) 
        grid[load]['voltage'] = grid[parent]['voltage'] - cable['vdrop_volts']
        grid[load]['vdrop_percent'] = 100*(V0-grid[load]['voltage'])/vdrop_ref

        cable['r'] = r
        cable['current'] = list(i)

        if verbose:
            print(f"\t\t cable: length {cable['length']:.0f}m, area: {cableArea:.1f}mm²")
            print(f"\t\t grid[parent]['voltage']: {grid[parent]['voltage']:.0f}V")
            print(f"\t\t grid[load]['voltage']: {grid[load]['voltage']:.0f}V")
            print(f"\t\t grid[load]['vdrop_percent']: {grid[load]['vdrop_percent']:.1f}%")
        
        
        if grid[load]['vdrop_percent']>th_percent:
            print(f"\t /!\ vdrop of {grid[load]['vdrop_percent']:.1f} percent at {load}")

    # recursive call
    children = grid[load]['children'].keys()
    for child in children:
        [grid, cablesDict] = computeVDrop(grid, cablesDict, child)

    return grid, cablesDict
