"""Pure-logic unit tests for the input parsers/validators in
app/api/map/edit/mapedit.py:
- get_new_bound(data)   (line 36)
- get_point(data)       (line 80)

All exception types/messages below were verified by directly exercising the
functions before writing assertions - some are the module's own deliberate
`Exception("...")` calls, others are incidental Python errors (ValueError
from tuple/dict unpacking, TypeError from comparing str to int) that leak
through untouched. Both kinds are documented here as actual behavior.
"""

import pytest

from api.map.edit.mapedit import get_new_bound, get_point

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_point - accepted shapes
# ---------------------------------------------------------------------------

def test_get_point_accepts_lat_lng_dict():
    assert get_point({"lat": 45.0, "lng": -70.0}) == (45.0, -70.0)


def test_get_point_accepts_bare_tuple_or_list():
    assert get_point((45.0, -70.0)) == (45.0, -70.0)
    assert get_point([45.0, -70.0]) == (45.0, -70.0)


@pytest.mark.parametrize("lat,lng", [(90, 180), (-90, -180), (0, 0)])
def test_get_point_accepts_boundary_values_inclusive(lat, lng):
    assert get_point({"lat": lat, "lng": lng}) == (lat, lng)


# ---------------------------------------------------------------------------
# get_point - rejection paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", [{"lat": None, "lng": 10}, {"lat": 10, "lng": None}])
def test_get_point_raises_on_missing_value(data):
    with pytest.raises(Exception, match="please provided these arguments: lat and lng"):
        get_point(data)


@pytest.mark.parametrize(
    "data",
    [
        {"lat": 90.0001, "lng": 0},
        {"lat": -90.0001, "lng": 0},
        {"lat": 0, "lng": 180.0001},
        {"lat": 0, "lng": -180.0001},
    ],
)
def test_get_point_raises_on_out_of_range_lat_or_lng(data):
    with pytest.raises(Exception, match="invalid input"):
        get_point(data)


def test_get_point_raises_type_error_on_non_numeric_value():
    # Documented actual behavior: the range check `-90 <= lat <= 90` is done
    # with no type validation first, so a string value blows up with a raw
    # TypeError instead of the "invalid input" Exception.
    with pytest.raises(TypeError):
        get_point({"lat": "10", "lng": 20})


@pytest.mark.parametrize(
    "data,match",
    [
        ({}, "not enough values to unpack"),
        ({"only_one": 1}, "not enough values to unpack"),
        ({"a": 1, "b": 2, "c": 3}, "too many values to unpack"),
    ],
)
def test_get_point_raises_value_error_when_dict_has_no_lat_lng_keys(data, match):
    # Documented actual behavior: when "lat"/"lng" aren't both present, the
    # code falls back to `lat, lng = data`, which for a dict unpacks its
    # *keys* (not values) and only works cleanly for a 2-key dict - anything
    # else raises a raw ValueError from tuple unpacking.
    with pytest.raises(ValueError, match=match):
        get_point(data)


def test_get_point_two_key_dict_without_lat_lng_unpacks_keys_as_strings():
    # A 2-key dict without "lat"/"lng" unpacks successfully (keys become
    # lat/lng as strings), then blows up in the range comparison instead.
    with pytest.raises(TypeError):
        get_point({"a": 1, "b": 2})


# ---------------------------------------------------------------------------
# get_new_bound - accepted shapes
# ---------------------------------------------------------------------------

def test_get_new_bound_accepts_nested_start_end_dicts():
    data = {"start": {"lat": 10, "lng": 20}, "end": {"lat": 30, "lng": 40}}
    assert get_new_bound(data) == ((10, 20), (30, 40))


def test_get_new_bound_accepts_nested_start_end_as_bare_points():
    data = {"start": [10, 20], "end": [30, 40]}
    assert get_new_bound(data) == ((10, 20), (30, 40))


def test_get_new_bound_accepts_flat_s_lat_s_lng_e_lat_e_lng():
    data = {"s_lat": 10, "s_lng": 20, "e_lat": 30, "e_lng": 40}
    assert get_new_bound(data) == ((10, 20), (30, 40))


def test_get_new_bound_accepts_point_only_shape_as_degenerate_bound():
    # Neither "start"/"end" nor the flat keys are present, so it falls back
    # to treating the whole payload as a single point and uses it for both
    # corners of the bound.
    data = {"lat": 10, "lng": 20}
    assert get_new_bound(data) == ((10, 20), (10, 20))


def test_get_new_bound_accepts_equal_start_and_end_flat():
    data = {"s_lat": 5, "s_lng": 5, "e_lat": 5, "e_lng": 5}
    assert get_new_bound(data) == ((5, 5), (5, 5))


# ---------------------------------------------------------------------------
# get_new_bound - rejection paths
# ---------------------------------------------------------------------------

def test_get_new_bound_raises_on_inverted_start_end_nested():
    data = {"start": {"lat": 30, "lng": 20}, "end": {"lat": 10, "lng": 40}}
    with pytest.raises(Exception, match="invalid input"):
        get_new_bound(data)


def test_get_new_bound_raises_on_inverted_start_end_flat():
    data = {"s_lat": 30, "s_lng": 20, "e_lat": 10, "e_lng": 40}
    with pytest.raises(Exception, match="invalid input"):
        get_new_bound(data)


def test_get_new_bound_raises_on_out_of_range_lat_via_nested_shape():
    data = {"start": {"lat": 100, "lng": 20}, "end": {"lat": 30, "lng": 40}}
    with pytest.raises(Exception, match="invalid input"):
        get_new_bound(data)


def test_get_new_bound_flat_shape_does_not_validate_lat_lng_range():
    # BUG-ish behavior, documented not fixed: the flat s_lat/s_lng/e_lat/e_lng
    # branch skips get_point() entirely, so it never runs the -90..90 /
    # -180..180 range check that the nested "start"/"end" shape gets. Only
    # the start<=end ordering check still applies.
    data = {"s_lat": 100, "s_lng": 0, "e_lat": 101, "e_lng": 1}
    assert get_new_bound(data) == ((100, 0), (101, 1))


def test_get_new_bound_raises_value_error_on_missing_end_key():
    data = {"start": {"lat": 10, "lng": 20}}
    with pytest.raises(ValueError, match="not enough values to unpack"):
        get_new_bound(data)


def test_get_new_bound_raises_value_error_on_empty_dict():
    with pytest.raises(ValueError, match="not enough values to unpack"):
        get_new_bound({})


def test_get_new_bound_raises_value_error_on_partial_flat_keys():
    # 3 of the 4 flat keys present -> elif fails -> falls through to the
    # point-only branch, which tries to unpack a 3-key dict into (lat, lng).
    data = {"s_lat": 1, "s_lng": 2, "e_lat": 3}
    with pytest.raises(ValueError, match="too many values to unpack"):
        get_new_bound(data)
