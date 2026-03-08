import json
import logging
from collections import defaultdict

import numpy as np

from .constants import CONNECTION_THRESHOLD_M, PF, V0, VDROP_THRESHOLD_PERCENT
from .geometry import geodesic_distance_m
from .models import PowerGrid

logger = logging.getLogger(__name__)


def _snap_cables_to_nodes(grid: PowerGrid) -> None:
    for cable in grid.cables.values():
        for attr, endpoint in [("from_node", cable.from_coords), ("to_node", cable.to_coords)]:
            if getattr(cable, attr) != "":
                continue
            for node in grid.nodes.values():
                dist = geodesic_distance_m(endpoint[0], endpoint[1], node.lon, node.lat)
                if dist <= CONNECTION_THRESHOLD_M:
                    setattr(cable, attr, node.name)
                    break


def _build_node_cables(grid: PowerGrid) -> dict[str, list[str]]:
    node_cables: dict[str, list[str]] = defaultdict(list)
    for cable_id, cable in grid.cables.items():
        if cable.from_node:
            node_cables[cable.from_node].append(cable_id)
        if cable.to_node:
            node_cables[cable.to_node].append(cable_id)
    return dict(node_cables)


def _assign_children(
    grid: PowerGrid,
    node_name: str,
    node_cables: dict[str, list[str]],
) -> None:
    node = grid.nodes[node_name]

    if node.children:
        raise ValueError(
            f"\n\nInfinite loop at {node_name}.\n"
            f"Connected nodes:\n"
            f"{json.dumps(node.children, sort_keys=False, indent=4)}\n"
            "Fix the cable layout."
        )

    children: dict[str, str] = {}
    for cable_id in node_cables.get(node_name, []):
        cable = grid.cables[cable_id]
        for endpoint in (cable.from_node, cable.to_node):
            if endpoint and endpoint != node_name:
                children[endpoint] = cable_id

    if node_name == grid.generator.name:
        node.parent = ""
        node.deepness = 0
    else:
        children.pop(node.parent, None)
        parent = grid.nodes.get(node.parent)
        if parent is not None:
            node.deepness = parent.deepness + 1

    node.children = children
    for child_name, cable_id in children.items():
        grid.nodes[child_name].parent = node_name
        grid.nodes[child_name].cable_to_parent = cable_id

    for child_name in children:
        _assign_children(grid, child_name, node_cables)


def _build_tree(grid: PowerGrid) -> list[list[str]]:
    node_cables = _build_node_cables(grid)
    _assign_children(grid, grid.generator.name, node_cables)
    return _compute_tree(grid)


def _compute_tree(grid: PowerGrid) -> list[list[str]]:
    dmax = max(
        (node.deepness for node in grid.nodes.values() if node.deepness is not None),
        default=0,
    )
    dlist: list[list[str]] = [[] for _ in range(dmax + 1)]
    for node in grid.nodes.values():
        if node.deepness is not None:
            dlist[node.deepness].append(node.name)
    return dlist


def _cumulate_current(grid: PowerGrid) -> None:
    for depth in range(len(grid.tree) - 1, 0, -1):
        for name in grid.tree[depth]:
            node = grid.nodes[name]
            parent = grid.nodes[node.parent]
            node.cum_power += node.power_per_phase
            parent.cum_power += node.cum_power

            cable = grid.cables[node.cable_to_parent]
            cable.current_per_phase = list(node.cum_power / V0 / PF)

            logger.debug(
                f"\t\t{name} cumulated power: "
                f"{np.array2string(1e-3 * node.cum_power, precision=1, floatmode='fixed')}kW"
            )

    logger.debug(
        f"\tgenerator cumulated power: "
        f"{np.array2string(1e-3 * grid.generator.cum_power, precision=1, floatmode='fixed')}kW"
    )


def _compute_distro_requirements(grid: PowerGrid) -> None:
    logger.info("compute_distro_requirements...")
    for node in grid.nodes.values():
        logger.debug(f"\t\t {node.name}:")

        if node.parent and len(node.parent) > 0:
            cable = grid.cables[node.cable_to_parent]
            ph = "3P" if cable.plugs_and_sockets_a > 16 else "1P"
            node.distro["in"] = f"{ph} {cable.plugs_and_sockets_a}A"
        elif node.is_generator:
            node.distro["in"] = "3P 125A"

        node.distro["out"] = {}
        if node.children:
            for cable_id in node.children.values():
                cable = grid.cables[cable_id]
                ph = "3P" if cable.plugs_and_sockets_a > 16 else "1P"
                desc = f"{ph} {cable.plugs_and_sockets_a}A"
                node.distro["out"][desc] = node.distro["out"].get(desc, 0) + 1


def _compute_voltage_drop(grid: PowerGrid, node_name: str | None = None) -> None:
    node_name = grid.generator.name if node_name is None else node_name
    node = grid.nodes[node_name]

    if node_name == grid.generator.name:
        node.voltage = V0
        node.vdrop_percent = 0.0
    else:
        parent = grid.nodes[node.parent]
        cable = grid.cables[node.cable_to_parent]
        cable.vdrop_volts = cable.resistance * np.max(cable.current_per_phase)
        node.voltage = parent.voltage - cable.vdrop_volts
        node.vdrop_percent = 100 * (V0 - node.voltage) / V0

        logger.debug(f"\t\t cable: length {cable.length_m:.0f}m, area: {cable.area_mm2:.1f}mm²")
        logger.debug(f"\t\t voltage at parent: {parent.voltage:.0f}V")
        logger.debug(f"\t\t voltage at load: {node.voltage:.0f}V")
        logger.debug(f"\t\t vdrop: {node.vdrop_percent:.1f}%")

        if node.vdrop_percent > VDROP_THRESHOLD_PERCENT:
            logger.info(f"\t /!\\ vdrop of {node.vdrop_percent:.1f} percent at {node_name}")

    for child_name in node.children:
        _compute_voltage_drop(grid, child_name)


def analyze(grid: PowerGrid) -> None:
    if not grid.cables:
        raise ValueError("At least one cable is required")
    _snap_cables_to_nodes(grid)
    grid.tree = _build_tree(grid)
    _cumulate_current(grid)
    _compute_distro_requirements(grid)
    _compute_voltage_drop(grid)
