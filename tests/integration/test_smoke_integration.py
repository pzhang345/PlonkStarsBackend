"""Smoke test proving the whole stack (factory -> app -> db_session ->
client -> real routes -> real DB) works end to end, and that the
per-test DB isolation actually isolates.

Test order matters here on purpose: the isolation test depends on the two
tests above it having run (and rolled back) first, in the same session.
"""

import pytest

from models.user import User
from tests.factories import make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration


def test_login_returns_a_token(client):
    make_user(username="smoke_login_user", password="correct-horse")

    response = client.post(
        "/api/account/login",
        json={"username": "smoke_login_user", "password": "correct-horse"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["token"]


def test_authenticated_route_accepts_generated_token(client):
    user = make_user(username="smoke_auth_user", password="correct-horse")

    response = client.get("/api/account/user", headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json() == {"user": "smoke_auth_user"}


def test_db_isolation_across_tests(client):
    # Neither user created by the two tests above should exist here - each
    # test runs inside its own transaction that gets rolled back in teardown.
    assert User.query.filter_by(username="smoke_login_user").first() is None
    assert User.query.filter_by(username="smoke_auth_user").first() is None
