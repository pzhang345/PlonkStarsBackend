"""Map editing routes: create, bounds, name, description, delete, editors.

Scope:
- Edit routes: create, bound/add, bound/add/all, bound/remove(/all),
  bound/reweight, name, description, delete, and editor add/remove.
  Validation rejects inverted or out-of-range bounds, zero or negative
  weights, and blank names - where the app actually validates them; where it
  doesn't, that's pinned as a bug (see the `..._documents_bug` tests below).

Two real bugs found while writing this file (also see tests/bugs.md):
- `POST bound/reweight` always crashes with TypeError, for any caller with
  enough permission to reach it: it calls
  `api.map.edit.mapedit.get_bound(data)` with only one argument, but
  `get_bound(data, map)` requires two. Route code also imports and calls
  `bound_recalculate(map, s_lat, s_lng, e_lat, e_lng, weight)` (a 6-arg call)
  when the function it presumably meant to reach for reweighting is
  `mapedit.reweight_bound(map, s_lat, s_lng, e_lat, e_lng, weight)` - which is
  never imported into route.py at all. So the endpoint is unreachable end to
  end regardless of payload.
- `POST /name` never validates `data.get("name")`: a missing name sets
  `map.name = None`, which crashes on commit (NOT NULL), and a blank string
  is silently accepted (unlike `POST /create`, which does reject a falsy
  name).
"""

import pytest

from models.db import db
from models.map import Bound, GameMap, MapBound, MapEditor
from tests.factories import make_user
from tests.helpers import assert_json_error, auth_header

pytestmark = pytest.mark.integration

BASE = "/api/map/edit"
CREATE_URL = f"{BASE}/create"
BOUND_ADD_URL = f"{BASE}/bound/add"
BOUND_ADD_ALL_URL = f"{BASE}/bound/add/all"
BOUND_REMOVE_URL = f"{BASE}/bound/remove"
BOUND_REMOVE_ALL_URL = f"{BASE}/bound/remove/all"
BOUND_REWEIGHT_URL = f"{BASE}/bound/reweight"
NAME_URL = f"{BASE}/name"
DESCRIPTION_URL = f"{BASE}/description"
DELETE_URL = f"{BASE}/delete"
EDITOR_ADD_URL = f"{BASE}/editor/add"
EDITOR_REMOVE_URL = f"{BASE}/editor/remove"
CAN_EDIT_URL = BASE  # GET "" under /edit


# ---------------------------------------------------------------------------
# GET  (can_edit_map)
# ---------------------------------------------------------------------------

