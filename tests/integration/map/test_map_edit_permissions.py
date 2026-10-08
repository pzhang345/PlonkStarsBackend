"""Map edit permission matrix: owner vs editor vs stranger vs demo vs anon.

Scope:
- Permissions matrix (parametrized): {owner, editor, stranger, demo, anon} x
  every edit route. Only the owner can delete the map. Editor management
  (editor/add, editor/remove) turns out not to be owner-exclusive - see
  test_editor_with_sufficient_permission_can_manage_lower_editors below.

Thresholds enforced by app/api/map/edit/route.py (`can_edit(user, map)`
returns 4 for the owner/an admin, else a MapEditor row's permission_level,
else 0):
- "Permission 1": bound/add, bound/add/all, bound/remove, bound/remove/all,
  bound/reweight - need can_edit >= 1.
- "Permission 2": name, description - need can_edit >= 2.
- "Permission 3": delete - need can_edit >= 3.

`editor_user` (tests/integration/map/conftest.py) is a permission_level=2
editor, so it clears tiers 1 and 2 but not tier 3 - exactly the "editor can
edit bounds/name/description but not delete" split.

bound/reweight is a special case: it crashes with TypeError for *any* caller
who clears its permission check (see tests/bugs.md and
test_map_edit_routes.py::test_bound_reweight_route_crashes_documents_bug), so
"has access" for that one route means "raises TypeError", not "200".
"""

import pytest

from models.db import db
from models.map import MapEditor
from tests.factories import make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration

BASE = "/api/map/edit"


def _new_bound_payload(map_uuid, lat, lng):
    return {
        "id": map_uuid,
        "start": {"lat": lat, "lng": lng},
        "end": {"lat": lat + 1.0, "lng": lng + 1.0},
    }


def _actions(game_map, bounds):
    """Build the list of (name, method, path, min_permission, is_crash_route,
    payload) for every edit route gated by can_edit, using `game_map`/
    `bounds` (from the map_with_bounds fixture) to build valid payloads."""
    return [
        ("bound_add", "POST", "bound/add", 1, False, _new_bound_payload(game_map.uuid, 50.0, 60.0)),
        (
            "bound_add_all",
            "POST",
            "bound/add/all",
            1,
            False,
            {"id": game_map.uuid, "bounds": [{"start": {"lat": 51.0, "lng": 61.0}, "end": {"lat": 52.0, "lng": 62.0}}]},
        ),
        ("bound_remove", "DELETE", "bound/remove", 1, False, {"id": game_map.uuid, "b_id": bounds[0].id}),
        (
            "bound_remove_all",
            "DELETE",
            "bound/remove/all",
            1,
            False,
            {"id": game_map.uuid, "bounds": [{"b_id": bounds[1].id}]},
        ),
        ("bound_reweight", "POST", "bound/reweight", 1, True, {"id": game_map.uuid, "b_id": bounds[0].id, "weight": 9}),
        ("name", "POST", "name", 2, False, {"id": game_map.uuid, "name": "Renamed"}),
        ("description", "POST", "description", 2, False, {"id": game_map.uuid, "description": "New description"}),
        ("delete", "DELETE", "delete", 3, False, {"id": game_map.uuid}),
    ]


def _call(client, method, path, payload, headers):
    return client.open(f"{BASE}/{path}", method=method, json=payload, headers=headers)


ACTION_NAMES = ["bound_add", "bound_add_all", "bound_remove", "bound_remove_all", "bound_reweight", "name", "description", "delete"]


def _run_and_assert(client, actor_level, headers, action):
    action_name, method, path, min_permission, is_crash, payload = action
    has_access = actor_level >= min_permission

    if has_access and is_crash:
        with pytest.raises(TypeError):
            _call(client, method, path, payload, headers)
        return

    response = _call(client, method, path, payload, headers)

    if not has_access:
        assert response.status_code == 403, f"{action_name}: expected 403, got {response.status_code}"
        assert response.get_json() == {"error": "Don't have access to the map"}, action_name
        return

    assert response.status_code == 200, f"{action_name}: expected 200, got {response.status_code}: {response.get_data(as_text=True)}"


@pytest.mark.parametrize("action_name", ACTION_NAMES)
def test_owner_can_use_every_edit_route(client, street_view_mock, map_with_bounds, action_name):
    game_map, owner, bounds = map_with_bounds
    action = next(a for a in _actions(game_map, bounds) if a[0] == action_name)

    _run_and_assert(client, actor_level=4, headers=auth_header(owner), action=action)


@pytest.mark.parametrize("action_name", ACTION_NAMES)
def test_editor_can_use_bound_and_metadata_edit_routes_but_not_delete(client, street_view_mock, map_with_bounds, editor_user, action_name):
    game_map, _owner, bounds = map_with_bounds
    action = next(a for a in _actions(game_map, bounds) if a[0] == action_name)

    _run_and_assert(client, actor_level=2, headers=auth_header(editor_user), action=action)


