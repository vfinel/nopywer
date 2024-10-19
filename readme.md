# intro 
This code analyses power grid draw on QGIS to compute current flowing through cables, 3-phases balance, and a rough estimation of voltage drop. 

This is not professional software, I am neither a professionnal electrician nor a python developer. This software does not comes with any waranties or whatsoever.

This project is under development. I am learning python along the way, the code is not very pythonic yet... 

Contributions welcome !

# setup

First of all, make sure that QGIS is configured in English.

## prepare QGIS python 
You need to install some modules. Below are the explanations (for Windows only, other systems yet to come...)
- open OSGeo4W shell. It is accessible from Windows' start menu or the QGIS installation folder. If you have multiple QGIS version installed, make sure to open the OSgeo4W shell of the QGIS version you are using.
- Use Python’s pip to install the libraries: ```python -m pip install odfpy pandas pulp networkx```

For more help see https://landscapearchaeology.org/2018/installing-python-packages-in-qgis-3-for-windows/


## how to set up your QGIS project

### configure QGIS 


This part of the documentation is incomplete. In a nutshell: 
- start by duplicating the nodes and cables layers of the example qgis project

*(note: the example project as yet to be created and shared, but if you are reading this we probably know each other and you got your hands on the qgis project ;))*

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

## type of layers you'll have
- nodes : what it is 
- phases: what it is (3P, 11, etc) 

## work on your layers 
- do not write power usage of your nodes in qgis  
- do not assign phases on qgis
--> nopywer reads the spreadsheet and does that for you
(the idea is to try to use very little qgis and more automated stuff as well spreadsheets)


## run code 
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
If you have errors, please reach out (please include of copy of complete message displayed in the console). 

Here are some explanations on how to interpret nopywer's output:

- loads not using power appear on the "on map but missing on spreadsheet" list: --> they should be added on the spreadsheet

- loads not using power appear on the "on spreadsheet but missing on map" list: 
--> they should be removed from the spreadsheet

- loads which have U or Y assigned appear on the 'loads not connected to a cable' list
--> connect them to a cable layer that nopywer is actually checking



