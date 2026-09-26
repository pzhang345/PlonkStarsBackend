"""Fixtures for tests/concurrency/.

- committed_db: unlike db_session, changes are really committed (not
  SAVEPOINT-wrapped). Concurrency tests spin up multiple threads that each
  make their own request through `app.test_client()`; Flask-SQLAlchemy scopes
  `db.session` per app context, so each request thread gets its own session
  and its own connection. For rows written by one thread to be visible to
  another thread's session, the writes have to be real commits against the
  real engine - the SAVEPOINT trick `db_session` uses only works because it
  forces every session in the test onto the *same* connection, which isn't
  possible here (and wouldn't exercise the race we're testing anyway).

  Because writes are real commits, they must not leak into later tests that
  rely on `db_session`'s rollback-based isolation (which only ever wraps the
  *outer* transaction - it doesn't stop the schema from already containing
  rows a concurrency test committed). So on teardown this fixture removes its
  own setup session (dropping any lock-holding idle transaction) and then
  TRUNCATEs every table this domain's routes touch, using a *fresh* session,
  so a leftover open transaction on the setup session can never block the
  TRUNCATE. Teardown runs in a try/finally so it still cleans up if the test
  body raised.
"""

import pytest
from sqlalchemy import text

from models.db import db

# Every table app/api/cosmetics/crates/routes.py's buy_crate can read or
# write, plus the tables that feed it (users, crates/crate_items) - order
# doesn't matter since RESTART IDENTITY CASCADE handles FK dependencies.
_TOUCHED_TABLES = (
    "users",
    "user_coins",
    "crates",
    "crate_items",
    "cosmetics",
    "cosmetics_ownership",
    "user_cosmetics",
)


@pytest.fixture()
def committed_db(app):
    """Function-scoped fixture for tests that need real, cross-thread-visible
    commits instead of `db_session`'s SAVEPOINT isolation.

    Pushes an app context (so `db.session`/factories resolve correctly for
    setup code in the test body) and yields the real `db.session`. Test
    bodies are expected to spawn their own threads/test clients, each of
    which gets its own session via Flask's per-request app context.

    Teardown: removes the setup session first (so it can't be left idle in a
    transaction holding a lock), then truncates every table this domain's
    routes touch via a fresh session, and removes that session too. This
    keeps committed rows from leaking into later SAVEPOINT-isolated tests.
    Wrapped in try/finally so cleanup still runs if the test failed or the
    truncate itself errors.
    """
    context = app.app_context()
    context.push()
    try:
        yield db.session
    finally:
        db.session.remove()
        try:
            db.session.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(_TOUCHED_TABLES)} RESTART IDENTITY CASCADE"
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
        finally:
            db.session.remove()
            context.pop()
