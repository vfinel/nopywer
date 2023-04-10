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
# - nodesDict: dict(). each node is a key. each node is itself a dictonnary.
#   nodesDict['someLoad'] has the following keys:
#       - cable: a list of cables. Each cable in the list is described as a dictionnary with keys 'layer' and 'id'
#           exemple: nodesDict['generator']['cable'][0]
#
#       - child: list ?
#       - , parent, cable, etc.
#
# - cablesDict['cableLayerName'][cableIdx]  = dict() with the following keys:
#        - nodes: list(c). Each item of the list contains node(s) names connected to this cable
#

print('\n\n=================================================')
print('get grid geometry')
print('=================================================')

# imports
import json # to do: print(json.dumps(cablesDict, sort_keys=True, indent=4))
exec(open('H:/Mon Drive/vico/map/sandbox/getLayer.py'.encode('utf-8')).read())
exec(open('H:/Mon Drive/vico/map/sandbox/getCoordinates.py'.encode('utf-8')).read())
exec(open('H:/Mon Drive/vico/map/sandbox/getChildren.py'.encode('utf-8')).read())
dClass = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
dClass.setEllipsoid('WGS84')

# tests
nodesDict = {} 
cablesDict = {} 

# user settings
loadLayersList = ["power usage"]
cablesLayersList = ["3phases_norg", "1phase_norg"]
thres = 5 # [meters] threshold to detect cable and load connections

# ======= 1. First step : find connections between loads and cables
for loadLayerName in loadLayersList:
    # get loads layer
    load_layer = getLayer(loadLayerName)
    print(f"loads layer = {load_layer}")

    # "loads" are qgis features. and a python iterator --> needs to be reset after each loop
    loads = load_layer.getFeatures() 
    for load in loads:
        print("\nload's ID: ", load.id())
        attrs = load.attributes() # attrs is a list. It contains all the attribute values of this feature
        print("load's attributes: ", attrs)
        loadName = attrs[1]
        
        # get load position
        loadPos = getCoordinates(load)
        
        # --- find which cable(s) are connected to load
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
                    print(f'\t cable layer  {cableLayerName}, cable {cable.id()} is connected to {attrs[1]}')
                    
                    # we found the cable, let's do some fill dictionnaries
                    if cableLayerName not in cablesDict: # if this cable LAYER hasn't been seen yet
                        cablesDict[cableLayerName] = [None]*len(cableLayer) # init "empty" (cable) list for this layer
                        
                    if cablesDict[cableLayerName][cableIdx] == None: # if this cable has't been seen in this layer
                        cablesDict[cableLayerName][cableIdx] = dict() # init a dict to describe cable
                        cablesDict[cableLayerName][cableIdx]['nodes'] = [] # init list of nodes connected to this cable
                        geom = cable.geometry()
                        cablesDict[cableLayerName][cableIdx]["length"] = dClass.measureLength(geom)
                    
                    cablesDict[cableLayerName][cableIdx]['nodes'].append(loadName)
                
                    if loadName not in nodesDict:
                        nodesDict[loadName] = dict()
                        nodesDict[loadName]['_cable'] = []
                    
                    nodesDict[loadName]['_cable'].append({"layer":cableLayerName,"idx":cableIdx})
                    
            # todo here: 
            # in the list of cables, test if one (or more) is closer than threshold 
            # if not, throw an error 
            

#print(json.dumps(cablesDict, sort_keys=True, indent=4))
#print(json.dumps(nodesDict, sort_keys=True, indent=4))

# =======  Second step: find connections between nodes 
# Now, all cables that are connected to something are (supposed to be) stored in cablesDict. 
# Let's loop over the nodes again, but this time, we will find to what node is connected each node
# We'll start with "generator" node, get its children, then check its children's children, etc

children = getChildren("generator", nodesDict, cablesDict)
#print(json.dumps(nodesDict, sort_keys=True, indent=4))


# objectif: un dictionnaire(struct matlab) "grid" du type:
# - grid has a field for each node (grid.gen, grid.mon, ...)
# - grid.nodename has the following fields:
#   - parent (eg, grid.noinfo.parent = gen)
#   - child (eg, grid.noinfo.child = [mon, noinfo_itself, someArtPiece]),
#       child[n].length
#       child[n].wireSection 
#       ...
#   - current going through node 
#   - voltage
#   - vdrop 
#   - ("self")load (if the node also has a load, for example noinfo)

# comment construire une telle structure ? 
# while node doesn't have any more connections (start with gen)
#   look at its connections
#   compute gen's fields
#   do the same for its childs

# so it means to build the actual grid (knowing who's child and parent, 
# first it is necessary to know which load is connected to which load 
# But to know that, it is necessary to know which cable is connected to which loads !

print("\n end of script for now :)")


