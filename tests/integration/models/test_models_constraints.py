"""Integration tests for the model layer (app/models/*.py) and app/utils.py.

Focus is on invariants that would actually break the app if they regressed:
unique/check constraints genuinely firing at the DB level, cascade deletes
actually removing dependent rows, enum columns round-tripping through
Postgres, Configs get/in_ semantics, and generate_code's collision retry.

IMPORTANT on IntegrityError tests: after an IntegrityError the surrounding
transaction is aborted in Postgres - every later statement in it fails until
a rollback happens. Every constraint-violation test below runs the violating
statement inside `_expect_integrity_error()`, which opens a SAVEPOINT via
`db.session.begin_nested()` before the violating flush, and lets
begin_nested's own __exit__ issue `ROLLBACK TO SAVEPOINT` when the exception
propagates. That leaves the outer per-test transaction (owned by the
db_session fixture) perfectly usable afterward. Several tests below assert on
DB state *after* the guarded block specifically to prove that.
"""

from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models.configs import Configs
from models.cosmetics import Cosmetic_Type, Cosmetics, Tier, UserCoins
from models.db import db
from models.location import SVLocation
from models.map import MapEditor
from models.party import Party
from models.session import (
    BaseRules,
    DailyChallenge,
    GameState,
    GameStateTracker,
    GameType,
    Guess,
    Player,
    Round,
    Session,
)
from models.user import User
from tests.factories import (
    make_base_rules,
    make_location,
    make_map,
    make_round,
    make_session,
    make_user,
)
from utils import generate_code

pytestmark = pytest.mark.integration


@contextmanager
def _expect_integrity_error():
    """Run the block inside a SAVEPOINT and assert it raises IntegrityError.

    Verified (see test_integrity_error_does_not_poison_later_assertions)
    that after this context manager exits on the expected error, the outer
    per-test transaction is still perfectly queryable.
    """
    with pytest.raises(IntegrityError):
        with db.session.begin_nested():
            yield
            db.session.flush()


# ---------------------------------------------------------------------------
# Proof that the savepoint trick actually isolates failures
# ---------------------------------------------------------------------------

def test_integrity_error_does_not_poison_later_assertions(db_session):
    make_user(username="poison_check_user")

    with _expect_integrity_error():
        db.session.add(User(username="poison_check_user", password="x"))

    # If the SAVEPOINT rollback hadn't worked, this ordinary query would blow
    # up with "current transaction is aborted" instead of returning cleanly.
    assert User.query.filter_by(username="poison_check_user").count() == 1
    # And we can keep doing normal DB work afterward in the same test.
    make_user(username="poison_check_user_2")
    assert User.query.filter_by(username="poison_check_user_2").count() == 1


# ---------------------------------------------------------------------------
# Unique constraints
# ---------------------------------------------------------------------------

def test_user_username_unique_constraint(db_session):
    make_user(username="dupe_user")

    with _expect_integrity_error():
        db.session.add(User(username="dupe_user", password="x"))


def test_svlocation_lat_lng_unique_constraint(db_session):
    make_location(latitude=12.34, longitude=56.78)

    with _expect_integrity_error():
        db.session.add(SVLocation(latitude=12.34, longitude=56.78))


def test_player_unique_per_user_and_session(db_session):
    session = make_session()
    user = make_user()
    db.session.add(Player(user_id=user.id, session_id=session.id))
    db.session.commit()

    with _expect_integrity_error():
        db.session.add(Player(user_id=user.id, session_id=session.id))


def test_guess_unique_per_user_and_round(db_session):
    round_ = make_round()
    user = make_user()
    db.session.add(Guess(user_id=user.id, round_id=round_.id, latitude=1, longitude=1, distance=1, score=1))
    db.session.commit()

    with _expect_integrity_error():
        db.session.add(Guess(user_id=user.id, round_id=round_.id, latitude=2, longitude=2, distance=2, score=2))


def test_round_unique_session_and_round_number(db_session):
    session = make_session()
    location_1 = make_location()
    location_2 = make_location()
    db.session.add(Round(
        location_id=location_1.id, session_id=session.id,
        round_number=1, base_rule_id=session.base_rule_id,
    ))
    db.session.commit()

    with _expect_integrity_error():
        db.session.add(Round(
            location_id=location_2.id, session_id=session.id,
            round_number=1, base_rule_id=session.base_rule_id,
        ))


def test_map_editor_unique_per_user_and_map(db_session):
    game_map = make_map()
    user = make_user()
    db.session.add(MapEditor(user_id=user.id, map_id=game_map.id))
    db.session.commit()

    with _expect_integrity_error():
        db.session.add(MapEditor(user_id=user.id, map_id=game_map.id))


def test_base_rules_unique_combination(db_session):
    game_map = make_map()
    make_base_rules(game_map=game_map, time_limit=30, max_rounds=5, nmpz=False)

    with _expect_integrity_error():
        db.session.add(BaseRules(map_id=game_map.id, time_limit=30, max_rounds=5, nmpz=False))


def test_daily_challenge_date_unique(db_session):
    session_1 = make_session()
    session_2 = make_session()
    today = date.today()
    db.session.add(DailyChallenge(session_id=session_1.id, date=today))
    db.session.commit()

    with _expect_integrity_error():
        db.session.add(DailyChallenge(session_id=session_2.id, date=today))


# ---------------------------------------------------------------------------
# Check constraint
# ---------------------------------------------------------------------------

def test_user_coins_negative_balance_rejected(db_session):
    user = make_user()

    with _expect_integrity_error():
        db.session.add(UserCoins(user_id=user.id, coins=-1))

    # Non-negative is fine.
    db.session.add(UserCoins(user_id=user.id, coins=0))
    db.session.commit()
    assert UserCoins.query.filter_by(user_id=user.id).first().coins == 0


