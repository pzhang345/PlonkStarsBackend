"""Map search and bounds routes.

Scope (TESTING_PLAN.md section 2 comment: "search, bounds" and section 3
Phase 3):
- Search: pagination, the name filter, and empty results. `bounds` returns
  the map's bounds.

Local helpers (tests/integration/map/conftest.py is owned by another agent
and is deliberately empty right now, so fixtures live here instead):
- `_seed_map_stats`: attaches a MapStats row to a map so `total_guesses`
  (the search route's sort key) is deterministic instead of tied at 0.
- `_add_bound`: attaches a Bound (+ MapBound) row to a map directly via the
  ORM, since the edit routes aren't in scope for this file.
"""

import pytest

from models.db import db
from models.map import Bound, MapBound
from models.stats import MapStats
from tests.factories import make_map, make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration

SEARCH_URL = "/api/map/search"
BOUNDS_URL = "/api/map/bounds"


def _seed_map_stats(game_map, total_guesses, total_score=0, nmpz=False):
    stats = MapStats(
        map_id=game_map.id, nmpz=nmpz,
        total_time=0, total_score=total_score, total_distance=0, total_guesses=total_guesses,
    )
    db.session.add(stats)
    db.session.commit()
    return stats


def _add_bound(game_map, s_lat, s_lng, e_lat, e_lng, weight=1):
    bound = Bound(start_latitude=s_lat, start_longitude=s_lng, end_latitude=e_lat, end_longitude=e_lng)
    db.session.add(bound)
    db.session.flush()
    map_bound = MapBound(bound_id=bound.id, map_id=game_map.id, weight=weight)
    db.session.add(map_bound)
    db.session.commit()
    return map_bound


# ---------------------------------------------------------------------------
# Search - BUG: the whole route crashes before returning anything
# ---------------------------------------------------------------------------
#
# BUG: get_all_maps builds its query with `db.session.query(GameMap, ...)`,
# which is a plain sqlalchemy.orm.Query - not the Flask-SQLAlchemy Query
# subclass (only `Model.query`, e.g. `GameMap.query`, uses that subclass).
# The plain Query has no `.paginate()` method at all, so the final
# `.paginate(page=page, per_page=per_page)` call raises AttributeError on
# every single request to this route, unconditionally - regardless of
# pagination params, the name filter, or whether there are zero or many
# matching maps. Verified directly: `hasattr(sqlalchemy.orm.Query,
# "paginate")` is False, `hasattr(flask_sqlalchemy.query.Query, "paginate")`
# is True. TESTING is True, so the exception propagates out of
# client.get(...) instead of becoming a 500 response, exactly like the
# UserCoins bug pinned in test_crates_shop.py.
#
# The three tests below pin this for the three scenarios named in
# TESTING_PLAN.md's map bullet (pagination, name filter, empty results) -
# each documents that the route crashes, not that the feature works. Once
# fixed, each becomes a real assertion on the (currently unreachable) JSON
# shape the scenario setup below is already built for.

def test_search_paginates_results_documents_bug(client):
    """15 maps owned by the same user, with distinct (seeded) total_guesses
    so the search route's `desc(total_guesses)` sort would be deterministic
    across pages once the route works - but the route currently crashes
    before pagination ever runs."""
    user = make_user()
    names = [f"paginate-map-{i}" for i in range(15)]
    for i, name in enumerate(names):
        game_map = make_map(creator=user, name=name)
        _seed_map_stats(game_map, total_guesses=100 - i)  # descending: map 0 has the most guesses

    with pytest.raises(AttributeError):
        client.get(SEARCH_URL, query_string={"page": 1, "per_page": 10}, headers=auth_header(user))


def test_search_filters_by_name_documents_bug(client):
    """The `name` query param is meant to do a case-insensitive substring
    match against GameMap.name (also uuid/creator username), but the route
    crashes on `.paginate()` before that filter's results can ever be
    returned."""
    user = make_user()
    make_map(creator=user, name="Alpha Desert")
    make_map(creator=user, name="Beta Ocean")

    with pytest.raises(AttributeError):
        client.get(SEARCH_URL, query_string={"name": "desert"}, headers=auth_header(user))


def test_search_with_no_matches_returns_empty_results_documents_bug(client):
    """Even a name filter matching nothing still hits the same
    `.paginate()` call and crashes - it does not short-circuit to an empty
    result set."""
    user = make_user()
    make_map(creator=user, name="Something")

    with pytest.raises(AttributeError):
        client.get(SEARCH_URL, query_string={"name": "zzz-no-such-map-zzz"}, headers=auth_header(user))


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def test_bounds_returns_the_maps_bounds(client):
    """The bounds route returns every Bound row attached to the map, in the
    shape Bound.to_json() produces (a rectangle vs. a degenerate point bound
    serialize differently), plus the MapBound's own weight/id."""
    user = make_user()
    game_map = make_map(creator=user)
    rect = _add_bound(game_map, 10.0, 20.0, 30.0, 40.0, weight=2)
    point = _add_bound(game_map, -5.0, -5.0, -5.0, -5.0, weight=1)

    response = client.get(BOUNDS_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
    by_id = {entry["id"]: entry for entry in body}
    assert by_id[rect.id] == {
        "start": {"lat": 10.0, "lng": 20.0},
        "end": {"lat": 30.0, "lng": 40.0},
        "weight": 2,
        "id": rect.id,
    }
    assert by_id[point.id] == {"lat": -5.0, "lng": -5.0, "weight": 1, "id": point.id}


def test_bounds_for_map_with_no_bounds_returns_empty_list(client):
    user = make_user()
    game_map = make_map(creator=user)

    response = client.get(BOUNDS_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == []


def test_bounds_missing_id_returns_400(client):
    user = make_user()

    response = client.get(BOUNDS_URL, headers=auth_header(user))

    assert response.status_code == 400
    assert response.get_json() == {"error": "provided: id"}


def test_bounds_unknown_map_id_returns_404(client):
    user = make_user()

    response = client.get(BOUNDS_URL, query_string={"id": "does-not-exist"}, headers=auth_header(user))

    assert response.status_code == 404
