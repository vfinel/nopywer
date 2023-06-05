# imports
# import imp
# import startup
# imp.reload(startup)

# from pathlib import Path
import numpy as np
# from pyqgis.getGridGeometry import getGridGeometry
# from pyqgis.computeVDrop import computeVDrop
exec(Path('../nopywer/getGridGeometry.py').read_text())
exec(Path('../nopywer/computeVDrop.py').read_text())
exec(Path('../nopywer/printGridInfo.py').read_text())

# find grid geometry
cablesDict, grid, dlist = getGridGeometry()

# spreadsheet: asign phases
# .....

# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
exec(Path('../nopywer/readSpreadsheet.py').read_text())

# compute cumulated current
exec(Path('../nopywer/cumulateCurrent.py').read_text())
grid = cumulateCurrent(grid, dlist)

phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))

print("computingVDrop...") 
grid, cablesDict = computeVDrop(grid, cablesDict)

# print('\nchecking inventory:')
# exec(Path('../nopywer/checkInventory.py').read_text())

printGridInfo()

print("\n end of script for now :)")