# ---------------------------------------------------------------------------
# Cascade deletes
# ---------------------------------------------------------------------------

def test_deleting_user_cascades_dependent_rows(db_session):
    user = make_user()
    round_ = make_round()

    guess = Guess(user_id=user.id, round_id=round_.id, latitude=1, longitude=1, distance=1, score=1)
    player = Player(user_id=user.id, session_id=round_.session_id)
    coins = UserCoins(user_id=user.id, coins=10)
    db.session.add_all([guess, player, coins])
    db.session.commit()

    guess_id, player_id, coins_id, user_id = guess.id, player.id, coins.id, user.id

    db.session.delete(user)
    db.session.commit()

    assert db.session.get(Guess, guess_id) is None
    assert db.session.get(Player, player_id) is None
    assert db.session.get(UserCoins, coins_id) is None
    assert db.session.get(User, user_id) is None


def test_deleting_session_cascades_rounds_and_players(db_session):
    session = make_session()
    round_ = make_round(session=session)
    user = make_user()
    player = Player(user_id=user.id, session_id=session.id)
    db.session.add(player)
    db.session.commit()

    round_id, player_id, session_id = round_.id, player.id, session.id

    db.session.delete(session)
    db.session.commit()

    assert db.session.get(Round, round_id) is None
    assert db.session.get(Player, player_id) is None
    assert db.session.get(Session, session_id) is None


def test_deleting_session_with_attached_party_raises_integrity_error(db_session):
    """FINDING (real data-integrity gap, not fixed here): every other
    session_id foreign key in this codebase is declared
    ForeignKey("sessions.id", ondelete="CASCADE"). Party.session_id
    (models/party.py) is declared as plain ForeignKey("sessions.id") - no
    ondelete clause - and Session.party is only passive_deletes=True with no
    ORM-level cascade either. So deleting a Session that has a Party attached
    does not cascade: it violates the FK and raises IntegrityError. Any
    caller that assumes "deleting a Session always succeeds" (e.g. session
    cleanup/expiry jobs) will crash on any session that still has a party
    attached. Documenting actual behavior.
    """
    host = make_user()
    session = make_session(host=host)
    db.session.add(Party(session_id=session.id, host_id=host.id, code="ZZZQ"))
    db.session.commit()

    with _expect_integrity_error():
        db.session.delete(session)


# ---------------------------------------------------------------------------
# Enum columns
# ---------------------------------------------------------------------------

def test_session_type_enum_roundtrips(db_session):
    session = make_session(game_type=GameType.LIVE)
    session_id = session.id
    db.session.expire_all()

    reloaded = db.session.get(Session, session_id)

    assert reloaded.type is GameType.LIVE
    assert isinstance(reloaded.type, GameType)


def test_game_state_tracker_enum_roundtrips(db_session):
    session = make_session()
    db.session.add(GameStateTracker(session_id=session.id, state=GameState.GUESSING))
    db.session.commit()
    session_id = session.id
    db.session.expire_all()

    reloaded = GameStateTracker.query.filter_by(session_id=session_id).first()

    assert reloaded.state is GameState.GUESSING


def test_cosmetics_enum_columns_roundtrip(db_session):
    cosmetic = Cosmetics(image="img_enum_test", item_name="item_enum_test", type=Cosmetic_Type.HAT, tier=Tier.EPIC)
    db.session.add(cosmetic)
    db.session.commit()
    cosmetic_id = cosmetic.id
    db.session.expire_all()

    reloaded = db.session.get(Cosmetics, cosmetic_id)

    assert reloaded.type is Cosmetic_Type.HAT
    assert reloaded.tier is Tier.EPIC


def test_tier_from_str():
    assert Tier.from_str("common") is Tier.COMMON
    assert Tier.from_str("LEGENDARY") is Tier.LEGENDARY
    assert Tier.from_str("not-a-real-tier") is None
    assert Tier.from_str(None) is None
    assert Tier.from_str("") is None


# ---------------------------------------------------------------------------
# Configs.get / Configs.in_
# ---------------------------------------------------------------------------

def test_configs_get_and_in_semantics(db_session):
    db.session.add(Configs(key="SOME_TEST_KEY", value="42"))
    db.session.commit()

    assert Configs.get("SOME_TEST_KEY") == "42"
    assert Configs.in_("SOME_TEST_KEY") is True
    assert Configs.get("MISSING_TEST_KEY") is None
    assert Configs.in_("MISSING_TEST_KEY") is False


# ---------------------------------------------------------------------------
# generate_code
# ---------------------------------------------------------------------------

def test_generate_code_shape(db_session):
    code = generate_code(Party)

    assert len(code) == 4
    assert code.isalpha()
    assert code.isupper()


def test_generate_code_retries_on_collision(db_session, monkeypatch):
    host = make_user()
    db.session.add(Party(session_id=None, host_id=host.id, code="AAAA"))
    db.session.commit()

    # First 4 draws spell "AAAA" (colliding with the row above and forcing a
    # retry), the next 4 spell "BBBB".
    draws = iter([65, 65, 65, 65, 66, 66, 66, 66])
    monkeypatch.setattr("utils.randint", lambda a, b: next(draws))

    code = generate_code(Party)

    assert code == "BBBB"


# ---------------------------------------------------------------------------
# Relationship wiring
# ---------------------------------------------------------------------------

def test_session_rounds_and_round_session_backrefs(db_session):
    session = make_session()
    round_ = make_round(session=session)

    assert round_ in session.rounds
    assert round_.session is session


def test_base_rules_map_and_map_rules_backrefs(db_session):
    game_map = make_map()
    rules = make_base_rules(game_map=game_map)

    assert rules.map is game_map
    assert rules in game_map.rules
