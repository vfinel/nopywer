from .get_layer import get_layer
from .logger_config import logger


def inspect_cable_layers(project, cables_layers_list, cables_nopywer: dict):
    logger.info("\n inspect cable layer:")
    inventory_3P = 785  # todo: smarter thing
    inventory_1P = 2340
    tot1P = 0  # [m] total length of 1P cables
    tot3P = 0  # [m] total length of 3P cables
    n1P = 0  # total number of 1P cables
    n3P = 0  # total number of 3P cables
    current_overloads = ""

    for cable_layer_name in cables_layers_list:
        cable_layer = get_layer(project, cable_layer_name)
        cables_qgis = cable_layer.getFeatures()
        # note that cables_qgis is an interator, so needs to be reset after each load
        totLayer = 0

        for cable_idx, cable in enumerate(cables_qgis):
            cable_nopywer = cables_nopywer[cable_layer_name][cable_idx]

            # --- get length
            totLayer += cable_nopywer.length
            msg = f"\t\tcable layer {cable_layer_name} idx {cable_idx} has length {cable_nopywer.length:.1f}m"
            if cable_nopywer.length < 5:
                raise ValueError(msg)

            logger.debug(msg)

            # --- get cable area and plugs&sockets type
            cable_info = {"layer": cable_layer_name, "idx": cable_idx}

            # --- check current
            if (len(cable_nopywer.current) > 0) and (
                cable_nopywer.plugs_and_sockets != None
            ):
                if max(cable_nopywer.current) >= 0.9 * (
                    cable_nopywer.plugs_and_sockets
                ):
                    current_str = ["%2.0f" % elem for elem in cable_nopywer.current]
                    a = f"\t /!\\ cable {cable_nopywer.nodes} overload:"
                    b = f"{current_str}A (plugs&sockets: {cable_nopywer.plugs_and_sockets}A) \n"
                    current_overloads += f"{a:60} {b}"

        n_cables_in_layer = cable_idx + 1
        if "1phase" in cable_layer_name:
            tot1P += totLayer
            n1P += n_cables_in_layer

        elif "3phases" in cable_layer_name:
            tot3P += totLayer
            n3P += n_cables_in_layer

        logger.info(
            f"\t total length of {cable_layer_name}: {totLayer:.0f} meters - {n_cables_in_layer} cables"
        )

    logger.info(
        f"\t total length of 1P cables: {tot1P:.0f} meters (inventory: {inventory_1P}m) - {n1P} cables"
    )
    logger.info(
        f"\t total length of 3P cables: {tot3P:.0f} meters (inventory: {inventory_3P}m) - {n3P} cables"
    )

    if (tot1P > 0.95 * inventory_1P) or (tot3P > 0.95 * inventory_3P):
        raise ValueError("You are running too short on cables (see above)")

    if len(current_overloads) > 0:
        logger.warning(f"\n{current_overloads}")

    else:
        logger.info("\t no overloaded cables")

    return cables_nopywer
