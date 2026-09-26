"""Integration tests for every route in app/api/account/routes.py:
register, login, delete, user, profile, avatar, coins.

Response shapes (confirmed by reading app/api/account/routes.py):
  * POST /register  -> 200 {"message": "User registered successfully"}
                     -> 400 {"error": "Username already exists"}
  * POST /login      -> 200 {"message": "Login successful", "token": <jwt>}
                     -> 401 {"error": "Invalid credentials"}
  * DELETE /delete   -> 200 {"message": "Account deleted successfully"}
  * GET /user        -> 200 {"user": <username>}
  * GET /profile     -> 200 <User.to_json()> == {"username":..., "user_cosmetics": {...} | None}
                     -> 404 {"error": "User not found"}  (unknown ?username=)
  * GET /avatar      -> 200 <User.to_json()>            (no ?username= at all)
                     -> 200 [<User.to_json()>, ...]      (one or more ?username=, even a single one)
  * GET /coins       -> 200 {"coins": <int>}
"""

import pytest
from sqlalchemy.exc import IntegrityError

from api.account.auth import generate_token
from api.account.routes import bcrypt
from models.cosmetics import UserCoins, UserCosmetics
from models.db import db
from models.user import User
from tests.factories import make_user
from tests.helpers import assert_json_error, auth_header

pytestmark = pytest.mark.integration


def _give_coins_and_cosmetics(user, coins=0):
    """Local helper: attach UserCoins/UserCosmetics rows to a factory-made
    user, mirroring what the /register route does as a side effect.
    Candidate for promotion to tests/factories.py as make_user_coins /
    make_user_cosmetics if other test files need it."""
    row_coins = UserCoins(user_id=user.id, coins=coins)
    row_cosmetics = UserCosmetics(user_id=user.id)
    db.session.add_all([row_coins, row_cosmetics])
    db.session.commit()
    return row_coins, row_cosmetics


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------

