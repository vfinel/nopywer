from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .constants import EXTRA_CABLE_LENGTH_M
from .io import load_geojson
from .models import PowerGrid
from .optimize import optimize_layout

app = FastAPI(title="nopywer", version="1.0.0")
frontend_dir = Path(__file__).resolve().parent / "frontend"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_frontend_cache(request: Request, call_next):
    response = await call_next(request)
    is_static_request = not request.url.path.startswith("/api/")
    if request.method in {"GET", "HEAD"} and is_static_request:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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
    )


app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


def run():
    import uvicorn

    uvicorn.run("nopywer.api:app", host="127.0.0.1", port=8042, reload=True)