@pytest.mark.parametrize("action_name", ACTION_NAMES)
def test_stranger_is_rejected_from_every_edit_route(client, street_view_mock, map_with_bounds, action_name):
    game_map, _owner, bounds = map_with_bounds
    stranger = make_user()
    action = next(a for a in _actions(game_map, bounds) if a[0] == action_name)

    _run_and_assert(client, actor_level=0, headers=auth_header(stranger), action=action)


@pytest.mark.parametrize("action_name", ACTION_NAMES)
def test_demo_user_is_rejected_from_every_edit_route(client, map_with_bounds, action_name):
    """None of these routes are decorated with login_required(allow_demo=True),
    so the demo token is rejected before any map/permission lookup happens -
    no "demo" user needs to exist in the DB for this."""
    game_map, _owner, bounds = map_with_bounds
    action = next(a for a in _actions(game_map, bounds) if a[0] == action_name)
    _action_name, method, path, _min_permission, _is_crash, payload = action

    response = _call(client, method, path, payload, demo_header())

    assert response.status_code == 403
    assert response.get_json() == {"error": "login required"}


@pytest.mark.parametrize("action_name", ACTION_NAMES)
def test_anonymous_user_is_rejected_from_every_edit_route(client, map_with_bounds, action_name):
    game_map, _owner, bounds = map_with_bounds
    action = next(a for a in _actions(game_map, bounds) if a[0] == action_name)
    _action_name, method, path, _min_permission, _is_crash, payload = action

    response = _call(client, method, path, payload, None)

    assert response.status_code == 403
    assert response.get_json() == {"error": "login required"}


# ---------------------------------------------------------------------------
# Delete: explicitly owner-only
# ---------------------------------------------------------------------------

def test_only_owner_can_delete_the_map(client, map_with_bounds, editor_user):
    game_map, owner, _bounds = map_with_bounds
    stranger = make_user()

    for actor in (stranger, editor_user):
        response = client.delete(f"{BASE}/delete", json={"id": game_map.uuid}, headers=auth_header(actor))
        assert response.status_code == 403
        assert response.get_json() == {"error": "Don't have access to the map"}

    response = client.delete(f"{BASE}/delete", json={"id": game_map.uuid}, headers=auth_header(owner))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Editor management: gated by a *relative* permission check, not owner-only
# ---------------------------------------------------------------------------

def test_editor_add_requires_permission_strictly_higher_than_granted(client, owned_map, editor_user):
    """route.py's own comment ("Can add or remove people with lower
    permissions") documents this as intentional: editor/add checks
    `can_edit(caller) <= permission`, not "caller is the owner"."""
    game_map, _owner = owned_map
    stranger = make_user()
    target = make_user()

    # A stranger (permission 0) has no access at all.
    response = client.post(
        f"{BASE}/editor/add", json={"id": game_map.uuid, "username": target.username, "permission": 0}, headers=auth_header(stranger)
    )
    assert response.status_code == 403

    # editor_user (permission_level=2) can grant a *lower* permission than its own.
    response = client.post(
        f"{BASE}/editor/add", json={"id": game_map.uuid, "username": target.username, "permission": 1}, headers=auth_header(editor_user)
    )
    assert response.status_code == 200
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=target.id).first().permission_level == 1

    # ...but not a permission at or above its own.
    target2 = make_user()
    response = client.post(
        f"{BASE}/editor/add", json={"id": game_map.uuid, "username": target2.username, "permission": 2}, headers=auth_header(editor_user)
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "Not high enough permission"}


def test_editor_with_sufficient_permission_can_manage_lower_editors(client, owned_map):
    """Documents the app's actual (and apparently intentional, per route.py's
    comment on the editor/add and editor/remove routes) design: editor
    management is not restricted to the map's owner - any user whose
    can_edit() level is strictly higher than the target permission/editor can
    add or remove them. Note: editor management is not owner-exclusive, in
    contrast to map deletion."""
    game_map, owner = owned_map
    senior_editor = make_user()
    junior_target = make_user()
    db.session.add(MapEditor(map_id=game_map.id, user_id=senior_editor.id, permission_level=2))
    db.session.commit()

    add_response = client.post(
        f"{BASE}/editor/add",
        json={"id": game_map.uuid, "username": junior_target.username, "permission": 1},
        headers=auth_header(senior_editor),
    )
    assert add_response.status_code == 200
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=junior_target.id).first() is not None

    remove_response = client.delete(
        f"{BASE}/editor/remove",
        json={"id": game_map.uuid, "username": junior_target.username},
        headers=auth_header(senior_editor),
    )
    assert remove_response.status_code == 200
    assert MapEditor.query.filter_by(map_id=game_map.id, user_id=junior_target.id).first() is None
