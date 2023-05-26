import numpy as np 

# todo: 
# - ca commence a merder parce qu'il y a plein de points sur la carte qui ne sont pas sur la spreadsheet et vice versa 
# - une solution est de mettre des "if" partout mais ca ne facilite franchement pas la lecture 
#   --> faire un truc un peu plus propre en lisant la spreadsheet, et mettre des valeurs par défault dans grid[...] si besoin 
#       (power, phase, cumPower)
# - il faut sommer cumPower et pas power ! --> créer un "cumPower" pour chaque load, et si grid[load][child] = empty, then cumPower = power 
# 

print('\n cumulateCurrent.py:')
for deepness in range(dmax, 0, -1):
    print(f"deepness: {deepness}")
    loads = dlist[deepness]
    for load in loads:
        parent = grid[load]['parent']
        ph = grid[load]["phase"]
        print(f'\t load: {load} is connected to {parent} on phase {ph}')
        
        if type(grid[load]['cumPower']).__module__ != 'numpy':
            grid[load]['cumPower'] = np.array([0.0]*3)
            
        if type(grid[parent]['cumPower']).__module__ != 'numpy':
            grid[parent]['cumPower'] = np.array([0.0]*3)

        if grid[load]['power']==None:
            grid[load]['power'] = 0
            
        # compute cumulated power 
        if ph!=None:

            # ... at load 
            if type(ph)==int:
                grid[load]['cumPower'][ph-1] += grid[load]["power"]
                
            elif ph=='T':
                grid[load]['cumPower'] = grid[load]['cumPower'] + grid[load]["power"]/3
                
            else: # U, Y
                pass # do nothing
            
            # and at parent
            grid[parent]['cumPower'] = grid[parent]['cumPower'] + grid[load]["cumPower"]
            
        else:
            print(f'\t load: {load} has no phase assigned')

    