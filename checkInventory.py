from itertools import combinations 
import numpy as np 
import os
import pandas as pd
 

def find_combinations(arr: list, target_sum, th=5): 
    # find combination of cables from in the list 'arr', to have make the length 'target_sum', with thresholt 'th'
    # https://www.quora.com/How-can-Python-be-used-to-find-all-possible-combinations-of-numbers-in-an-array-that-add-up-to-a-given-sum
    # https://www.geeksforgeeks.org/python-closest-sum-pair-in-list/
    nMaxExtension = 4   # could go up to len(arr) but that would be a lot of extensions which increases the risks of failure are connectors
    output = None 

    if len(arr)>0:
        for n in range(1, nMaxExtension + 1):
            for combo in combinations(arr, n):
                found = 0 < (sum(combo)-target_sum) < th
                if found:         
                    return combo

        if (not found) and (th < 5*target_sum): # second arg is a sanity check to avoid infinite recursion 
            # print(f'unable to find, trying with increase threshold to {th+5}m ')
            output = find_combinations(arr, target_sum, 1.5*th)

    return output 


def compute_cable_length_in_inventory():
    debug = 1

    print('\nReading inventory spreadsheet')
    sh = pd.read_excel("../Miss PiggyInventory 2023.ods",sheet_name="build2023", skiprows=2, engine="odf")

    items = list(sh['Item'])
    qty = list(sh['Qty'])

    inventory = {}
    inventory['3p'] = {};
    inventory['1p'] = {};
    len_3p = 0
    len_1p = 0

    # loop through loads on the map and find corresponding info on the spreadsheet
    for idx, item in enumerate(items):
        #print(f'\titem: {item}')
        if isinstance(item,str):
            if "3P Cable" in item:
                idxStart = len('3P Cable')
                idxStop = item.index('m')
                length = float(item[idxStart:idxStop])
                
                len_3p += qty[idx]*length

                if debug: print(f'\t\t3P cable: {qty[idx]} times "{item} (length: {length:.0f})"')
                inventory['3p'][item] = {}
                inventory['3p'][item]['length'] = length
                inventory['3p'][item]['qty'] = qty[idx]

            elif "1P Cable" in item: 
                idxStart = len('1P Cable')
                idxStop = item.index('m')
                length = float(item[idxStart:idxStop])
                
                len_1p += qty[idx]*length

                if debug: print(f'\t\t1P cable: {qty[idx]} times "{item} (length: {length:.0f})"')
                inventory['1p'][item] = {}
                inventory['1p'][item]['length'] = length
                inventory['1p'][item]['qty'] = qty[idx]

    print(f'\n\t total 3p length: {len_3p:.0f}m')
    print(f'\t total 1p length: {len_1p:.0f}m')


def choose_cables_in_inventory(project_path: str, cablesDict: dict, sh_name: str) -> int:
    verbose = 1
    unmatched = []
    print('\nReading cables inventory')
    df = pd.read_excel(os.path.join(project_path, sh_name), 
                       sheet_name='cables', 
                       skiprows=0, 
                       engine="odf")
    
    if verbose>=3: print(f'\t {df}')

    for cableLayerName in cablesDict.keys():
        if verbose: print(f'\n\t\t layer: {cableLayerName}')
        
        # sort cables. Decreasing order allows to make sure long cables are used for long dsitances, decreasing number of extensions
        cableLayer = sorted(cablesDict[cableLayerName], key=lambda d: d['length'], reverse=True) # https://stackoverflow.com/questions/72899/how-to-sort-a-list-of-dictionaries-by-a-value-of-the-dictionary-in-python
        
        for idx, cable in enumerate(cableLayer):
            if verbose>=2: print(f"\n\t\t\t taking care of cable {idx+1}/{len(cableLayer)}, length {cable['length']} m")

            # get compatible cables 
            if '3phases' in cableLayerName:
                nPhases = 3
            
            elif '1phase' in cableLayerName:
                nPhases = 1

            else:
                raise Exception(f'unable to find out nuymber of phases of layer {cableLayerName}')
            
            if verbose>=2: print(f" n phases: {nPhases}")
            
            compatibleRows = (df['number of phases'] == nPhases) \
                             & (df['plugs&sockets [A]']==cable['plugsAndsockets']) \
                             & (df['section [mm2]']==cable['area'])
            
            compatible_df = df[ compatibleRows ]
            if verbose>=2: print(f"\t\t\t compatible cables dataframe: \n {compatible_df}")

            comb = None
            if compatible_df.empty:
                if verbose>=2: print('DataFrame is empty --> no compatible cables in inventory!')

            else:
                # build a list of all compatible cables (account for their quantity) https://stackoverflow.com/questions/16476924/how-can-i-iterate-over-rows-in-a-pandas-dataframe
                list_of_cables = [length for qty, length in zip(compatible_df['quantity'], compatible_df['length [m]']) 
                                for i in range(qty)]

                # find best combination 
                target_sum = cable['length'] # note that slack was added from "extra_cable_length" parameters when computing cablesDict
                comb = find_combinations(list_of_cables, target_sum)
                if (comb==None) | verbose:
                    print(f"\t\t\t cable {cable['nodes']}: {comb}")

                # update inventory's panda dataframe (and list?)
                if comb!=None:
                    found = True 
                    for c in comb:
                        df.loc[compatibleRows & (df['length [m]']==c), 'quantity'] -= 1
                        if verbose>=2:
                            print(f"\t\t\t qty of {c}m remaining: {df.loc[compatibleRows & (df['length [m]']==c), 'quantity'].values}")

            if comb==None:
                unmatched.append(cable)
            
    print(f'\t unmatched cables: ')
    for unm in unmatched:
        print(f"\t {unm['plugsAndsockets']}{'A':.<4} ({unm['length']:.0f}m) {'-'.join(unm['nodes'])} ")

    return None