# imports
# from pathlib import Path
from pyqgis.computeVDrop import computeVDrop


grid = None

# find grid geometry
exec(Path('./pyqgis/getGridGeometry.py').read_text())

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
print(f"total power: {1e-3*np.sum(grid['generator']['cumPower']):.0f}kW \t {1e-3*grid['generator']['cumPower'].round()} ")
print(f"phase balance: {phaseBalance.round(1)} %")
for deep in range(len(dlist)):
    print(f"\t deepness {deep}")
    for load in dlist[deep]:
        print(f"\t\t {load}'s cumPower={np.round(1e-3*grid[load]['cumPower'],1)}kW, vdrop {grid[load]['vdrop_percent']:.1f}%")


print("\n end of script for now :)")