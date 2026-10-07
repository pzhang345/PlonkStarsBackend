"""Integration tests for the JWT auth mechanism in api/account/auth.py and
the login_required decorator, exercised both directly and through real
routes.

Route inventory used here (found by grepping app/ for `login_required`):
  * GET /api/account/user       -> @login_required()               (no demo)
  * GET /api/cosmetics/all      -> @login_required(allow_demo=True) (demo ok)
"""

import json
from datetime import datetime, timedelta

import jwt
import pytest
import pytz
from jwt.utils import base64url_encode

from api.account.auth import JWT_SECRET_KEY, generate_token, get_user_from_token
from models.db import db
from tests.factories import make_user
from tests.helpers import assert_json_error, auth_header, demo_header

pytestmark = pytest.mark.integration


# Default to the key auth.py actually verifies with (bound from the base
# Config at import time, not TestConfig), so the expired-token tests differ
# from a valid token only in `exp`.
def _forge_token(secret=JWT_SECRET_KEY, exp_delta=timedelta(days=30), sub=None, username="whoever"):
    payload = {
        "sub": sub,
        "name": username,
        "exp": datetime.now(tz=pytz.utc) + exp_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# generate_token / get_user_from_token, exercised directly
# ---------------------------------------------------------------------------

def test_generate_token_round_trips_to_same_user(db_session):
    user = make_user()

    token = generate_token(user)
    resolved = get_user_from_token(token)

    assert resolved is not None
    assert resolved.id == user.id
    assert resolved.username == user.username


def test_bearer_prefix_works_identically_to_bare_token(db_session):
    user = make_user()
    token = generate_token(user)

    resolved_bare = get_user_from_token(token)
    resolved_bearer = get_user_from_token(f"Bearer {token}")

    assert resolved_bare is not None
    assert resolved_bearer is not None
    assert resolved_bare.id == resolved_bearer.id == user.id


def test_expired_token_is_rejected(db_session):
    user = make_user()
    valid_token = _forge_token(sub=str(user.id), username=user.username)
    expired_token = _forge_token(sub=str(user.id), username=user.username, exp_delta=timedelta(days=-1))

    # Control: the same forged token minus the past `exp` is accepted, so the
    # rejection below is down to expiry, not the signature.
    assert get_user_from_token(valid_token).id == user.id
    assert get_user_from_token(expired_token) is None


def test_token_signed_with_wrong_secret_is_rejected(db_session):
    user = make_user()
    bad_token = _forge_token(secret="totally-wrong-secret", sub=str(user.id), username=user.username)

    assert get_user_from_token(bad_token) is None


def test_structurally_malformed_token_is_rejected(db_session):
    assert get_user_from_token("this-is-not-a-jwt-at-all") is None


def test_empty_token_string_is_rejected(db_session):
    assert get_user_from_token("") is None


def test_missing_token_is_rejected(db_session):
    assert get_user_from_token(None) is None


def test_token_for_deleted_user_is_rejected_not_crashed(db_session):
    user = make_user()
    token = generate_token(user)

    db.session.delete(user)
    db.session.commit()

    # Must not raise - the user id in `sub` no longer resolves to a row.
    assert get_user_from_token(token) is None


# ---------------------------------------------------------------------------
# login_required, exercised end-to-end through real routes
# ---------------------------------------------------------------------------

def test_missing_authorization_header_is_rejected(client):
    response = client.get("/api/account/user")

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_empty_authorization_header_is_rejected(client):
    response = client.get("/api/account/user", headers={"Authorization": ""})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_malformed_authorization_header_is_rejected(client):
    response = client.get("/api/account/user", headers={"Authorization": "not.a.valid.jwt"})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_valid_token_is_accepted_on_protected_route(client):
    user = make_user(username="auth_route_user")

    response = client.get("/api/account/user", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"user": "auth_route_user"}


def test_demo_token_rejected_on_route_without_allow_demo(client):
    # /api/account/user is decorated @login_required() with no allow_demo,
    # so the literal "demo" token must be refused even before any DB lookup.
    response = client.get("/api/account/user", headers=demo_header())

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_demo_token_accepted_on_route_with_allow_demo(client):
    # A user literally named "demo" is required for the allow_demo path -
    # login_required looks it up by that exact username.
    make_user(username="demo")

    response = client.get("/api/cosmetics/all", headers=demo_header())

    assert response.status_code == 200
    body = response.get_json()
    assert set(body.keys()) == {
        "owned_faces", "owned_bodies", "owned_hats",
        "unowned_faces", "unowned_bodies", "unowned_hats",
    }
    assert body["owned_faces"] == []


def test_demo_token_without_demo_user_present(client):
    # No "demo" user exists in this test's transaction. login_required still
    # matches the "demo" literal and (since allow_demo=True) passes user=None
    # straight into the view. get_all_maps/get_cosmetic_ownership then use
    # `user.id` unconditionally further down.
    #
    # BUG: this is an unhandled-crash path, not a clean 403/404. Documenting
    # actual behavior rather than fixing app code.
    with pytest.raises(AttributeError):
        client.get("/api/cosmetics/all", headers=demo_header())


# ---------------------------------------------------------------------------
# Tampered token (payload segment swapped, original signature kept)
# ---------------------------------------------------------------------------

def _tamper_sub(token, new_sub):
    """Take a validly-signed JWT and swap only its payload segment for one
    base64url-encoding a different `sub`, keeping the original header and
    signature segments untouched. Simulates an attacker editing the payload
    of a token they intercepted without knowing the signing secret."""
    header_seg, _payload_seg, signature_seg = token.split(".")
    new_payload_seg = base64url_encode(json.dumps({"sub": new_sub, "name": "whoever"}).encode()).decode()
    return f"{header_seg}.{new_payload_seg}.{signature_seg}"


def test_tampered_payload_is_rejected_directly(db_session):
    user_a = make_user()
    user_b = make_user()
    token = generate_token(user_a)

    tampered = _tamper_sub(token, str(user_b.id))

    assert get_user_from_token(tampered) is None


def test_tampered_payload_is_rejected_via_route(client):
    user_a = make_user()
    user_b = make_user()
    token = generate_token(user_a)

    tampered = _tamper_sub(token, str(user_b.id))

    response = client.get("/api/account/user", headers={"Authorization": tampered})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# alg: none (unsigned) token
# ---------------------------------------------------------------------------

def test_alg_none_unsigned_token_is_rejected_directly(db_session):
    user = make_user()
    unsigned = jwt.encode({"sub": str(user.id), "name": user.username}, None, algorithm="none")

    assert get_user_from_token(unsigned) is None


def test_alg_none_unsigned_token_is_rejected_via_route(client):
    user = make_user()
    unsigned = jwt.encode({"sub": str(user.id), "name": user.username}, None, algorithm="none")

    response = client.get("/api/account/user", headers={"Authorization": unsigned})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# Route-level (HTTP 403) versions of expired / wrong-secret / deleted-user
# ---------------------------------------------------------------------------

def test_expired_token_is_rejected_via_route(client):
    user = make_user()
    expired_token = _forge_token(sub=str(user.id), username=user.username, exp_delta=timedelta(days=-1))

    response = client.get("/api/account/user", headers={"Authorization": expired_token})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_token_signed_with_wrong_secret_is_rejected_via_route(client):
    user = make_user()
    bad_token = _forge_token(secret="totally-wrong-secret", sub=str(user.id), username=user.username)

    response = client.get("/api/account/user", headers={"Authorization": bad_token})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_token_for_deleted_user_is_rejected_via_route(client):
    user = make_user()
    token = generate_token(user)

    db.session.delete(user)
    db.session.commit()

    response = client.get("/api/account/user", headers={"Authorization": token})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# The "demo" token can't reach routes that aren't allow_demo=True
#
# Built by grepping app/api for `@login_required()` (no allow_demo=True):
# one route per blueprint that has at least one such route. Two blueprints
# in the requested coverage list have none at all - `game` (every route
# under app/api/game/routes.py is allow_demo=True) and `feedback`
# (app/api/feedback/routes.py:9 has no login_required decorator whatsoever,
# auth there is optional/manual) - so they're not represented below.
# Path params are filled with dummy values; the decorator rejects the
# request before the view (and therefore any real lookup) ever runs.
# ---------------------------------------------------------------------------

NON_DEMO_LOGIN_REQUIRED_ROUTES = [
    ("GET", "/api/account/profile"),  # app/api/account/routes.py:73-74
    ("GET", "/api/session/info?id=dummy"),  # app/api/session/routes.py:15-16
    ("POST", "/api/party/create"),  # app/api/party/routes.py:25-26
    ("GET", "/api/party/teams?code=dummy"),  # app/api/party/teams/routes.py:14-15
    ("GET", "/api/party/rules?code=dummy"),  # app/api/party/rules/routes.py:14-15
    ("POST", "/api/party/game/start"),  # app/api/party/game/routes.py:15-16
    ("GET", "/api/party/users?code=dummy"),  # app/api/party/users/routes.py:12-13
    ("GET", "/api/map/edit?id=dummy"),  # app/api/map/edit/route.py:12-14
    ("PUT", "/api/cosmetics/customize"),  # app/api/cosmetics/routes.py:13-14
    ("POST", "/api/cosmetics/crates/buy"),  # app/api/cosmetics/crates/routes.py:32-33
    ("POST", "/api/admin/usercosmetics/initialize"),  # app/api/admin/routes.py:17-18
]


@pytest.mark.parametrize("method, path", NON_DEMO_LOGIN_REQUIRED_ROUTES)
def test_demo_token_cannot_reach_non_demo_routes(client, method, path):
    # A real "demo" user exists so the rejection is meaningful (not an
    # incidental failure to find the user) - but login_required() rejects
    # the literal "demo" token before it ever looks the user up, for any
    # route not decorated with allow_demo=True.
    make_user(username="demo")

    response = client.open(path, method=method, headers=demo_header())

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# Complementary sanity check: demo IS accepted on an allow_demo=True route
# other than /api/cosmetics/all
# ---------------------------------------------------------------------------

def test_demo_token_accepted_on_map_bounds(client):
    # GET /api/map/bounds (app/api/map/routes.py:217-218) is allow_demo=True.
    # /bounds needs no setup beyond a "demo" user: with no
    # `id` query param it takes the clean early-return 400 branch, which
    # only proves the auth layer let it through - it never yields the 403
    # `{"error": "login required"}` a rejected demo token would.
    make_user(username="demo")

    response = client.get("/api/map/bounds", headers=demo_header())

    assert response.status_code == 400
    assert response.get_json() == {"error": "provided: id"}
