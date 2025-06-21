from itertools import combinations
import numpy as np
import os
import pandas as pd
import re
from .logger_config import logger


def find_combinations(arr: list, target_sum, th: float = 5.0):
    # find combination of cables from in the list 'arr', to have make the length 'target_sum', with thresholt 'th'
    # https://www.quora.com/How-can-Python-be-used-to-find-all-possible-combinations-of-numbers-in-an-array-that-add-up-to-a-given-sum
    # https://www.geeksforgeeks.org/python-closest-sum-pair-in-list/
    nMaxExtension = 4  # could go up to len(arr) but that would be a lot of extensions which increases the risks of failure are connectors
    output = None

    if len(arr) > 0:
        for n in range(1, nMaxExtension + 1):
            for combo in combinations(arr, n):
                found = 0 < (sum(combo) - target_sum) < th
                if found:
                    return combo

        if (not found) and (th < 5 * target_sum):
            # second arg is a sanity check to avoid infinite recursion
            # print(f'unable to find, trying with increase threshold to {th+5}m ')
            output = find_combinations(arr, target_sum, 1.5 * th)

    return output


def compute_cable_length_in_inventory():
    logger.info("\nReading inventory spreadsheet")
    sh = pd.read_excel(
        "../Miss PiggyInventory 2023.ods",  # TODO: why is this still here ?
        sheet_name="build2023",
        skiprows=2,
        engine="odf",
    )

    items = list(sh["Item"])
    qty = list(sh["Qty"])

    inventory = {}
    inventory["3p"] = {}
    inventory["1p"] = {}
    len_3p = 0
    len_1p = 0

    # loop through loads on the map and find corresponding info on the spreadsheet
    for idx, item in enumerate(items):
        # logger.debug(f'\titem: {item}')
        if isinstance(item, str):
            if "3P Cable" in item:
                idxStart = len("3P Cable")
                idxStop = item.index("m")
                length = float(item[idxStart:idxStop])
                len_3p += qty[idx] * length
                logger.debug(
                    f'\t\t3P cable: {qty[idx]} times "{item} (length: {length:.0f})"'
                )
                inventory["3p"][item] = {}
                inventory["3p"][item]["length"] = length
                inventory["3p"][item]["qty"] = qty[idx]

            elif "1P Cable" in item:
                idxStart = len("1P Cable")
                idxStop = item.index("m")
                length = float(item[idxStart:idxStop])
                len_1p += qty[idx] * length
                logger.debug(
                    f'\t\t1P cable: {qty[idx]} times "{item} (length: {length:.0f})"'
                )
                inventory["1p"][item] = {}
                inventory["1p"][item]["length"] = length
                inventory["1p"][item]["qty"] = qty[idx]

    logger.info(f"\n\t total 3p length: {len_3p:.0f}m")
    logger.info(f"\t total 1p length: {len_1p:.0f}m")


def choose_cables_in_inventory(
    project_path: str, cables_dict: dict, sh_name: str
) -> None:
    verbose = 1
    unmatched = []
    logger.info("\nReading cables inventory")
    df = pd.read_excel(
        os.path.join(project_path, sh_name),
        sheet_name="cables",
        skiprows=0,
        engine="odf",
    )

    if verbose >= 3:
        logger.debug(f"\t {df}")

    for cable_layer_name in cables_dict.keys():
        logger.debug(f"\n\t\t layer: {cable_layer_name}")

        # sort cables. Decreasing order allows to make sure long cables are used for long dsitances, decreasing number of extensions
        # https://stackoverflow.com/questions/72899/how-to-sort-a-list-of-dictionaries-by-a-value-of-the-dictionary-in-python
        cable_layer = sorted(
            cables_dict[cable_layer_name], key=lambda d: d.length, reverse=True
        )

        for idx, cable in enumerate(cable_layer):
            if verbose >= 2:
                logger.debug(
                    f"\n\t\t\t taking care of cable {idx + 1}/{len(cable_layer)}, length {cable['length']} m"
                )

            # get compatible cables
            if "3phases" in cable_layer_name:
                n_phases = 3

            elif "1phase" in cable_layer_name:
                n_phases = 1

            else:
                raise Exception(
                    f"unable to find out nuymber of phases of layer {cable_layer_name}"
                )

            if verbose >= 2:
                logger.debug(f" n phases: {n_phases}")

            compatible_rows = (
                (df["number of phases"] == n_phases)
                & (df["plugs&sockets [A]"] == cable.plugs_and_sockets)
                & (df["section [mm2]"] == cable.area)
            )

            compatible_df = df[compatible_rows]
            if verbose >= 2:
                logger.debug(f"\t\t\t compatible cables dataframe: \n {compatible_df}")

            comb = None
            if compatible_df.empty:
                if verbose >= 2:
                    logger.debug(
                        "DataFrame is empty --> no compatible cables in inventory!"
                    )

            else:
                # build a list of all compatible cables (account for their quantity) https://stackoverflow.com/questions/16476924/how-can-i-iterate-over-rows-in-a-pandas-dataframe
                list_of_cables = [
                    length
                    for qty, length in zip(
                        compatible_df["quantity"], compatible_df["length [m]"]
                    )
                    for i in range(qty)
                ]

                # find best combination
                # note that slack was added from "extra_cable_length" parameters when computing cables_dict
                target_sum = cable.length
                comb = find_combinations(list_of_cables, target_sum)
                if (comb == None) | verbose:
                    logger.debug(f"\t\t\t cable {cable.nodes}: {comb}")

                # update inventory's panda dataframe (and list?)
                if comb is not None:
                    found = True
                    for c in comb:
                        df.loc[
                            compatible_rows & (df["length [m]"] == c), "quantity"
                        ] -= 1
                        if verbose >= 2:
                            logger.debug(
                                f"\t\t\t qty of {c}m remaining: {df.loc[compatible_rows & (df['length [m]'] == c), 'quantity'].values}"
                            )

            if comb is None:
                unmatched.append(cable)

    logger.info("\t unmatched cables: ")
    for unm in unmatched:
        logger.info(
            f"\t {unm.plugs_and_sockets}{'A':.<4} ({unm.length:.0f}m) {'-'.join(unm.nodes)} "
        )

    return None


