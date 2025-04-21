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
# - nodes_dict=grid: dict(). each node is a key. each node is itself a dictonnary.
#   nodes_dict['someLoad'] has the following keys:
#       - _cable: a list of cables. Each cable in the list is described as a dictionnary with keys 'layer' and 'id'
#           exemple: nodes_dict['generator']['cable'][0]
#
#       - children: dictionary. One kid = one key. 
#           each kid is itself a dict. eg: grid['generator']['children']['Werkhaus'].keys() ---> dict_keys(['cable']) 
#       - parent: a str 
#       - cable = cable to parent 
#       - load = [watts] on all 3 phases ?
#       - cumulated load = [ on the 3 phases ---> a list ?] 
#       - etc.
#
# - cables_dict['cable_layer_name'][cable_idx]  = dict() with the following keys:
#        - nodes: list(c). Each item of the list contains node(s) names connected to this cable
#

# imports
import json # to do: print(json.dumps(cables_dict, sort_keys=True, indent=4))
from qgis.core import QgsDistanceArea, QgsUnitTypes, QgsVectorLayer, QgsFeature
from .get_layer import get_layer
from .get_coordinates import get_coordinates
from .get_children import get_children
from .get_user_parameters import get_user_parameters
import traceback
import logging

# user settings
param = get_user_parameters()
loads_layers_list = param['loads_layers_list']
cables_layers_list = param['cables_layers_list']

thres = 5 # [meters] threshold to detect cable and load connections
nodes_dictModel = ['_cable','parent','children','deepness','cable','power','phase','date', 'cum_power', 'distro']
cables_dictModel = ['nodes','length','phase','area','current','r',"plugsAndsockets"]

verbose = 0


def get_load_name(load: QgsFeature) -> str:
    verbose = 0

    load_name = load.attribute('name')
    assert isinstance(load_name, str), 'this should be a string containing the name of the load'

    load_name = load_name.lower() 
    load_name = load_name.replace('\n',' ') # in case of some names on the map have a \n
    load_name = load_name.replace('  ', ' ') # avoid double blanks

    if verbose: 
        attrs = load.attributes() # attrs is a list. It contains all the attribute values of this feature
        print("\n\t load's ID: ", load.id())
        print("\t load's attributes: ", attrs)

    return load_name 


def find_connections(project, loads_layers_list, cables_layers_list, thres):
    verbose = 0 
    nodes_dict = {} 
    cables_dict = {} 

    # --- fill cables dict with lengthes
    for cable_layer_name in cables_layers_list:
        cable_layer = get_layer(project, cable_layer_name)
        cables_dict[cable_layer_name] = [None]*len(cable_layer) # init "empty" (cable) list for this layer 

        # --- mesure distance ---  https://gis.stackexchange.com/questions/347802/calculating-elipsoidal-length-of-line-in-pyqgis
        assert project.crs() == cable_layer.crs(), \
               f"project CRS ({project.crs()}) does not match layer {cable_layer_name}'s CRS ({cable_layer.crs()}), stg is weird... "
        
        qgsDist = QgsDistanceArea() # https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html
        qgsDist.setSourceCrs(cable_layer.crs(), project.transformContext()) # https://gis.stackexchange.com/questions/57745/how-to-get-crs-of-a-raster-layer-in-pyqgis
        
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
            print(f'in layer "{cable_layer_name}", qgsDist.lengthUnits()): {QgsUnitTypes.toString(qgsDist.lengthUnits())}')
            raise ValueError('distance units should be meters') 

        for cable_idx, cable in enumerate(cable_layer.getFeatures()):
            cables_dict[cable_layer_name][cable_idx] = dict.fromkeys(cables_dictModel) # init a dict to describe cable
            cables_dict[cable_layer_name][cable_idx]['nodes'] = [] # init empty list of nodes connected to this cable
            cable_length = qgsDist.measureLength(cable.geometry())
            assert cable_length>0, f"in layer '{cable_layer}', cable {cable_idx+1} has length = 0m. It should be deleted"
            cables_dict[cable_layer_name][cable_idx]["length"] = cable_length + param['extra_cable_length']
            cables_dict[cable_layer_name][cable_idx]["area"] = cable.attribute('area')
            cables_dict[cable_layer_name][cable_idx]["plugsAndsockets"] = cable.attribute(r'plugs&sockets')


    # --- find connections 
    for load_layer_name in loads_layers_list:
        load_layer = get_layer(project, load_layer_name)
        if verbose: print(f"loads layer = {load_layer}")
        field = 'name'
        assert field in load_layer.fields().names(), f'layer "{load_layer_name}" does not have a field "{field}"'
        
        for load in load_layer.getFeatures():
            load_name = get_load_name(load)
            if verbose: print(f'\t load {load_name}')

            # init a dict for that node
            nodes_dict[load_name] = dict.fromkeys(nodes_dictModel) 
            nodes_dict[load_name]['_cable'] = []
            
            # --- find which cable(s) are connected to that load
            try:
                load_pos = get_coordinates(load)
                nodes_dict[load_name]['coordinates'] = load_pos

            except Exception as e:  #https://stackoverflow.com/questions/4990718/how-can-i-write-a-try-except-block-that-catches-all-exceptions/4992124#4992124
                print(f'\t there is a problem with load "{load_name}" in "{load_layer_name}" layer:')
                logging.error(traceback.format_exc()) # Logs the error appropriately. 
                
            
            is_load_connected = False
            for cable_layer_name in cables_layers_list:
                cable_layer = get_layer(project, cable_layer_name)
                for cable_idx, cable in enumerate(cable_layer.getFeatures()):
                    cable_pos = get_coordinates(cable) # TODO: check correctness of distance ??
                    
                    elist = list() # elist = extremities list. one list for each cable. todo: use numpy array ?
                    for extrem in cable_pos: # compute distance load-extremities of the cable
                        elist.append(qgsDist.measureLine(load_pos, extrem))
                        
                    dmin = min(elist)
                    if dmin<= thres: # we found a connection 
                        # TODO: would be better to do the test outside cable loop (see below)
                        is_load_connected = True
                        if verbose: print(f'\t\t in cable layer "{cable_layer_name}", cable {cable.id()} is connected to "{load_name}"')
                        
                        # update dicts
                        cables_dict[cable_layer_name][cable_idx]['nodes'].append(load_name)
                        nodes_dict[load_name]['_cable'].append({"layer":cable_layer_name,"idx":cable_idx})

                        
            if verbose:
                if is_load_connected==0:
                    print(f'\t{load_name} is NOT connected')

                else:
                    print(f'\t{load_name} is connected')

                # TODO here: 
                # in the list of cables, test if one (or more) is closer than threshold 
                # if not, throw an error 
            
    return nodes_dict, cables_dict


