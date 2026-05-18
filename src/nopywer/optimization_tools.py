import logging

import openpyxl

from nopywer.models import _CABLE_TYPES
MULTI_PHASE_THRESHOLD_W = 10000  # 10kW

MULTI_PHASE_3_THRESHOLD_W = 11000  # >= 10kW → 3 phases
MULTI_PHASE_2_THRESHOLD_W = 8000   # >= 5kW  → 2 phases
                                # < 5kW   → 1 phases


def assign_phases_from_grid(nodes: dict, cables: list, logger: logging.Logger) -> tuple:
    children = {n: [] for n in nodes}
    cable_map = {}
    for cable in cables:
        children[cable.from_node].append(cable.to_node)
        cable_map[(cable.from_node, cable.to_node)] = cable

    generator = next(n for n, node in nodes.items() if node.is_generator)
    load_cache = {}
    descendant_cache = {}

    def get_load(root):
        if root in load_cache:
            return load_cache[root]
        total, stack = 0, [root]
        while stack:
            n = stack.pop()
            total += nodes[n].power_watts
            stack.extend(children[n])
        load_cache[root] = total
        return total

    def get_descendants(root):
        if root in descendant_cache:
            return descendant_cache[root]
        count, stack = 0, list(children[root])
        while stack:
            n = stack.pop()
            count += 1
            stack.extend(children[n])
        descendant_cache[root] = count
        return count

    for n in nodes:
        get_load(n)
        get_descendants(n)

    total_load = sum(n.power_watts for n in nodes.values() if not n.is_generator)
    total_nodes = len(nodes) - 1
    THREE_PHASE_DESCENDANT_THRESHOLD = total_nodes // 3
    THREE_PHASE_LOAD_THRESHOLD = total_load // 3

    def is_distro(name: str) -> bool:
        return name.lower().startswith('distro')

    def should_receive_three_phase(from_node, to_node) -> bool:
        cable = cable_map.get((from_node, to_node))
        num_phases = getattr(cable, 'num_phases', 3) if cable else 3
        if num_phases < 3:
            return False
        descendants = get_descendants(to_node)
        load = get_load(to_node)
        return (
            descendants >= THREE_PHASE_DESCENDANT_THRESHOLD or
            load >= THREE_PHASE_LOAD_THRESHOLD or
            is_distro(to_node)  # distros always receive 3-phase if possible
        )


    # Almacena el reparto real de cada nodo: {node: {0: W, 1: W, 2: W}}
    node_phase_split = {}

    def split_load_across_phases(node, load_w, phase_loads) -> dict:
        """
        Decides how to split node load across phases based on power.
        Returns {phase: watts} and updates phase_loads in place.
        """
        if load_w >= MULTI_PHASE_3_THRESHOLD_W:
            # 3 phases: equitable distribution
            split = {p: load_w / 3 for p in range(3)}

        elif load_w >= MULTI_PHASE_2_THRESHOLD_W:
            # 2 phases: the two least loaded
            sorted_phases = sorted(phase_loads, key=lambda p: phase_loads[p])
            p1, p2 = sorted_phases[0], sorted_phases[1]
            split = {p1: load_w / 2, p2: load_w / 2}

        else: #only one phase
            assigned = min(phase_loads, key=lambda p: phase_loads[p])
            split = {assigned: load_w}

        # Global counter update
        for p, w in split.items():
            phase_loads[p] += w

        logger.info(
            f"[PHASE SPLIT] {node}: {load_w:.0f}W → "
            + ", ".join(f"L{p}={w:.0f}W" for p, w in split.items())
        )
        return split
    
    def assign_phases_to_kids_balanced(node, kids, phase_loads):
        """
        Greedy balanced assignment for kids of a 3-phase node.
        Looks ahead at full subtree load of each kid.
        Returns {kid: phase} assignments.
        """
        assignments = {}
        local_loads = phase_loads.copy()

        for kid in sorted(kids, key=get_load, reverse=True):
            kid_load = get_load(kid)
            cable = cable_map.get((node, kid))
            num_phases = getattr(cable, 'num_phases', 3) if cable else 3

            if should_receive_three_phase(node, kid) or (kid_load >= MULTI_PHASE_2_THRESHOLD_W and num_phases == 3):
                assignments[kid] = 3  # cable trifásico
                # Split de carga según potencia
                split = split_load_across_phases(kid, kid_load, local_loads)
                node_phase_split[kid] = split
            else:
                assigned = min(local_loads, key=lambda p: local_loads[p])
                local_loads[assigned] += kid_load
                assignments[kid] = assigned
                node_phase_split[kid] = {assigned: kid_load}

        # Sync local_loads back to phase_loads
        for p in phase_loads:
            phase_loads[p] = local_loads[p]

        return assignments                    
                              
    node_phase = {generator: 3}
    cable_phase = {}
    phase_loads = {0: 0.0, 1: 0.0, 2: 0.0}

    queue = [(generator, 3)]

    while queue:
        node, incoming_phase = queue.pop(0)
        kids = sorted(children[node], key=get_load, reverse=True)

        if not kids:
            continue

        if incoming_phase == 3:
            assignments = assign_phases_to_kids_balanced(node, kids, phase_loads)

            for kid, phase in assignments.items():
                cable_phase[(node, kid)] = phase
                node_phase[kid] = phase
                queue.append((kid, phase))

        else:
            # Single-phase: check if kid is high-power enough to warrant 3-phase upgrade
            for kid in kids:
                kid_load = get_load(kid)
                cable = cable_map.get((node, kid))
                num_phases = getattr(cable, 'num_phases', 3) if cable else 3

                if kid_load >= MULTI_PHASE_THRESHOLD_W and num_phases == 3:
                    # High power node on single-phase branch: upgrade to 3-phase
                    cable_phase[(node, kid)] = 3
                    node_phase[kid] = 3
                    for p in range(3):
                        phase_loads[p] += kid_load / 3
                    queue.append((kid, 3))
                    logger.info(
                        f"[PHASE] {kid}: upgraded to 3-phase "
                        f"(load={kid_load:.0f}W >= {MULTI_PHASE_THRESHOLD_W}W)"
                    )
                else:
                    cable_phase[(node, kid)] = incoming_phase
                    node_phase[kid] = incoming_phase
                    queue.append((kid, incoming_phase))

    # Balance report
    real_phase_loads = {0: 0.0, 1: 0.0, 2: 0.0}
    for n, split in node_phase_split.items():
        if n.startswith('distro'):
            continue
        for p, w in split.items():
            real_phase_loads[p] += w

    total = sum(real_phase_loads.values())
    for p, load in real_phase_loads.items():
        pct = 100 * load / total if total else 0
        logger.info(f"[PHASE] L{p}: {load:.0f}W ({pct:.1f}%)")
    if total:
        imbalance = max(real_phase_loads.values()) - min(real_phase_loads.values())
        logger.info(f"[PHASE] imbalance: {imbalance:.0f}W ({100*imbalance/total:.1f}%)")

    return node_phase, cable_phase, real_phase_loads
    

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
