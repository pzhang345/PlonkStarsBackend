"""Pure-logic unit tests for geo math helpers:
- haversine(lat1, lng1, lat2, lng2)              app/api/map/map.py
- add_meters(lat, lng, d_lat, d_lng)             app/api/location/generate.py
- map_max_distance(map)                          app/api/map/edit/mapedit.py

None of these touch the DB or network, so map_max_distance is exercised with
a plain SimpleNamespace standing in for a GameMap row (only the four corner
attributes it actually reads, plus the attribute it writes, are needed).
"""

import math
from types import SimpleNamespace

import pytest

from api.location.generate import add_meters
from api.map.edit.mapedit import map_max_distance
from api.map.map import haversine

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# haversine
# ---------------------------------------------------------------------------

def test_haversine_identical_points_is_zero():
    assert haversine(12.34, 56.78, 12.34, 56.78) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_of_latitude_is_about_111_19_km():
    assert haversine(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, rel=1e-3)


@pytest.mark.parametrize(
    "lat1,lng1,lat2,lng2",
    [
        (40.7128, -74.0060, 51.5074, -0.1278),  # NYC -> London
        (-33.8688, 151.2093, 35.6762, 139.6503),  # Sydney -> Tokyo
        (0.0, 0.0, 10.0, -20.0),
    ],
)
def test_haversine_is_symmetric(lat1, lng1, lat2, lng2):
    forward = haversine(lat1, lng1, lat2, lng2)
    backward = haversine(lat2, lng2, lat1, lng1)
    assert forward == pytest.approx(backward)


def test_haversine_known_long_haul_distance_nyc_to_london():
    # Real-world great-circle distance between NYC and London is
    # well-documented as ~5,570 km - an independently-known figure, not
    # derived from the formula under test.
    distance = haversine(40.7128, -74.0060, 51.5074, -0.1278)
    assert distance == pytest.approx(5570, rel=0.01)


@pytest.mark.parametrize(
    "lat1,lng1,lat2,lng2",
    [
        (0.0, 0.0, 0.0, 180.0),
        (10.0, 20.0, -10.0, -160.0),
        (30.0, 30.0, -30.0, -150.0),
        (60.0, 10.0, -60.0, -170.0),
    ],
)
def test_haversine_antipodal_points_is_about_half_earth_circumference(lat1, lng1, lat2, lng2):
    # Antipodal great-circle distance = pi * R = pi * 6371.0 ~= 20015.1 km.
    distance = haversine(lat1, lng1, lat2, lng2)
    assert distance == pytest.approx(math.pi * 6371.0, rel=1e-6)
    assert distance == pytest.approx(20015.09, rel=1e-4)


def test_haversine_antipodal_points_survive_float_rounding_past_one():
    # Regression: for this pair, float rounding pushes the intermediate `a`
    # to 1.0000000000000002, which used to make sqrt(1 - a) raise
    # 'math domain error' before `a` was clamped to [0, 1].
    distance = haversine(45.0, -30.0, -45.0, 150.0)
    assert distance == pytest.approx(math.pi * 6371.0, rel=1e-6)


def test_haversine_sign_handling_across_the_equator():
    # A point just north of the equator and a point just south by the same
    # magnitude are the same distance apart regardless of argument order.
    a_to_b = haversine(-1.0, 0.0, 1.0, 0.0)
    b_to_a = haversine(1.0, 0.0, -1.0, 0.0)
    assert a_to_b == pytest.approx(b_to_a)
    assert a_to_b == pytest.approx(222.39, rel=1e-3)


def test_haversine_sign_handling_across_the_prime_meridian():
    distance = haversine(0.0, -1.0, 0.0, 1.0)
    assert distance == pytest.approx(222.39, rel=1e-3)