def test_can_edit_reports_permission_level_for_the_owner(client, owned_map):
    game_map, owner = owned_map

    response = client.get(CAN_EDIT_URL, query_string={"id": game_map.uuid}, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json() == {"permission": 4}


def test_can_edit_reports_zero_for_an_unrelated_user(client, owned_map):
    game_map, _owner = owned_map
    stranger = make_user()

    response = client.get(CAN_EDIT_URL, query_string={"id": game_map.uuid}, headers=auth_header(stranger))

    assert response.status_code == 200
    assert response.get_json() == {"permission": 0}


def test_can_edit_requires_an_id_query_param(client, owned_map):
    _game_map, owner = owned_map

    response = client.get(CAN_EDIT_URL, headers=auth_header(owner))

    body = assert_json_error(response, 400)
    assert body == {"error": "provided: id"}


def test_can_edit_unknown_map_returns_404(client, owned_map):
    _game_map, owner = owned_map

    response = client.get(CAN_EDIT_URL, query_string={"id": "does-not-exist"}, headers=auth_header(owner))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /create
# ---------------------------------------------------------------------------

def test_create_map_creates_a_new_map_owned_by_the_caller(client):
    user = make_user()

    response = client.post(CREATE_URL, json={"name": "My New Map"}, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    game_map = GameMap.query.filter_by(uuid=body["id"]).first()
    assert game_map is not None
    assert game_map.name == "My New Map"
    assert game_map.creator_id == user.id


def test_create_map_without_name_returns_400(client):
    user = make_user()

    response = client.post(CREATE_URL, json={}, headers=auth_header(user))

    body = assert_json_error(response, 400)
    assert body == {"error": "provided: name"}


def test_create_map_with_blank_name_returns_400(client):
    user = make_user()

    response = client.post(CREATE_URL, json={"name": ""}, headers=auth_header(user))

    body = assert_json_error(response, 400)
    assert body == {"error": "provided: name"}


def test_create_map_unauthenticated_returns_403(client):
    response = client.post(CREATE_URL, json={"name": "Nope"})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_create_map_with_whitespace_only_name_documents_bug(client):
    # BUG: create_map only checks `if not name`, which a whitespace-only
    # string passes (it's truthy), unlike an empty string. The map is
    # created with a name that's effectively blank.
    user = make_user()

    response = client.post(CREATE_URL, json={"name": "   "}, headers=auth_header(user))

    assert response.status_code == 200
    game_map = GameMap.query.filter_by(uuid=response.get_json()["id"]).first()
    assert game_map.name == "   "


# ---------------------------------------------------------------------------
# POST bound/add
# ---------------------------------------------------------------------------

def test_bound_add_adds_a_single_bound(client, street_view_mock, owned_map):
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "start": {"lat": 50.0, "lng": 60.0},
        "end": {"lat": 51.0, "lng": 61.0},
        "weight": 7,
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    body = response.get_json()
    assert body["weight"] == 7
    assert body["start"] == {"lat": 50.0, "lng": 60.0}
    assert body["end"] == {"lat": 51.0, "lng": 61.0}
    assert MapBound.query.filter_by(id=body["id"], map_id=game_map.id).first() is not None


def test_bound_add_rejects_duplicate_bound(client, street_view_mock, map_with_bounds):
    game_map, owner, bounds = map_with_bounds
    existing = Bound.query.filter_by(id=bounds[0].bound_id).first()
    payload = {
        "id": game_map.uuid,
        "start": {"lat": existing.start_latitude, "lng": existing.start_longitude},
        "end": {"lat": existing.end_latitude, "lng": existing.end_longitude},
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(owner))

    body = assert_json_error(response, 400)
    assert body == {"error": "Bound already added"}


def test_bound_add_rejects_inverted_lat_lng_range(client, owned_map):
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "start": {"lat": 10.0, "lng": 10.0},
        "end": {"lat": 5.0, "lng": 5.0},
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(owner))

    assert_json_error(response, 400)
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 0


def test_bound_add_rejects_out_of_range_coordinates(client, owned_map):
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "start": {"lat": 10.0, "lng": 10.0},
        "end": {"lat": 200.0, "lng": 10.0},
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(owner))

    assert_json_error(response, 400)
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 0


def test_bound_add_unauthorized_user_returns_403(client, owned_map):
    game_map, _owner = owned_map
    stranger = make_user()
    payload = {
        "id": game_map.uuid,
        "start": {"lat": 10.0, "lng": 10.0},
        "end": {"lat": 11.0, "lng": 11.0},
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(stranger))

    body = assert_json_error(response, 403)
    assert body == {"error": "Don't have access to the map"}


