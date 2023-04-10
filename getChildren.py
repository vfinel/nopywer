import os
debug = 0

def getChildren(nodeName, grid, cables):
    childrenDict = dict()
    
    # --- find what node(=children) is connected to nodeName
    for cable in grid[nodeName]['_cable']: # cables connected to nodeName
        # nodes connected to this cable: 
        nodes = cables[cable['layer']][cable['idx']]['nodes'] 
        for node in nodes:
            if node!=nodeName:
                childrenDict[node] = dict()
                childrenDict[node]['cable'] = {"layer": cable['layer'],"idx":cable['idx']}
                
        if debug: print(f"\t {nodeName} has one cable connecting it to: {nodes}")
        
    
    # --- remove parent from the list of connected nodes (except if nodeName == generator)
    if nodeName=="generator":
        grid[nodeName]["parent"] = []
    
    else: # this node has a previously identified parent ---> remove it from children list
        try: # could have done a test, but less readable ?: if any(child in grid[nodeName]["parent"] for child in childrenlist):
            del childrenDict[grid[nodeName]["parent"]]
        except ValueError:
            pass
        
    
    # --- store 
    grid[nodeName]["children"] = childrenDict
    for child in childrenDict.keys():
        grid[child]["parent"] = nodeName 
        
    if debug: print(f"\n---> {nodeName} has children: {childrenDict.keys()}")
    
    # --- recursive call to find all the grid
    for child in childrenDict.keys():
        grid,kids = getChildren(child, grid, cables)

    return grid, childrenDict
    
# ---------

if __name__ == "__main__":
# test: 
    getChildren("generator", nodesDict, cablesDict)