def parse_distro_req(req: str) -> tuple[str, float]:
    """parse map's distro requirement based on the input argument 'req'
    'req' should look like: '3P 125A', '1P 16.0', ...
    """
    phase_type = req[:2]
    assert (phase_type == "3P") or (phase_type == "1P")
    result = re.search("P(.*)A", req)
    current_rating = float(result.group(1))
    return phase_type, current_rating


def distro_serie_to_dict(serie: pd.core.series.Series) -> dict:
    """convert a Serie (extracted from a DataFrame) describing a distro to a dict.
    The Serie looks like this
        input - type                     3P
        input - current [A]              63
        3P output - current [A]        63.0
        3P output - quantity            1.0
        3P 2nd output - current [A]    32.0
        3P 2nd output - quantity        2.0
        1P output - current [A]        16.0
        1P output - quantity            3.0
        how many distros                  0

    and the dict looks like this
        {'in': '3P - 63A',
        'out':
            ['3P - 63A (x1)',
            '3P - 32A (x2)',
            '1P - 16A (x3)']
        }

    """

    # find out the outputs of this distro
    # this assumes that they are described as mentionned above
    outputs = []
    for header in serie.index:
        if "output" in header:
            delimiter = header.find("-")
            assert delimiter != -1, "unable to parse distro output"
            output_desc = header[: delimiter - 1]
            if output_desc not in outputs:
                outputs.append(output_desc)

    # build distro dictionnary
    distro_dict = dict.fromkeys(["in", "out"])

    distro_dict["in"] = f"{serie['input - type']} - {serie['input - current [A]']}A"

    distro_dict["out"] = []
    for output_desc in outputs:
        for header in serie.index:
            # note : this could have been done in a more elegant way but this is more robust to spelling errors
            if (output_desc in header) and ("current" in header):
                n_phases = header[:2]
                current_rating = serie[header]

            elif (output_desc in header) and ("quantity" in header):
                quantity = serie[header]

        if not np.isnan(current_rating):
            output_str = f"{n_phases} - {current_rating:.0f}A (x{quantity:.0f})"
            distro_dict["out"].append(output_str)

    return distro_dict


