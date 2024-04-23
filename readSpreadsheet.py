import pandas as pd
import numpy as np 
import os
import copy 

def readSpreadsheet(project_path, grid, cablesDict):
    verbose = 0

    print('\nReading spreadsheet')
    #TODO: one sheet per "norg / power swap / art", loop on sheets, build dict of all loadsOnSheet ---> avoid manual editing of .ods
    sh = pd.read_excel(os.path.join(project_path, "Power 2023 map balance.ods"), sheet_name="Sheet1", skiprows=3, engine="odf")

    loadsOnMap = list(grid.keys())
    loadsOnSheet = list(sh['Project'])
    missingOnSheet = [] # list of loads on the map but not on the spreadsheet 
    missingOnMap = [] # list of loads on the spreadsheet but not on the map
    hasNoPhase =[]

    # clean loadsOnSheet in case of it contains NaN
    # (happens if all columns of the sheet don't have the same length)
    # TODO: can probably do it nicely with panda dataframe
    for idx, load in reversed(list(enumerate(loadsOnSheet))):
        if isinstance(loadsOnSheet[idx],str)==0:
            loadsOnSheet.pop(idx)


    # loop through loads on the map and find corresponding info on the spreadsheet
    for load in loadsOnMap:

        grid[load]['power'] = np.array([0.0]*3)
        
        # find idx of the row in the spreadsheet
        idx = []
        nameOnMap = load.lower().strip()

        for i,x in enumerate(loadsOnSheet):
            nameOnSheet = x.lower().strip()
            isOnMap = (nameOnMap in nameOnSheet) and not (nameOnMap=='generator')

            if isOnMap:
                idx.append(i)

                phase = sh['which phase(1, 2, 3, T, U or Y)'][i] 
                pwr = np.double(sh['worstcase power [W]'][i])

                if verbose: 
                    print(f"\t On map, '{load}' draws {pwr}W (on sheet: '{nameOnSheet}' phase '{phase})'")
    
                if pwr>0:

                    # --- parse phase info                 
                    if isinstance(phase, int):
                        phaseParsed = phase

                    elif isinstance(phase, str):
                        if len(phase)==1:
                            phaseParsed = phase
                            if (phase=='X'):                                   
                                hasNoPhase.append(nameOnSheet)

                            else:
                                pass

                        else: # len(phase)>1
                            phaseParsed = list(map(int, phase.split(','))) # conv to a list of int

                    elif phase==float('nan'):
                        hasNoPhase.append(nameOnSheet)

                    else:
                        print(grid[load])
                        raise ValueError(f'{nameOnSheet} has a wrong phase assigned: {phase}')
                    
                    # --- store phase info in cableDict and grid
                    grid[load]['phase'] = phaseParsed
                    if grid[load]['cable'] != None: 
                        cableLayer = grid[load]['cable']['layer']
                        cableIdx = grid[load]['cable']['idx']
                        cablesDict[cableLayer][cableIdx]['phase'] = phaseParsed
                        #grid[load]['cable'].update(cablesDict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict

                    # --- deduce and store power info
                    if isinstance(phaseParsed, int):
                        grid[load]['power'][phaseParsed-1] += pwr
                            
                    elif isinstance(phaseParsed, list):
                        grid[load]['power'][[p-1 for p in phaseParsed]] += pwr/len(phaseParsed)

                    elif isinstance(phaseParsed, str): # one-letter string
                        if phase=='T':
                            grid[load]['power'] += pwr/3

                        else:
                            grid[load]['power'] = pwr

                    # store date info:
                    #   grid[load]['date'] = dict()
                    #   grid[load]['date']['from'] = sh['Arrive'][idx[0]]
                    #   grid[load]['date']['to'] = sh['Depart'][idx[0]]

                else: # pwr is zero or none 
                    if verbose: print(f"deleting {load} because doesn't draw power")
                    del grid[load]

                
        # print(f"\t {load} draws {grid[load]['power']/1e3:.1f}kW on phase {grid[load]['phase']} \
        #           from {grid[load]['date']['from']} to {grid[load]['date']['to']}")

        if (len(idx)==0) and (load!='generator'): # load exists on the map but not on the spreadsheet
            missingOnSheet.append(nameOnMap)


    # sanity check: loop on spreadsheet to check if some are projects not on the map 
    for idxOnSheet, nameOnSheet in enumerate(loadsOnSheet):
        if sh['worstcase power [W]'][idxOnSheet]>0:
            idxOnMap = [idx for idx,nameOnMap in enumerate(loadsOnMap) if (nameOnMap in nameOnSheet.lower())]
            if len(idxOnMap) == 0:
                missingOnMap.append(nameOnSheet)


    print('\n!!! you should not go any futher if some loads on the map are not on spreadsheet:')
    print(f"\ton map but missing on spreadsheet: \n\t{missingOnSheet}") # will make computeVDrop to crash because those don't have cable lengthes
    print(f"\n\ton spreadsheet but missing on map: \n\t{missingOnMap}")
    print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{hasNoPhase} \n ")

    return grid, cablesDict, hasNoPhase