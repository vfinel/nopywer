# imports
# from pathlib import Path
import numpy as np
# from pyqgis.getGridGeometry import getGridGeometry
# from pyqgis.computeVDrop import computeVDrop
exec(Path('./pyqgis/getGridGeometry.py').read_text())
exec(Path('./pyqgis/computeVDrop.py').read_text())

# find grid geometry
cablesDict, grid, dlist = getGridGeometry()

# spreadsheet: asign phases
# .....

# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
exec(Path('./pyqgis/readSpreadsheet.py').read_text())

#print(json.dumps(grid, sort_keys=True, indent=4))

# compute cumulated current
exec(Path('./pyqgis/cumulateCurrent.py').read_text())

phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))

grid = computeVDrop(grid)

# print grid
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

print('\norphelin load:')
for load in grid.keys():
    if (grid[load]['parent'] == None) and not (grid[load]=='generator'):
        print(f'\t{load}')

print("\n end of script for now :)")