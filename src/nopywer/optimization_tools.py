import openpyxl

from nopywer.models import _CABLE_TYPES

# import matplotlib.pyplot as plt
# import networkx as nx
# from qgis.core import QgsDistanceArea
# from nopywer.minimum_spanning_tree2 import minimum_spanning_tree

# def assign_phases_from_grid(nodes: dict, cables: list, logger: logging.Logger) -> dict:
#     children = {n: [] for n in nodes}
#     for cable in cables:
#         children[cable.from_node].append(cable.to_node)

#     generator = next(n for n, node in nodes.items() if node.is_generator)

#     def subtree_load(node):
#         return nodes[node].power_watts + sum(subtree_load(c) for c in children[node])

#     phases = [0, 0, 0]
#     node_phase = {generator: 0}

#     branches = sorted(
#         children[generator],
#         key=lambda n: subtree_load(n),
#         reverse=True  # asigna primero las ramas más pesadas
#     )

#     for branch in branches:
#         assigned = min(range(3), key=lambda p: phases[p])
#         phases[assigned] += subtree_load(branch)
#         logger.info(f"[PHASE] branch {branch}: {subtree_load(branch):.0f}W → phase {assigned}")

#         # Propaga fase a todo el subárbol
#         def propagate(node, phase):
#             node_phase[node] = phase
#             for child in children[node]:
#                 propagate(child, phase)

#         propagate(branch, assigned)

#     logger.info(f"[TOTAL PHASES] loads per phase: {phases}")
#     return node_phase  # {node_name: phase_int}


def assign_phases_from_grid(nodes: dict, cables: list) -> dict:
    children = {n: [] for n in nodes}
    for cable in cables:
        children[cable.from_node].append(cable.to_node)

    generator = next(n for n, node in nodes.items() if node.is_generator)

    def subtree_load(root):
        total = 0
        stack = [root]
        while stack:
            n = stack.pop()
            total += nodes[n].power_watts
            stack.extend(children[n])
        return total

    node_phase = {generator: 3}
    cable_phase = {}  # (from, to) → phase

    # (node, incoming phase, node father)
    queue = [(generator, 3, None)]

    while queue:
        node, incoming_phase, parent = queue.pop(0)
        cable = (
            next((c for c in cables if c.from_node == parent and c.to_node == node), None)
            if parent
            else None
        )
        if node.lower().split()[0] in ("mirror", "distro"):
            pass
        kids = sorted(children[node], key=lambda n: subtree_load(n), reverse=True)

        if len(kids) == 0:
            continue
        incoming_three_phase = (
            incoming_phase == 3
        )  # comes from generator or from a node with 3-phase cable

        # If the incoming cable is three-phase and there are 3 or more children,
        # this cable must be three-phase
        if incoming_three_phase and len(kids) >= 3:
            cable_phase[(parent, node)] = 3

        if len(kids) == 3:
            # Incoming cable can be three-phase and there are exactly 3 children:
            # assign 0, 1, 2 to the children
            for i, child in enumerate(kids):
                cable_phase[(node, child)] = i
                node_phase[child] = i
                queue.append((child, i, node))

        for kid in kids:
            # if node.lower().split()[0] in ("mirror", "distro"):
            #     pass
            cable_can_be_three_phase = cable.num_phases == 3 if cable else True
            kids_of_kid = sorted(children[kid], key=lambda n: subtree_load(n), reverse=True)
            if len(kids_of_kid) >= 3 and incoming_three_phase:
                # stop = 1  # debugging
                assign_phases_from_grid
            if incoming_three_phase and cable_can_be_three_phase and len(kids) == 3:
                # Splits incoming three-phase into three single-phase cables
                for i, child in enumerate(kids):
                    cable_phase[(node, child)] = i
                    node_phase[child] = i
                    queue.append((child, i, node))
                break

            else:
                # Inherits phase from parent or greedy by load if parent is three-phase
                if incoming_three_phase:
                    # comes from gennie but can't split into 3 → assign to
                    # the phase with less load
                    phase_loads = {0: 0, 1: 0, 2: 0}
                    for p_node, p in node_phase.items():
                        if p in phase_loads:
                            phase_loads[p] += nodes[p_node].power_watts

                    # Asign phases to kids one by one, starting with the heaviest,
                    # and always assigning to the phase with less load
                    for kid in kids:
                        kid_load = subtree_load(kid)
                        assigned = min(phase_loads, key=lambda p: phase_loads[p])
                        phase_loads[assigned] += kid_load

                        kids_of_kid = sorted(
                            children[kid], key=lambda n: subtree_load(n), reverse=True
                        )
                        if len(kids_of_kid) >= 3:
                            cable_phase[(node, kid)] = 3
                        else:
                            cable_phase[(node, kid)] = assigned
                        if len(kids_of_kid) >= 3 and cable_phase.get((node, kid), 0) == 3:
                            cable_phase[(node, kid)] = 3
                            assigned = 3
                        node_phase[kid] = assigned
                        queue.append((kid, assigned, node))
                else:
                    assigned = incoming_phase

                    cable_phase[(node, kid)] = assigned
                    node_phase[kid] = assigned
                    queue.append((kid, assigned, node))

    print("Cable phases are", cable_phase)

    phase_loads = {0: 0.0, 1: 0.0, 2: 0.0}
    for n, phase in node_phase.items():
        if phase in phase_loads and not nodes[n].is_generator:
            phase_loads[phase] += nodes[n].power_watts

    return node_phase, cable_phase, phase_loads


def segments_cross(p1, p2, p3, p4):
    """Returns True if segment p1-p2 crosses p3-p4"""

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def on_segment(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(
            p[1], r[1]
        )

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    if d1 == 0 and on_segment(p3, p1, p4):
        return True
    if d2 == 0 and on_segment(p3, p2, p4):
        return True
    if d3 == 0 and on_segment(p1, p3, p2):
        return True
    if d4 == 0 and on_segment(p1, p4, p2):
        return True
    return False


def load_inventory(path: str) -> list[dict]:
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    inventory = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        phases, section, plugs, length, quantity = row
        for i in range(int(quantity)):
            inventory.append(
                {
                    "id": f"cable_{section}mm2_{plugs}A_{length}m_{i}",
                    "section_mm2": float(section),
                    "plugs_a": float(plugs),
                    "length_m": float(length),
                    "num_phases": int(phases),
                    "tier": next(
                        t for t, tier in enumerate(_CABLE_TYPES) if tier.area_mm2 == float(section)
                    ),
                }
            )
    return inventory


# def phase_assignment_greedy(grid: dict):
#     """
#     each item has the foloowing:
#     - 'power' (or 'cum_power')
#             - name
#             - ....
#     """
#     phases = [{"total_load": 0}, {"total_load": 0}, {"total_load": 0}]

#     loads_unsorted = {key: value["power"].sum() for key, value in grid.items()}
#     loads = dict(sorted(loads_unsorted.items(), key=lambda x: x[1], reverse=True))
#     for key, value in loads.items():
#         assigned_phase = min(range(len(phases)), key=lambda i: phases[i]["total_load"])
#         # grid[key]['assigned_phase'] = assigned_phase
#         phases[assigned_phase]["total_load"] += value
#         print(f"{key}: {value:.0f}W, phase {assigned_phase}")

#     print(f"\ntotal on phases: {phases}")
#     phase_balance = 100 * np.std(
#         grid["generator"]["cum_power"] / np.mean(grid["generator"]["cum_power"])
#     )
#     print(f"balance : {phase_balance:.1f}%")

#     return loads
