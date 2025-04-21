import numpy as np 
import pandas as pd 

def write_spreadsheet(grid: dict, sh):
    '''
    - build 2 pd dataFrames (norg vs art), with:
        - the input spreadsheet (to have all loads sharing one loc)
            - phase 
            - power / current

        - the grid dict
            - add cum_power if load exist (eg not for Spoonhaus)
            - add nodes without loads (eg malfarenode)
    '''

    print('write_spreadsheet...')

    verbose = 0
    # start from the input spreadsheet, and...
    # ... drop unnmamed cols https://stackoverflow.com/questions/43983622/remove-unnamed-columns-in-pandas-dataframe
    sh = sh.loc[:, ~sh.columns.str.contains('^Unnamed')] # TODO: move in read_spreadsheet ?

    # ... drop useless cols, and rename others
    sh = sh.drop(columns=['Arrive', 'Depart', 'daytime power [W]', 'nighttime power [W]'])
    sh = sh.rename(columns = {'worstcase power [W]':'power [W]', 'which phase(1, 2, 3, T, U or Y)': 'phase'})
        
    sh = sh[sh['power [W]'] != 0] # drop rows not requiring power (art pieces)

    # ... add extra info from map 
    for l in range(3):
        sh[f'cumulated power L{l+1} [kW]'] = 'NA' # init columns

    for loadOnMap in grid.keys():
        # cum_power from grid dict...
        idx = [loadOnMap in nameOnSheet.lower() for nameOnSheet in sh['Project']]
        if isinstance(grid[loadOnMap]['cum_power'], np.ndarray):
            for l in range(3):
                sh.loc[idx, f'cumulated power L{l+1} [kW]'] = 1e-3*grid[loadOnMap]['cum_power'][l]

        # even if load is on map, but not on input spreadsheets, and has a parent (eg, nodes)
        if (any(idx)==False) and (len(grid[loadOnMap]['parent'])>0):
            tmpDict = {'Project': loadOnMap, 'power [W]':0, 'current [A]': 0, 'phase':'NA'}
            for l in range(3):
                tmpDict[f'cumulated power L{l+1} [kW]'] = 1e-3*grid[loadOnMap]['cum_power'][l]

            sh = sh.append(pd.DataFrame(tmpDict,index=[0]))

    # convert all names to lower case and sort alphabetically 
    sh['Project'] = [str(i).lower() for i in sh['Project']]  
    sh = sh.sort_values('Project')

    # separate "norg" and "others" tab
    norgLoads = []
    otherLoads = []
    for idx, loadOnSheet in enumerate(sh['Project']):
        isOnMap = [loadOnMap for loadOnMap in grid.keys() if loadOnMap in loadOnSheet.lower()]

        if len(isOnMap)==1:
            loadOnMap = isOnMap[0]

        elif len(isOnMap)>1:
            loadOnMap = [name for name in isOnMap if name==loadOnSheet][0]

        else:
            loadOnMap = None

        if (loadOnMap!=None) and (grid[loadOnMap]['parent']!=None):
            cable_layer = grid[loadOnMap]['cable']['layer'] 
            if "norg" in cable_layer:
                norgLoads.append(idx)

    otherLoads = [i for j, i in enumerate(range(len(sh))) if j not in norgLoads]
    dfNorg = sh.iloc[norgLoads, :]
    dfOthers = sh.iloc[otherLoads, :]

    if verbose:
        print(f'norg loads: {norgLoads}')
        print(f'otherLoads: {otherLoads}')
        with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
            print(sh)
            print('splitted:')
            print(dfNorg)
            print(dfOthers)

    # ... create a excel writer object and write file
    with pd.ExcelWriter("output.ods") as writer:
        sh.to_excel(writer, sheet_name="all", index=False)
        dfNorg.to_excel(writer, sheet_name="norg", index=False)
        dfOthers.to_excel(writer, sheet_name="other", index=False)

    return None