def choose_distros_in_inventory(project_path: str, grid: dict, sh_name: str) -> None:
    """assumes that the inventory spreadsheet has colmuns like;
    input - type                | input - current [A]           | ...
    3P output - current [A]     | 3P output - quantity          | ...
    3P 2nd output - current [A] | 3P 2nd output - quantity      | ...
    ... <contiuning for has many types of ouput necessay> ...   | ...
    1P output - current [A]     | 1P output - quantity          | ...
    how many distros                                            |

    """
    verbose = 0
    expected_cols = [
        "input - type",
        "input - current [A]",
        "3P output - current [A]",
        "3P output - quantity",
        "3P 2nd output - current [A]",
        "3P 2nd output - quantity",
        "1P output - current [A]",
        "1P output - quantity",
        "how many distros",
    ]

    logger.info("\nReading distros inventory")
    df = pd.read_excel(
        os.path.join(project_path, sh_name),
        sheet_name="distros",
        skiprows=0,
        engine="odf",
    )

    if verbose >= 2:
        logger.debug(f"\t {df}")

    assert list(df.columns) == expected_cols, (
        f"The 'distos' tab of the inventory spreadsheet should have the following columns: {expected_cols}"
    )

    # init list of unmatched distros
    unmatched = []

    # get names of 'outputs' cols assuming they are in the "output - xxxx" format
    output_cols_head = set(
        [col.split("-")[0][:-1] for col in df.head() if "output" in col]
    )

    for load_name, load in grid.items():
        distro = load.distro  # replace by distro_requirements
        logger.debug(f"\n\t{load_name} needs a distro with {distro}")

        if (distro["in"] != None) and (distro["out"] != {}):
            score_cols = (
                ["in: " + distro["in"]]
                + ["out: " + req for req in distro["out"].keys()]
                + ["has it all"]
            )
            scoreboard = pd.DataFrame(None, index=df.index, columns=score_cols)

            # --- check input
            ph_in, c_in = parse_distro_req(distro["in"])
            has_input = (df["input - type"].str.find(ph_in) != -1) & (
                df["input - current [A]"] == c_in
            )
            scoreboard.loc[:, score_cols[0]] = has_input
            scoreboard.loc[:, score_cols[-1]] = has_input  # init total score

            # --- check output(s)

            # create a dict to check if considered distro has the correct outputs
            has_output = dict.fromkeys(distro["out"].keys(), False)
            no = 0  # output type counter
            for desc, qty in distro["out"].items():
                if verbose >= 2:
                    logger.debug(
                        f"\t looking for a distro with {qty} output(s) of type {desc}..."
                    )

                no += 1
                ph_out, c_out = parse_distro_req(desc)

                # loop on the type of outputs the distros have in the inventory that could match(3P or 1P?)
                inventory_col_to_check = [
                    col for col in output_cols_head if ph_out in col
                ]
                for available_ouput in inventory_col_to_check:
                    if verbose >= 2:
                        logger.debug(f"\t looking in the '{available_ouput}' column...")

                    # find out which distro(s) have the needed type of output
                    has_output_rating = df[f"{available_ouput} - current [A]"] == c_out
                    has_output_qty = df.loc[:, f"{available_ouput} - quantity"] >= qty
                    has_output[desc] = has_output[desc] | (
                        has_output_rating & has_output_qty
                    )

                    # update score for this output
                    scoreboard.loc[:, score_cols[no]] = has_output[desc]

                    if verbose >= 3:
                        logger.debug(f"has output: \n{has_output}")
                        logger.debug(f"scoreboard: {scoreboard}")

                # now that the output possibilities have been checked, update total score
                scoreboard.loc[:, score_cols[-1]] &= scoreboard.loc[:, score_cols[no]]

            # now that distro requirements have been checked, check that there is enough left in stock
            scoreboard.loc[:, score_cols[-1]] &= df.loc[:, "how many distros"] >= 1
            candidates = df[scoreboard.loc[:, score_cols[-1]] == True]

            if len(candidates) == 0:
                prt = "\t -> could not find a good distro :( "
                choice = None
                unmatched.append(load_name)

            elif len(candidates) == 1:
                prt = "\t -> could find the perfect type of distro"
                choice = df[scoreboard.loc[:, score_cols[-1]] == True].index[0]

            else:
                prt = f"\t -> could find {len(candidates)} types of distros"
                # take first ok one https://stackoverflow.com/a/40660434
                choice = df[scoreboard.loc[:, score_cols[-1]] == True].index[0]

            if choice != None:  # update inventory
                df.loc[choice, "how many distros"] -= 1
                # TODO: write destination in spreadsheet ?
                # update grid with chosen distro
                grid[load_name].distro_chosen = distro_serie_to_dict(df.loc[choice, :])

            else:
                grid[load_name].distro_chosen = "no distro available"

            if verbose:
                logger.debug(prt)

            if verbose >= 2:
                logger.debug(f"\t candidates: \n{candidates}")

            if verbose >= 3:
                logger.debug(f"scoreboard : \n{scoreboard}")

        else:
            logger.info(
                f"\t -> Unable to get distro requirements for {load_name}: {load.distro} -> skipping"
            )
            choice = None
            unmatched.append(load_name)

    if len(unmatched) == 0:
        logger.info("\nall nodes have a distro assigned from the inventory !")

    else:
        logger.info(f"\ncould not find distros for the following loads: {unmatched}")

    return grid
