# This code is intented to find which load is connected to which cable
#
# It uses the class QgsDistanceArea and its methods:
#   - measureLength (argin: geometry)
#   - measureLine (args in : list of points)
#
# Documentation of the class:
# https://qgis.org/pyqgis/3.22/core/QgsDistanceArea.html#qgis.core.QgsDistanceArea
#
# Tutorial: "Santa claus is a workaholic and needs a summer break," in:
# https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/geometry.html
#
# notes on structures: TODO: move this into a class !
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
import json  # to print: print(json.dumps(cables_dict, sort_keys=True, indent=4))
from qgis.core import QgsDistanceArea, QgsUnitTypes, QgsFeature
from .get_layer import get_layer
from .get_coordinates import get_coordinates
from .get_children import get_children
from .core_objects import Cable, Node
import traceback
import logging

thres = 5  # [meters] threshold to detect cable and load connection
verbose = 0


def get_load_name(load: QgsFeature) -> str:
    verbose = 0

    load_name = load.attribute("name")
    assert isinstance(load_name, str), (
        "this should be a string containing the name of the load"
    )

    load_name = load_name.lower()
    load_name = load_name.replace(
        "\n", " "
    )  # in case of some names on the map have a \n
    load_name = load_name.replace("  ", " ")  # avoid double blanks

    if verbose:
        attrs = (
            load.attributes()
        )  # attrs is a list. It contains all the attribute values of this feature
        print("\n\t load's ID: ", load.id())
        print("\t load's attributes: ", attrs)

    return load_name


def get_cables_info(project, cables_layers_list, extra_cable_length) -> dict:
    """get cables info (layers' CRS and cables attributes"""

    cables_dict = {}

    for cable_layer_name in cables_layers_list:
        cable_layer = get_layer(project, cable_layer_name)
        cables_dict[cable_layer_name] = [None] * len(cable_layer)

        # --- check cable CRS to measure distances
        # tips to mesure distance https://gis.stackexchange.com/questions/347802/calculating-elipsoidal-length-of-line-in-pyqgis
        assert project.crs() == cable_layer.crs(), (
            f"project CRS ({project.crs()}) does not match layer {cable_layer_name}'s CRS ({cable_layer.crs()}), stg is weird... "
        )

        qgsDist = QgsDistanceArea()

        # https://gis.stackexchange.com/questions/57745/how-to-get-crs-of-a-raster-layer-in-pyqgis
        qgsDist.setSourceCrs(cable_layer.crs(), project.transformContext())

        # on ellipsoids:
        #   - set global settings on qgis: https://gis.stackexchange.com/questions/341997/how-to-set-global-setting-ellipsoid-in-qgis
        #   - crs for ellipsoid measurements: https://gis.stackexchange.com/questions/376703/crs-for-ellipsoid-measurements

        # check that units are meters
        # https://gis.stackexchange.com/questions/341455/how-to-display-the-correct-unit-of-measure-in-pyqgis
        units_in_meters = QgsUnitTypes.toString(qgsDist.lengthUnits()) == "meters"
        if not units_in_meters:
            print(
                f'in layer "{cable_layer_name}", qgsDist.lengthUnits()): {QgsUnitTypes.toString(qgsDist.lengthUnits())}'
            )
            raise ValueError("distance units should be meters")

        # --- get info from each cable of the current cable layer
        for cable_idx, cable_qgis in enumerate(cable_layer.getFeatures()):
            cable_length = qgsDist.measureLength(cable_qgis.geometry())
            assert cable_length > 0, (
                f"in layer '{cable_layer}', cable_qgis {cable_idx + 1} has length = 0m. It should be deleted"
            )

            try:
                cable_nopywer = Cable(
                    length=cable_length + extra_cable_length,
                    area=cable_qgis.attribute("area"),
                    plugs_and_sockets=cable_qgis.attribute(r"plugs&sockets"),
                )
                cable_nopywer.coordinates = get_coordinates(cable_qgis)
                cable_nopywer.layer_name = cable_layer_name
                cable_nopywer.id = cable_idx

            except Exception as error:
                raise ValueError(
                    f"There is a problem with the cable number {cable_idx + 1} of layer {cable_layer_name}: \n{repr(error)}"
                )

            cables_dict[cable_layer_name][cable_idx] = cable_nopywer

    return cables_dict


def get_loads_info(project, loads_layers_list) -> dict:
    """get loads info"""
    nodes_dict = {}
    for load_layer_name in loads_layers_list:
        load_layer = get_layer(project, load_layer_name)
        if verbose:
            print(f"loads layer = {load_layer}")

        field = "name"
        assert field in load_layer.fields().names(), (
            f'layer "{load_layer_name}" does not have a field "{field}"'
        )

        for load in load_layer.getFeatures():
            load_name = get_load_name(load)
            if verbose:
                print(f"\t load {load_name}")

            # init a Node for that node
            nodes_dict[load_name] = Node(name=load_name)

            try:
                load_pos = get_coordinates(load)
                nodes_dict[load_name].coordinates = load_pos

            except Exception:  # https://stackoverflow.com/questions/4990718/how-can-i-write-a-try-except-block-that-catches-all-exceptions/4992124#4992124
                print(
                    f'\t there is a problem with load "{load_name}" in "{load_layer_name}" layer:'
                )
                logging.error(traceback.format_exc())  # Logs the error appropriately.

    return nodes_dict


