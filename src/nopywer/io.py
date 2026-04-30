import json
import logging
from pathlib import Path
import re 

import numpy as np

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode

logger = logging.getLogger(__name__)


def _parse_power_per_phase(power: float, phase: str | int):
    """
    TODO:
        - add description 
        - add tests: (check value returned ?)
            phase = ['1', '1,2', '1,2,3',
                    '4', '1,4', '1,2,3,1', {}]
        - can doctests be ran with pytests ?
    """
    power_per_phase = np.zeros(3)

    if isinstance(phase, int):
        if 1 <= phase <= 3:
            power_per_phase[phase - 1] = power
        else:
            raise ValueError(f"phase must be between 1 and 3 but is {phase}")
    
    elif isinstance(phase, str):
        match = re.findall('\\d+', phase) 

        # version for n-phases:
        n_phases = len(match)
        for ph in match:
            idx = int(ph)-1
            power_per_phase[idx] = power / n_phases


    else:
        logger.info(f"unable to parse phase ({phase}), assuming 3-phases repartition.")
        power_per_phase += power / 3
    
    logger.debug(f"{power_per_phase = }")

    return power_per_phase 


def load_geojson(source: str | Path | dict) -> tuple[dict[str, PowerNode], dict[str, Cable]]:
    """Parse a GeoJSON FeatureCollection (file path or dict).

    Returns (nodes_dict, cables_dict).
    TODO: check that coordinates are actual longitude and latitude (abs(360) as a rough check ?)
    """
    if isinstance(source, dict):
        fc = source
    else:
        with open(source) as f:
            fc = json.load(f)

    nodes: list[PowerNode] = []
    cables: list[Cable] = []
    cable_counter = 0

    for feature in fc.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        gtype = geom.get("type", "")

        if gtype == "Point":
            name = (props.get("name") or "").strip().lower()
            if not name:
                continue
            coords = geom["coordinates"]
            power = float(props.get("power", 0) or 0)
            phase = props.get("phase")

            node = PowerNode(
                name=name,
                lon=coords[0],
                lat=coords[1],
                power_watts=power,
                is_generator=("generator" in name),
                phase=phase,
            )

            node.power_per_phase = _parse_power_per_phase(power, phase)

            nodes.append(node)

        elif gtype == "LineString" or "MultiLineString":
            coords = geom.get("coordinates", [])
            
            if gtype == "MultiLineString":
                # TODO: what happens if Line has more than one edge ?
                coords =  coords[0]

            if len(coords) < 2:
                logger.warning('Line as less than two points, discarding it.')
                continue

            area = float(props.get("area", 2.5) or 2.5)
            ps = float(props.get("plugs&sockets", 16.0) or 16.0)

            length = float(props.get("length", 0) or 0)
            if length <= 0:
                length = geodesic_distance_m(
                    coords[0][0], coords[0][1], coords[-1][0], coords[-1][1]
                )
            length += EXTRA_CABLE_LENGTH_M

            cable = Cable(
                id=f"cable_{cable_counter}",
                length_m=length,
                area_mm2=area,
                plugs_and_sockets_a=ps,
                phase=props.get("phase"),
                from_coords=(coords[0][0], coords[0][1]),
                to_coords=(coords[-1][0], coords[-1][1]),
            )

            cables.append(cable)
            cable_counter += 1

        else:
            logger.warning(f"{feature = } has an unrecongized {gtype :}")
    
    return {n.name: n for n in nodes}, {c.id: c for c in cables}


def print_grid_info(
    nodes: dict[str, PowerNode],
    cables: dict[str, Cable],
    dlist: list[list[str]],
    generator: PowerNode,
) -> None:
    """Log a human-readable grid summary."""
    logger.info(" === info about the grid === ")
    logger.info(
        f" total power: "
        f"{1e-3 * np.sum(generator.cum_power):.0f}kW \t "
        f"{np.round(1e-3 * generator.cum_power, 1)}kW "
        f"/ {np.round(generator.cum_power / PF / V0)}A"
    )

    cum = generator.cum_power
    pb = float(100 * np.std(cum) / np.mean(cum))
    flag = " <<<<<<<<<<" if pb > 5 else ""
    logger.info(f" phase balance: {pb:.1f} % {flag}")

    for deep, names in enumerate(dlist):
        logger.info(f"\t deepness {deep}")
        for name in names:
            node = nodes[name]
            pwr = np.round(1e-3 * node.cum_power, 1).tolist()
            total = 1e-3 * np.sum(node.cum_power)
            vd = node.vdrop_percent
            flag = " <<<<<<<<<<" if vd > 5 else ""
            logger.info(
                f"\t\t {name:20} cum_power={pwr}kW, total {total:5.1f}kW, vdrop {vd:.1f}%{flag} "
            )

    loads_not_connected = []
    for name, node in nodes.items():
        needs_power = bool(np.double(node.power_per_phase > 0).sum())
        load_not_connected = node.cable_to_parent is None and not node.is_generator and needs_power
        if load_not_connected:
            if len(loads_not_connected)==0:
                logger.warning(" Loads not connected to a cable:")
            loads_not_connected.append(node)
            logger.info(f"\t{name}")

    unphased = [n for n, nd in nodes.items() if not nd.is_generator and nd.phase is None]
    if len(unphased):
        logger.info(f" Loads without a phase assigned: ")
        logger.info(f"\t{unphased} \n ")

    logger.info(" total power on other grids: ")
    subgrid_dict = {"tot": 0.0, "msg": ""}
    subgrid = {"red": subgrid_dict.copy(), "yellow": subgrid_dict.copy()}
    for name, node in nodes.items():
        g = {"U": "red", "Y": "yellow"}.get(node.phase)
        if g is not None:
            subgrid[g]["tot"] += node.power_per_phase
            subgrid[g]["msg"] += f"\t\t {name} ({node.power_watts}W) \n"

    for sg_name, sg_val in subgrid.items():
        tot = sg_val["tot"]
        if isinstance(tot, np.ndarray):
            tot = tot.sum()
        logger.info(f"\t {sg_name} grid: {tot / 1e3:.1f}kW / {tot / V0:.1f}A")
        logger.info(sg_val["msg"])

    logger.debug("\ndistro requirements:")
    for deep, names in enumerate(dlist):
        logger.debug(f"\t deepness {deep}")
        for name in names:
            distro = nodes[name].distro
            logger.debug(f"\t\t {name}:")
            logger.debug(f"\t\t\t in: {distro['in']}")
            logger.debug("\t\t\t out: ")
            for desc, count in distro["out"].items():
                logger.debug(f"\t\t\t\t {desc}: {count}")
