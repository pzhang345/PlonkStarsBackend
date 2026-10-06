"""Daily challenge generation and day rollover.

Scope:
- Use freezegun to cross midnight: a new day creates a new challenge, and the
  same day returns the existing one.
- Pin the timezone boundary (UTC vs local).

Code under test: app/api/session/daily.py (create_daily,
award_prev_daily_challenge_coins, award_daily_challenge_coins),
app/api/session/routes.py (GET /api/session/daily), app/models/session.py
(DailyChallenge), and the app/cli scheduler entrypoint that calls
create_daily() with no arguments (app/cli/cli.py's `daily-tasks` /
`create-daily` commands).

GET /api/session/daily (routes.py:get_daily) always computes
`now = datetime.now(tz=pytz.utc)` and calls `create_daily(today)` with an
*explicit* date, so the route itself is not subject to the frozen-default-arg
bug below - only bare `create_daily()` calls (i.e. the CLI/scheduler path)
are.
"""

import inspect
from datetime import date, datetime, timedelta

import pytest
import pytz
from freezegun import freeze_time

from api.session.daily import award_daily_challenge_coins, create_daily
from models.configs import Configs
from models.cosmetics import UserCoins
from models.db import db
from models.map import Bound, MapBound
from models.session import BaseRules, DailyChallenge, GameType
from models.stats import RoundStats
from tests.factories import make_base_rules, make_map, make_session, make_user, make_user_coins
from tests.helpers import auth_header

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Local helpers (private to this file - see the task's hard rules: only
# test_game_tasks.py / test_daily_challenge.py / bugs.md may be touched).
# ---------------------------------------------------------------------------

def _seed_configs(**pairs):
    """Insert Configs rows from kwargs, stringifying values (Configs.value is
    a plain String(50) column; every reader does int(...)/str(...).lower())."""
    for key, value in pairs.items():
        db.session.add(Configs(key=key, value=str(value)))
    db.session.commit()


def _attach_point_bound(game_map):
    """Give a map a single-point Bound/MapBound pair so
    api.location.generate.get_random_bounds()/generate_location() can resolve
    a bound for it (create_daily() calls create_round() for every round,
    which needs this). A "point" bound (start == end) is what makes
    generate_location call check_multiple_street_views(bound, 1) - matching
    exactly what the street_view_mock fixture fakes."""
    weight = game_map.total_weight or 1
    bound = Bound(
        start_latitude=1.0, start_longitude=2.0,
        end_latitude=1.0, end_longitude=2.0,
    )
    db.session.add(bound)
    db.session.commit()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=weight))
    db.session.commit()
    return bound


def _seed_daily_config(rounds=2, time_limit=-1, nmpz=False, host_username=None):
    """Seed every Configs key create_daily() reads, plus a matching BaseRules
    row (create_daily does BaseRules.query...first() and would crash on None
    if the row isn't there - see
    test_create_daily_without_matching_base_rules_crashes_documents_bug)."""
    host = make_user(username=host_username)
    game_map = make_map(creator=host, name="Daily Map " + host.username)
    _attach_point_bound(game_map)
    rules = make_base_rules(game_map=game_map, time_limit=time_limit, max_rounds=rounds, nmpz=nmpz)
    _seed_configs(
        DAILY_DEFAULT_ROUNDS=rounds,
        DAILY_DEFAULT_TIME_LIMIT=time_limit,
        DAILY_DEFAULT_NMPZ=str(nmpz),
        DAILY_DEFAULT_MAP_ID=game_map.id,
        DAILY_DEFAULT_HOST_ID=host.id,
    )
    return host, game_map, rules


# ---------------------------------------------------------------------------
# create_daily() / GET /api/session/daily - basic create + idempotency
# ---------------------------------------------------------------------------

def test_create_daily_creates_session_and_rounds(db_session, street_view_mock):
    _seed_daily_config(rounds=3, host_username="direct_daily_host")

    with freeze_time("2026-01-05 10:00:00"):
        target_date = datetime.now(tz=pytz.utc).date()
        daily = create_daily(target_date)

    assert daily.date == target_date
    assert daily.session is not None
    assert len(daily.session.rounds) == 3


def test_create_daily_duplicate_date_raises(db_session, street_view_mock):
    _seed_daily_config(rounds=2, host_username="dup_daily_host")
    target_date = date(2026, 2, 1)

    create_daily(target_date)

    with pytest.raises(Exception, match="Daily challenge already exists"):
        create_daily(target_date)


def test_daily_route_same_day_returns_existing_challenge(client, street_view_mock):
    _seed_daily_config(rounds=2, host_username="same_day_host")
    caller = make_user(username="same_day_caller")

    with freeze_time("2026-03-10 10:00:00"):
        first = client.get("/api/session/daily", headers=auth_header(caller))
        assert first.status_code == 200, first.get_data(as_text=True)
        first_body = first.get_json()

        second = client.get("/api/session/daily", headers=auth_header(caller))
        assert second.status_code == 200, second.get_data(as_text=True)
        second_body = second.get_json()

    assert first_body["id"] == second_body["id"]
    assert DailyChallenge.query.filter_by(date=date(2026, 3, 10)).count() == 1


