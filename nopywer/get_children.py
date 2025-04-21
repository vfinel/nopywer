import os
import json # print(json.dumps(cablesDict, sort_keys=True, indent=4))

def get_children(nodeName, grid, cables):
    debugPrint = 0
    childrenDict = dict() # for parent to store info about its children

    if grid[nodeName]['children'] != None: 
        raise ValueError(f"\n\nThere is an infinite loop going from/to {nodeName} on the map. \n"\
                         f"It is connected by the following nodes:\n"
                         f"{json.dumps(grid[nodeName]['children'], sort_keys=False, indent=4)}\n"
                         "Make sure to display all cable layers and fix.")
    
    # --- find what node(=children) is connected to nodeName
    for cable in grid[nodeName]['_cable']: # cables connected to nodeName
        # children = nodes connected to this cable (+parent, but we'll remove it later): 
        children = cables[cable['layer']][cable['idx']]['nodes'] 
        for child in children:
            if child!=nodeName:
                childrenDict[child] = dict() 
                childrenDict[child]['cable'] = {"layer": cable['layer'],"idx":cable['idx']} # cable parent<-->child

                #grid[child]["cable"] = childrenDict[child]['cable']
                
        if debugPrint>1: print(f"\t {nodeName} has one cable connecting it to: {children}")
        
    
    # --- remove parent from the list of connected nodes
    if nodeName!="generator": # if this node has a parent ---> remove it from children list
        try: # could have done a test, but less readable ?: if any(child in grid[nodeName]["parent"] for child in childrenlist):
            del childrenDict[grid[nodeName]["parent"]]
        except ValueError:
            pass
    
    else: 
        grid[nodeName]["parent"] = []
        
    if debugPrint: print(f"\t{nodeName} has children: {childrenDict.keys()}")
    
    # --- store 
    grid[nodeName]["children"] = childrenDict # store current node's children
    for child in childrenDict.keys():         # tell the children who their parent is
        grid[child]["parent"] = nodeName 

    # --- compute deepness 
    if nodeName=="generator":
        grid[nodeName]["deepness"] = 0
    else:
        parent = grid[nodeName]["parent"]
        grid[nodeName]["deepness"] = grid[parent]["deepness"] + 1
    
    # --- recursive call to find all the grid
    for child in childrenDict.keys():
        grid, kids = get_children(child, grid, cables)

    return grid, childrenDict
    
# ---------

if __name__ == "__main__":
# test: 
    grid, childrenDict = get_children("generator", nodesDict, cablesDict)
