# intro 
This code analyses power grid draw on QGIS to compute current flowing through cables, 3-phases balance, and a rough estimation of voltage drop. 

This is not professional software, I am neither a professionnal electrician nor a python developer. This software does not comes with any waranties or whatsoever.

This project is under development. I am learning python along the way, the code is not very pythonic yet... 

Contributions welcome !


# setup

## how to set up your QGIS project
This part of the documentation is incomplete. In a nutshell: 
- start by duplicating the nodes and cables layers of the example qgis project

*(note: the example project as yet to created and shared, but if you are reading this we probably know each other and you got your hands on the qgis project ;))*

- create a spreadsheet containing power requirements for each load of the qgis' loads layer(s). The spreadsheet must comply with the following rules:
    - should be a .ods file 
    - should contain the following columns: 
        - ```Project```: the name of the project should match the names on qgis nodes layer(s)
        - ```which phase(1, 2, 3, T, U or Y)```: split the load on selected phases.
            - ```T``` splits it on the 3 phases 
            - ```Y``` and ```U``` assign them to the Y and U grids and does not compute power stuff for them.
        - ```worstcase power [W]```: how many watts this loads needs 
    - should NOT contains any notes or comments on the cells 

## how to setup nopywer parameters 

To download the code, click on the green ```<> Code``` button on the top-right corner of this page, and then click on "Download ZIP". Note that if you are familiar with git, it would be best to clone the repository to get updates easily. 

The file ```get_user_parameters.py``` contains some fields that can be edited:
- ```project_file```: this actually NOT used if you run nopywer from QGIS console directly, so you can ignore this 
- ```extra_cable_length```: extra length to add to the "straight line length" measured on the map, to get the necessary length of the cable to have some slack. 10m should be the minimum.

The file ```get_constant_parameters.py``` also contains some informations you might want to look at. 


# usage 
- download the nopywer code on your computer 
- open your qgis project 
- open the python console by typing Ctrl+Alt+P (or clicking on Plugins -> Python Console)
- if it's the first time you are running nopywer:
    - Click on 'Show Editor' icon
    - Click on 'Open Script...' icon 
    - Navigate to the folder where you downloaded nopywer and select the file ```main.py```
    - Click on 'Run Script' icon 

- if you have already ran nopywer before:
    - press the "arrow up" key on your keyboard, to retrieve previously executed python commands. You should see something like ```exec(Path('<some path>/nopywer/main.py').read_text())``` (where ```<some path>``` shows where you downloaded nopywer on your computer)
    - press Enter 

- That's it ! The code should run, show lots of info, and conclude by "end of script for now :)"


# troubleshooting
If you have erros, please reach out (please include of copy of complete message displayed in the console)