def is_load_connected(cable, load, qgsDist):
    """compute distance load-extremities of the cable and store it
    TODO: check correctness of distance ??
    """
    verbose = 0

    elist = [
        qgsDist.measureLine(load.coordinates, extrem) for extrem in cable.coordinates
    ]

    dmin = min(elist)
    is_load_connected = dmin <= thres
    if is_load_connected and verbose:
        print(
            f'\t\t in cable layer "{cable._layer_name}", cable {cable._id} is connected to "{load.name}"'
        )

    return is_load_connected


def find_connections(
    project, loads_layers_list, cables_layers_list, extra_cable_length, thres
) -> tuple[dict, dict]:
    verbose = 0
    qgsDist = QgsDistanceArea()
    cables_dict = get_cables_info(project, cables_layers_list, extra_cable_length)
    nodes_dict = get_loads_info(project, loads_layers_list)

    # find connections : for each node, loop through all cables until you find close enough to the load
    for load in nodes_dict.values():
        for cable_layer in cables_dict.values():
            for cable in cable_layer:
                if is_load_connected(cable, load, qgsDist):
                    cables_dict[cable._layer_name][cable._id].nodes.append(load.name)
                    load.cables.append({"layer": cable._layer_name, "idx": cable._id})

        if verbose:
            if is_load_connected == 0:
                print(f"\t{load.name} is NOT connected")

            else:
                print(f"\t{load.name} is connected to {len(load.cables)} cable(s)")

    # to debug
    if verbose:
        print("list of cables:")
        for cable_layer in cables_dict.values():
            for cable in cable_layer:
                print(f"\t {cable}")

    return nodes_dict, cables_dict


def compute_deepness_list(grid):
    # --- sort loads by deepness
    dmax = 0
    for load in grid.keys():  # find max deepness
        deepness = grid[load].deepness
        if deepness is not None:
            dmax = max(dmax, grid[load].deepness)

    dlist = [None] * (dmax + 1)
    for load in grid.keys():
        deepness = grid[load].deepness
        if deepness is not None:
            if dlist[deepness] is None:
                dlist[deepness] = []
            dlist[deepness].append(load)
    return dlist


def compute_distro_requirements(grid, cables_dict):
    """must be run after 'inspect_cable_layer'"""
    verbose = 0
    print("\ncompute_distro_requirements...")
    for load in grid.values():
        if verbose:
            print(f"\n\t\t {load.name}:")

        # --- checking input...
        if (load.parent is not None) and (len(load.parent) > 0):
            cable2parent_ref = load.cable
            cable2parent = cables_dict[cable2parent_ref["layer"]][
                cable2parent_ref["idx"]
            ]
            if "3phases" in cable2parent_ref["layer"]:
                ph = "3P"
            elif "1phase" in cable2parent_ref["layer"]:
                ph = "1P"
            else:
                print("\t\t\t can't figure out if this cable is 3P or 1P")

            if cable2parent.plugs_and_sockets is None:
                raise ValueError(
                    "cable2parent.plugs_and_sockets is None, run inspect_cable_layer?"
                )
            else:
                load.distro["in"] = f"{ph} {cable2parent.plugs_and_sockets}A"

        elif load == "generator":
            load.distro["in"] = "3P 125A"

        # --- checking output...
        load.distro["out"] = {}
        if load.children is not None:
            cables2children_ref = [
                load.children[child]["cable"] for child in load.children
            ]
            cables2children = [
                cables_dict[c["layer"]][c["idx"]] for c in cables2children_ref
            ]
            for idx, cable in enumerate(cables2children):
                if "3phases" in cables2children_ref[idx]["layer"]:
                    ph = "3P"
                elif "1phase" in cables2children_ref[idx]["layer"]:
                    ph = "1P"
                else:
                    print("\t\t\t can't figure out if this cable is 3P or 1P")

                rating = f"{cable.plugs_and_sockets}A"
                desc = f"{ph} {rating}"
                if desc not in load.distro["out"]:
                    load.distro["out"][desc] = 1
                else:
                    load.distro["out"][desc] += 1

        if verbose:
            print(f"\t\t\t in: {load.distro['in']}")
            print("\t\t\t out: ")
            for desc in load.distro["out"].keys():
                print(f"\t\t\t\t {desc}: {load.distro['out'][desc]}")

    return grid


def get_grid_geometry(project, param: dict):
    verbose = 0
    if verbose:
        print("get grid geometry: \nfind_connections")

    loads_layers_list = param["loads_layers_list"]
    cables_layers_list = param["cables_layers_list"]

    # 1. find connections between loads and cables (find what load is plugged into what cable, and vice-versa)
    nodes_dict, cables_dict = find_connections(
        project,
        loads_layers_list,
        cables_layers_list,
        param["extra_cable_length"],
        thres,
    )

    # 2. find connections between nodes to get the "flow direction":
    # Now, all cables that are connected to something are (supposed to be) stored in cables_dict.
    # Let's loop over the nodes again, but this time, we will find to what node is connected each node
    # We'll start with "generator" node, get its children, then check its children's children, etc
    if verbose:
        print("\nget_children")

    grid = get_children("generator", nodes_dict, cables_dict)
    grid = grid[0]

    # --- for each load, add "cable to daddy" information
    for load in grid.keys():
        if load != "generator":
            parent = grid[load].parent
            if parent != None:
                cable2parent = grid[parent].children[load]["cable"]
                grid[load].cable = cable2parent

    dlist = compute_deepness_list(grid)

    if 0:
        print("\n")
        print(json.dumps(cables_dict, sort_keys=True, indent=4))
        print(json.dumps(nodes_dict, sort_keys=True, indent=4))
        print(json.dumps(grid, sort_keys=True, indent=4))

    return cables_dict, grid, dlist
