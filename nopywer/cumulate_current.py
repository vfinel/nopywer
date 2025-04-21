import numpy as np 

def cumulate_current(grid, cables_dict, dlist, V0, PF):
    verbose =  0
    if verbose: print('\ncumulate_current.py:')

    for deepness in range(len(dlist)-1, 0, -1):
        if verbose: print(f"\tdeepness: {deepness}")
        loads = dlist[deepness]
        for load in loads:
            parent = grid[load]['parent']
            
            if type(grid[load]['cum_power']).__module__ != 'numpy':
                grid[load]['cum_power'] = np.array([0.0]*3)
                
            if type(grid[parent]['cum_power']).__module__ != 'numpy':
                grid[parent]['cum_power'] = np.array([0.0]*3)

            # compute cumulated power for the load and its parent...        
            grid[load]['cum_power'] += grid[load]["power"] # ... at load 
            grid[parent]['cum_power'] += grid[load]["cum_power"] # ... and at parent

            # add info to cables_dict 
            cable = cables_dict[grid[load]['cable']['layer']][grid[load]['cable']['idx']]
            cable['current'] = list(grid[load]['cum_power']/V0/PF) # todo: constant power or constant voltage ?

            if verbose: 
                print(f"\t\t{load} cumulated power: {np.array2string(1e-3*grid[load]['cum_power'], precision=1, floatmode='fixed')}kW")

    if verbose: 
        load = 'generator'
        print(f"\t{load} cumulated power: {np.array2string(1e-3*grid[load]['cum_power'], precision=1, floatmode='fixed')}kW")

    return grid, cables_dict