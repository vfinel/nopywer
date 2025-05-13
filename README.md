# nopywer

Welcome to npywer source code. Visit the homepage of the project here: https://vfinel.github.io/nopywer/

## Introduction

This code analyses power grid gathered from QGIS to compute current flowing through cables, 3-phases balance, and voltage drop. 

Contributions are welcome and encouraged! Please see the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines.

## Setup


### Configuration to run nopywer outside QGIS 
To run outside QGIS, it is necessary to use a virtual environment with ```conda```.
```
conda create -n "nopywer" --channel conda-forge --file requirements.yaml
```

### Configuration to run nopywer from QGIS python console 

You need to install some modules in the python environment used by QGIS. To do so, follow the instructions below (Windows only, other systems yet to come...)
- open OSGeo4W shell. It is accessible from Windows' start menu or the QGIS installation folder. If you have multiple QGIS version installed, make sure to open the OSgeo4W shell of the QGIS version you are using.
- Use Python’s pip to install the libraries: ```python -m pip install odfpy pandas pulp networkx```

For further details see https://landscapearchaeology.org/2018/installing-python-packages-in-qgis-3-for-windows/


### How to set up your QGIS project

#### Configure QGIS 

prerequisites: make sure that QGIS is configured in English.

prerequisites: make sure that QGIS is configured in English.

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

### How to setup nopywer parameters 

To download the code, click on the green ```<> Code``` button on the top-right corner of this page, and then click on "Download ZIP". Note that if you are familiar with git, it would be best to clone the repository to get updates easily. 

The file ```get_user_parameters.py``` contains some fields that can be edited:
- ```project_file```: this actually NOT used if you run nopywer from QGIS console directly, so you can ignore this 
- ```extra_cable_length```: extra length to add to the "straight line length" measured on the map, to get the necessary length of the cable to have some slack. 10m should be the minimum.

The file ```get_constant_parameters.py``` also contains some informations you might want to look at. 


## Usage 
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


## Troubleshooting
If you have errors, please reach out (please include of copy of complete message displayed in the console). 

Here are some explanations on how to interpret nopywer's output:

- loads not using power appear on the "on map but missing on spreadsheet" list: --> they should be added on the spreadsheet

- loads not using power appear on the "on spreadsheet but missing on map" list: 
--> they should be removed from the spreadsheet

- loads which have U or Y assigned appear on the 'loads not connected to a cable' list
--> connect them to a cable layer that nopywer is actually checking

## Disclaimer 
While efforts have been made to ensure this project functionality, it is provided "as is" without any warranties.

