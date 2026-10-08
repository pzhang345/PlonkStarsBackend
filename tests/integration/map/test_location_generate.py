"""generate_location via the Street View mock.

Scope:
- generate_location with street_view_mock: the point falls inside a bound,
  and "no street view found" is handled.

`generate_location` (app/api/location/generate.py) picks a random weighted
Bound via `get_random_bounds`, then calls `check_multiple_street_views`
(which checks candidate points on a thread pool) to find a Street-View-covered point in it. The
`street_view_mock` fixture (tests/conftest.py) replaces that call with a fake
that deterministically returns the bound's start corner as a real SVLocation
row. random.uniform is patched to a fixed midpoint value everywhere below so
bound selection itself is deterministic (each map here has exactly one
bound, so any value in range would pick it - this just removes the
theoretical, vanishingly-rare edge case where uniform(0, w) returns w
itself).
"""

import pytest

import api.location.generate as generate_module
from api.location.generate import generate_location
from models.db import db
from models.map import Bound, MapBound
from tests.factories import make_location, make_map

pytestmark = pytest.mark.integration


def _add_single_bound(game_map, s_lat, s_lng, e_lat, e_lng, weight=1):
    bound = Bound(start_latitude=s_lat, start_longitude=s_lng, end_latitude=e_lat, end_longitude=e_lng)
    db.session.add(bound)
    db.session.flush()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=weight))
    db.session.commit()
    return bound


def _force_bound_selection(monkeypatch):
    """Deterministically select the (only) bound on the map regardless of
    real randomness."""
    monkeypatch.setattr(generate_module.random, "uniform", lambda a, b: (a + b) / 2)


# ---------------------------------------------------------------------------
# Street View found
# ---------------------------------------------------------------------------

def test_generated_point_falls_inside_the_bound(client, street_view_mock, monkeypatch):
    game_map = make_map(total_weight=1)
    _add_single_bound(game_map, 10.0, 20.0, 15.0, 25.0, weight=1)
    _force_bound_selection(monkeypatch)

    location = generate_location(game_map)

    assert location is not None
    assert 10.0 <= location.latitude <= 15.0
    assert 20.0 <= location.longitude <= 25.0
    # street_view_mock deterministically returns the bound's start corner.
    assert location.latitude == 10.0
    assert location.longitude == 20.0


def test_generated_point_on_degenerate_point_bound_is_that_point(client, street_view_mock, monkeypatch):
    """A single-point bound (start == end, as produced by
    tests.factories.make_bounded_map) still round-trips through
    generate_location and street_view_mock to land exactly on that point."""
    game_map = make_map(total_weight=1)
    _add_single_bound(game_map, 42.0, -71.0, 42.0, -71.0, weight=1)
    _force_bound_selection(monkeypatch)

    location = generate_location(game_map)

    assert location.latitude == 42.0
    assert location.longitude == -71.0


# ---------------------------------------------------------------------------
# No Street View coverage found
# ---------------------------------------------------------------------------

def test_no_street_view_found_is_handled_gracefully(client, street_view_mock, monkeypatch):
    """When check_multiple_street_views can never find coverage,
    generate_location falls back to db_location(bound) instead of raising -
    and returns None (rather than blowing up) when that fallback also finds
    nothing nearby."""
    def _always_none(bound, num_checks=100):
        return None
    monkeypatch.setattr(generate_module, "check_multiple_street_views", _always_none)

    game_map = make_map(total_weight=1)
    _add_single_bound(game_map, 10.0, 20.0, 10.0, 20.0, weight=1)
    _force_bound_selection(monkeypatch)

    location = generate_location(game_map)

    assert location is None


def test_no_street_view_found_falls_back_to_a_nearby_existing_location(client, street_view_mock, monkeypatch):
    """Same "no coverage" scenario, but this time an SVLocation already
    exists just inside db_location's +/-50m buffer around the bound - the
    fallback should return that row instead of None."""
    def _always_none(bound, num_checks=100):
        return None
    monkeypatch.setattr(generate_module, "check_multiple_street_views", _always_none)

    game_map = make_map(total_weight=1)
    _add_single_bound(game_map, 10.0, 20.0, 10.0, 20.0, weight=1)
    _force_bound_selection(monkeypatch)
    # ~11m away in both lat/lng - well within the +/-50m buffer.
    existing = make_location(latitude=10.0001, longitude=20.0001)

    location = generate_location(game_map)

    assert location is not None
    assert location.id == existing.id
