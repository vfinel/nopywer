import numpy as np 

# todo: 
# - ca commence a merder parce qu'il y a plein de points sur la carte qui ne sont pas sur la spreadsheet et vice versa 
# - une solution est de mettre des "if" partout mais ca ne facilite franchement pas la lecture 
#   --> faire un truc un peu plus propre en lisant la spreadsheet, et mettre des valeurs par défault dans grid[...] si besoin 
#       (power, phase, cumPower)
# - il faut sommer cumPower et pas power ! --> créer un "cumPower" pour chaque load, et si grid[load][child] = empty, then cumPower = power 
# 

print('\ncumulateCurrent.py:')
for deepness in range(len(dlist)-1, 0, -1):
    print(f"\tdeepness: {deepness}")
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

        print(f"\t\t{load} cumulated power: {np.array2string(1e-3*grid[load]['cumPower'], precision=1, floatmode='fixed')}kW")
            

    