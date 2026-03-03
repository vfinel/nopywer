from __future__ import annotations

import json
from pathlib import Path

from .constants import EXTRA_CABLE_LENGTH_M
from .core_objects import Cable, Node
from .geometry import geodesic_distance_m


def load_grid_geojson(
    path: str | Path,
) -> tuple[list[Node], dict]:
    """Read a single GeoJSON file containing Point (nodes) and LineString (cables).

    Returns (nodes_list, cables_dict) where cables_dict is
    ``{layer_name: [Cable, ...]}``, matching the structure expected by
    the rest of the pipeline (inventory, distro requirements, etc.).
    """
    with open(path) as f:
        fc = json.load(f)

    nodes: list[Node] = []
    cables_by_layer: dict[str, list[Cable]] = {}

    for feature in fc.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        gtype = geom.get("type", "")

        if gtype == "Point":
            name = (props.get("name") or "").strip().lower()
            if not name:
                continue
            coords = geom["coordinates"]
            node = Node(name=name)
            node.coordinates = (coords[0], coords[1])

            power = float(props.get("power", 0) or 0)
            phase = props.get("phase")
            if isinstance(phase, int) and 1 <= phase <= 3:
                node.power[phase - 1] = power
            else:
                node.power += power / 3
            node.phase = phase
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
                    coords[0][0], coords[0][1],
                    coords[-1][0], coords[-1][1],
                )
            length += EXTRA_CABLE_LENGTH_M

            layer = props.get("layer") or (
                "3phases" if ps > 16 else "1phase"
            )

            cable = Cable(length=length, area=area, plugs_and_sockets=ps)
            cable.coordinates = [(c[0], c[1]) for c in coords]
            cable.phase = props.get("phase")
            cable.layer_name = layer
            cable.vdrop_volts = 0.0

            if layer not in cables_by_layer:
                cables_by_layer[layer] = []
            cable.id = len(cables_by_layer[layer])
            cables_by_layer[layer].append(cable)

    return nodes, cables_by_layer


def analysis_to_geojson(grid: dict, cables_dict: dict) -> dict:
    """Serialize analysis results back to a GeoJSON FeatureCollection."""
    features: list[dict] = []

    for cable_layer in cables_dict.values():
        for cable in cable_layer:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(c) for c in cable.coordinates],
                },
                "properties": {
                    "layer": cable.layer_name,
                    "nodes": cable.nodes,
                    "length_m": round(cable.length, 1),
                    "area_mm2": cable.area,
                    "plugs_and_sockets_a": cable.plugs_and_sockets,
                    "current_a": (
                        [round(c, 2) for c in cable.current]
                        if cable.current else []
                    ),
                    "vdrop_volts": round(cable.vdrop_volts, 2),
                },
            })

    for node in grid.values():
        coords = list(node.coordinates) if node.coordinates else [0, 0]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coords,
            },
            "properties": {
                "name": node.name,
                "type": "generator" if node.name == "generator" else "load",
                "power_watts": round(float(node.power.sum()), 1),
                "cum_power_watts": round(float(node.cum_power.sum()), 1),
                "voltage": round(
                    getattr(node, "voltage", 0.0), 1
                ),
                "vdrop_percent": round(
                    getattr(node, "vdrop_percent", 0.0), 2
                ),
                "distro": node.distro,
            },
        })

    return {"type": "FeatureCollection", "features": features}