def compute_deepness_list(grid):
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
    

def compute_distro_requirements(grid, cables_dict):
    ''' must be run after "inspect_cable_layer" '''
    verbose = 0
    print('\ncompute_distro_requirements...')
    for load in grid.keys():
        distro = dict.fromkeys(['in','out'])
        if verbose: print(f"\n\t\t {load}:")

        # --- checking input... 
        if (grid[load]['parent']!=None) and (len(grid[load]['parent'])>0):
            cable2parent_ref = grid[load]['cable']
            cable2parent = cables_dict[cable2parent_ref['layer']][cable2parent_ref['idx']]
            if "3phases" in cable2parent_ref['layer']:
                ph = "3P"
            elif "1phase" in cable2parent_ref['layer']:
                ph = "1P"
            else: 
                print("\t\t\t can't figure out if this cable is 3P or 1P")

            if cable2parent['plugsAndsockets']==None:
                raise ValueError(f"cable2parent['plugsAndsockets'] is None, run inspect_cable_layer?")
            else:
                distro['in'] = f"{ph} {cable2parent['plugsAndsockets']}A"

        elif load == "generator":
            distro["in"] = "3P 125A"
        
        #--- checking output...
        distro['out'] = {}
        if grid[load]['children']!=None:
            cables2children_ref = [grid[load]['children'][child]['cable'] for child in grid[load]['children']]
            cables2children = [ cables_dict[c['layer']][c['idx']] for c in cables2children_ref ]
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


def get_grid_geometry(project):
    verbose = 0
    if verbose: print('get grid geometry: \nfind_connections')

    # 1. find connections between loads and cables (find what load is plugged into what cable, and vice-versa)
    nodes_dict, cables_dict = find_connections(project, loads_layers_list, cables_layers_list, thres)

    # 2. find connections between nodes to get the "flow direction":
    # Now, all cables that are connected to something are (supposed to be) stored in cables_dict. 
    # Let's loop over the nodes again, but this time, we will find to what node is connected each node
    # We'll start with "generator" node, get its children, then check its children's children, etc
    if verbose: print('\nget_children')
    grid = get_children("generator", nodes_dict, cables_dict)
    grid = grid[0]

    # --- for each load, add "cable to daddy" information
    for load in grid.keys():
        if load!='generator':
            parent = grid[load]['parent']
            if parent != None:
                cable2parent = grid[parent]['children'][load]["cable"]
                grid[load]['cable'] = cable2parent
                #grid[load]['cable'].update(cables_dict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict
     
    dlist = compute_deepness_list(grid)

    if 0:
        print('\n')
        print(json.dumps(cables_dict, sort_keys=True, indent=4))
        print(json.dumps(nodes_dict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))

    return cables_dict, grid, dlist

