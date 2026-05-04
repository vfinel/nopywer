from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from nopywer.api import OptimizeRequest
from nopywer.io import load_geojson
from nopywer.models import PowerGrid

# from nopywer.optimize import optimize_layout
from nopywer.ortools_solverV1 import optimize_layout


class OptimizeResponse(BaseModel):
    cables_geojson: dict
    total_cable_length_m: float
    num_cables: int
    phase_loads: dict[int, float]


def optimize(req: OptimizeRequest):
    nodes, _ = load_geojson(req.nodes_geojson)
    if not nodes:
        raise HTTPException(400, "No valid nodes found in GeoJSON")

    try:
        grid = PowerGrid(nodes=nodes, cables={})
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    loads = [n for n in grid.nodes.values() if not n.is_generator]
    if not loads:
        raise HTTPException(400, "At least one load is required")

    grid = optimize_layout(grid, extra_cable_m=req.extra_cable_m)

    return OptimizeResponse(
        cables_geojson=grid.to_geojson(),
        total_cable_length_m=round(
            sum(c.length_m for c in grid.cables.values()),
            1,
        ),
        num_cables=len(grid.cables),
        phase_loads=grid.phase_loads,
    )


if __name__ == "__main__":
    import json

    with open(Path(__file__).parent.parent.parent / "tests/fixtures/power-nodes.geojson") as f:
        nodes_geojson = json.load(f)
    req = OptimizeRequest(nodes_geojson=nodes_geojson)
    res = optimize(req)
    print(json.dumps(res.dict(), indent=2))
