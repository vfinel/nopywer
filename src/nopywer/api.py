from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .constants import EXTRA_CABLE_LENGTH_M
from .io import layout_to_geojson, load_geojson
from .optimize import optimize_layout

app = FastAPI(title="nopywer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class OptimizeRequest(BaseModel):
    nodes_geojson: dict
    extra_cable_m: float = EXTRA_CABLE_LENGTH_M


class OptimizeResponse(BaseModel):
    cables_geojson: dict
    total_cable_length_m: float
    num_cables: int


@app.post("/api/v1/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    nodes, _ = load_geojson(req.nodes_geojson)
    if not nodes:
        raise HTTPException(400, "No valid nodes found in GeoJSON")

    generators = [n for n in nodes.values() if n.is_generator]
    if not generators:
        raise HTTPException(
            400,
            "At least one generator is required (name must contain 'generator')",
        )

    loads = [n for n in nodes.values() if not n.is_generator]
    if not loads:
        raise HTTPException(400, "At least one load is required")

    cables = optimize_layout(list(nodes.values()), extra_cable_m=req.extra_cable_m)

    return OptimizeResponse(
        cables_geojson=layout_to_geojson(cables, nodes),
        total_cable_length_m=round(sum(c.length_m for c in cables), 1),
        num_cables=len(cables),
    )


def run():
    import uvicorn

    uvicorn.run("nopywer.api:app", host="0.0.0.0", port=8042, reload=True)