def test_haversine_wraps_correctly_across_the_antimeridian():
    # Documented actual behavior: 179E and 179W longitudes are only 2 degrees
    # apart on the globe, even though the raw numeric difference is 358
    # degrees. Because the formula only ever consumes the longitude delta
    # through sin()/cos() (periodic functions), it "just works" here - this
    # is NOT a bug, verified by comparing against the equivalent 2-degree
    # separation computed directly.
    antimeridian_distance = haversine(0.0, 179.0, 0.0, -179.0)
    two_degree_distance = haversine(0.0, 0.0, 0.0, 2.0)
    assert antimeridian_distance == pytest.approx(two_degree_distance, rel=1e-9)
    assert antimeridian_distance == pytest.approx(222.39, rel=1e-3)


# ---------------------------------------------------------------------------
# add_meters
# ---------------------------------------------------------------------------

def test_add_meters_zero_offset_is_identity():
    lat, lng = add_meters(5.0, 5.0, 0, 0)
    assert lat == pytest.approx(5.0)
    assert lng == pytest.approx(5.0)


def test_add_meters_roundtrips_sensibly_against_haversine():
    # Offsetting by (1000m, 1000m) should land ~sqrt(2) km away per haversine.
    lat, lng = 10.0, 20.0
    new_lat, new_lng = add_meters(lat, lng, 1000, 1000)
    distance_km = haversine(lat, lng, new_lat, new_lng)
    assert distance_km == pytest.approx(math.sqrt(2), rel=1e-3)


def test_add_meters_pure_longitude_offset_at_equator_is_one_km():
    # At the equator, cos(lat) == 1, so a pure longitude offset of 1000m
    # should measure as ~1.0 km via haversine, with latitude unchanged.
    lat, lng = 0.0, 0.0
    new_lat, new_lng = add_meters(lat, lng, 0, 1000)
    assert new_lat == pytest.approx(0.0)
    assert haversine(lat, lng, new_lat, new_lng) == pytest.approx(1.0, rel=1e-6)


def test_add_meters_pure_latitude_offset_is_one_km_anywhere():
    # Latitude degrees-per-meter doesn't depend on longitude/cos(lat).
    lat, lng = 40.0, -70.0
    new_lat, new_lng = add_meters(lat, lng, 1000, 0)
    assert new_lng == pytest.approx(lng)
    assert haversine(lat, lng, new_lat, new_lng) == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# map_max_distance
# ---------------------------------------------------------------------------
# Reads/writes exactly these attributes (confirmed by reading the source):
# reads start_latitude/start_longitude/end_latitude/end_longitude, computes
# the max diagonal across the 4 rectangle corners, and mutates
# `map.max_distance` in place. It returns None - callers rely on the mutation.

def test_map_max_distance_mutates_in_place_and_returns_none():
    game_map = SimpleNamespace(
        start_latitude=0.0, start_longitude=0.0,
        end_latitude=1.0, end_longitude=1.0,
    )
    result = map_max_distance(game_map)
    assert result is None
    assert game_map.max_distance == pytest.approx(157.249, rel=1e-3)


def test_map_max_distance_degenerate_point_floors_at_one():
    # start == end on all axes -> every corner distance is 0, but the
    # function floors the result at 1 (max(max_dist, 1)) rather than 0.
    game_map = SimpleNamespace(
        start_latitude=5.0, start_longitude=5.0,
        end_latitude=5.0, end_longitude=5.0,
    )
    map_max_distance(game_map)
    assert game_map.max_distance == 1


def test_map_max_distance_picks_the_diagonal_not_an_edge():
    # A 0x1 degree rectangle (line, really): the diagonal corner-to-corner
    # distance must equal the single non-zero edge distance.
    game_map = SimpleNamespace(
        start_latitude=5.0, start_longitude=5.0,
        end_latitude=5.0, end_longitude=6.0,
    )
    map_max_distance(game_map)
    assert game_map.max_distance == pytest.approx(110.7718, rel=1e-3)
    assert game_map.max_distance == pytest.approx(haversine(5.0, 5.0, 5.0, 6.0))
