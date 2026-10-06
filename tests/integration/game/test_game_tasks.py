"""Celery game-state tasks.

Scope: Celery update_game_state/stop_current_task.
- Mock celery.control.revoke, apply_async, and redis_instance.publish.
- update_game_state creates a CeleryTaskTracker. Calling it again revokes the
  old task and replaces the row.
- Calling __update_game_state__ directly deletes the tracker and publishes
  db_changes.
- A session deleted before the task fires currently raises AttributeError on
  None. Pin that, then fix it.

Code under test: app/api/game/tasks.py, app/models/session.py
(CeleryTaskTracker), app/my_celery/base_celery.py, app/my_celery/db_sync.py.

Note: importing my_celery.db_sync creates a real redis client at import time
(`redis.from_url(...)`), which already happened once when the app fixture
built the Flask app. To avoid opening any real connection, every test here
patches the *method* on the already-constructed `api.game.tasks.redis_instance`
object (and similarly `api.game.tasks.celery.control.revoke`) rather than
reassigning/reconnecting anything.
"""

import itertools
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import api.game.tasks as tasks_module
from api.game.gametype import game_type
from models.db import db
from models.session import CeleryTaskTracker, GameState, GameType
from tests.factories import make_session

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Local fixtures (private to this file - see the task's hard rules: only
# test_game_tasks.py / test_daily_challenge.py / bugs.md may be touched).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mocked_celery(monkeypatch):
    """Patch every external side effect update_game_state()/stop_current_task()/
    __update_game_state__ can trigger:
      - celery.control.revoke
      - __update_game_state__.apply_async (returns an object with a distinct
        .id on every call, like the real AsyncResult would)
      - redis_instance.publish

    Returns a SimpleNamespace with each mock, plus `task_ids` (the fake task
    ids handed out, in call order) and `apply_async_calls` (the raw
    args/countdown each call was made with) for convenience.
    """
    revoke_mock = MagicMock()
    monkeypatch.setattr(tasks_module.celery.control, "revoke", revoke_mock)

    publish_mock = MagicMock()
    monkeypatch.setattr(tasks_module.redis_instance, "publish", publish_mock)

    id_counter = itertools.count(1)
    task_ids = []
    apply_async_calls = []

    def _fake_apply_async(args=None, countdown=None, **kwargs):
        task_id = f"fake-task-{next(id_counter)}"
        task_ids.append(task_id)
        apply_async_calls.append({"args": args, "countdown": countdown})
        return SimpleNamespace(id=task_id)

    apply_async_mock = MagicMock(side_effect=_fake_apply_async)
    monkeypatch.setattr(tasks_module.__update_game_state__, "apply_async", apply_async_mock)

    return SimpleNamespace(
        revoke=revoke_mock,
        publish=publish_mock,
        apply_async=apply_async_mock,
        task_ids=task_ids,
        apply_async_calls=apply_async_calls,
    )


# ---------------------------------------------------------------------------
# update_game_state()
# ---------------------------------------------------------------------------

def test_update_game_state_creates_tracker_with_apply_async_task_id(db_session, mocked_celery):
    session = make_session(game_type=GameType.CHALLENGE)
    data = {"state": GameState.GUESSING}

    tasks_module.update_game_state(data, session, 30)

    # apply_async is called with the *converted* state (enum -> .value),
    # since update_game_state mutates `data` in place before dispatching.
    mocked_celery.apply_async.assert_called_once_with(args=[data, session.id], countdown=30)
    assert data == {"state": GameState.GUESSING.value}

    tracker = CeleryTaskTracker.query.filter_by(session_id=session.id).first()
    assert tracker is not None
    assert tracker.task_id == mocked_celery.task_ids[0]


def test_update_game_state_second_call_revokes_previous_task_and_replaces_tracker(db_session, mocked_celery):
    session = make_session(game_type=GameType.CHALLENGE)

    tasks_module.update_game_state({"state": GameState.GUESSING}, session, 10)
    first_task_id = mocked_celery.task_ids[0]

    tasks_module.update_game_state({"state": GameState.RESULTS}, session, 20)
    second_task_id = mocked_celery.task_ids[1]

    assert first_task_id != second_task_id
    mocked_celery.revoke.assert_called_once_with(first_task_id)

    trackers = CeleryTaskTracker.query.filter_by(session_id=session.id).all()
    assert len(trackers) == 1
    assert trackers[0].task_id == second_task_id


def test_stop_current_task_with_no_tracker_is_a_noop(db_session, mocked_celery):
    session = make_session(game_type=GameType.CHALLENGE)

    tasks_module.stop_current_task(session)

    mocked_celery.revoke.assert_not_called()
    assert CeleryTaskTracker.query.filter_by(session_id=session.id).count() == 0


# ---------------------------------------------------------------------------
# __update_game_state__ (the task body itself, called synchronously)
# ---------------------------------------------------------------------------

def test_dunder_update_game_state_dispatches_updates_and_cleans_up(db_session, monkeypatch, mocked_celery):
    # GameType.LIVE, not CHALLENGE: update_game_state()/__update_game_state__
    # are only ever called from games/live.py and games/duels.py (grep
    # confirms it - ChallengeGame doesn't even define update_state, so a
    # CHALLENGE session would never legitimately reach this task body).
    session = make_session(game_type=GameType.LIVE)
    # Seed a tracker row the way update_game_state() would, so we can assert
    # it gets deleted by the task body.
    tasks_module.update_game_state({"state": GameState.GUESSING}, session, 5)
    assert CeleryTaskTracker.query.filter_by(session_id=session.id).first() is not None

    update_state_mock = MagicMock()
    monkeypatch.setattr(game_type[GameType.LIVE], "update_state", update_state_mock)

    tasks_module.__update_game_state__.run({"state": GameState.RESULTS.value}, session.id)

    update_state_mock.assert_called_once()
    call_data, call_session = update_state_mock.call_args.args
    # The int is converted back into a GameState enum before being handed to
    # game_type[session.type].update_state.
    assert call_data == {"state": GameState.RESULTS}
    assert call_session.id == session.id

    mocked_celery.publish.assert_called_once_with("db_changes", "game state updated")
    assert CeleryTaskTracker.query.filter_by(session_id=session.id).first() is None


# ---------------------------------------------------------------------------
# BUG: task fires after its session was deleted
# ---------------------------------------------------------------------------

def test_task_fired_after_session_deleted_raises_attribute_error_documents_bug(db_session, mocked_celery):
    """BUG: __update_game_state__ does `Session.query.filter_by(id=session_id).first()`
    with no None-check before touching `session.type`. If the session row is
    gone by the time the (delayed, apply_async'd) task actually fires - e.g.
    the party/session was cleaned up in the meantime - the task blows up with
    an unhandled AttributeError on None instead of a clean no-op. See
    tests/bugs.md.
    """
    session = make_session(game_type=GameType.CHALLENGE)
    session_id = session.id
    db.session.delete(session)
    db.session.commit()

    with pytest.raises(AttributeError):
        tasks_module.__update_game_state__.run({"state": GameState.GUESSING.value}, session_id)
