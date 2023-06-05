import pandas as pd
import numpy as np 
import copy 

verbose = 0

print('\nReading spreadsheet')
#TODO: one sheet per "norg / power swap / art", loop on sheets, build dict of all loadsOnSheet ---> avoid manual editing of .ods
sh = pd.read_excel("Power 2023 map balance.ods",sheet_name="Sheet1", skiprows=3, engine="odf")

loadsOnMap = list(grid.keys())
loadsOnSheet = list(sh['Project'])
missingOnSheet = [] # list of loads on the map but not on the spreadsheet 
missingOnMap = [] # list of loads on the spreadsheet but not on the map
hasNoPhase =[]

# loop through loads on the map and find corresponding info on the spreadsheet
for load in loadsOnMap:

    grid[load]['power'] = np.array([0.0]*3)
    
    # find idx of the row in the spreadsheet
    idx = []
    nameOnMap = load.lower()

    for i,x in enumerate(loadsOnSheet):
        nameOnSheet = x.lower().strip()
        isOnMap = (nameOnMap in nameOnSheet) and not (nameOnMap=='generator')
        if isOnMap:
            idx.append(i)

            phase = sh['which phase(1, 2, 3, T, U or Y)'][i] 
            pwr = sh['worstcase power [W]'][i] 

            if verbose: 
                print(f"\t On map, '{load}' draws {pwr}W (on sheet: '{nameOnSheet}' phase '{phase})'")
 
            if pwr>0:
                # store phase info into cable 
                if grid[nameOnMap]['cable'] != None: 
                    cableLayer = grid[nameOnMap]['cable']['layer']
                    cableIdx = grid[nameOnMap]['cable']['idx']
                    cable = cablesDict[cableLayer][cableIdx]
                    if cable['phase'] == None:
                        cable['phase'] = phase

                    elif isinstance(cable['phase'], int):
                        cable['phase'] = 'T'

                    else:
                        pass # should be a Y,U phase, already assigned

                    #grid[load]['cable'].update(cablesDict[cable2parent['layer']][cable2parent['idx']]) # add info from cableDict
                
                # add grid info and sanity checks 
                if (isinstance(phase, int) or (isinstance(phase,str) and (phase in 'TUY'))) \
                    and (pwr>0):
                    
                    # cumulate power to this location
                    if isinstance(phase, int):
                            grid[load]['power'][phase-1] += pwr

                    elif phase=='T':
                        grid[load]['power'] += pwr/3

                    else: # U, Y
                        pass # do nothing
                    
                    # store date info:
                    #   grid[load]['date'] = dict()
                    #   grid[load]['date']['from'] = sh['Arrive'][idx[0]]
                    #   grid[load]['date']['to'] = sh['Depart'][idx[0]]
                
                elif (pwr>0) and ((phase==float('nan')) or (phase=='N') or (phase=='X')):
                    hasNoPhase.append(nameOnSheet)
                
                elif pwr>0:
                    print(grid[load])
                    raise ValueError(f'{nameOnSheet} has a wrong phase assigned: {phase}')
                
            else: # pwr is zero or none 
                if verbose: print(f"deleting {load} because doesn't draw power")
                del grid[load]

            
    # print(f"\t {load} draws {grid[load]['power']/1e3:.1f}kW on phase {grid[load]['phase']} \
    #           from {grid[load]['date']['from']} to {grid[load]['date']['to']}")

    if (len(idx)==0) and (load!='generator'): # load exists on the map but not on the spreadsheet
        missingOnSheet.append(load)


# sanity check: loop on spreadsheet to check if some are projects not on the map 
for idxOnSheet, nameOnSheet in enumerate(loadsOnSheet):
    if sh['worstcase power [W]'][idxOnSheet]>0:
        idxOnMap = [idx for idx,nameOnMap in enumerate(loadsOnMap) if (nameOnMap in nameOnSheet.lower())]
        if len(idxOnMap) == 0:
            missingOnMap.append(load)


print('\n!!! you should not go any futher if some loads on the map are not on spreadsheet:')
print(f"\ton map but missing on spreadsheet: \n\t{missingOnSheet}") # will make computeVDrop to crash because those don't have cable lengthes
print(f"\n\ton spreadsheet but missing on map: \n\t{missingOnMap}")
print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{hasNoPhase} \n ")

