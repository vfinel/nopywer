import json
from collections import Counter
from pathlib import Path

from nopywer.io import load_geojson
from nopywer.optimize import optimize_layout

FIXTURES = Path(__file__).parent


def test_optimization_summary():
    # source data from an event in 2025
    with open(FIXTURES / "input_nodes.geojson") as f:
        input_geojson = json.load(f)

    nodes, _ = load_geojson(input_geojson)
    cables = optimize_layout(list(nodes.values()))

    count = Counter(int(c.plugs_and_sockets_a) for c in cables)
    total_length = {}
    for c in cables:
        key = int(c.plugs_and_sockets_a)
        total_length[key] = total_length.get(key, 0) + c.length_m

    assert count[16] == 43
    assert count[32] == 5
    assert count[63] == 1
    assert count[125] == 1
    assert len(cables) == 50

    assert round(total_length[16]) == 2514
    assert round(total_length[32]) == 279
    assert round(total_length[63]) == 40
    assert round(total_length[125]) == 41
    assert round(sum(c.length_m for c in cables)) == 2874
