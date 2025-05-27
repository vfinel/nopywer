from qgis.core import edit, QgsProject
from .get_layer import get_layer
from .get_grid_geometry import get_load_name
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsField

# based on https://gis.stackexchange.com/questions/428973/writing-list-as-attribute-field-in-pyqgis


def update_1phase_layers(grid: dict, cables: dict, project: QgsProject):
    verbose = 0

    print("\nupdating 1-phase layers with phase label...")

    # write phase (=attribute) for each cable (=feature) of each cable layer
    for cable_layer_name in cables.keys():
        if "1phase" in cable_layer_name:
            if verbose:
                print(f"\t cable layer {cable_layer_name}")
            cable_layer = get_layer(project, cable_layer_name)
            if not cable_layer.isEditable():
                with edit(cable_layer):
                    for i, cable in enumerate(list(cable_layer.getFeatures())):
                        if (
                            cables[cable_layer_name][i].current is not None
                        ):  # don't update not connecte cables
                            phase = cables[cable_layer_name][i].phase
                            if phase is None:
                                phase = 0

                            if verbose:
                                print(
                                    f"\t\t cable idx {i} on phase {phase} (type: {type(phase)})"
                                )
                            if phase == "T":
                                raise ValueError(
                                    f'cable idx {i} cannot be on phase "{phase}" because it is in a single phase layer.'
                                )

                            cable.setAttribute("phase", f"{phase}")
                            try:
                                cable_layer.updateFeature(cable)

                            except ValueError as err:
                                print(
                                    f'problem found in {cable_layer_name} while updating cable idx {i} with phase info "{phase}":'
                                )
                                print(err.args)
                                raise ValueError(err.args)

            else:
                raise ValueError(
                    f'Layer "{cable_layer_name}" cannot be edited by nopywer '
                    "because it is already in edit mode in QGIS. Please untoggle edit mode."
                )

    return None


def update_load_layers(grid: dict, loads_layers_list: list, project: QgsProject):
    # write nodes' power and cum_power (=attributes) for each nodes (=feature) of load layer
    print("\nupdating load layers with power usage and cumulated power...")
    for load_layer_name in loads_layers_list:
        layer = get_layer(project, load_layer_name)

        # Ensure 'distro assigned' field exists
        distro_field = "distro assigned"
        if distro_field not in layer.fields().names():
            layer.dataProvider().addAttributes(
                [QgsField(distro_field, QVariant.String)]
            )
            layer.updateFields()

        if not layer.isEditable():
            with edit(layer):
                for load in list(layer.getFeatures()):
                    load_name = get_load_name(load)

                    if load_name in grid.keys():
                        field = "power"
                        assert field in load.fields().names(), (
                            f'layer "{load_layer_name} does not have a field "{field}"'
                        )
                        load.setAttribute(
                            field, f"{1e-3 * grid[load_name].power.sum()}"
                        )

                        if (
                            grid[load_name].cum_power is not None
                        ):  # this can be False if load is not connected
                            assert field in load.fields().names(), (
                                f'layer "{load_layer_name}" does not have a field cum_power"'
                            )
                            load.setAttribute(
                                field, f"{1e-3 * sum(grid[load_name].cum_power)}"
                            )

                        # Check for "distro assigned" field and set it if present
                        distro_value = getattr(grid[load_name], "distro_chosen", None)
                        load.setAttribute(distro_field, str(distro_value))

                        layer.updateFeature(load)

        else:
            raise ValueError(
                f'Layer "{load_name}" cannot be edited by nopywer '
                "because it is already in edit mode in QGIS. Please untoggle edit mode."
            )

    return None
