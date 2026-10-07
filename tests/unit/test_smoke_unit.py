"""Smoke test proving the pure-function layer works with zero DB/IO setup."""

import pytest

from api.game.gameutils import caculate_score
from api.map.map import haversine

pytestmark = pytest.mark.unit


def test_caculate_score_is_max_score_at_zero_distance():
    assert caculate_score(0, 1000, 5000) == pytest.approx(5000)


def test_caculate_score_decreases_as_distance_grows():
    near = caculate_score(1, 1000, 5000)
    far = caculate_score(500, 1000, 5000)
    assert near > far > 0


def test_haversine_same_point_is_zero():
    assert haversine(40.0, -70.0, 40.0, -70.0) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_latitude_is_about_111km():
    distance = haversine(0.0, 0.0, 1.0, 0.0)
    assert distance == pytest.approx(111.19, rel=0.01)
