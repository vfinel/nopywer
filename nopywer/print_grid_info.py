import json 
import numpy as np 
from .get_constant_parameters import get_constant_parameters

def print_grid_info(grid, cables_dict, phaseBalance, has_no_phase, dlist):    

    CONSTANTS = get_constant_parameters()
    V0 = CONSTANTS['V0']
    PF = CONSTANTS['PF']

    print("\n === info about the grid === \n") 

    print(f"total power: {1e-3*np.sum(grid['generator']['cum_power']):.0f}kW \t {np.round(1e-3*grid['generator']['cum_power'],1)}kW "\
          + f"/ {np.round(grid['generator']['cum_power']/PF/V0)}A")

    # --- print vdrop for each load, sorted by deepness
    if phaseBalance>5:
        flag = ' <<<<<<<<<<'
    else:
        flag = ''
    print(f"phase balance: {phaseBalance.round(1)} % {flag}")

    for deep in range(len(dlist)):
        print(f"\t deepness {deep}")
        for load in dlist[deep]:
            pwrPerPhase = np.round(1e-3*grid[load]['cum_power'],1).tolist()
            pwrTotal = 1e-3*np.sum(grid[load]['cum_power'])
            vdrop = grid[load]['vdrop_percent']
            if vdrop>5:
                flag = ' <<<<<<<<<<'
            else:
                flag = ''
            
            print(f"\t\t {load:20} cum_power={pwrPerPhase}kW, total {pwrTotal:5.1f}kW, vdrop {vdrop:.1f}% {flag} ")
            

    # --- 
    
    print('\nLoads not connected to a cable:')
    for load in grid.keys():
        needsPower = bool( np.double(grid[load]['power']>0).sum() )
        if (grid[load]['_cable'] == []) and not (grid[load]=='generator') and needsPower:
            print(f'\t{load}')

    print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{has_no_phase} \n ")

    # --- compute and print loads on red and yellow grids 
    print(f'total power on other grids: ')
    subgrid_dict = {'tot': 0, "msg":""}
    subgrid = {'red':subgrid_dict.copy(), 'yellow':subgrid_dict.copy()}
    for load in grid.keys():
        if grid[load]['phase'] == 'U':
            g = 'red'
            
        elif grid[load]['phase'] == 'Y':
            g = 'yellow'

        else:
            g = None

        if g!=None:
            subgrid[g]['tot'] += grid[load]['power']
            subgrid[g]['msg'] += f"\t\t {load} ({grid[load]['power']}W) \n"
    
    for g in subgrid.keys():
        print(f"\t {g} grid: {subgrid[g]['tot']/1e3:.1f}kW / {subgrid[g]['tot']/V0:.1f}A")
        print(subgrid[g]['msg'])

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
        print(json.dumps(cables_dict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))
