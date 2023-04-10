import os
debug = 1

def getChildren(nodeName, grid, cables):
    #childrenlist = []
    childrenDict = dict()
    
    # --- find what node(=children) is connected to nodeName
    for cable in grid[nodeName]['_cable']: # cables connected to nodeName
        # nodes connected to this cable: 
        nodes = cables[cable['layer']][cable['idx']]['nodes'] 
        #childrenlist.extend(nodes)
        #childrenlist.remove(nodeName) # remove origin
        
        for node in nodes:
            if node!=nodeName:
                childrenDict[node] = dict()
                childrenDict[node]['cable'] = {"layer": cable['layer'],"idx":cable['idx']}
                
        if debug: print(f"\t {nodeName} has one cable connecting it to: {nodes}")
        
    
    # --- remove parent from the list of connected nodes (except if nodeName == generator)
    if nodeName=="generator":
        grid[nodeName]["parent"] = []
    
    else: # this node has a previously identified parent ---> remove it from children list
#        try: # could have done a test, but less readable ?: if any(child in grid[nodeName]["parent"] for child in childrenlist):
#            childrenlist.remove(grid[nodeName]["parent"])
#        except ValueError:
#            pass
            
        try: # could have done a test, but less readable ?: if any(child in grid[nodeName]["parent"] for child in childrenlist):
            del childrenDict[grid[nodeName]["parent"]]
        except ValueError:
            pass
        
    
    # --- store 
    
    # rm list's duplicates because dictionaries cannot have duplicate keys.
    #childrenlist = list(dict.fromkeys(childrenlist)) 
    
    #grid[nodeName]["children"] = childrenlist
    grid[nodeName]["children"] = dict()
    grid[nodeName]["children"] = childrenDict
    
    print(f"\n load {nodeName}")
    #print(childrenlist)
    print(childrenDict.keys())
    print(childrenDict)
    print('\n')
    
#    for child in childrenlist:
#        grid[child]["parent"] = nodeName 
    for child in childrenDict.keys():
        grid[child]["parent"] = nodeName 
       
#        print('compare storage:')
#        print(child)
#        print(childrenDict)

#        grid[nodeName]["children"][child] = dict() 
#        grid[nodeName]["children"][child]['cable'] = childrenDict
        
    if debug: print(f"\n---> {nodeName} has children: {childrenDict.keys()}")
    
    # --- recursive call to find all the grid
    for child in childrenDict.keys():
        #print(f'\t checking  {child}')
        #os.system('pause')
        grid,kids = getChildren(child, grid, cables)
        #print(f'\t {child}, has childs: {kids}')

    return grid, childrenDict
    
# ---------

if __name__ == "__main__":
# test: 
    getChildren("generator", nodesDict, cablesDict)
