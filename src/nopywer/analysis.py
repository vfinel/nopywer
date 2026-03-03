import json
import logging

import numpy as np

from .constants import CONNECTION_THRESHOLD_M, PF, V0, VDROP_THRESHOLD_PERCENT
from .geometry import geodesic_distance_m

logger = logging.getLogger(__name__)

_vdrop_ref = np.sqrt(3) * V0
_vdrop_coef = 1  # TODO: change coef for 1-phase vs 3-phase


# ---------------------------------------------------------------------------
# Grid topology: snap cables to nodes, build parent/child tree, compute depth
# ---------------------------------------------------------------------------


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
                            node.cables.append({"layer": layer_name, "idx": cable.id})


def get_children(node_name: str, grid: dict, cables: dict) -> tuple[dict, dict]:
    children_dict = dict()

    if grid[node_name].children != {}:
        raise ValueError(
            f"\n\nThere is an infinite loop going from/to {node_name} on the map. \n"
            f"It is connected by the following nodes:\n"
            f"{json.dumps(grid[node_name].children, sort_keys=False, indent=4)}\n"
            "Make sure to display all cable layers and fix."
        )

    for cable in grid[node_name].cables:
        children = cables[cable["layer"]][cable["idx"]].nodes
        for child in children:
            if child != node_name:
                children_dict[child] = {
                    "cable": {
                        "layer": cable["layer"],
                        "idx": cable["idx"],
                    }
                }

    if node_name != "generator":
        try:
            del children_dict[grid[node_name].parent]
        except (KeyError, ValueError):
            pass
    else:
        grid[node_name].parent = ""

    grid[node_name].children = children_dict
    for child in children_dict:
        grid[child].parent = node_name

    if node_name == "generator":
        grid[node_name].deepness = 0
    else:
        parent = grid[node_name].parent
        if parent is not None:
            grid[node_name].deepness = grid[parent].deepness + 1

    for child in children_dict:
        grid, _ = get_children(child, grid, cables)

    return grid, children_dict


def compute_deepness_list(grid):
    dmax = 0
    for load in grid:
        deepness = grid[load].deepness
        if deepness is not None:
            dmax = max(dmax, deepness)

    dlist = [None] * (dmax + 1)
    for load in grid:
        deepness = grid[load].deepness
        if deepness is not None:
            if dlist[deepness] is None:
                dlist[deepness] = []
            dlist[deepness].append(load)
    return dlist


# ---------------------------------------------------------------------------
# Electrical analysis: cumulate current, distro requirements, voltage drop
# ---------------------------------------------------------------------------


def cumulate_current(grid, cables_dict, dlist, v0, pf):
    for deepness in range(len(dlist) - 1, 0, -1):
        loads = dlist[deepness]
        for load in loads:
            parent = grid[load].parent
            grid[load].cum_power += grid[load].power
            grid[parent].cum_power += grid[load].cum_power

            cable = cables_dict[grid[load].cable["layer"]][grid[load].cable["idx"]]
            cable.current = list(grid[load].cum_power / v0 / pf)

            logger.debug(
                f"\t\t{load} cumulated power: "
                f"{np.array2string(1e-3 * grid[load].cum_power, precision=1, floatmode='fixed')}kW"
            )

    logger.debug(
        f"\tgenerator cumulated power: "
        f"{np.array2string(1e-3 * grid['generator'].cum_power, precision=1, floatmode='fixed')}kW"
    )
    return grid, cables_dict


def compute_distro_requirements(grid, cables_dict):
    logger.info("compute_distro_requirements...")
    for load in grid.values():
        logger.debug(f"\t\t {load.name}:")

        if (load.parent is not None) and (len(load.parent) > 0):
            cable2parent_ref = load.cable
            cable2parent = cables_dict[cable2parent_ref["layer"]][cable2parent_ref["idx"]]
            if "3phases" in cable2parent_ref["layer"]:
                ph = "3P"
            elif "1phase" in cable2parent_ref["layer"]:
                ph = "1P"
            else:
                logger.info("\t\t\t can't figure out if this cable is 3P or 1P")

            if cable2parent.plugs_and_sockets is None:
                raise ValueError("cable2parent.plugs_and_sockets is None")
            load.distro["in"] = f"{ph} {cable2parent.plugs_and_sockets}A"

        elif load.name == "generator":
            load.distro["in"] = "3P 125A"

        load.distro["out"] = {}
        if load.children is not None:
            cables2children_ref = [load.children[child]["cable"] for child in load.children]
            cables2children = [cables_dict[c["layer"]][c["idx"]] for c in cables2children_ref]
            for idx, cable in enumerate(cables2children):
                if "3phases" in cables2children_ref[idx]["layer"]:
                    ph = "3P"
                elif "1phase" in cables2children_ref[idx]["layer"]:
                    ph = "1P"
                else:
                    logger.info("\t\t\t can't figure out if this cable is 3P or 1P")

                desc = f"{ph} {cable.plugs_and_sockets}A"
                if desc not in load.distro["out"]:
                    load.distro["out"][desc] = 1
                else:
                    load.distro["out"][desc] += 1

    return grid


