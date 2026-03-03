import json
import logging
from pathlib import Path

import numpy as np

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode

logger = logging.getLogger(__name__)


def load_geojson(source: str | Path | dict) -> tuple[dict[str, PowerNode], dict[str, Cable]]:
    """Parse a GeoJSON FeatureCollection (file path or dict).

    Returns (nodes_dict, cables_dict).
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
                is_generator=(name == "generator"),
                phase=phase,
            )
            if isinstance(phase, int) and 1 <= phase <= 3:
                node.power_per_phase[phase - 1] = power
            else:
                node.power_per_phase += power / 3
            nodes.append(node)

        elif gtype == "LineString":
            coords = geom.get("coordinates", [])
            if len(coords) < 2:
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

    return {n.name: n for n in nodes}, {c.id: c for c in cables}


def to_geojson(nodes: dict[str, PowerNode], cables: dict[str, Cable]) -> dict:
    """Serialize analysis results to a GeoJSON FeatureCollection."""
    features: list[dict] = []

    for cable in cables.values():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(cable.from_coords), list(cable.to_coords)],
                },
                "properties": {
                    "nodes": [cable.from_node, cable.to_node],
                    "length_m": round(cable.length_m, 1),
                    "area_mm2": cable.area_mm2,
                    "plugs_and_sockets_a": cable.plugs_and_sockets_a,
                    "current_a": (
                        [round(c, 2) for c in cable.current_per_phase]
                        if cable.current_per_phase
                        else []
                    ),
                    "vdrop_volts": round(cable.vdrop_volts, 2),
                },
            }
        )

    for node in nodes.values():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node.lon, node.lat],
                },
                "properties": {
                    "name": node.name,
                    "type": "generator" if node.is_generator else "load",
                    "power_watts": round(float(node.power_per_phase.sum()), 1),
                    "cum_power_watts": round(float(node.cum_power.sum()), 1),
                    "voltage": round(node.voltage, 1),
                    "vdrop_percent": round(node.vdrop_percent, 2),
                    "distro": node.distro,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def print_grid_info(
    nodes: dict[str, PowerNode],
    cables: dict[str, Cable],
    dlist: list[list[str]],
) -> None:
    """Log a human-readable grid summary."""
    gen = nodes["generator"]
    logger.info("\n === info about the grid === \n")
    logger.info(
        f"total power: "
        f"{1e-3 * np.sum(gen.cum_power):.0f}kW \t "
        f"{np.round(1e-3 * gen.cum_power, 1)}kW "
        f"/ {np.round(gen.cum_power / PF / V0)}A"
    )

    cum = gen.cum_power
    pb = float(100 * np.std(cum) / np.mean(cum))
    flag = " <<<<<<<<<<" if pb > 5 else ""
    logger.info(f"phase balance: {pb:.1f} % {flag}")

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

    logger.info("\nLoads not connected to a cable:")
    for name, node in nodes.items():
        needs_power = bool(np.double(node.power_per_phase > 0).sum())
        if node.cable_to_parent is None and not node.is_generator and needs_power:
            logger.info(f"\t{name}")

    unphased = [n for n, nd in nodes.items() if not nd.is_generator and nd.phase is None]
    logger.info(f"\nLoads without a phase assigned: \n\t{unphased} \n ")

    logger.info("total power on other grids: ")
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


def layout_to_geojson(
    cables: list[Cable],
    nodes: dict[str, PowerNode],
) -> dict:
    """Convert optimized cable layout to a GeoJSON FeatureCollection."""
    features: list[dict] = []

    for cable in cables:
        max_current = max(cable.current_per_phase) if cable.current_per_phase else 0.0
        cum_power_w = max_current * V0 * PF * 3

        ph = "3P" if cable.plugs_and_sockets_a > 16 else "1P"
        cable_type = f"{ph} {cable.plugs_and_sockets_a:.0f}A — {cable.area_mm2}mm²"

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(cable.from_coords), list(cable.to_coords)],
                },
                "properties": {
                    "id": cable.id,
                    "from": cable.from_node,
                    "to": cable.to_node,
                    "length_m": round(cable.length_m, 1),
                    "area_mm2": cable.area_mm2,
                    "plugs_and_sockets_a": cable.plugs_and_sockets_a,
                    "cable_type": cable_type,
                    "current_a": round(max_current, 1),
                    "cum_power_kw": round(cum_power_w / 1000, 2),
                },
            }
        )

    for node in nodes.values():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node.lon, node.lat],
                },
                "properties": {
                    "name": node.name,
                    "type": "generator" if node.is_generator else "load",
                    "power_watts": node.power_watts,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}