@pytest.mark.parametrize("weight", [0, -5])
def test_bound_add_documents_zero_and_negative_weight_are_not_rejected_bug(client, street_view_mock, owned_map, weight):
    # BUG: bound/add does `weight = max(1, weight) if weight else <default>`.
    # A negative weight is truthy, so it's silently clamped to 1 instead of
    # being rejected; a zero weight is falsy, so it silently falls back to
    # the computed default instead of being rejected either. Zero/negative
    # weights should be rejected with 400 - they aren't.
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "start": {"lat": 50.0, "lng": 60.0},
        "end": {"lat": 51.0, "lng": 61.0},
        "weight": weight,
    }

    response = client.post(BOUND_ADD_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json()["weight"] > 0


# ---------------------------------------------------------------------------
# POST bound/add/all
# ---------------------------------------------------------------------------

def test_bound_add_all_adds_multiple_bounds(client, street_view_mock, owned_map):
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "bounds": [
            {"start": {"lat": 1.0, "lng": 1.0}, "end": {"lat": 2.0, "lng": 2.0}},
            {"start": {"lat": 3.0, "lng": 3.0}, "end": {"lat": 4.0, "lng": 4.0}},
        ],
    }

    response = client.post(BOUND_ADD_ALL_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 2
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 2


def test_bound_add_all_silently_skips_invalid_entries(client, street_view_mock, owned_map):
    """A batch with one invalid (inverted) bound still succeeds overall - the
    route wraps each bound in its own try/except and only reports the valid
    ones, dropping the invalid one with no error surfaced for it."""
    game_map, owner = owned_map
    payload = {
        "id": game_map.uuid,
        "bounds": [
            {"start": {"lat": 1.0, "lng": 1.0}, "end": {"lat": 2.0, "lng": 2.0}},
            {"start": {"lat": 10.0, "lng": 10.0}, "end": {"lat": 5.0, "lng": 5.0}},  # inverted
        ],
    }

    response = client.post(BOUND_ADD_ALL_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 1


def test_bound_add_all_requires_a_bounds_list(client, owned_map):
    game_map, owner = owned_map

    response = client.post(BOUND_ADD_ALL_URL, json={"id": game_map.uuid}, headers=auth_header(owner))

    body = assert_json_error(response, 400)
    assert body == {"error": "please provided these arguments:bounds"}


# ---------------------------------------------------------------------------
# DELETE bound/remove
# ---------------------------------------------------------------------------

def test_bound_remove_removes_a_single_bound(client, map_with_bounds):
    game_map, owner, bounds = map_with_bounds
    target = bounds[0]

    response = client.delete(BOUND_REMOVE_URL, json={"id": game_map.uuid, "b_id": target.id}, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json() == {"id": target.id}
    assert MapBound.query.filter_by(id=target.id).first() is None


def test_bound_remove_unknown_bound_returns_400(client, owned_map):
    game_map, owner = owned_map

    response = client.delete(BOUND_REMOVE_URL, json={"id": game_map.uuid, "b_id": 999999}, headers=auth_header(owner))

    assert_json_error(response, 400)


def test_bound_remove_bound_belonging_to_another_map_returns_400(client, map_with_bounds):
    """`get_bound` looks a MapBound up by `b_id` alone (no map_id filter), but
    `map_remove_bound` then rejects it because `mapbound.map_id != map.id`."""
    game_map, owner, bounds = map_with_bounds
    other_owner = make_user()
    other_map = GameMap(creator_id=other_owner.id, name=f"other-map-{other_owner.id}")
    db.session.add(other_map)
    db.session.commit()

    response = client.delete(
        BOUND_REMOVE_URL, json={"id": other_map.uuid, "b_id": bounds[0].id}, headers=auth_header(other_owner)
    )

    assert_json_error(response, 400)
    assert MapBound.query.filter_by(id=bounds[0].id).first() is not None


# ---------------------------------------------------------------------------
# DELETE bound/remove/all
# ---------------------------------------------------------------------------

def test_bound_remove_all_removes_every_bound(client, map_with_bounds):
    game_map, owner, bounds = map_with_bounds
    payload = {"id": game_map.uuid, "bounds": [{"b_id": b.id} for b in bounds]}

    response = client.delete(BOUND_REMOVE_ALL_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    assert sorted(response.get_json()) == sorted(b.id for b in bounds)
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 0


def test_bound_remove_all_silently_skips_invalid_entries(client, map_with_bounds):
    game_map, owner, bounds = map_with_bounds
    payload = {"id": game_map.uuid, "bounds": [{"b_id": bounds[0].id}, {"b_id": 999999}]}

    response = client.delete(BOUND_REMOVE_ALL_URL, json=payload, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json() == [bounds[0].id]
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 1


def test_bound_remove_all_missing_bounds_field_returns_400(client, owned_map):
    game_map, owner = owned_map

    response = client.delete(BOUND_REMOVE_ALL_URL, json={"id": game_map.uuid}, headers=auth_header(owner))

    assert_json_error(response, 400)


# ---------------------------------------------------------------------------
# POST bound/reweight - always crashes (see module docstring / tests/bugs.md)
# ---------------------------------------------------------------------------

def test_bound_reweight_route_crashes_documents_bug(client, map_with_bounds):
    # BUG: route.reweight_bound calls mapedit.get_bound(data) with only one
    # argument, but get_bound(data, map) requires two - TypeError on every
    # call that gets past the permission check, regardless of payload.
    game_map, owner, bounds = map_with_bounds
    payload = {"id": game_map.uuid, "b_id": bounds[0].id, "weight": 9}

    with pytest.raises(TypeError):
        client.post(BOUND_REWEIGHT_URL, json=payload, headers=auth_header(owner))


def test_bound_reweight_still_403s_a_caller_without_access(client, map_with_bounds):
    """The crash above only happens after the permission check, so a caller
    with no access at all still gets a normal 403, not the crash."""
    game_map, _owner, bounds = map_with_bounds
    stranger = make_user()
    payload = {"id": game_map.uuid, "b_id": bounds[0].id, "weight": 9}

    response = client.post(BOUND_REWEIGHT_URL, json=payload, headers=auth_header(stranger))

    body = assert_json_error(response, 403)
    assert body == {"error": "Don't have access to the map"}


# ---------------------------------------------------------------------------
# POST /name
# ---------------------------------------------------------------------------

def test_name_updates_the_map_name(client, owned_map):
    game_map, owner = owned_map

    response = client.post(NAME_URL, json={"id": game_map.uuid, "name": "Renamed Map"}, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json() == {"message": "name updated"}
    assert GameMap.query.filter_by(id=game_map.id).first().name == "Renamed Map"


def test_name_accepts_a_blank_name_documents_bug(client, owned_map):
    # BUG: edit_name does `map.name = data.get("name")` with no validation at
    # all - unlike POST /create, which rejects a falsy name. A blank string
    # is happily persisted.
    game_map, owner = owned_map

    response = client.post(NAME_URL, json={"id": game_map.uuid, "name": ""}, headers=auth_header(owner))

    assert response.status_code == 200
    assert GameMap.query.filter_by(id=game_map.id).first().name == ""


def test_name_missing_field_crashes_documents_bug(client, owned_map):
    # BUG: with no "name" in the body, map.name is set to None, and the
    # `name` column is NOT NULL - commit() raises IntegrityError.
    from sqlalchemy.exc import IntegrityError

    game_map, owner = owned_map

    with pytest.raises(IntegrityError):
        client.post(NAME_URL, json={"id": game_map.uuid}, headers=auth_header(owner))


def test_name_unauthorized_user_returns_403(client, owned_map):
    game_map, _owner = owned_map
    stranger = make_user()

    response = client.post(NAME_URL, json={"id": game_map.uuid, "name": "Hi"}, headers=auth_header(stranger))

    body = assert_json_error(response, 403)
    assert body == {"error": "Don't have access to the map"}


# ---------------------------------------------------------------------------
# POST /description
# ---------------------------------------------------------------------------

def test_description_updates_the_map_description(client, owned_map):
    game_map, owner = owned_map

    response = client.post(
        DESCRIPTION_URL, json={"id": game_map.uuid, "description": "A lovely map"}, headers=auth_header(owner)
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "description updated"}
    assert GameMap.query.filter_by(id=game_map.id).first().description == "A lovely map"


def test_description_accepts_a_missing_description(client, owned_map):
    """Unlike /name, the description column allows NULL, so a missing field
    is handled fine (not a bug)."""
    game_map, owner = owned_map

    response = client.post(DESCRIPTION_URL, json={"id": game_map.uuid}, headers=auth_header(owner))

    assert response.status_code == 200
    assert GameMap.query.filter_by(id=game_map.id).first().description is None


# ---------------------------------------------------------------------------
# DELETE /delete
# ---------------------------------------------------------------------------

def test_delete_removes_the_map_and_its_bounds(client, map_with_bounds):
    game_map, owner, bounds = map_with_bounds
    bound_ids = [b.bound_id for b in bounds]

    response = client.delete(DELETE_URL, json={"id": game_map.uuid}, headers=auth_header(owner))

    assert response.status_code == 200
    assert response.get_json() == {"message": "map deleted"}
    assert GameMap.query.filter_by(id=game_map.id).first() is None
    assert MapBound.query.filter_by(map_id=game_map.id).count() == 0
    assert Bound.query.filter(Bound.id.in_(bound_ids)).count() == 0


def test_delete_unauthorized_user_returns_403(client, owned_map):
    game_map, _owner = owned_map
    stranger = make_user()

    response = client.delete(DELETE_URL, json={"id": game_map.uuid}, headers=auth_header(stranger))

    body = assert_json_error(response, 403)
    assert body == {"error": "Don't have access to the map"}
    assert GameMap.query.filter_by(id=game_map.id).first() is not None


# ---------------------------------------------------------------------------
# POST /editor/add
# ---------------------------------------------------------------------------

def test_editor_add_grants_editor_access(client, owned_map):
    game_map, owner = owned_map
    target = make_user()

    response = client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": target.username, "permission": 1},
        headers=auth_header(owner),
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "editor added"}
    editor = MapEditor.query.filter_by(map_id=game_map.id, user_id=target.id).first()
    assert editor is not None
    assert editor.permission_level == 1


def test_editor_add_upserts_an_existing_editors_permission(client, owned_map):
    game_map, owner = owned_map
    target = make_user()

    client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": target.username, "permission": 1},
        headers=auth_header(owner),
    )
    response = client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": target.username, "permission": 2},
        headers=auth_header(owner),
    )

    assert response.status_code == 200
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=target.id).count() == 1
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=target.id).first().permission_level == 2


def test_editor_add_unknown_username_returns_400(client, owned_map):
    game_map, owner = owned_map

    response = client.post(
        EDITOR_ADD_URL, json={"id": game_map.uuid, "username": "nobody", "permission": 1}, headers=auth_header(owner)
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "provided valid username"}


def test_editor_add_cannot_target_self(client, owned_map):
    game_map, owner = owned_map

    response = client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": owner.username, "permission": 1},
        headers=auth_header(owner),
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "provided valid username"}