def compute_voltage_drop(grid, cables_dict, load=None):
    logger.debug(f"\n\t propagating vdrop to {load}")

    if load is None:
        load = "generator"
        grid[load].voltage = V0
        grid[load].vdrop_percent = 0.0
    else:
        parent = grid[load].parent
        cable = cables_dict[grid[load].cable["layer"]][grid[load].cable["idx"]]
        cable.vdrop_volts = _vdrop_coef * cable.r * np.max(cable.current)
        grid[load].voltage = grid[parent].voltage - cable.vdrop_volts
        grid[load].vdrop_percent = 100 * (V0 - grid[load].voltage) / _vdrop_ref

        logger.debug(f"\t\t cable: length {cable.length:.0f}m, area: {cable.area:.1f}mm²")
        logger.debug(f"\t\t voltage at parent: {grid[parent].voltage:.0f}V")
        logger.debug(f"\t\t voltage at load: {grid[load].voltage:.0f}V")
        logger.debug(f"\t\t vdrop: {grid[load].vdrop_percent:.1f}%")

        if grid[load].vdrop_percent > VDROP_THRESHOLD_PERCENT:
            logger.info(f"\t /!\\ vdrop of {grid[load].vdrop_percent:.1f} percent at {load}")

    for child in grid[load].children:
        grid, cables_dict = compute_voltage_drop(grid, cables_dict, child)

    return grid, cables_dict


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_grid_info(grid, cables_dict, phase_balance, has_no_phase, dlist):
    logger.info("\n === info about the grid === \n")

    logger.info(
        f"total power: "
        f"{1e-3 * np.sum(grid['generator'].cum_power):.0f}kW \t "
        f"{np.round(1e-3 * grid['generator'].cum_power, 1)}kW "
        f"/ {np.round(grid['generator'].cum_power / PF / V0)}A"
    )

    if phase_balance > 5:
        flag = " <<<<<<<<<<"
    else:
        flag = ""
    logger.info(f"phase balance: {phase_balance.round(1)} % {flag}")

    for deep in range(len(dlist)):
        logger.info(f"\t deepness {deep}")
        for load in dlist[deep]:
            pwr_per_phase = np.round(1e-3 * grid[load].cum_power, 1).tolist()
            pwr_total = 1e-3 * np.sum(grid[load].cum_power)
            vdrop = grid[load].vdrop_percent
            flag = " <<<<<<<<<<" if vdrop > 5 else ""
            logger.info(
                f"\t\t {load:20} cum_power={pwr_per_phase}kW, "
                f"total {pwr_total:5.1f}kW, vdrop {vdrop:.1f}%"
                f"{flag} "
            )

    logger.info("\nLoads not connected to a cable:")
    for load in grid:
        needs_power = bool(np.double(grid[load].power > 0).sum())
        is_unconnected = grid[load]._cable == []
        is_load = grid[load].name != "generator"
        if is_unconnected and is_load and needs_power:
            logger.info(f"\t{load}")

    logger.info(f"\nLoads without a phase assigned: \n\t{has_no_phase} \n ")

    logger.info("total power on other grids: ")
    subgrid_dict = {"tot": 0.0, "msg": ""}
    subgrid = {"red": subgrid_dict.copy(), "yellow": subgrid_dict.copy()}
    for load in grid:
        if grid[load].phase == "U":
            g = "red"
        elif grid[load].phase == "Y":
            g = "yellow"
        else:
            g = None

        if g is not None:
            subgrid[g]["tot"] += grid[load].power
            subgrid[g]["msg"] += f"\t\t {load} ({grid[load].power}W) \n"

    for subgrid_name, subgrid_val in subgrid.items():
        tot = subgrid_val["tot"]
        if isinstance(tot, np.ndarray):
            tot = tot.sum()
        logger.info(f"\t {subgrid_name} grid: {tot / 1e3:.1f}kW / {tot / V0:.1f}A")
        logger.info(subgrid_val["msg"])

    logger.debug("\ndistro requirements:")
    for deep in range(len(dlist)):
        logger.debug(f"\t deepness {deep}")
        for load in dlist[deep]:
            logger.debug(f"\t\t {load}:")
            distro = grid[load].distro
            logger.debug(f"\t\t\t in: {distro['in']}")
            logger.debug("\t\t\t out: ")
            for desc in distro["out"]:
                logger.debug(f"\t\t\t\t {desc}: {distro['out'][desc]}")
