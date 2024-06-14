import sys
sys.path += ['C:/PROGRA~1/QGIS33~1.3/apps/qgis/./python', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python/plugins', 'C:/PROGRA~1/QGIS33~1.3/apps/qgis/./python/plugins', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\grass\\grass83\\etc\\python', 'H:\\Mon Drive\\vico\\map\\map2023\\map_20230701_correctionCRS', 'C:\\PROGRA~1\\QGIS33~1.3\\bin\\python39.zip', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\DLLs', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib', 'C:\\PROGRA~1\\QGIS33~1.3\\bin', 'C:\\Users\\v.finel\\AppData\\Roaming\\Python\\Python39\\site-packages', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\win32', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\win32\\lib', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\Pythonwin', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python', 'H:/Mon Drive/vico/map/map2023/map_20230701_correctionCRS'] #from sys.path ran from qgis' python console
sys.path.append('H:\\Mon Drive\\vico\\map\\map2023\\nopywer') # to import nopywer modules from qgis' python cosole

# imports
import json 
from qgis.core import QgsApplication, QgsProject
import qgis.utils
import numpy as np
import os

# nopywer imports 
from checkInventory import choose_cables_in_inventory, choose_distros_in_inventory
from cumulateCurrent import cumulateCurrent
from getGridGeometry import getGridGeometry, computeDistroRequirements
from readSpreadsheet import readSpreadsheet
from inspectCableLayer import inspectCableLayers
from get_user_parameters import get_user_parameters
from get_constant_parameters import get_constant_parameters
from computeVDrop import computeVDrop
from printGridInfo import printGridInfo
from updateLayers import update1PhaseLayers, updateLoadLayers


# tests (to reload code from QGIS python terminal ?)
# import imp
# import startup
# imp.reload(startup)


# --------------------------------------------------------- #
# --- constant data (global variables)
CONSTANTS = get_constant_parameters()
V0 = CONSTANTS['V0']
PF = CONSTANTS['PF']

# user parameters
updateStuff = 1
param = get_user_parameters()
cablesLayersList = param['cablesLayersList']

project = QgsProject.instance() 

standalone_exec = __name__ == '__main__'
if standalone_exec: # code is not ran from QGIS 
    # --- run qgis (to be able to run code from vscode - NOT HELPING)
    # Supply path to qgis install location
    # QgsApplication.setPrefixPath("C:/Program Files/QGIS 3.34.3/apps/qgis/", True) # true=default paths to be used
    print('initializing QGIS...')
    QgsApplication.setPrefixPath('C:/PROGRA~1/QGIS33~1.3/apps/qgis', True)
    qgs = QgsApplication([], False) # second argument to False disables the GUI.
    qgs.initQgis() # Load providers

    # --- load project 
    # from https://gis.stackexchange.com/questions/136861/getting-layer-by-name-in-pyqgis/136879#136879
    print('\nloading project...')
    project_file = param['project_file']
    assert os.path.isfile(project_file), f'the project file does not exists: "{project_file}"'
    status = project.read(project_file)
    assert status, f'unable to read project "{project_file}"'

else: # code is ran from QGIS
    project_file = project.absoluteFilePath()

print(f'project filename: {project.fileName()}\n')


# find grid geometry
cablesDict, grid, dlist = getGridGeometry(project)


# spreadsheet: assign phases
# .....


# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
project_path = os.path.split(project_file)[0]
grid, cablesDict, hasNoPhase = readSpreadsheet(project_path, grid, cablesDict, param['spreadsheet'])


# compute cumulated current
grid, cablesDict = cumulateCurrent(grid, cablesDict, dlist, V0, PF)

phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))

cablesDict = inspectCableLayers(project, cablesLayersList, cablesDict) 
grid = computeDistroRequirements(grid, cablesDict)

print("\ncomputingVDrop...") 
grid, cablesDict = computeVDrop(grid, cablesDict)

print('\nchecking inventory:')
choose_cables_in_inventory(project_path, cablesDict, param['inventory'])
choose_distros_in_inventory(project_path, grid, param['inventory'])

printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

if updateStuff:
    update1PhaseLayers(grid, cablesDict, project)
    updateLoadLayers(grid, param['loadLayersList'], project)
    #writeSpreadsheet(grid, sh)


print("\n end of script for now :)")

if standalone_exec:
    qgs.exitQgis()
