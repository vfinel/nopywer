import logging
import os
import re
from itertools import combinations

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def find_combinations(arr: list, target_sum, th: float = 5.0):
    n_max_extension = 4
    output = None

    if len(arr) > 0:
        found = False
        for n in range(1, n_max_extension + 1):
            for combo in combinations(arr, n):
                found = 0 < (sum(combo) - target_sum) < th
                if found:
                    return combo

        if (not found) and (th < 5 * target_sum):
            output = find_combinations(arr, target_sum, 1.5 * th)

    return output


def choose_cables_in_inventory(project_path: str, cables_dict: dict, sh_name: str) -> None:
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

    sorted_cables = sorted(cables_dict.values(), key=lambda c: c.length_m, reverse=True)

    for idx, cable in enumerate(sorted_cables):
        if verbose >= 2:
            logger.debug(
                f"\n\t\t\t taking care of cable {idx + 1}/{len(sorted_cables)}, "
                f"length {cable.length_m} m"
            )

        n_phases = 3 if cable.plugs_and_sockets_a > 16 else 1

        if verbose >= 2:
            logger.debug(f" n phases: {n_phases}")

        compatible_rows = (
            (df["number of phases"] == n_phases)
            & (df["plugs&sockets [A]"] == cable.plugs_and_sockets_a)
            & (df["section [mm2]"] == cable.area_mm2)
        )

        compatible_df = df[compatible_rows]
        if verbose >= 2:
            logger.debug(f"\t\t\t compatible cables dataframe: \n {compatible_df}")

        comb = None
        if compatible_df.empty:
            if verbose >= 2:
                logger.debug("DataFrame is empty --> no compatible cables in inventory!")
        else:
            list_of_cables = [
                length
                for qty, length in zip(compatible_df["quantity"], compatible_df["length [m]"])
                for i in range(qty)
            ]

            target_sum = cable.length_m
            comb = find_combinations(list_of_cables, target_sum)
            if comb is None or verbose:
                nodes = [cable.from_node, cable.to_node]
                logger.debug(f"\t\t\t cable {nodes}: {comb}")

            if comb is not None:
                for c in comb:
                    df.loc[compatible_rows & (df["length [m]"] == c), "quantity"] -= 1
                    if verbose >= 2:
                        remaining = df.loc[
                            compatible_rows & (df["length [m]"] == c), "quantity"
                        ].values
                        logger.debug(f"\t\t\t qty of {c}m remaining: {remaining}")

        if comb is None:
            unmatched.append(cable)

    logger.info("\t unmatched cables: ")
    for unm in unmatched:
        nodes = [unm.from_node, unm.to_node]
        logger.info(
            f"\t {unm.plugs_and_sockets_a}{'A':.<4} ({unm.length_m:.0f}m) {'-'.join(nodes)} "
        )

    return None


def parse_distro_req(req: str) -> tuple[str, float]:
    """Parse distro requirement string like '3P 125A' or '1P 16.0'."""
    phase_type = req[:2]
    assert phase_type in ("3P", "1P")
    result = re.search("P(.*)A", req)
    current_rating = float(result.group(1))
    return phase_type, current_rating


def distro_serie_to_dict(serie: pd.core.series.Series) -> dict:
    """Convert a pandas Series describing a distro to a dict.

    The Serie looks like this:
        input - type                     3P
        input - current [A]              63
        3P output - current [A]        63.0
        3P output - quantity            1.0
        ...

    Returns dict with 'in' and 'out' keys.
    """
    outputs = []
    for header in serie.index:
        if "output" in header:
            delimiter = header.find("-")
            assert delimiter != -1, "unable to parse distro output"
            output_desc = header[: delimiter - 1]
            if output_desc not in outputs:
                outputs.append(output_desc)

    distro_dict = dict.fromkeys(["in", "out"])
    distro_dict["in"] = f"{serie['input - type']} - {serie['input - current [A]']}A"

    distro_dict["out"] = []
    for output_desc in outputs:
        for header in serie.index:
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
    """Match distro requirements against inventory spreadsheet."""
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
        f"The 'distros' tab should have columns: {expected_cols}"
    )

    unmatched = []

    output_cols_head = {col.split("-")[0][:-1] for col in df.head() if "output" in col}

    for load_name, load in grid.items():
        distro = load.distro
        logger.debug(f"\n\t{load_name} needs a distro with {distro}")

        if (distro["in"] is not None) and (distro["out"] != {}):
            score_cols = (
                ["in: " + distro["in"]] + ["out: " + req for req in distro["out"]] + ["has it all"]
            )
            scoreboard = pd.DataFrame(None, index=df.index, columns=score_cols)

            ph_in, c_in = parse_distro_req(distro["in"])
            has_input = (df["input - type"].str.find(ph_in) != -1) & (
                df["input - current [A]"] == c_in
            )
            scoreboard.loc[:, score_cols[0]] = has_input
            scoreboard.loc[:, score_cols[-1]] = has_input

            has_output = dict.fromkeys(distro["out"].keys(), False)
            no = 0
            for desc, qty in distro["out"].items():
                if verbose >= 2:
                    logger.debug(f"\t looking for a distro with {qty} output(s) of type {desc}...")

                no += 1
                ph_out, c_out = parse_distro_req(desc)

                inventory_col_to_check = [col for col in output_cols_head if ph_out in col]
                for available_ouput in inventory_col_to_check:
                    if verbose >= 2:
                        logger.debug(f"\t looking in the '{available_ouput}' column...")

                    has_output_rating = df[f"{available_ouput} - current [A]"] == c_out
                    has_output_qty = df.loc[:, f"{available_ouput} - quantity"] >= qty
                    has_output[desc] = has_output[desc] | (has_output_rating & has_output_qty)

                    scoreboard.loc[:, score_cols[no]] = has_output[desc]

                    if verbose >= 3:
                        logger.debug(f"has output: \n{has_output}")
                        logger.debug(f"scoreboard: {scoreboard}")

                scoreboard.loc[:, score_cols[-1]] &= scoreboard.loc[:, score_cols[no]]

            scoreboard.loc[:, score_cols[-1]] &= df.loc[:, "how many distros"] >= 1
            mask = scoreboard.loc[:, score_cols[-1]] == True  # noqa: E712
            candidates = df[mask]

            if len(candidates) == 0:
                prt = "\t -> could not find a good distro :( "
                choice = None
                unmatched.append(load_name)
            elif len(candidates) == 1:
                prt = "\t -> could find the perfect type of distro"
                choice = df[mask].index[0]
            else:
                prt = f"\t -> could find {len(candidates)} types of distros"
                choice = df[mask].index[0]

            if choice is not None:
                df.loc[choice, "how many distros"] -= 1
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
                f"\t -> Unable to get distro requirements for {load_name}: "
                f"{load.distro} -> skipping"
            )
            choice = None
            unmatched.append(load_name)

    if len(unmatched) == 0:
        logger.info("\nall nodes have a distro assigned from the inventory !")
    else:
        logger.info(f"\ncould not find distros for the following loads: {unmatched}")

    return grid
