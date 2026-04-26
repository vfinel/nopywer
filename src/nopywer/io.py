import json
import logging
from pathlib import Path

import numpy as np

from .constants import EXTRA_CABLE_LENGTH_M, PF, V0
from .geometry import geodesic_distance_m
from .models import Cable, PowerNode

logger = logging.getLogger(__name__)

# A round-tripped nopywer export uses different property keys from the
# hand-authored input schema (e.g. `area_mm2` vs `area`). Map each export
# key onto its input-schema equivalent so either form loads.
_EXPORT_KEY_ALIASES = {
    "area_mm2": "area",
    "plugs_and_sockets_a": "plugs&sockets",
    "length_m": "length",
}

# Property keys we read from features after alias normalisation. Anything
# outside this set is either a nopywer-export computed field (silently
# ignored, the loader doesn't need it) or genuinely unknown (worth a
# DEBUG line so a fixture author can spot a typo). Keep in sync with
# what `load_geojson` actually reads.
_KNOWN_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        # input-schema keys read by the loader
        "name",
        "power",
        "phase",
        "area",
        "plugs&sockets",
        "length",
        # widely-used metadata we ignore but recognise
        "type",
        "id",
        "from",
        "to",
        "nodes",
        # nopywer-export computed fields (output of `PowerNode.to_geojson`
        # / `Cable.to_geojson`) — silently ignored on re-load
        "power_watts",
        "cum_power_watts",
        "cum_power",  # legacy export key (pre-2026); kept for back-compat
        "voltage",
        "vdrop_percent",
        "i_sc_ka",
        "distro",
        "cable_type",
        "current_a",
        "cum_power_kw",
        "vdrop_volts",
    }
)


def _normalise_keys(props: dict) -> dict:
    """Return props with export-schema keys renamed to input-schema keys."""
    return {_EXPORT_KEY_ALIASES.get(k, k): v for k, v in props.items()}


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
        raw_props = feature.get("properties", {})
        props = _normalise_keys(raw_props)
        gtype = geom.get("type", "")

        unknown = set(props) - _KNOWN_FEATURE_KEYS
        if unknown:
            logger.debug(
                "Feature %r carries property keys not used by load_geojson: %s. "
                "If one of these is a typo for a known key the value will be "
                "silently ignored.",
                props.get("name") or props.get("id") or "<unnamed>",
                sorted(unknown),
            )

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
            if isinstance(phase, int) and 1 <= phase <= 3:
                node.power_per_phase[phase - 1] = power
            elif isinstance(phase, list) and phase:
                # Multi-phase load: split power evenly across the listed legs
                # (e.g. phase=[1, 2] on a 10 kW load -> 5 kW on L1, 5 kW on L2).
                legs = [p for p in phase if isinstance(p, int) and 1 <= p <= 3]
                for leg in legs:
                    node.power_per_phase[leg - 1] += power / len(legs)
            else:
                if isinstance(phase, str):
                    logger.warning(
                        "Node %r has legacy string phase marker %r; treating "
                        "as unphased (balanced across L1/L2/L3). Strip these "
                        "markers from the fixture once the sub-grid reporting "
                        "they came from is no longer needed.",
                        name,
                        phase,
                    )
                node.power_per_phase += power / 3
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
    logger.info("\n === info about the grid === \n")
    logger.info(
        f"total power: "
        f"{1e-3 * np.sum(generator.cum_power):.0f}kW \t "
        f"{np.round(1e-3 * generator.cum_power, 1)}kW "
        f"/ {np.round(generator.cum_power / PF / V0)}A"
    )

    cum = generator.cum_power
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