def test_daily_route_crosses_midnight_utc_creates_new_challenge(client, street_view_mock):
    """Pins the day boundary at UTC midnight: every call site reads
    `datetime.now(tz=pytz.utc)`, so 23:30 and 00:30 UTC are different days
    regardless of the server's local timezone. (freezegun's `tz_offset` is not
    usable here: it also shifts `now(tz=utc)`, so it can't distinguish UTC
    from local time.)"""
    _seed_daily_config(rounds=2, host_username="midnight_host")
    caller = make_user(username="midnight_caller")

    with freeze_time("2026-03-10 23:30:00"):
        first = client.get("/api/session/daily", headers=auth_header(caller))
        assert first.status_code == 200, first.get_data(as_text=True)
        first_id = first.get_json()["id"]

    with freeze_time("2026-03-11 00:30:00"):
        second = client.get("/api/session/daily", headers=auth_header(caller))
        assert second.status_code == 200, second.get_data(as_text=True)
        second_id = second.get_json()["id"]

    assert first_id != second_id
    assert DailyChallenge.query.count() == 2
    assert DailyChallenge.query.filter_by(date=date(2026, 3, 10)).count() == 1
    assert DailyChallenge.query.filter_by(date=date(2026, 3, 11)).count() == 1


# ---------------------------------------------------------------------------
# BUG: create_daily()'s default date argument is frozen at import time
# ---------------------------------------------------------------------------

def test_create_daily_default_date_is_frozen_at_import_time_documents_bug(db_session, street_view_mock):
    """BUG: `def create_daily(date=datetime.now(tz=pytz.utc).date() + timedelta(days=1))`
    evaluates its default value exactly once, when api/session/daily.py is
    first imported (process startup) - not on every call. This module was
    already imported long before this test (or any freeze_time block) ran,
    so the baked-in default is "tomorrow relative to whenever the test
    process started up", not "tomorrow relative to now".

    This matters for app/cli/cli.py's `daily-tasks` / `create-daily`
    commands, which call `create_daily()` with no arguments - presumably
    from a daily cron/scheduler. On a long-running process (or one started
    well before the scheduled run), every such call keeps targeting the same
    frozen date forever, not "tomorrow" as intended.

    Fix: use a sentinel default (e.g. `date=None`) and compute
    `datetime.now(tz=pytz.utc).date() + timedelta(days=1)` inside the
    function body when `date is None`.
    """
    frozen_at_import_default = inspect.signature(create_daily).parameters["date"].default

    _seed_daily_config(rounds=2, host_username="frozen_default_host")

    # Freeze at a moment far away from whenever this test module was
    # actually imported, so "tomorrow relative to *now*" would clearly be a
    # different date than the baked-in default.
    with freeze_time("2030-06-15 10:00:00"):
        real_tomorrow = datetime.now(tz=pytz.utc).date() + timedelta(days=1)
        assert frozen_at_import_default != real_tomorrow, (
            "test setup assumption broken: the frozen import-time default "
            "happens to coincide with the frozen 'tomorrow' - pick a "
            "different freeze_time value"
        )

        daily = create_daily()

    assert daily.date == frozen_at_import_default
    assert daily.date != real_tomorrow


# ---------------------------------------------------------------------------
# BUG: create_daily() crashes when no matching BaseRules row exists
# ---------------------------------------------------------------------------

def test_create_daily_without_matching_base_rules_crashes_documents_bug(db_session):
    """BUG: create_daily() looks up
    `BaseRules.query.filter_by(map_id=..., time_limit=..., max_rounds=...,
    nmpz=...).first()` and, unlike app/api/game/games/basegame.py's
    BaseGame.create() (which creates a BaseRules row on the fly if none
    matches), assumes the row already exists. If the Configs-described
    combination has no matching BaseRules row, `rules` is None and
    `Session(..., base_rule_id=rules.id)` raises AttributeError instead of
    creating the rules row or returning a clean error.
    """
    host = make_user(username="missing_rules_host")
    game_map = make_map(creator=host, name="Missing Rules Map")
    # Deliberately do NOT create a BaseRules row matching these Configs.
    _seed_configs(
        DAILY_DEFAULT_ROUNDS=4,
        DAILY_DEFAULT_TIME_LIMIT=30,
        DAILY_DEFAULT_NMPZ="false",
        DAILY_DEFAULT_MAP_ID=game_map.id,
        DAILY_DEFAULT_HOST_ID=host.id,
    )

    with pytest.raises(AttributeError):
        create_daily(date(2026, 5, 1))


# ---------------------------------------------------------------------------
# award_daily_challenge_coins() - placement rewards
# ---------------------------------------------------------------------------

def test_award_daily_challenge_coins_grants_placement_rewards(db_session):
    host = make_user(username="award_host")
    game_map = make_map(creator=host, name="Award Map")
    rules = make_base_rules(game_map=game_map, max_rounds=1)
    session = make_session(host=host, base_rules=rules, game_type=GameType.CHALLENGE)

    daily = DailyChallenge(session_id=session.id, date=date(2026, 6, 1))
    db.session.add(daily)
    db.session.commit()

    winner = make_user(username="award_winner")
    loser = make_user(username="award_loser")
    make_user_coins(winner, coins=0)
    make_user_coins(loser, coins=0)

    db.session.add(RoundStats(session_id=session.id, user_id=winner.id, round=1, total_score=5000, total_time=10))
    db.session.add(RoundStats(session_id=session.id, user_id=loser.id, round=1, total_score=100, total_time=20))
    db.session.commit()

    award_daily_challenge_coins(daily)
    db.session.commit()

    winner_coins = UserCoins.query.filter_by(user_id=winner.id).first()
    loser_coins = UserCoins.query.filter_by(user_id=loser.id).first()

    # Both participants land in the top-3 placement_rewards table (ranks 1
    # and 2 out of 2 total), plus total_score // 50 (score_per_coin) each.
    assert winner_coins.coins == 500 + 5000 // 50
    assert loser_coins.coins == 450 + 100 // 50
    assert daily.coins_added is True
