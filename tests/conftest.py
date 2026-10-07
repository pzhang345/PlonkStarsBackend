"""Shared pytest fixtures for the whole suite.

Import note: this file (and every other tests/ support module) reaches the
test-only config via the dotted path `tests.config`, never a bare
`import config`. That's deliberate - see the comment in pytest.ini. Bare
`import config` anywhere in this repo always means app/config.py.
"""

import smtplib

import pytest
from sqlalchemy.orm import scoped_session, sessionmaker

from factory import create_app
from models.db import db
from models.location import SVLocation
from tests.config import TestConfig


# ---------------------------------------------------------------------------
# App / DB lifecycle
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Session-scoped Flask app built from TestConfig.

    db, mail, socketio, celery, and admin are process-wide singletons
    (module-level objects imported by app/*), so there must be exactly one
    app built per test session - building a second one would re-init those
    singletons against a different app and step on the first.

    Schema lifecycle is owned here: drop_all (to recover from a dirty prior
    run) then create_all once for the whole session; drop_all again at
    teardown. Per-test isolation is handled separately by `db_session`.
    """
    flask_app = create_app(TestConfig)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()

    yield flask_app

    with flask_app.app_context():
        db.drop_all()


@pytest.fixture()
def db_session(app):
    """Function-scoped isolation: wrap each test in an outer transaction on
    its own connection, and bind `db.session` to that connection for the
    duration of the test. `join_transaction_mode="create_savepoint"` makes
    the bound session issue a SAVEPOINT instead of a real COMMIT, so route
    handlers that call `db.session.commit()` internally still work (the
    commit just releases/renews the savepoint) without ever touching the
    outer transaction. At teardown, the outer transaction is rolled back and
    the connection closed, so every test starts from a clean, fully-migrated
    schema regardless of what previous tests committed.

    Verified against the real Postgres test DB: a test that calls
    db.session.commit() twice, then relies on this fixture's rollback, does
    NOT leak rows into the next test.
    """
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()

        # query_cls matches what Flask-SQLAlchemy's own session uses, so
        # db.session.query(...) returns a Query with .paginate() like in prod.
        session_factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", query_cls=db.Query
        )
        test_session = scoped_session(session_factory)

        original_session = db.session
        db.session = test_session

        try:
            yield test_session
        finally:
            test_session.remove()
            db.session = original_session
            transaction.rollback()
            connection.close()


@pytest.fixture()
def client(app, db_session):
    """Flask test client. Depends on db_session so every request made
    through it runs inside the per-test isolated transaction."""
    return app.test_client()


@pytest.fixture()
def socketio_client(app, client):
    """Factory fixture: call it to get a connected flask_socketio test
    client sharing the same Flask test client (and therefore the same
    isolated DB transaction). Usage:

        def test_foo(socketio_client):
            sio = socketio_client()                       # default namespace
            sio2 = socketio_client(namespace="/socket/party")
    """
    from fsocket import socketio as sio

    created = []

    def _make(namespace=None, auth=None):
        kwargs = {"flask_test_client": client}
        if namespace is not None:
            kwargs["namespace"] = namespace
        if auth is not None:
            kwargs["auth"] = auth
        test_client = sio.test_client(app, **kwargs)
        created.append((test_client, namespace))
        return test_client

    yield _make

    # is_connected()/disconnect() default to the "/" namespace, so pass the
    # one each client actually connected to or it never gets disconnected.
    for test_client, namespace in created:
        if test_client.is_connected(namespace):
            test_client.disconnect(namespace=namespace)


# ---------------------------------------------------------------------------
# Network safety net
# ---------------------------------------------------------------------------

def _blocked(*_args, **_kwargs):
    raise RuntimeError(
        "Outbound network access is blocked in tests. Mock the call instead "
        "(see the google_maps_mock/street_view_mock fixture for the Google "
        "Street View case)."
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Make any accidental outbound HTTP or mail send fail loudly instead of
    hitting the real network. Applies to every test automatically."""
    monkeypatch.setattr("requests.sessions.Session.request", _blocked)
    monkeypatch.setattr("aiohttp.client.ClientSession._request", _blocked)
    monkeypatch.setattr(smtplib.SMTP, "connect", _blocked)
    monkeypatch.setattr(smtplib.SMTP_SSL, "connect", _blocked)
    yield


# ---------------------------------------------------------------------------
# Google Street View mock
# ---------------------------------------------------------------------------

@pytest.fixture()
def street_view_mock(monkeypatch, db_session):
    """Patch api.location.generate.check_multiple_street_views so location
    generation never calls the real Google Street View API.

    The real function is `async def check_multiple_street_views(bound,
    num_checks=100)` and returns an `SVLocation` row (via `add_coord`) or
    `None`. It is always invoked as `asyncio.run(check_multiple_street_views(...))`
    by api/location/generate.py:generate_location, so the replacement must
    also be an `async def` (asyncio.run needs a coroutine to run).

    The fake deterministically returns a point at the bound's start corner,
    persisted as a real SVLocation row so downstream code (which expects an
    ORM object with .id/.latitude/.longitude) works unchanged.
    """
    import api.location.generate as generate_module

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

    monkeypatch.setattr(generate_module, "check_multiple_street_views", fake_check_multiple_street_views)
    return fake_check_multiple_street_views


@pytest.fixture()
def google_maps_mock(street_view_mock):
    """Alias for street_view_mock, for tests that ask for it by this name."""
    return street_view_mock