def test_editor_add_rejects_granting_permission_at_or_above_the_callers_own(client, owned_map):
    game_map, owner = owned_map
    target = make_user()

    response = client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": target.username, "permission": 4},
        headers=auth_header(owner),
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "Not high enough permission"}
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=target.id).first() is None


def test_editor_add_missing_permission_field_crashes_documents_bug(client, owned_map):
    # BUG: `if can_edit(user,map) <= permission:` with `permission = data.get
    # ("permission")` defaulting to None raises TypeError - int <= NoneType
    # is not supported.
    game_map, owner = owned_map
    target = make_user()

    with pytest.raises(TypeError):
        client.post(EDITOR_ADD_URL, json={"id": game_map.uuid, "username": target.username}, headers=auth_header(owner))


def test_editor_add_unauthorized_user_returns_403(client, owned_map):
    game_map, _owner = owned_map
    stranger = make_user()
    target = make_user()

    response = client.post(
        EDITOR_ADD_URL,
        json={"id": game_map.uuid, "username": target.username, "permission": 1},
        headers=auth_header(stranger),
    )

    body = assert_json_error(response, 403)
    assert body == {"error": "Don't have access to the map"}


# ---------------------------------------------------------------------------
# DELETE /editor/remove
# ---------------------------------------------------------------------------

