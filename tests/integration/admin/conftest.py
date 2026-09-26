"""Fixtures for tests/integration/admin/.

- admin_user: a User row with admin privileges.
- admin_header: an Authorization header dict built from admin_user's
  generated token, for use with `client`.
- normal_user / normal_header: same, but for a non-admin user - used by the
  authz matrix in test_admin_authz.py.
"""

import pytest

from tests.factories import make_user
from tests.helpers import auth_header


@pytest.fixture()
def admin_user(db_session):
    return make_user(is_admin=True)


@pytest.fixture()
def admin_header(admin_user):
    return auth_header(admin_user)


@pytest.fixture()
def normal_user(db_session):
    return make_user(is_admin=False)


@pytest.fixture()
def normal_header(normal_user):
    return auth_header(normal_user)