def test_register_happy_path_creates_user_and_side_effect_rows(client):
    response = client.post(
        "/api/account/register",
        json={"username": "new_reg_user", "password": "correct-horse"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "User registered successfully"}

    user = User.query.filter_by(username="new_reg_user").first()
    assert user is not None
    assert user.is_admin is False

    # Password must be bcrypt-hashed, not stored as plaintext.
    assert user.password != "correct-horse"
    assert user.password.startswith("$2b$")
    assert bcrypt.check_password_hash(user.password, "correct-horse")

    # Side-effect rows the route is documented to create.
    coins = UserCoins.query.filter_by(user_id=user.id).first()
    cosmetics = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert coins is not None
    assert coins.coins == 0
    assert cosmetics is not None


def test_register_duplicate_username_is_rejected(client):
    make_user(username="dupe_user")

    response = client.post(
        "/api/account/register",
        json={"username": "dupe_user", "password": "whatever123"},
    )

    body = assert_json_error(response, 400)
    assert body == {"error": "Username already exists"}


def test_register_missing_password_crashes_instead_of_400(client):
    # BUG: there is no input validation on `password`. flask_bcrypt raises
    # ValueError("Password must be non-empty.") for both a missing and a
    # blank password, which (since TestConfig/TESTING propagates exceptions)
    # surfaces here as an unhandled ValueError instead of a clean 400. In
    # production this would be an unhandled 500. Documenting actual
    # behavior, not fixing app code.
    with pytest.raises(ValueError, match="Password must be non-empty"):
        client.post("/api/account/register", json={"username": "no_password_user"})

    assert User.query.filter_by(username="no_password_user").first() is None


def test_register_blank_password_crashes_instead_of_400(client):
    # Same underlying bug as above, triggered by an empty string rather than
    # a missing key.
    with pytest.raises(ValueError, match="Password must be non-empty"):
        client.post(
            "/api/account/register",
            json={"username": "blank_password_user", "password": ""},
        )

    assert User.query.filter_by(username="blank_password_user").first() is None


def test_register_missing_username_crashes_with_integrity_error(client, db_session):
    # BUG: there is no input validation on `username` either. A missing
    # username reaches the INSERT as NULL, which violates the NOT NULL
    # column constraint and raises an unhandled IntegrityError instead of a
    # clean 400 (production: unhandled 500). Documenting actual behavior.
    with pytest.raises(IntegrityError):
        client.post("/api/account/register", json={"password": "whatever123"})

    # The failed flush leaves the session needing a rollback before it can
    # be used again in this test.
    db_session.rollback()
    assert User.query.count() == 0


def test_register_blank_username_is_accepted(client):
    # BUG: an empty-string username passes the `if existing_user` duplicate
    # check (no row has username=="" yet) and the NOT NULL constraint (""
    # is not NULL), so registration silently succeeds with a blank
    # username. No validation rejects this. Documenting actual behavior.
    response = client.post(
        "/api/account/register",
        json={"username": "", "password": "whatever123"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "User registered successfully"}
    assert User.query.filter_by(username="").first() is not None


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------

def test_login_happy_path_token_is_usable(client):
    make_user(username="login_user", password="correct-horse")

    response = client.post(
        "/api/account/login",
        json={"username": "login_user", "password": "correct-horse"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["message"] == "Login successful"
    token = body["token"]
    assert token

    # Prove the token actually works against a protected route.
    authed = client.get("/api/account/user", headers={"Authorization": token})
    assert authed.status_code == 200
    assert authed.get_json() == {"user": "login_user"}


def test_login_wrong_password_is_rejected(client):
    make_user(username="wrongpw_user", password="correct-horse")

    response = client.post(
        "/api/account/login",
        json={"username": "wrongpw_user", "password": "incorrect-horse"},
    )

    body = assert_json_error(response, 401)
    assert body == {"error": "Invalid credentials"}


def test_login_nonexistent_username_is_rejected(client):
    response = client.post(
        "/api/account/login",
        json={"username": "no_such_user_at_all", "password": "whatever123"},
    )

    body = assert_json_error(response, 401)
    assert body == {"error": "Invalid credentials"}


# ---------------------------------------------------------------------------
# DELETE /delete
# ---------------------------------------------------------------------------

def test_delete_removes_user_and_cascades(client):
    user = make_user(username="to_be_deleted")
    user_id = user.id
    _give_coins_and_cosmetics(user)
    token = generate_token(user)

    response = client.delete("/api/account/delete", headers={"Authorization": token})

    assert response.status_code == 200
    assert response.get_json() == {"message": "Account deleted successfully"}

    assert User.query.filter_by(id=user_id).first() is None
    assert UserCoins.query.filter_by(user_id=user_id).first() is None
    assert UserCosmetics.query.filter_by(user_id=user_id).first() is None

    # The now-stale token must no longer authenticate anything.
    reused = client.get("/api/account/user", headers={"Authorization": token})
    body = assert_json_error(reused, 403)
    assert body == {"error": "login required"}


def test_delete_requires_auth(client):
    response = client.delete("/api/account/delete")
    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# GET /user
# ---------------------------------------------------------------------------

def test_get_user_returns_own_username(client):
    user = make_user(username="whoami_user")

    response = client.get("/api/account/user", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"user": "whoami_user"}


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

def test_profile_own(client):
    user = make_user(username="profile_self")

    response = client.get("/api/account/profile", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"username": "profile_self", "user_cosmetics": None}


def test_profile_other_user_via_query_param(client):
    caller = make_user(username="profile_caller")
    other = make_user(username="profile_other")

    response = client.get(
        "/api/account/profile?username=profile_other",
        headers=auth_header(caller),
    )

    assert response.status_code == 200
    assert response.get_json() == {"username": "profile_other", "user_cosmetics": None}


def test_profile_other_user_with_cosmetics(client):
    caller = make_user(username="profile_caller2")
    other = make_user(username="profile_other2")
    _, cosmetics = _give_coins_and_cosmetics(other)

    response = client.get(
        f"/api/account/profile?username={other.username}",
        headers=auth_header(caller),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["username"] == "profile_other2"
    assert body["user_cosmetics"] == {
        "hue": cosmetics.hue,
        "saturation": cosmetics.saturation,
        "brightness": cosmetics.brightness,
        "face": None,
        "body": None,
        "hat": None,
    }


def test_profile_nonexistent_username(client):
    caller = make_user(username="profile_caller3")

    response = client.get(
        "/api/account/profile?username=does_not_exist_at_all",
        headers=auth_header(caller),
    )

    body = assert_json_error(response, 404)
    assert body == {"error": "User not found"}


# ---------------------------------------------------------------------------
# GET /avatar
# ---------------------------------------------------------------------------

def test_avatar_no_username_returns_own_profile_as_object(client):
    user = make_user(username="avatar_self")

    response = client.get("/api/account/avatar", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"username": "avatar_self", "user_cosmetics": None}


def test_avatar_single_username_returns_a_list(client):
    caller = make_user(username="avatar_caller")
    other = make_user(username="avatar_other")

    response = client.get(
        "/api/account/avatar?username=avatar_other",
        headers=auth_header(caller),
    )

    assert response.status_code == 200
    # Note: even a single `username=` query param goes through the "list of
    # matches" branch, so the response is a list, not a bare object.
    assert response.get_json() == [{"username": "avatar_other", "user_cosmetics": None}]


def test_avatar_repeatable_username_returns_multiple(client):
    caller = make_user(username="avatar_caller2")
    user_a = make_user(username="avatar_multi_a")
    user_b = make_user(username="avatar_multi_b")

    response = client.get(
        "/api/account/avatar?username=avatar_multi_a&username=avatar_multi_b",
        headers=auth_header(caller),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert {entry["username"] for entry in body} == {"avatar_multi_a", "avatar_multi_b"}


def test_avatar_unknown_username_returns_empty_list_not_404(client):
    caller = make_user(username="avatar_caller3")

    response = client.get(
        "/api/account/avatar?username=nobody_by_this_name",
        headers=auth_header(caller),
    )

    # Unlike /profile, an unmatched username here is not a 404 - it just
    # yields an empty list, since the route filters with `.in_(usernames)`.
    assert response.status_code == 200
    assert response.get_json() == []


# ---------------------------------------------------------------------------
# GET /coins
# ---------------------------------------------------------------------------

def test_coins_creates_row_if_missing(client):
    user = make_user(username="coins_new_user")
    assert UserCoins.query.filter_by(user_id=user.id).first() is None

    response = client.get("/api/account/coins", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"coins": 0}
    row = UserCoins.query.filter_by(user_id=user.id).first()
    assert row is not None
    assert row.coins == 0


def test_coins_returns_existing_balance(client):
    user = make_user(username="coins_existing_user")
    _give_coins_and_cosmetics(user, coins=250)

    response = client.get("/api/account/coins", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"coins": 250}
    # No duplicate row should have been created.
    assert UserCoins.query.filter_by(user_id=user.id).count() == 1
