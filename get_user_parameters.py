def get_user_parameters():
    param = {
            'project_file': "H:\\Mon Drive\\vico\\map\\map2024\\qfieldcloud\\_cloud.qgs", # this is not used and be ignored if the code is ran from QGIS console.
            'loadLayersList': ["norg_nodes_2024"],
            'cablesLayersList': ["norg_3phases_63A_2024", "norg_3phases_32A_2024", "norg_1phase_2024"],
            'spreadsheet': {
                'name': "Power 2024 map balance.ods",
                'sheet': "All",
                'skiprows': 0
            },
            'extra_cable_length': 10  # extra length to add to the "straight line length" to get the necessary length of the cable to have some slack. 10m should be the minimum
            }
        
    return param