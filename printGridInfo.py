import json 
import numpy as np 

def printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist):    
    print("\n === info about the grid === \n") 

    print(f"total power: {1e-3*np.sum(grid['generator']['cumPower']):.0f}kW \t {np.round(1e-3*grid['generator']['cumPower'],1)}kW "\
          + f"/ {np.round(grid['generator']['cumPower']/PF/V0)}A")

    # --- print vdrop for each load, sorted by deepness
    if phaseBalance>5:
        flag = ' <<<<<<<<<<'
    else:
        flag = ''
    print(f"phase balance: {phaseBalance.round(1)} % {flag}")

    for deep in range(len(dlist)):
        print(f"\t deepness {deep}")
        for load in dlist[deep]:
            pwrPerPhase = np.round(1e-3*grid[load]['cumPower'],1).tolist()
            pwrTotal = 1e-3*np.sum(grid[load]['cumPower'])
            vdrop = grid[load]['vdrop_percent']
            if vdrop>5:
                flag = ' <<<<<<<<<<'
            else:
                flag = ''
            
            print(f"\t\t {load:20} cumPower={pwrPerPhase}kW, total {pwrTotal:5.1f}kW, vdrop {vdrop:.1f}% {flag} ")
            

    # --- 
    
    print('\nLoads not connected to a cable:')
    for load in grid.keys():
        if (grid[load]['_cable'] == []) and not (grid[load]=='generator') and any(grid[load]['power']>0):
            print(f'\t{load}')

    print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{hasNoPhase} \n ")

    # --- compute and print loads on red and yellow grids 
    print(f'total power on other grids: ')
    tot = {'red':0, 'yellow':0}
    for load in grid.keys():
        if grid[load]['phase'] == 'U':
            tot['red'] += grid[load]['power']
        elif grid[load]['phase'] == 'Y':
            tot['yellow'] += grid[load]['power']
    for g in tot.keys():
        print(f'\t {g} grid: {tot[g]/1e3:.1f}kW / {tot[g]/V0:.1f}A')
    
    # --- print distro requirements at each load , sorted by deepness
    if 0:
        print('\ndistro requirements:')
        for deep in range(0, len(dlist)):
            print(f"\t deepness {deep}")
            for load in dlist[deep]:
                print(f"\t\t {load}:")
                distro = grid[load]['distro']
                print(f"\t\t\t in: {distro['in']}")
                print(f"\t\t\t out: ")
                for desc in distro['out'].keys():
                    print(f"\t\t\t\t {desc}: {distro['out'][desc]}")

    # --- print usng json (doesnt work if np arrays in dict)
    if 0:
        print('\n')
        print(json.dumps(cablesDict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))
