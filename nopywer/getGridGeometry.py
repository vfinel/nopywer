# This code is intented to find which load is connected to which cable
#
# For now, we ll start the loop on loads: each loads must be attached to a cable
# (/!\ in the 2022 map, not all cables were attached to a "real load" on the map")
#
# We'll use the class: QgsDistanceArea, and its methods:
#   - measureLength (argin: geometry)
#   - measureLine (args in : list of points)
#
# Documentation of the class:
# https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html#qgis.core.QgsDistanceArea
#
# Tutorial: "Santa claus is a workaholic and needs a summer break," in:
# https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/geometry.html

# todo: 
#   - clean the map: 
#       - ok: add missing nodes: generator, werkhaus,, etc
#       - make sure each load is connected with a cable.
#       - move bbcham node to babycham?
#
#   - create a list of cables:
#        each item of the list is one cable, described as a dictionnary with keys such as:
#           ok: loads connected to
#           pos of extremities
#           distance2load, ...
#
#   - create a node/load structure with the folowing info: 
#       - ok: name, connection to cable(s), parent load/child load
#
#   - test pour verifier qu'on a bien identifie a quoi chaque cable etait branche...
#
# 
# 
# 

# notes on structures:
#
# - nodesDict=grid: dict(). each node is a key. each node is itself a dictonnary.
#   nodesDict['someLoad'] has the following keys:
#       - _cable: a list of cables. Each cable in the list is described as a dictionnary with keys 'layer' and 'id'
#           exemple: nodesDict['generator']['cable'][0]
#
#       - children: dictionary. One kid = one key. 
#           each kid is itself a dict. eg: grid['generator']['children']['Werkhaus'].keys() ---> dict_keys(['cable']) 
#       - parent: a str 
#       - cable = cable to parent 
#       - load = [watts] on all 3 phases ?
#       - cumulated load = [ on the 3 phases ---> a list ?] 
#       - etc.
#
# - cablesDict['cableLayerName'][cableIdx]  = dict() with the following keys:
#        - nodes: list(c). Each item of the list contains node(s) names connected to this cable
#

# imports
import json # to do: print(json.dumps(cablesDict, sort_keys=True, indent=4))
from qgis.core import QgsDistanceArea, QgsUnitTypes, QgsVectorLayer, QgsFeature
from .getLayer import getLayer
from .getCoordinates import getCoordinates
from .getChildren import getChildren
from .get_user_parameters import get_user_parameters
import traceback
import logging

# user settings
param = get_user_parameters()
loadLayersList = param['loadLayersList']
cablesLayersList = param['cablesLayersList']

thres = 5 # [meters] threshold to detect cable and load connections
nodesDictModel = ['_cable','parent','children','deepness','cable','power','phase','date', 'cumPower', 'distro']
cablesDictModel = ['nodes','length','phase','area','current','r',"plugsAndsockets"]

verbose = 0


def getLoadName(load: QgsFeature) -> str:
    verbose = 0

    loadName = load.attribute('name')
    assert isinstance(loadName, str), 'this should be a string containing the name of the load'

    loadName = loadName.lower() 
    loadName = loadName.replace('\n',' ') # in case of some names on the map have a \n
    loadName = loadName.replace('  ', ' ') # avoid double blanks

    if verbose: 
        attrs = load.attributes() # attrs is a list. It contains all the attribute values of this feature
        print("\n\t load's ID: ", load.id())
        print("\t load's attributes: ", attrs)

    return loadName 


