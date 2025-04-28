import numpy as np
import pandas as pd


def write_spreadsheet(grid: dict, sh):
    """
    - build 2 pd dataFrames (norg vs art), with:
        - the input spreadsheet (to have all loads sharing one loc)
            - phase
            - power / current

        - the grid dict
            - add cum_power if load exist (eg not for Spoonhaus)
            - add nodes without loads (eg malfarenode)
    """

    print("write_spreadsheet...")

    verbose = 0
    # start from the input spreadsheet, and...
    # ... drop unnmamed cols https://stackoverflow.com/questions/43983622/remove-unnamed-columns-in-pandas-dataframe
    sh = sh.loc[
        :, ~sh.columns.str.contains("^Unnamed")
    ]  # TODO: move in read_spreadsheet ?

    # ... drop useless cols, and rename others
    sh = sh.drop(
        columns=["Arrive", "Depart", "daytime power [W]", "nighttime power [W]"]
    )
    sh = sh.rename(
        columns={
            "worstcase power [W]": "power [W]",
            "which phase(1, 2, 3, T, U or Y)": "phase",
        }
    )

    sh = sh[sh["power [W]"] != 0]  # drop rows not requiring power (art pieces)

    # ... add extra info from map
    for l in range(3):
        sh[f"cumulated power L{l + 1} [kW]"] = "NA"  # init columns

    for load_on_map in grid.keys():
        # cum_power from grid dict...
        idx = [load_on_map in name_on_sheet.lower() for name_on_sheet in sh["Project"]]
        if isinstance(grid[load_on_map]["cum_power"], np.ndarray):
            for l in range(3):
                sh.loc[idx, f"cumulated power L{l + 1} [kW]"] = (
                    1e-3 * grid[load_on_map]["cum_power"][l]
                )

        # even if load is on map, but not on input spreadsheets, and has a parent (eg, nodes)
        if (any(idx) == False) and (len(grid[load_on_map]["parent"]) > 0):
            tmp_dict = {
                "Project": load_on_map,
                "power [W]": 0,
                "current [A]": 0,
                "phase": "NA",
            }
            for l in range(3):
                tmp_dict[f"cumulated power L{l + 1} [kW]"] = (
                    1e-3 * grid[load_on_map]["cum_power"][l]
                )

            sh = sh.append(pd.DataFrame(tmp_dict, index=[0]))

    # convert all names to lower case and sort alphabetically
    sh["Project"] = [str(i).lower() for i in sh["Project"]]
    sh = sh.sort_values("Project")

    # separate "norg" and "others" tab
    norg_loads = []
    other_loads = []
    for idx, load_on_sheet in enumerate(sh["Project"]):
        is_on_map = [
            load_on_map
            for load_on_map in grid.keys()
            if load_on_map in load_on_sheet.lower()
        ]

        if len(is_on_map) == 1:
            load_on_map = is_on_map[0]

        elif len(is_on_map) > 1:
            load_on_map = [name for name in is_on_map if name == load_on_sheet][0]

        else:
            load_on_map = None

        if (load_on_map != None) and (grid[load_on_map]["parent"] != None):
            cable_layer = grid[load_on_map]["cable"]["layer"]
            if "norg" in cable_layer:
                norg_loads.append(idx)

    other_loads = [i for j, i in enumerate(range(len(sh))) if j not in norg_loads]
    df_norg = sh.iloc[norg_loads, :]
    df_others = sh.iloc[other_loads, :]

    if verbose:
        print(f"norg loads: {norg_loads}")
        print(f"other_loads: {other_loads}")
        with pd.option_context(
            "display.max_rows", None, "display.max_columns", None
        ):  # more options can be specified also
            print(sh)
            print("splitted:")
            print(df_norg)
            print(df_others)

    # ... create a excel writer object and write file
    with pd.ExcelWriter("output.ods") as writer:
        sh.to_excel(writer, sheet_name="all", index=False)
        df_norg.to_excel(writer, sheet_name="norg", index=False)
        df_others.to_excel(writer, sheet_name="other", index=False)

    return None
