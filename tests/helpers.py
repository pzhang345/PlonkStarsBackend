"""Small assertion/auth helpers shared across tests."""

from api.account.auth import generate_token


def auth_header(user):
    """Build an Authorization header for `user`.

    api/api/account/auth.py's `login_required` reads the raw Authorization
    header and passes it to `decode()`, which does
    `token.replace("Bearer ", "")` before verifying - so a bare token (no
    "Bearer " prefix) works, and is what this helper sends.
    """
    return {"Authorization": generate_token(user)}


def demo_header():
    """Authorization header for the special-cased "demo" literal token.
    Only works against routes decorated with `login_required(allow_demo=True)`,
    and only if a user with username "demo" exists in the DB."""
    return {"Authorization": "demo"}


def assert_json_error(response, status):
    """Assert `response` has the given status code and a JSON body containing
    an "error" key. Returns the parsed body for further assertions."""
    assert response.status_code == status, (
        f"expected status {status}, got {response.status_code}: {response.get_data(as_text=True)}"
    )
    body = response.get_json()
    assert body is not None, "expected a JSON body"
    assert "error" in body, f"expected an 'error' key, got: {body}"
    return body
