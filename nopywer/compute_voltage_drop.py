import numpy as np
from .get_constant_parameters import get_constant_parameters

# --- constant data
th_percent = 5  # vdrop threshold in %, above with a message is printed
CONSTANTS = get_constant_parameters()
V0 = CONSTANTS["V0"]


# --- parameters
vdrop_ref = np.sqrt(3) * V0
vdrop_coef = 1  # np.sqrt(3) # todo: change coef for 1-phase vs 3-phase https://drive.google.com/file/d/14_rlY05iPmopzXP5nSGixhvf_KH9mJ0p/view

verbose = 0


def compute_voltage_drop(grid: dict, cables_dict: dict, load=None):
    # load is supposed to be a string
    verbose = 0
    if verbose:
        print(f"\n\t propagating vdrop to {load}")

    if load == None:  # first call of the function. no vdrop at generator
        load = "generator"
        grid[load]["voltage"] = V0
        grid[load]["vdrop_percent"] = 0

    else:  # compute vdrop at load
        parent = grid[load]["parent"]
        cable = cables_dict[grid[load]["cable"]["layer"]][grid[load]["cable"]["idx"]]

        cable.vdrop_volts = vdrop_coef * cable.r * np.max(cable.current)
        grid[load]["voltage"] = grid[parent]["voltage"] - cable.vdrop_volts
        grid[load]["vdrop_percent"] = 100 * (V0 - grid[load]["voltage"]) / vdrop_ref

        if verbose:
            print(f"\t\t cable: length {cable.length:.0f}m, area: {cable.area:.1f}mm²")
            print(f"\t\t grid[parent]['voltage']: {grid[parent]['voltage']:.0f}V")
            print(f"\t\t grid[load]['voltage']: {grid[load]['voltage']:.0f}V")
            print(
                f"\t\t grid[load]['vdrop_percent']: {grid[load]['vdrop_percent']:.1f}%"
            )

        if grid[load]["vdrop_percent"] > th_percent:
            print(
                f"\t /!\\ vdrop of {grid[load]['vdrop_percent']:.1f} percent at {load}"
            )

    # recursive call
    children = grid[load]["children"].keys()
    for child in children:
        [grid, cables_dict] = compute_voltage_drop(grid, cables_dict, child)

    return grid, cables_dict
