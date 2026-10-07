# Backend test suite

## Prerequisites

The suite needs a real Postgres instance for integration tests (the `app`
fixture builds the real Flask app and creates the real schema against it).

The easiest way is to let `make test` manage it for you (see "Running the
suite" below) - it starts/reuses a container from
`tests/docker-compose.test.yml` automatically.

If you'd rather manage the container yourself, start one with Docker:

```bash
docker run -d --name plonkstars-test-db \
  -e POSTGRES_USER=plonktest \
  -e POSTGRES_PASSWORD=plonktest \
  -e POSTGRES_DB=plonkstars_test \
  -p 55432:5432 \
  postgres:17-alpine
```

or with the same compose file directly:

```bash
docker compose -f tests/docker-compose.test.yml up -d --wait
```

By default the suite points at:

```
postgresql+psycopg2://plonktest:plonktest@localhost:55432/plonkstars_test
```

Override with the `TEST_DATABASE_URL` env var if you point at a different
instance (must be a `postgresql+psycopg2://` URL - the driver is already in
requirements.txt).

## Installing test dependencies

```bash
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

## Running the suite

The one-command option handles the test DB container (starting or reusing
`plonkstars-test-db`, waiting for it to be ready) and then runs pytest. From
`Backend/`:

```bash
make test ARGS=-q
```

Extra pytest arguments go in `ARGS`, e.g. `make test ARGS="-m unit"` or
`make test ARGS=--cov=app`. It leaves the DB container running afterwards;
stop it with `make db-down` when you're done. `make db-up` starts the DB
without running tests.

If you're managing the DB container yourself (see "Prerequisites"), you can
invoke pytest directly instead:

```bash
./.venv/Scripts/python.exe -m pytest -q
```

Always invoke pytest as `python -m pytest` (not the bare `pytest` script) so
the current directory (`Backend/`) is on `sys.path` - `tests/config.py`,
`tests/factories.py`, and `tests/helpers.py` are imported via the dotted path
`tests.xxx`, which relies on `Backend/` being importable as the root for the
`tests` namespace package.

Useful variations:

```bash
# only fast, pure-logic tests
./.venv/Scripts/python.exe -m pytest -m unit

# only DB/IO tests
./.venv/Scripts/python.exe -m pytest -m integration

# with coverage (opt-in, not part of default addopts)
./.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing
```

## Markers

- `unit` - pure-logic tests with no DB or network I/O. Should be fast and
  never need the `app`/`client`/`db_session` fixtures.
- `integration` - tests that exercise the Flask app, the real database, or
  other I/O (through the `client`/`db_session`/`socketio_client` fixtures).
- `slow` - anything notably slower than the rest of the suite (use sparingly;
  prefer making the test faster).

Mark a test module or test function with, e.g.:

```python
import pytest
pytestmark = pytest.mark.unit
```

## How isolation works

- `app` (session-scoped, `tests/conftest.py`): built once per test run via
  `create_app(TestConfig)`, with the real schema created via `db.create_all()`
  and dropped at the very end. Because `db`/`mail`/`socketio`/`celery`/`admin`
  are process-wide singletons, there is intentionally only ever one Flask app
  per test session.
- `db_session` (function-scoped): opens a new connection + outer transaction
  before each test and rebinds `db.session` to it (via
  `sessionmaker(bind=connection, join_transaction_mode="create_savepoint")`),
  then rolls the whole thing back after the test. Route handlers that call
  `db.session.commit()` internally still work correctly - the commit just
  releases a SAVEPOINT, it never reaches the outer transaction. Nothing a
  test writes is ever visible to another test.
- `client`: a Flask test client that depends on `db_session`, so every
  request you make through it is automatically wrapped in the isolated
  transaction.
- `socketio_client`: call it (it's a factory fixture) to get a connected
  `flask_socketio` test client sharing the same Flask test client/session,
  e.g. `sio = socketio_client()` or `sio = socketio_client(namespace="/socket/party")`.

## Network safety net

An autouse fixture (`_no_network` in `tests/conftest.py`) patches
`requests`, `aiohttp`, and `smtplib` so any accidental outbound HTTP call or
mail send raises immediately instead of hitting the real network. If a test
needs to exercise code that calls the Google Street View API
(`api/location/generate.py:check_multiple_street_views`), request the
`street_view_mock` (or `google_maps_mock`, same fixture) fixture, which
patches that one call to return a deterministic `SVLocation` instead.

## Adding a new test

1. Tests are grouped by domain under `unit/<domain>/` and
   `integration/<domain>/`, mirroring the domains under `app/api/` (account,
   admin, cosmetics, feedback, game, map, models, party, session). Pick
   `unit/<domain>/` (no DB/IO) or `integration/<domain>/` (needs the
   app/DB) for the domain your test covers. Each domain has its own
   `conftest.py` holding that domain's fixtures. `concurrency/` holds
   real-commit tests marked `slow` (skip them with `-m "not slow"`), `data/`
   holds static JSON seed data, and ad-hoc scripts belong in `Backend/scripts/`,
   not in `tests/`.
2. Name the file `test_<something>.py` with a basename that is unique across
   the whole `tests/` tree - do not reuse a basename in another directory.
   There are no `__init__.py` files in `tests/`, and pytest is configured
   with `--import-mode=importlib`; unique basenames avoid any ambiguity in
   how pytest names collected modules.
3. Import test-only support code via the dotted `tests.*` path, e.g.:
   ```python
   from tests.factories import make_user, make_map
   from tests.helpers import auth_header, demo_header, assert_json_error
   ```
   Never `from config import TestConfig` as a bare import - always
   `from tests.config import TestConfig`. See the comment in `pytest.ini` for
   why (bare `import config` must always resolve to `app/config.py`).
4. Use `client` for HTTP requests, `db_session` if you only need direct DB
   access, `socketio_client` for Socket.IO, and the `tests.factories` helpers
   to set up data. Tag the module with `pytestmark = pytest.mark.unit` or
   `pytest.mark.integration`.
