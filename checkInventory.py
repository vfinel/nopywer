import pandas as pd
import numpy as np 

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