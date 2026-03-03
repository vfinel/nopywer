import logging

from .constants import CONNECTION_THRESHOLD_M
from .geometry import geodesic_distance_m

logger = logging.getLogger(__name__)


def find_connections(grid, cables_dict):
    for layer_name, cable_layer in cables_dict.items():
        for cable in cable_layer:
            for node in grid.values():
                if node.coordinates is None:
                    continue
                for endpoint in (
                    cable.coordinates[0],
                    cable.coordinates[-1],
                ):
                    dist = geodesic_distance_m(
                        endpoint[0],
                        endpoint[1],
                        node.coordinates[0],
                        node.coordinates[1],
                    )
                    if dist <= CONNECTION_THRESHOLD_M:
                        if node.name not in cable.nodes:
                            cable.nodes.append(node.name)
                            node.cables.append(
                                {"layer": layer_name, "idx": cable.id}
                            )


def compute_deepness_list(grid):
    dmax = 0
    for load in grid.keys():
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
    logger.info("compute_distro_requirements...")
    for load in grid.values():
        logger.debug(f"\t\t {load.name}:")

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
                logger.info(
                    "\t\t\t can't figure out if this cable is 3P or 1P"
                )

            if cable2parent.plugs_and_sockets is None:
                raise ValueError(
                    "cable2parent.plugs_and_sockets is None"
                )
            else:
                load.distro["in"] = (
                    f"{ph} {cable2parent.plugs_and_sockets}A"
                )

        elif load.name == "generator":
            load.distro["in"] = "3P 125A"

        load.distro["out"] = {}
        if load.children is not None:
            cables2children_ref = [
                load.children[child]["cable"]
                for child in load.children
            ]
            cables2children = [
                cables_dict[c["layer"]][c["idx"]]
                for c in cables2children_ref
            ]
            for idx, cable in enumerate(cables2children):
                if "3phases" in cables2children_ref[idx]["layer"]:
                    ph = "3P"
                elif "1phase" in cables2children_ref[idx]["layer"]:
                    ph = "1P"
                else:
                    logger.info(
                        "\t\t\t can't figure out if this cable"
                        " is 3P or 1P"
                    )

                desc = f"{ph} {cable.plugs_and_sockets}A"
                if desc not in load.distro["out"]:
                    load.distro["out"][desc] = 1
                else:
                    load.distro["out"][desc] += 1

    return grid
