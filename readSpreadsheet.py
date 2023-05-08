import pandas as pd

sh = pd.read_excel("Power 2023 map balance.ods",sheet_name="Sheet1", skiprows=3,
                    engine="odf")
                    

# sh['Project']
# sh['Worst case [W]']
# sh['wire area(from source)']
# sh['which phase(1, 2, 3, T, U or Y)']

loadsOnMap = list(grid.keys())
loadsOnSheet = list(sh['Project'])
missingOnSheet = [] # list of loads on the map but not on the spreadsheet 
missingOnMap = [] # list of loads on the spreadsheet but not on the map

# loop through loads on the map and find corresponding info on the spreadsheet
for load in loadsOnMap:
    idx = [i for i,x in enumerate(loadsOnSheet) if x.lower()==load] # find idx of the row in the spreadsheet
    if len(idx)==1: # the load appears exactly one time in the spreadsheet
        grid[load]['power'] = sh['worstcase power [W]'][idx[0]]
        grid[load]['phase'] = sh['which phase(1, 2, 3, T, U or Y)'][idx[0]] 
        grid[load]['date'] = dict()
        grid[load]['date']['from'] = sh['Arrive'][idx[0]]
        grid[load]['date']['to'] = sh['Depart'][idx[0]]

        cable = grid[load]['cable']
        grid[load]['cable'].update(cablesDict[cable['layer']][cable['idx']]) # add info from cableDict
        #print(f'cable : {cable}')

        print(f"\t {load} draws {grid[load]['power']/1e3}kW on phase {grid[load]['phase']} \
              from {grid[load]['date']['from']} to {grid[load]['date']['to']}")
        

    elif len(idx)>1:
        raise ValueError(f'load "{load}" appears {len(idx)} times in the spreadsheet" ')
    
    else: # load exists on the map but not on the spreadsheet
        if load!='generator':
            missingOnSheet.append(load)


# sanity check: loop on spreadsheet if there are projects not on the map 
for load in loadsOnSheet:
    idx = [i for i,x in enumerate(loadsOnMap) if x==load]
    if len(idx) == 0:
        missingOnMap.append(load)
    elif len(idx)>1:
        raise ValueError(f'load "{load}" appears {len(idx)} times on the map" ')


print(f"on map but missing on spreadsheet: {missingOnSheet}")
print(f"on spreadsheet but missing on map: {missingOnMap}")



