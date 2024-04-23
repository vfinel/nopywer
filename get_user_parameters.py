def get_user_parameters():
    param = {
            'project_file': "H:\\Mon Drive\\vico\\map\\map_experiments\\\map_20230701_correctionCRS\\nowhere2023 map.qgz",
            #'project_file': "H:\\Mon Drive\\vico\\map\\map_experiments\\map_20230620_testFarMoN\\powerMap_farMoN.qgs.qgz",
            'loadLayersList': ["norg2023_nodes", "art2023"],
            'cablesLayersList': ["norg2023_3phases", "norg2023_1phase","art2023_3phases", "art2023_1phase"],
            'V0': 230,
            'extra_cable_length': 10    # extra length to ad to each cable. 10 should be the minimum
            }
        
    return param