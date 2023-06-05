import json 
import numpy as np 

def printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist):    
    print("\n === info about the grid === \n") 

    print(f"total power: {1e-3*np.sum(grid['generator']['cumPower']):.0f}kW \t {np.round(1e-3*grid['generator']['cumPower'],1)} ")

    if phaseBalance>5:
        flag = ' <<<<<<<<<<'
    else:
        flag = ''
    print(f"phase balance: {phaseBalance.round(1)} % {flag}")

    for deep in range(len(dlist)):
        print(f"\t deepness {deep}")
        for load in dlist[deep]:
            pwrPerPhase = np.round(1e-3*grid[load]['cumPower'],1)
            pwrTotal = 1e-3*np.sum(grid[load]['cumPower'])
            vdrop = grid[load]['vdrop_percent']
            if vdrop>5:
                flag = ' <<<<<<<<<<'
            else:
                flag = ''
            
            print(f"\t\t {load} cumPower={pwrPerPhase}kW, total {pwrTotal:.0f}kW, vdrop {vdrop:.1f}% {flag} ")

    print('\nLoads not connected to a cable:')
    for load in grid.keys():
        if (grid[load]['_cable'] == []) and not (grid[load]=='generator'):
            print(f'\t{load}')

    print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{hasNoPhase} \n ")

    if 0:
        print('\n')
        print(json.dumps(cablesDict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))
