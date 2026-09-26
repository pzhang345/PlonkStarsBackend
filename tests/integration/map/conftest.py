"""Fixtures for tests/integration/map/.

- owned_map: a GameMap row created the same way POST .../create does (only
  name/creator_id set - everything else takes the model defaults: bbox
  columns at -1, total_weight 0, max_distance -1). Returns (game_map, owner).
- map_with_bounds: owned_map plus two Bound rows, attached directly through
  the ORM (the same shape api/map/edit/mapedit.py:map_add_bound persists),
  bypassing map_add_bound's Street View lookup so tests don't need any mock
  just to get bounds seeded. Returns (game_map, owner, [mapbound_a, mapbound_b]).
- editor_user: a second User granted MapEditor access on owned_map's map, at
  permission_level=2 - the "Permission 2" tier in
  app/api/map/edit/route.py, enough to edit bounds (tier 1) and
  name/description (tier 2), but not enough to delete the map (tier 3).
  Returns the User row (not the MapEditor row).

Only these three fixtures are shared - other tests in this directory use
local fixtures/helpers, so nothing else should be added here that they'd end
up implicitly depending on. Plain helper functions (not fixtures) used by
this domain's own test files also live below.
"""

import pytest

from models.db import db
from models.map import Bound, GameMap, MapBound, MapEditor
from tests.factories import make_user
from utils import float_equals


@pytest.fixture()
def owned_map(db_session):
    owner = make_user()
    game_map = GameMap(creator_id=owner.id, name=f"owned-map-{owner.id}")
    db.session.add(game_map)
    db.session.commit()
    return game_map, owner


def _attach_bound(game_map, s_lat, s_lng, e_lat, e_lng, weight):
    """Attach a Bound + MapBound to `game_map` directly via the ORM, mirroring
    the bbox/total_weight bookkeeping api/map/edit/mapedit.py:map_add_bound
    does for a bound it persists - without exercising that function's Street
    View lookup for a brand-new Bound."""
    bound = Bound(start_latitude=s_lat, start_longitude=s_lng, end_latitude=e_lat, end_longitude=e_lng)
    db.session.add(bound)
    db.session.flush()

    if float_equals(game_map.max_distance, -1):
        game_map.start_latitude = s_lat
        game_map.start_longitude = s_lng
        game_map.end_latitude = e_lat
        game_map.end_longitude = e_lng
        game_map.max_distance = 1
    else:
        game_map.start_latitude = min(game_map.start_latitude, s_lat)
        game_map.start_longitude = min(game_map.start_longitude, s_lng)
        game_map.end_latitude = max(game_map.end_latitude, e_lat)
        game_map.end_longitude = max(game_map.end_longitude, e_lng)

    mapbound = MapBound(bound_id=bound.id, map_id=game_map.id, weight=weight)
    db.session.add(mapbound)
    game_map.total_weight += weight
    db.session.commit()
    return mapbound


@pytest.fixture()
def map_with_bounds(owned_map):
    game_map, owner = owned_map
    bounds = [
        _attach_bound(game_map, 10.0, 20.0, 10.0, 20.0, weight=3),
        _attach_bound(game_map, 30.0, 40.0, 31.0, 41.0, weight=5),
    ]
    return game_map, owner, bounds


@pytest.fixture()
def editor_user(owned_map):
    game_map, _owner = owned_map
    editor = make_user()
    db.session.add(MapEditor(map_id=game_map.id, user_id=editor.id, permission_level=2))
    db.session.commit()
    return editor


def grant_editor(game_map, user, permission_level):
    """Local helper (not a fixture): grant `user` MapEditor access on
    `game_map` at an arbitrary `permission_level`, for tests that need a tier
    other than editor_user's fixed level=2 (e.g. a level-1 "bounds only"
    editor, or exercising editor/add's own permission math)."""
    editor = MapEditor(map_id=game_map.id, user_id=user.id, permission_level=permission_level)
    db.session.add(editor)
    db.session.commit()
    return editor


@pytest.fixture()
def mapedit_street_view_mock(monkeypatch, db_session):
    """Patch `api.map.edit.mapedit.check_multiple_street_views` - NOT the
    root conftest's `street_view_mock`, which patches
    `api.location.generate.check_multiple_street_views`. That works for code
    that calls it as `generate_module.check_multiple_street_views(...)` (like
    `api.location.generate.generate_location` itself), but
    `api/api/map/edit/mapedit.py` does `from api.location.generate import
    check_multiple_street_views` at import time - a separate name binding in
    mapedit's own module namespace - so patching the origin module's
    attribute never reaches map_add_bound's call site. This fixture patches
    the right name for bound/add and bound/add/all. Same deterministic
    behavior as street_view_mock: returns a real SVLocation at the bound's
    start corner."""
    import api.map.edit.mapedit as mapedit_module
    from models.location import SVLocation

    async def fake_check_multiple_street_views(bound, num_checks=100):
        latitude = bound.start_latitude
        longitude = bound.start_longitude
        existing = SVLocation.query.filter_by(latitude=latitude, longitude=longitude).first()
        if existing:
            return existing
        location = SVLocation(latitude=latitude, longitude=longitude)
        db.session.add(location)
        db.session.commit()
        return location

    monkeypatch.setattr(mapedit_module, "check_multiple_street_views", fake_check_multiple_street_views)
    return fake_check_multiple_street_views
