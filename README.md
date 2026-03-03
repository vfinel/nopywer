# nopywer

Welcome to npywer source code. Visit the homepage of the project here: https://vfinel.github.io/nopywer/

## Introduction

This code analyses power grids to compute current flowing through cables, 3-phases balance, and voltage drop.

Contributions are welcome and encouraged! Please see the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines.

## Setup

```
uv sync
```

### Input data

Nopywer reads a GeoJSON file containing nodes and cables. A spreadsheet (.ods) can optionally be provided for equipment inventory.

The spreadsheet must comply with the following rules:
- should be a .ods file
- should contain the following columns:
    - ```Project```: the name of the project should match the node names
    - ```which phase(1, 2, 3, T, U or Y)```: split the load on selected phases.
        - ```T``` splits it on the 3 phases
        - ```Y``` and ```U``` assign them to the Y and U grids and does not compute power stuff for them.
    - ```worstcase power [W]```: how many watts this loads needs
- should NOT contains any notes or comments on the cells

## Usage

```
nopywer-analyze input.geojson
```

See `nopywer-analyze --help` for all options.

## Troubleshooting
If you have errors, please reach out (please include of copy of complete message displayed in the console).

Here are some explanations on how to interpret nopywer's output:

- loads not using power appear on the "on map but missing on spreadsheet" list: --> they should be added on the spreadsheet

- loads not using power appear on the "on spreadsheet but missing on map" list:
--> they should be removed from the spreadsheet

## Disclaimer
While efforts have been made to ensure this project functionality, it is provided "as is" without any warranties.
