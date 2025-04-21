from itertools import combinations 
import numpy as np 
import os
import pandas as pd
import re 

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


def choose_cables_in_inventory(project_path: str, cables_dict: dict, sh_name: str) -> None:
    verbose = 1
    unmatched = []
    print('\nReading cables inventory')
    df = pd.read_excel(os.path.join(project_path, sh_name), 
                       sheet_name='cables', 
                       skiprows=0, 
                       engine="odf")
    
    if verbose>=3: print(f'\t {df}')

    for cableLayerName in cables_dict.keys():
        if verbose: print(f'\n\t\t layer: {cableLayerName}')
        
        # sort cables. Decreasing order allows to make sure long cables are used for long dsitances, decreasing number of extensions
        cableLayer = sorted(cables_dict[cableLayerName], key=lambda d: d['length'], reverse=True) # https://stackoverflow.com/questions/72899/how-to-sort-a-list-of-dictionaries-by-a-value-of-the-dictionary-in-python
        
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
                target_sum = cable['length'] # note that slack was added from "extra_cable_length" parameters when computing cables_dict
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


def parse_distro_req(req: str) -> tuple[str, float]:
    ''' parse map's distro requirement based on the input argument 'req' 
    'req' should look like: '3P 125A', '1P 16.0', ...
    '''
    phaseType = req[:2] 
    assert ((phaseType=='3P') or (phaseType=='1P'))
    result = re.search('P(.*)A', req)
    currentRating = float(result.group(1))
    return phaseType, currentRating


def choose_distros_in_inventory(project_path: str, grid: dict, sh_name: str) -> None: 
    '''assumes that the inventory spreadsheet has colmuns like;
            input - type                | input - current [A]           | ...
            3P output - current [A]     | 3P output - quantity          | ...
            3P 2nd output - current [A] | 3P 2nd output - quantity      | ...
            ... <contiuning for has many types of ouput necessay> ...   | ...
            1P output - current [A]     | 1P output - quantity          | ...
            how many distros                                            |

    '''
    verbose = 0
    print('\nReading distros inventory')
    df = pd.read_excel(os.path.join(project_path, sh_name), 
                       sheet_name='distros', 
                       skiprows=0, 
                       engine="odf")
    
    if verbose>=2: print(f'\t {df}')
    unmatched = []

    # get names of 'outputs' cols assuming they are in the "output - xxxx" format
    output_cols_head = set([col.split('-')[0][:-1] for col in df.head() if 'output' in col])

    for loadName, load in grid.items():
        distro = load['distro']
        if (distro['in']!=None) and (distro['out']!={}):
            if verbose:
                print(f"\n{loadName} needs a distro with {distro}")

            score_cols = ['in: ' + distro['in']] + ['out: ' + req for req in distro['out'].keys()] + ['has it all']
            scoreboard = pd.DataFrame(None, index=df.index, columns=score_cols) 

            # check input 
            ph_in, c_in = parse_distro_req(distro['in'])
            has_input = (df['input - type'].str.find(ph_in) != -1) & (df['input - current [A]']==c_in)            
            scoreboard.loc[:, score_cols[0]] = has_input
            scoreboard.loc[:, score_cols[-1]] = has_input # init total score

            # check output(s)
            has_output = dict.fromkeys(distro['out'].keys(), False) # a dict checking if considered distro has the correct outputs
            no = 0  # output type counter
            for desc, qty in distro['out'].items():
                if verbose>=2:
                    print(f'\t looking for a distro with {qty} output(s) of type {desc}...')

                no += 1
                ph_out, c_out = parse_distro_req(desc)

                # loop on the type of outputs the distros have in the inventory that could match(3P or 1P?)
                inventory_col_to_check = [col for col in output_cols_head if ph_out in col]         
                for availableOuput in inventory_col_to_check:
                    if verbose>=2:
                        print(f"\t\t looking in the '{availableOuput}' column...")
                    
                    # find out which distro(s) have the needed type of output 
                    has_output_rating = (df[f'{availableOuput} - current [A]'] == c_out) 
                    has_output_qty = df.loc[:, f'{availableOuput} - quantity'] >= qty
                    has_output[desc] = has_output[desc] | (has_output_rating & has_output_qty)
                    scoreboard.loc[:, score_cols[no]] = has_output[desc] # update score for this output
                    if verbose>=3:
                        print(f'has output: \n{has_output}')
                        print(f'scoreboard: {scoreboard}')       
                    
                # now that the output possibilities have been checked, update total score
                scoreboard.loc[:, score_cols[-1]] &= scoreboard.loc[:, score_cols[no]]
                
            # now that distro requirements have been checked, check that there is enough left in stock
            scoreboard.loc[:, score_cols[-1]] &= df.loc[:, 'how many distros']>=1
            candidates = df[scoreboard.loc[:, score_cols[-1]] == True]

            if len(candidates)==0:
                prt = '\t could not find a good distro :( '
                choice = None 
                unmatched.append(loadName)

            elif len(candidates)==1:
                prt = '\t could find the perfect type of distro'
                choice = df[scoreboard.loc[:, score_cols[-1]]==True].index[0]

            else:
                prt = f'\t could find {len(candidates)} types of distros'
                # take first ok one https://stackoverflow.com/a/40660434
                choice = df[scoreboard.loc[:, score_cols[-1]]==True].index[0] 

            if choice != None: # update inventory
                df.loc[choice, 'how many distros'] -= 1 
                # TODO: write destination in spreadsheet ? update grid ? 

            if verbose:
                print(prt)

            if verbose>=2: 
                print(f'\t candidates: \n{candidates}')

            if verbose>=3: 
                print(f'scoreboard : \n{scoreboard}')

        else:
            choice = None 

        # TODO: update grid with chosen distro ?
        # grid[loadName]['distro_chosen'] = df.loc[choice, :] 
    print(f'\ncould not find distros for the following loads: {unmatched}')
                    
    return None 