def findConnections(project, loadLayersList, cablesLayersList, thres):
    verbose = 0 
    nodesDict = {} 
    cablesDict = {} 

    # --- fill cables dict with lengthes
    for cableLayerName in cablesLayersList:
        cableLayer = getLayer(project, cableLayerName)
        cablesDict[cableLayerName] = [None]*len(cableLayer) # init "empty" (cable) list for this layer 

        # --- mesure distance ---  https://gis.stackexchange.com/questions/347802/calculating-elipsoidal-length-of-line-in-pyqgis
        assert project.crs() == cableLayer.crs(), \
               f"project CRS ({project.crs()}) does not match layer {cableLayerName}'s CRS ({cableLayer.crs()}), stg is weird... "
        
        qgsDist = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
        qgsDist.setSourceCrs(cableLayer.crs(), project.transformContext()) # https://gis.stackexchange.com/questions/57745/how-to-get-crs-of-a-raster-layer-in-pyqgis
        
        # on ellipsoids: 
        #   - set global settings on qgis: https://gis.stackexchange.com/questions/341997/how-to-set-global-setting-ellipsoid-in-qgis
        #   - crs for ellipsoid measurements: https://gis.stackexchange.com/questions/376703/crs-for-ellipsoid-measurements

        # d.setEllipsoid(QgsProject.instance().ellipsoid())
        # project.ellipsoid() why this is NONE ? 
        # qgsDist.setEllipsoid('WGS84') #todo: this is not smart, should get the CRS from the project ?!

        # check that units are meters 
        # https://gis.stackexchange.com/questions/341455/how-to-display-the-correct-unit-of-measure-in-pyqgis
        units_in_meters = QgsUnitTypes.toString(qgsDist.lengthUnits())=='meters'
        if not units_in_meters: 
            print(f'in layer "{cableLayerName}", qgsDist.lengthUnits()): {QgsUnitTypes.toString(qgsDist.lengthUnits())}')
            raise ValueError('distance units should be meters') 

        for cableIdx, cable in enumerate(cableLayer.getFeatures()):
            cablesDict[cableLayerName][cableIdx] = dict.fromkeys(cablesDictModel) # init a dict to describe cable
            cablesDict[cableLayerName][cableIdx]['nodes'] = [] # init empty list of nodes connected to this cable
            cableLength = qgsDist.measureLength(cable.geometry())
            assert cableLength>0, f"in layer '{cableLayer}', cable {cableIdx+1} has length = 0m. It should be deleted"
            cablesDict[cableLayerName][cableIdx]["length"] = cableLength + param['extra_cable_length']
            cablesDict[cableLayerName][cableIdx]["area"] = cable.attribute('area')
            cablesDict[cableLayerName][cableIdx]["plugsAndsockets"] = cable.attribute(r'plugs&sockets')


    # --- find connections 
    for loadLayerName in loadLayersList:
        load_layer = getLayer(project, loadLayerName)
        if verbose: print(f"loads layer = {load_layer}")
        field = 'name'
        assert field in load_layer.fields().names(), f'layer "{loadLayerName}" does not have a field "{field}"'
        
        for load in load_layer.getFeatures():
            loadName = getLoadName(load)
            if verbose: print(f'\t load {loadName}')

            # init a dict for that node
            nodesDict[loadName] = dict.fromkeys(nodesDictModel) 
            nodesDict[loadName]['_cable'] = []
            
            # --- find which cable(s) are connected to that load
            try:
                loadPos = getCoordinates(load)
                nodesDict[loadName]['coordinates'] = loadPos

            except Exception as e:  #https://stackoverflow.com/questions/4990718/how-can-i-write-a-try-except-block-that-catches-all-exceptions/4992124#4992124
                print(f'\t there is a problem with load "{loadName}" in "{loadLayerName}" layer:')
                logging.error(traceback.format_exc()) # Logs the error appropriately. 
                
            
            is_load_connected = False
            for cableLayerName in cablesLayersList:
                cableLayer = getLayer(project, cableLayerName)
                for cableIdx, cable in enumerate(cableLayer.getFeatures()):
                    cablePos = getCoordinates(cable) # TODO: check correctness of distance ??
                    
                    elist = list() # elist = extremities list. one list for each cable. todo: use numpy array ?
                    for extrem in cablePos: # compute distance load-extremities of the cable
                        elist.append(qgsDist.measureLine(loadPos, extrem))
                        
                    dmin = min(elist)
                    if dmin<= thres: # we found a connection 
                        # TODO: would be better to do the test outside cable loop (see below)
                        is_load_connected = True
                        if verbose: print(f'\t\t in cable layer "{cableLayerName}", cable {cable.id()} is connected to "{loadName}"')
                        
                        # update dicts
                        cablesDict[cableLayerName][cableIdx]['nodes'].append(loadName)
                        nodesDict[loadName]['_cable'].append({"layer":cableLayerName,"idx":cableIdx})

                        
            if verbose:
                if is_load_connected==0:
                    print(f'\t{loadName} is NOT connected')

                else:
                    print(f'\t{loadName} is connected')

                # TODO here: 
                # in the list of cables, test if one (or more) is closer than threshold 
                # if not, throw an error 
            
    return nodesDict, cablesDict


