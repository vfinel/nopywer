import pytest

from nopywer.models import (
    Cable16A,
    Cable32A,
    Cable63A,
    Cable125A,
    pick_cable_for,
)


@pytest.mark.parametrize(
    "power_watts, expected_cls",
    [
        (0, Cable16A),
        (1000, Cable16A),
        (3312, Cable16A),
        (3313, Cable32A),
        (10_000, Cable32A),
        (19_872, Cable32A),
        (19_873, Cable63A),
        (39_123, Cable63A),
        (39_124, Cable125A),
        (77_625, Cable125A),
        (100_000, Cable125A),
    ],
)
def test_pick_cable_for(power_watts, expected_cls):
    assert pick_cable_for(power_watts) is expected_cls
