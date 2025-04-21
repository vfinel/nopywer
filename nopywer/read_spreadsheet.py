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
    has_no_phase =[]

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
        name_on_map = load.lower().strip()

        for row,x in enumerate(loadsOnSheet):
            name_on_sheet = x.lower().strip()
            is_on_map = (name_on_map in name_on_sheet) and not (name_on_map=='generator')

            if is_on_map:
                idx.append(row)
                phase = sh[headers['phase']][row]
                pwr = np.double(sh[headers['power']][row]) 
                assert pwr!=np.nan, f'load {name_on_sheet} has no power indicated'
                if verbose: 
                    print(f"\t'{name_on_sheet}' draws {pwr}W on phase {phase} ('{load}' on the map)")
    
                if pwr>0:
                    # --- parse phase info                 
                    if isinstance(phase, int):
                        phase_parsed = phase

                    elif isinstance(phase, str):
                        if len(phase)==1:
                            phase_parsed = phase
                            if (phase=='X'):                                   
                                has_no_phase.append(name_on_sheet)

                            else:
                                pass

                        else: # len(phase)>1
                            phase_parsed = list(map(int, phase.split(','))) # conv to a list of int

                    elif phase==float('nan'):
                        has_no_phase.append(name_on_sheet)

                    else:
                        print(grid[load])
                        raise ValueError(f'{name_on_sheet} has a wrong phase assigned: {phase}')
                    
                    # --- store phase info in cableDict and grid
                    grid[load]['phase'] = phase_parsed
                    if grid[load]['cable'] != None: 
                        cable_layer = grid[load]['cable']['layer']
                        cable_idx = grid[load]['cable']['idx']
                        cables_dict[cable_layer][cable_idx]['phase'] = phase_parsed
                        #grid[load]['cable'].update(cables_dict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict

                    # --- deduce and store power info
                    if isinstance(phase_parsed, int):
                        grid[load]['power'][phase_parsed-1] += pwr
                            
                    elif isinstance(phase_parsed, list):
                        grid[load]['power'][[p-1 for p in phase_parsed]] += pwr/len(phase_parsed)

                    elif isinstance(phase_parsed, str): # one-letter string
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
                    raise ValueError(f'Unable to read "{name_on_sheet}" power usage')
                
        # print(f"\t {load} draws {grid[load]['power']/1e3:.1f}kW on phase {grid[load]['phase']} \
        #           from {grid[load]['date']['from']} to {grid[load]['date']['to']}")

        if (len(idx)==0) and (load!='generator'): # load exists on the map but not on the spreadsheet
            missingOnSheet.append(name_on_map)


    # sanity check: loop on spreadsheet to check if some are projects not on the map 
    for idxOnSheet, name_on_sheet in enumerate(loadsOnSheet):
        idxOnMap = [idx for idx,name_on_map in enumerate(loadsOnMap) if (name_on_map in name_on_sheet.lower())]
        if len(idxOnMap) == 0:
            missingOnMap.append(name_on_sheet)


    print('\n!!! you should not go any further if some loads on the map are not on spreadsheet:')
    print(f"\t on map but missing on spreadsheet: \n\t {missingOnSheet}") # will make compute_voltage_drop to crash because those don't have cable lengthes
    print(f"\n\t on spreadsheet but missing on map: \n\t {missingOnMap}")
    print(f"\n list of loads on the spreadsheet that don't have a phase assigned: \n\t {has_no_phase} \n ")

    return grid, cables_dict, has_no_phase