# imports
from qgis.core import *
import qgis.utils
from get_user_parameters import get_user_parameters
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
exec(Path('../nopywer/updateLayers.py').read_text())
exec(Path('../nopywer/inspectCableLayer.py').read_text())
exec(Path('../nopywer/writeSpreadsheet.py').read_text())
# --------------------------------------------------------- #
# --- constant data (global variables)
CONSTANTS = get_constant_parameters()
V0 = CONSTANTS['V0']
PF = CONSTANTS['PF']

param = get_user_parameters()

# find grid geometry
cablesDict, grid, dlist = getGridGeometry()

# spreadsheet: asign phases
# .....

# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
exec(Path('../nopywer/readSpreadsheet.py').read_text())

# compute cumulated current
exec(Path('../nopywer/cumulateCurrent.py').read_text())
grid, cablesDict = cumulateCurrent(grid, cablesDict, dlist)

phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))

cablesDict = inspectCableLayers(cablesLayersList, cablesDict)
grid = computeDistroRequirements(grid, cablesDict)

print("\ncomputingVDrop...") 
grid, cablesDict = computeVDrop(grid, cablesDict)

# print('\nchecking inventory:')
# exec(Path('../nopywer/checkInventory.py').read_text())


printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

updateLayers(grid, cablesDict)

writeSpreadsheet(grid, sh)


print("\n end of script for now :)")
