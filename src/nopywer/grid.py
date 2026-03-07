import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .constants import CONNECTION_THRESHOLD_M, PF, V0, VDROP_THRESHOLD_PERCENT
from .geometry import geodesic_distance_m
from .io import load_geojson, print_grid_info, to_geojson
from .models import Cable, PowerNode

logger = logging.getLogger(__name__)


@dataclass
class PowerGrid:
    nodes: dict[str, PowerNode]
    cables: dict[str, Cable]
    tree: list[list[str]] = field(default_factory=list, repr=False)

    @classmethod
    def from_geojson(cls, path: str | Path) -> "PowerGrid":
        """Parse a GeoJSON file containing Point (nodes) and LineString (cables)."""
        nodes, cables = load_geojson(path)
        return cls(nodes=nodes, cables=cables)

    @property
    def generator(self) -> PowerNode:
        return self.nodes["generator"]

    @property
    def phase_balance(self) -> float:
        cum = self.generator.cum_power
        return float(100 * np.std(cum) / np.mean(cum))

    @property
    def unphased_loads(self) -> list[str]:
        return [
            name
            for name, node in self.nodes.items()
            if not node.is_generator and node.phase is None
        ]

    def analyze(self) -> None:
        self._snap_cables_to_nodes()
        self.tree = self._build_tree()
        self._cumulate_current()
        self._compute_distro_requirements()
        self._compute_voltage_drop("generator")

    def to_geojson(self) -> dict:
        return to_geojson(self.nodes, self.cables)

    def print_info(self) -> None:
        print_grid_info(self.nodes, self.cables, self.tree)

    def _snap_cables_to_nodes(self) -> None:
        for cable in self.cables.values():
            for attr, endpoint in [
                ("from_node", cable.from_coords),
                ("to_node", cable.to_coords),
            ]:
                if getattr(cable, attr) != "":
                    continue
                for node in self.nodes.values():
                    dist = geodesic_distance_m(endpoint[0], endpoint[1], node.lon, node.lat)
                    if dist <= CONNECTION_THRESHOLD_M:
                        setattr(cable, attr, node.name)
                        break

    def _build_node_cables(self) -> dict[str, list[str]]:
        node_cables: dict[str, list[str]] = defaultdict(list)
        for cable_id, cable in self.cables.items():
            if cable.from_node:
                node_cables[cable.from_node].append(cable_id)
            if cable.to_node:
                node_cables[cable.to_node].append(cable_id)
        return dict(node_cables)

    def _build_tree(self) -> list[list[str]]:
        node_cables = self._build_node_cables()
        self._assign_children("generator", node_cables)
        return self._compute_dlist()

    def _assign_children(self, node_name: str, node_cables: dict[str, list[str]]) -> None:
        node = self.nodes[node_name]

        if node.children:
            raise ValueError(
                f"\n\nInfinite loop at {node_name}.\n"
                f"Connected nodes:\n"
                f"{json.dumps(node.children, sort_keys=False, indent=4)}\n"
                "Fix the cable layout."
            )

        children: dict[str, str] = {}
        for cable_id in node_cables.get(node_name, []):
            cable = self.cables[cable_id]
            for endpoint in (cable.from_node, cable.to_node):
                if endpoint and endpoint != node_name:
                    children[endpoint] = cable_id

        if node_name == "generator":
            node.parent = ""
            node.deepness = 0
        else:
            children.pop(node.parent, None)
            parent = self.nodes.get(node.parent)
            if parent is not None:
                node.deepness = parent.deepness + 1

        node.children = children
        for child_name, cable_id in children.items():
            self.nodes[child_name].parent = node_name
            self.nodes[child_name].cable_to_parent = cable_id

        for child_name in children:
            self._assign_children(child_name, node_cables)

    def _compute_tree(self) -> list[list[str]]:
        dmax = max(
            (n.deepness for n in self.nodes.values() if n.deepness is not None),
            default=0,
        )
        dlist: list[list[str]] = [[] for _ in range(dmax + 1)]
        for node in self.nodes.values():
            if node.deepness is not None:
                dlist[node.deepness].append(node.name)
        return dlist

    def _cumulate_current(self) -> None:
        for depth in range(len(self.tree) - 1, 0, -1):
            for name in self.tree[depth]:
                node = self.nodes[name]
                parent = self.nodes[node.parent]
                node.cum_power += node.power_per_phase
                parent.cum_power += node.cum_power

                cable = self.cables[node.cable_to_parent]
                cable.current_per_phase = list(node.cum_power / V0 / PF)

                logger.debug(
                    f"\t\t{name} cumulated power: "
                    f"{np.array2string(1e-3 * node.cum_power, precision=1, floatmode='fixed')}kW"
                )

        logger.debug(
            f"\tgenerator cumulated power: "
            f"{np.array2string(1e-3 * self.generator.cum_power, precision=1, floatmode='fixed')}kW"
        )

    def _compute_distro_requirements(self) -> None:
        logger.info("compute_distro_requirements...")
        for node in self.nodes.values():
            logger.debug(f"\t\t {node.name}:")

            if node.parent and len(node.parent) > 0:
                cable = self.cables[node.cable_to_parent]
                ph = "3P" if cable.plugs_and_sockets_a > 16 else "1P"
                node.distro["in"] = f"{ph} {cable.plugs_and_sockets_a}A"
            elif node.is_generator:
                node.distro["in"] = "3P 125A"

            node.distro["out"] = {}
            if node.children:
                for cable_id in node.children.values():
                    cable = self.cables[cable_id]
                    ph = "3P" if cable.plugs_and_sockets_a > 16 else "1P"
                    desc = f"{ph} {cable.plugs_and_sockets_a}A"
                    node.distro["out"][desc] = node.distro["out"].get(desc, 0) + 1

    def _compute_voltage_drop(self, node_name: str) -> None:
        node = self.nodes[node_name]

        if node_name == "generator":
            node.voltage = V0
            node.vdrop_percent = 0.0
        else:
            parent = self.nodes[node.parent]
            cable = self.cables[node.cable_to_parent]
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
            self._compute_voltage_drop(child_name)
