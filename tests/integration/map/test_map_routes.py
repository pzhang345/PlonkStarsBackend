"""Map search and bounds routes.

Scope:
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
# Search
# ---------------------------------------------------------------------------
#
# get_all_maps returns {"maps": [...], "pages": <int>}, where each map entry
# is {name, id (the map's uuid, not its db id), creator (username),
# average_score, average_generation_time, total_guesses}. Results are
# paginated via `.paginate(page=page, per_page=per_page)` and ordered by
# (creator priority, desc total_guesses); `pages` follows Flask-SQLAlchemy's
# Pagination.pages, which is 0 when there are no matching rows and otherwise
# ceil(total / per_page).

def test_search_paginates_results(client):
    """15 maps owned by the same user, with distinct (seeded) total_guesses
    so the search route's `desc(total_guesses)` sort is deterministic across
    pages. All 15 share a creator, so they all get the same (highest) sort
    priority and the tie is broken purely by total_guesses - map 0 has the
    most guesses (100) down to map 14 (86), so page 1 (per_page=10) is maps
    0-9 and page 2 is maps 10-14."""
    user = make_user()
    names = [f"paginate-map-{i}" for i in range(15)]
    maps_by_name = {}
    for i, name in enumerate(names):
        game_map = make_map(creator=user, name=name)
        _seed_map_stats(game_map, total_guesses=100 - i)  # descending: map 0 has the most guesses
        maps_by_name[name] = game_map

    page_1 = client.get(SEARCH_URL, query_string={"page": 1, "per_page": 10}, headers=auth_header(user))
    assert page_1.status_code == 200
    body_1 = page_1.get_json()
    assert body_1["pages"] == 2
    assert [m["name"] for m in body_1["maps"]] == names[:10]
    assert [m["total_guesses"] for m in body_1["maps"]] == [100 - i for i in range(10)]
    assert [m["average_score"] for m in body_1["maps"]] == [0] * 10
    first = body_1["maps"][0]
    assert first["id"] == maps_by_name[names[0]].uuid
    assert first["creator"] == user.username

    page_2 = client.get(SEARCH_URL, query_string={"page": 2, "per_page": 10}, headers=auth_header(user))
    assert page_2.status_code == 200
    body_2 = page_2.get_json()
    assert body_2["pages"] == 2
    assert [m["name"] for m in body_2["maps"]] == names[10:]
    assert [m["total_guesses"] for m in body_2["maps"]] == [100 - i for i in range(10, 15)]


def test_search_filters_by_name(client):
    """The `name` query param does a case-insensitive substring match
    against GameMap.name (also uuid/creator username) - a query matching one
    of two maps returns only that map."""
    user = make_user()
    alpha = make_map(creator=user, name="Alpha Desert")
    make_map(creator=user, name="Beta Ocean")

    response = client.get(SEARCH_URL, query_string={"name": "desert"}, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    assert body["pages"] == 1
    assert [m["name"] for m in body["maps"]] == ["Alpha Desert"]
    assert body["maps"][0]["id"] == alpha.uuid


def test_search_with_no_matches_returns_empty_results(client):
    """A name filter matching nothing returns an empty `maps` list and
    `pages` 0 (Flask-SQLAlchemy's Pagination.pages is 0 when total is 0),
    rather than e.g. omitting the fields or erroring."""
    user = make_user()
    make_map(creator=user, name="Something")

    response = client.get(SEARCH_URL, query_string={"name": "zzz-no-such-map-zzz"}, headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"maps": [], "pages": 0}


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
