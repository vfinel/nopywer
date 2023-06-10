import numpy as np 

def cumulateCurrent(grid, cablesDict, dlist):
    verbose =  0
    if verbose: print('\ncumulateCurrent.py:')

    for deepness in range(len(dlist)-1, 0, -1):
        if verbose: print(f"\tdeepness: {deepness}")
        loads = dlist[deepness]
        for load in loads:
            parent = grid[load]['parent']
            
            if type(grid[load]['cumPower']).__module__ != 'numpy':
                grid[load]['cumPower'] = np.array([0.0]*3)
            if type(grid[parent]['cumPower']).__module__ != 'numpy':
                grid[parent]['cumPower'] = np.array([0.0]*3)

            # compute cumulated power for the load and its parent...        
            grid[load]['cumPower'] += grid[load]["power"] # ... at load 
            grid[parent]['cumPower'] += grid[load]["cumPower"] # ... and at parent

            # add info to cablesDict 
            cable = cablesDict[grid[load]['cable']['layer']][grid[load]['cable']['idx']]
            cable['current'] = list(grid[load]['cumPower']/V0/PF) # todo: constant power or constant voltage ?

            if verbose: 
                print(f"\t\t{load} cumulated power: {np.array2string(1e-3*grid[load]['cumPower'], precision=1, floatmode='fixed')}kW")

    if verbose: 
        load = 'generator'
        print(f"\t{load} cumulated power: {np.array2string(1e-3*grid[load]['cumPower'], precision=1, floatmode='fixed')}kW")

    return grid, cablesDict