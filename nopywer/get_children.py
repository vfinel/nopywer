import os
import json # print(json.dumps(cables_dict, sort_keys=True, indent=4))

def get_children(node_name, grid, cables):
    debugPrint = 0
    children_dict = dict() # for parent to store info about its children

    if grid[node_name]['children'] != None: 
        raise ValueError(f"\n\nThere is an infinite loop going from/to {node_name} on the map. \n"\
                         f"It is connected by the following nodes:\n"
                         f"{json.dumps(grid[node_name]['children'], sort_keys=False, indent=4)}\n"
                         "Make sure to display all cable layers and fix.")
    
    # --- find what node(=children) is connected to node_name
    for cable in grid[node_name]['_cable']: # cables connected to node_name
        # children = nodes connected to this cable (+parent, but we'll remove it later): 
        children = cables[cable['layer']][cable['idx']]['nodes'] 
        for child in children:
            if child!=node_name:
                children_dict[child] = dict() 
                children_dict[child]['cable'] = {"layer": cable['layer'],"idx":cable['idx']} # cable parent<-->child

                #grid[child]["cable"] = children_dict[child]['cable']
                
        if debugPrint>1: print(f"\t {node_name} has one cable connecting it to: {children}")
        
    
    # --- remove parent from the list of connected nodes
    if node_name!="generator": # if this node has a parent ---> remove it from children list
        try: # could have done a test, but less readable ?: if any(child in grid[node_name]["parent"] for child in childrenlist):
            del children_dict[grid[node_name]["parent"]]
        except ValueError:
            pass
    
    else: 
        grid[node_name]["parent"] = []
        
    if debugPrint: print(f"\t{node_name} has children: {children_dict.keys()}")
    
    # --- store 
    grid[node_name]["children"] = children_dict # store current node's children
    for child in children_dict.keys():         # tell the children who their parent is
        grid[child]["parent"] = node_name 

    # --- compute deepness 
    if node_name=="generator":
        grid[node_name]["deepness"] = 0
    else:
        parent = grid[node_name]["parent"]
        grid[node_name]["deepness"] = grid[parent]["deepness"] + 1
    
    # --- recursive call to find all the grid
    for child in children_dict.keys():
        grid, kids = get_children(child, grid, cables)

    return grid, children_dict
    
# ---------

if __name__ == "__main__":
# test: 
    grid, children_dict = get_children("generator", nodes_dict, cables_dict)
