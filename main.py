
# find grid geometru
exec(Path('H:/Mon Drive/vico/map/sandbox/getGridGeometry.py').read_text())

# spreadsheet: asign phases

# load spreadsheet (power usage + phase) and add it to "grid" dictionnary
exec(Path('H:/Mon Drive/vico/map/sandbox/readSpreadsheet.py').read_text())

#print(json.dumps(grid, sort_keys=True, indent=4))

print("\n end of script for now :)")