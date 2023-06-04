import pandas as pd
import numpy as np 

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
        if (nameOnMap in nameOnSheet) and not (nameOnMap=='generator'):
            idx.append(i)

            phase = sh['which phase(1, 2, 3, T, U or Y)'][i] 
            if isinstance(phase, int) or(isinstance(phase,str) and (phase in 'TUY')):
                  
                  # cumulate power to this location
                  pwr = sh['worstcase power [W]'][i] 
                  if isinstance(phase, int):
                        grid[load]['power'][phase-1] += pwr

                  elif phase=='T':
                      grid[load]['power'] += pwr/3

                  else: # U, Y
                      pass # do nothing
                  
                # store info about date:
                #   grid[load]['date'] = dict()
                #   grid[load]['date']['from'] = sh['Arrive'][idx[0]]
                #   grid[load]['date']['to'] = sh['Depart'][idx[0]]
            
            elif (phase==float('nan')) or (phase=='N') or (phase=='X'):
                hasNoPhase.append(nameOnSheet)
            
            else:
                raise ValueError(f'{nameOnSheet} has a wrong phase assigned: {phase}')                  

            if verbose: 
                draw = np.array2string(1e-3*grid[load]['power'], precision=2, floatmode='fixed')
                print(f"\t On map, '{load}' draws {draw}kW (on sheet: '{nameOnSheet}' phase '{phase})'")
            
    # print(f"\t {load} draws {grid[load]['power']/1e3:.1f}kW on phase {grid[load]['phase']} \
    #           from {grid[load]['date']['from']} to {grid[load]['date']['to']}")

    if (len(idx)==0) and (load!='generator'): # load exists on the map but not on the spreadsheet
        missingOnSheet.append(load)


# sanity check: loop on spreadsheet to check if some are projects not on the map 
for load in loadsOnSheet:
    idx = [i for i,x in enumerate(loadsOnMap) if (x in load.lower())]
    if len(idx) == 0:
        missingOnMap.append(load)

print('\n!!! you should not go any futher if some loads on the map are not on spreadsheet:')
print(f"\ton map but missing on spreadsheet: \n\t{missingOnSheet}") # will make computeVDrop to crash because those don't have cable lengthes
print(f"\n\ton spreadsheet but missing on map: \n\t{missingOnMap}")
print(f"\nlist of loads on the spreadsheet that don't have a phase assigned: \n\t{hasNoPhase} \n ")