def computeDeepnessList(grid):
    # --- sort loads by deepness
    dmax = 0
    for load in grid.keys(): # find max deepness
        deepness = grid[load]['deepness']
        if deepness!=None:
            dmax = max(dmax, grid[load]['deepness'])

    dlist = [None]*(dmax+1)
    for load in grid.keys():
        deepness = grid[load]["deepness"]
        if deepness!=None:
            #print(f"load {load} has deepness {deepness} together with {dlist[deepness]}")
            if dlist[deepness]==None:
                dlist[deepness] = []
            
            dlist[deepness].append(load)

    return dlist
    

def computeDistroRequirements(grid, cablesDict):
    ''' must be run after "inspectCableLayer" '''
    verbose = 0
    print('\ncomputeDistroRequirements...')
    for load in grid.keys():
        distro = dict.fromkeys(['in','out'])
        if verbose: print(f"\n\t\t {load}:")

        # --- checking input... 
        if (grid[load]['parent']!=None) and (len(grid[load]['parent'])>0):
            cable2parent_ref = grid[load]['cable']
            cable2parent = cablesDict[cable2parent_ref['layer']][cable2parent_ref['idx']]
            if "3phases" in cable2parent_ref['layer']:
                ph = "3P"
            elif "1phase" in cable2parent_ref['layer']:
                ph = "1P"
            else: 
                print("\t\t\t can't figure out if this cable is 3P or 1P")

            if cable2parent['plugsAndsockets']==None:
                raise ValueError(f"cable2parent['plugsAndsockets'] is None, run inspectCableLayer?")
            else:
                distro['in'] = f"{ph} {cable2parent['plugsAndsockets']}A"

        elif load == "generator":
            distro["in"] = "3P 125A"
        
        #--- checking output...
        distro['out'] = {}
        if grid[load]['children']!=None:
            cables2children_ref = [grid[load]['children'][child]['cable'] for child in grid[load]['children']]
            cables2children = [ cablesDict[c['layer']][c['idx']] for c in cables2children_ref ]
            for idx, cable in enumerate(cables2children):
                if "3phases" in cables2children_ref[idx]['layer']:
                    ph = "3P"
                elif "1phase" in cables2children_ref[idx]['layer']:
                    ph = "1P"
                else: 
                    print("\t\t\t can't figure out if this cable is 3P or 1P")

                rating = f"{cable['plugsAndsockets']}A"
                desc = f"{ph} {rating}"
                if desc not in distro['out']:
                    distro['out'][desc] = 1
                else:
                    distro['out'][desc] += 1

        grid[load]['distro'] = distro 
        
        if verbose:  
            print(f"\t\t\t in: {distro['in']}")
            print(f"\t\t\t out: ")
            for desc in distro['out'].keys():
                print(f"\t\t\t\t {desc}: {distro['out'][desc]}")

    return grid


def getGridGeometry(project):
    verbose = 0
    if verbose: print('get grid geometry: \nfindConnections')

    # 1. find connections between loads and cables (find what load is plugged into what cable, and vice-versa)
    nodesDict, cablesDict = findConnections(project, loadLayersList, cablesLayersList, thres)

    # 2. find connections between nodes to get the "flow direction":
    # Now, all cables that are connected to something are (supposed to be) stored in cablesDict. 
    # Let's loop over the nodes again, but this time, we will find to what node is connected each node
    # We'll start with "generator" node, get its children, then check its children's children, etc
    if verbose: print('\ngetChildren')
    grid = getChildren("generator", nodesDict, cablesDict)
    grid = grid[0]

    # --- for each load, add "cable to daddy" information
    for load in grid.keys():
        if load!='generator':
            parent = grid[load]['parent']
            if parent != None:
                cable2parent = grid[parent]['children'][load]["cable"]
                grid[load]['cable'] = cable2parent
                #grid[load]['cable'].update(cablesDict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict
     
    dlist = computeDeepnessList(grid)

    if 0:
        print('\n')
        print(json.dumps(cablesDict, sort_keys=True, indent=4))
        print(json.dumps(nodesDict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))

    return cablesDict, grid, dlist

