import pandas as pd
import numpy as np 
import os
import copy 

def read_spreadsheet(project_path: str, grid: dict, cables_dict: dict, sparam: dict) -> tuple[dict, dict, list]:
    verbose = 0
    headers = {'name': 'Project',
            'phase': 'which phase(1, 2, 3, T, U or Y)',
            'power': 'worstcase power [W]'}

    print('\nReading spreadsheet')
    #TODO: one sheet per "norg / power swap / art", loop on sheets, build dict of all loadsOnSheet ---> avoid manual editing of .ods
    sh = pd.read_excel(os.path.join(project_path, sparam['name']), 
                       sheet_name=sparam['sheet'], 
                       skiprows=sparam['skiprows'], 
                       engine="odf")

    for key in headers.values():
        assert key in sh.keys(), f'key "{key}" is not on the spreadsheet. The following keys were found: {sh.keys()}'

    loadsOnMap = list(grid.keys())
    loadsOnSheet = list(sh[headers['name']])
    missingOnSheet = [] # list of loads on the map but not on the spreadsheet 
    missingOnMap = []   # list of loads on the spreadsheet but not on the map
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

        for row,x in enumerate(loadsOnSheet):
            nameOnSheet = x.lower().strip()
            isOnMap = (nameOnMap in nameOnSheet) and not (nameOnMap=='generator')

            if isOnMap:
                idx.append(row)
                phase = sh[headers['phase']][row]
                pwr = np.double(sh[headers['power']][row]) 
                assert pwr!=np.nan, f'load {nameOnSheet} has no power indicated'
                if verbose: 
                    print(f"\t'{nameOnSheet}' draws {pwr}W on phase {phase} ('{load}' on the map)")
    
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
                        cable_layer = grid[load]['cable']['layer']
                        cable_idx = grid[load]['cable']['idx']
                        cables_dict[cable_layer][cable_idx]['phase'] = phaseParsed
                        #grid[load]['cable'].update(cables_dict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict

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

                elif pwr==0:
                    if verbose: print(f"deleting {load} because doesn't draw power")
                    del grid[load]

                else:
                    raise ValueError(f'Unable to read "{nameOnSheet}" power usage')
                
        # print(f"\t {load} draws {grid[load]['power']/1e3:.1f}kW on phase {grid[load]['phase']} \
        #           from {grid[load]['date']['from']} to {grid[load]['date']['to']}")

        if (len(idx)==0) and (load!='generator'): # load exists on the map but not on the spreadsheet
            missingOnSheet.append(nameOnMap)


    # sanity check: loop on spreadsheet to check if some are projects not on the map 
    for idxOnSheet, nameOnSheet in enumerate(loadsOnSheet):
        idxOnMap = [idx for idx,nameOnMap in enumerate(loadsOnMap) if (nameOnMap in nameOnSheet.lower())]
        if len(idxOnMap) == 0:
            missingOnMap.append(nameOnSheet)


    print('\n!!! you should not go any further if some loads on the map are not on spreadsheet:')
    print(f"\t on map but missing on spreadsheet: \n\t {missingOnSheet}") # will make compute_voltage_drop to crash because those don't have cable lengthes
    print(f"\n\t on spreadsheet but missing on map: \n\t {missingOnMap}")
    print(f"\n list of loads on the spreadsheet that don't have a phase assigned: \n\t {hasNoPhase} \n ")

    return grid, cables_dict, hasNoPhase