from qgis.core import QgsApplication, QgsProject
import qgis.utils
import numpy as np
import os
import nopywer as npw


# --------------------------------------------------------- #
# --- constant data (global variables)
CONSTANTS = npw.get_constant_parameters()
V0 = CONSTANTS['V0']
PF = CONSTANTS['PF']

# user parameters
updateStuff = 1
param = npw.get_user_parameters()
cablesLayersList = param['cablesLayersList']

project = QgsProject.instance() 

standalone_exec = __name__ == '__main__'
if standalone_exec: # code is not ran from QGIS 
    # --- run qgis (to be able to run code from vscode - NOT HELPING)
    # Supply path to qgis install location
    print('initializing QGIS...')
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
cablesDict, grid, dlist = npw.getGridGeometry(project)


# spreadsheet: assign phases
# .....


# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
project_path = os.path.split(project_file)[0]
grid, cablesDict, hasNoPhase = npw.readSpreadsheet(project_path, grid, cablesDict, param['spreadsheet'])


# compute cumulated current
grid, cablesDict = npw.cumulateCurrent(grid, cablesDict, dlist, V0, PF)

phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))

cablesDict = npw.inspectCableLayers(project, cablesLayersList, cablesDict) 
grid = npw.computeDistroRequirements(grid, cablesDict)

print("\ncomputingVDrop...") 
grid, cablesDict = npw.computeVDrop(grid, cablesDict)

print('\nchecking inventory:')
npw.choose_cables_in_inventory(project_path, cablesDict, param['inventory'])
npw.choose_distros_in_inventory(project_path, grid, param['inventory'])

npw.printGridInfo(grid, cablesDict, phaseBalance, hasNoPhase, dlist)

if updateStuff:
    npw.update1PhaseLayers(grid, cablesDict, project)
    npw.updateLoadLayers(grid, param['loadLayersList'], project)
    #npw.writeSpreadsheet(grid, sh)


print("\n end of script for now :)")

if standalone_exec:
    qgs.exitQgis()