def test_editor_remove_removes_editor_access(client, owned_map, editor_user):
    game_map, owner = owned_map

    response = client.delete(
        EDITOR_REMOVE_URL, json={"id": game_map.uuid, "username": editor_user.username}, headers=auth_header(owner)
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "editor deleted"}
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=editor_user.id).first() is None


def test_editor_remove_unknown_username_returns_400(client, owned_map):
    game_map, owner = owned_map

    response = client.delete(EDITOR_REMOVE_URL, json={"id": game_map.uuid, "username": "nobody"}, headers=auth_header(owner))

    body = assert_json_error(response, 400)
    assert body == {"error": "provided valid username"}


def test_editor_remove_user_who_is_not_an_editor_returns_400(client, owned_map):
    game_map, owner = owned_map
    not_an_editor = make_user()

    response = client.delete(
        EDITOR_REMOVE_URL, json={"id": game_map.uuid, "username": not_an_editor.username}, headers=auth_header(owner)
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "provided valid map editor"}


def test_editor_remove_requires_permission_higher_than_the_targets(client, owned_map, editor_user):
    """editor_user is permission_level=2. Another editor at the same level
    can't remove them (can_edit(caller) <= editor.permission_level)."""
    game_map, _owner = owned_map
    peer = make_user()
    db.session.add(MapEditor(map_id=game_map.id, user_id=peer.id, permission_level=2))
    db.session.commit()

    response = client.delete(
        EDITOR_REMOVE_URL, json={"id": game_map.uuid, "username": editor_user.username}, headers=auth_header(peer)
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "Not high enough permission"}
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=editor_user.id).first() is not None
