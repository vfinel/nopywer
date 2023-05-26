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
from qgis.core import QgsDistanceArea
from pyqgis.getLayer import getLayer
from pyqgis.getCoordinates import getCoordinates
from pyqgis.getChildren import getChildren

dClass = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
dClass.setEllipsoid('WGS84')

# tests
nodesDict = {} 
cablesDict = {} 

# user settings
loadLayersList = ["power usage"]
cablesLayersList = ["3phases_norg", "1phase_norg"]
thres = 5 # [meters] threshold to detect cable and load connections

nodesDictModel = ['_cable','parent','children','deepness','cable','power','phase','date', 'cumPower']

verbose = 1

def inspectCableLayers(cablesLayersList):
    for cableLayerName in cablesLayersList:
        cableLayer = getLayer(cableLayerName)
        cables = cableLayer.getFeatures() # is an interator, so needs to be reset after each load
        for cableIdx, cable in enumerate(cables):
            geom = cable.geometry()
            length = dClass.measureLength(geom)
            print(f"cable layer {cableLayerName} idx {cableIdx} has length {length:.1f}m")

    return None 

def getGridGeometry():
    if verbose: print('get grid geometry: \nfindConnections')

    # 1. find connections between loads and cables (find what load is plugged into what cable, and vice-versa)
    nodesDict, cablesDict = findConnections(loadLayersList, cablesLayersList, thres)

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

    dlist = computeDeepnessList(grid)

    if 0:
        print('\n')
        print(json.dumps(cablesDict, sort_keys=True, indent=4))
        print(json.dumps(nodesDict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))

    return cablesDict, grid, dlist 


def findConnections(loadLayersList, cablesLayersList, thres):
    for loadLayerName in loadLayersList:
        load_layer = getLayer(loadLayerName)
        if verbose: print(f"loads layer = {load_layer}")
        # "loads" are qgis features (and a python iterator --> needs to be reset after each loop)
        loads = load_layer.getFeatures() 

        for load in loads:
            attrs = load.attributes() # attrs is a list. It contains all the attribute values of this feature
            loadName = attrs[1].lower()
            if verbose: 
                print("\n\t load's ID: ", load.id())
                print("\t load's attributes: ", attrs)
            
            # get load position
            loadPos = getCoordinates(load)
            
            # --- find which cable(s) are connected to that load
            for cableLayerName in cablesLayersList:
                cableLayer = getLayer(cableLayerName)
                cables = cableLayer.getFeatures() # is an interator, so needs to be reset after each load
                
                for cableIdx, cable in enumerate(cables):
                    cablePos = getCoordinates(cable)
                    
                    elist = list() # elist = extremities list. one list for each cable. todo: use numpy array ?
                    for extrem in cablePos: # compute distance load-extremities of the cable
                        elist.append(dClass.measureLine(loadPos, extrem))
                        
                    dmin = min(elist)
                    if dmin<= thres: # we found a connection 
                        # todo: better to do the test outside cable loop (see below)
                        if verbose: print(f'\t\t cable layer  {cableLayerName}, cable {cable.id()} is connected to {attrs[1]}')
                        
                        # we found the cable, let's fill dictionnaries
                        if cableLayerName not in cablesDict: # if this cable LAYER hasn't been seen yet
                            cablesDict[cableLayerName] = [None]*len(cableLayer) # init "empty" (cable) list for this layer
                            
                        if cablesDict[cableLayerName][cableIdx] == None: # if this cable has't been seen in this layer
                            cablesDict[cableLayerName][cableIdx] = dict() # init a dict to describe cable
                            cablesDict[cableLayerName][cableIdx]['nodes'] = [] # init list of nodes connected to this cable
                            geom = cable.geometry()
                            cablesDict[cableLayerName][cableIdx]["length"] = dClass.measureLength(geom)
                        
                        cablesDict[cableLayerName][cableIdx]['nodes'].append(loadName)
                    
                        if loadName not in nodesDict:
                            nodesDict[loadName] = dict.fromkeys(nodesDictModel) # init a dict for loads 
                            nodesDict[loadName]['_cable'] = []
                        
                        nodesDict[loadName]['_cable'].append({"layer":cableLayerName,"idx":cableIdx})
                        
                # todo here: 
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
    
    
