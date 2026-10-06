"""Integration tests for the DUELS multiplier/HP-damage schedule
(app/api/game/games/duels.py: DuelsGame.next() computes the round's
multiplier, DuelsGame.update_state() applies HP damage from it).

This logic is inline in `next()`/`update_state()`, not a pure function we can
unit-test in isolation - so these tests drive the real DuelsGame() against the
real DB, bypassing Party entirely (next()/update_state() only ever touch
Session, GameStateTracker, DuelRulesLinker, and GameTeamLinker/GameTeam/
TeamPlayer rows - never Party/PartyTeam), which keeps the setup here to "one
team per guess" instead of a full party+team-routes dance.

Multiplier derivation (read directly off duels.py's `next()`):
    prev_multi = prev_round.duels_state.multi if prev_round else 1
    if (session.current_round - start_round) % freq == 0 and start_round <= session.current_round:
        new_multi = mult * prev_multi + add
    else:
        new_multi = prev_multi
    <round is created here, which increments session.current_round>

The critical, easy-to-miss detail: `session.current_round` at the time of
that check is still the *previous* round's number (0 before round 1 is
created) - the increment happens inside create_round(), called after this
check. So when round R is being created, the gate condition is evaluated
against R-1, not R. Given rules_config()'s min for "multi_start" is 1 (so
start_round is always >= 1 through any real, validated path), round 1 always
computes `start_round <= 0` as False, so round 1's multiplier is always
exactly 1 regardless of rule values - this is a real, unconditional fact
about the schedule, not a simplifying assumption made for these tests.

Damage application (read directly off update_state()'s RESULTS branch, which
only runs once every currently-alive team has a guess in - `all_guessed`):
    highest_score = highest-scoring Guess this round (0 if nobody guessed)
    multi = round.duels_state.multi
    for each team with hp > 0:
        guess_score = that team's linked Guess.score, or 0 if it has none
        hp = max(0, hp - ((highest_score - guess_score) * multi) // 1)
`// 1` floors the (possibly fractional, since multi is a float) damage
before subtracting - the highest scorer always takes 0 damage (its own
guess_score IS highest_score), a tie leaves both sides at 0 damage, and a
team with no Guess at all (never guessed, never plonked) is charged the full
highest_score with no discount.

Elimination: a team whose DuelHp.hp is driven to 0 simply gets no DuelHp row
carried into the next round (next()'s round>1 branch only carries forward
`DuelHp.hp > 0` rows) - so it's "still alive" for computing this round's
damage, but not the next one. next() itself checks the *previous* round's
`DuelHp.hp > 0` count before creating a new round; when it drops below 2, it
finishes the game instead of creating another round.
"""

from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from api.game.games.duels import DuelsGame
from models.db import db
from models.duels import DuelHp, DuelRulesLinker, GameTeam, GameTeamLinker, TeamPlayer
from models.session import GameState, GameStateTracker, GameType, Guess, Round, Session
from tests.factories import make_base_rules, make_bounded_map, make_duel_rules, make_user

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# File-local setup helpers (this file's own - tests/factories.py/conftest.py
# are not touched, and this setup - a DUELS session with no Party at all -
# isn't generally reusable enough to belong there).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_celery(monkeypatch):
    """DuelsGame.next()/update_state() call api.game.tasks.update_game_state
    and stop_current_task (imported by name into duels.py) whenever a round
    has a finite time_limit, or whenever a round closes with at least one
    real guess in it - both happen in this file's tests - so these must
    always be mocked, not just for the tests that use a finite time_limit."""
    monkeypatch.setattr("api.game.games.duels.update_game_state", MagicMock())
    monkeypatch.setattr("api.game.games.duels.stop_current_task", MagicMock())


@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    """Every test here calls DuelsGame.next(), which generates a round
    location via api.location.generate.generate_location."""
    return street_view_mock


def make_duels_session(map_lat=None, map_lng=None, max_rounds=-1, time_limit=-1,
                        start_hp=100000, damage_multi_start_round=1, damage_multi_mult=1.0,
                        damage_multi_add=0.0, damage_multi_freq=1, guess_time_limit=15,
                        team_user_lists=None):
    """Build a DUELS Session directly via the ORM (no Party/PartyTeam
    involved) with one GameTeamLinker (+ backing GameTeam/TeamPlayer rows)
    per inner list of `team_user_lists` (two solo-user teams by default).
    Returns (session, [GameTeam, ...]) in the same order as the input."""
    team_user_lists = team_user_lists or [[make_user()], [make_user()]]
    host = team_user_lists[0][0]

    game_map = make_bounded_map(lat=map_lat, lng=map_lng)
    base_rules = make_base_rules(game_map=game_map, time_limit=time_limit, max_rounds=max_rounds, nmpz=False)
    duel_rules = make_duel_rules(
        start_hp=start_hp,
        damage_multi_start_round=damage_multi_start_round,
        damage_multi_mult=damage_multi_mult,
        damage_multi_add=damage_multi_add,
        damage_multi_freq=damage_multi_freq,
        guess_time_limit=guess_time_limit,
    )

    session = Session(host_id=host.id, type=GameType.DUELS, base_rule_id=base_rules.id)
    db.session.add(session)
    db.session.flush()
    db.session.add(GameStateTracker(session_id=session.id))
    db.session.add(DuelRulesLinker(session_id=session.id, rules_id=duel_rules.id))
    db.session.flush()

    teams = []
    for users in team_user_lists:
        ids = sorted(u.id for u in users)
        team = GameTeam(hash=",".join(str(i) for i in ids))
        db.session.add(team)
        db.session.flush()
        for user in users:
            db.session.add(TeamPlayer(user_id=user.id, team_id=team.id))
        db.session.add(GameTeamLinker(session_id=session.id, team_id=team.id, name=f"team{team.id}", color=team.id))
        teams.append(team)

    db.session.commit()
    return session, teams


def play_round(session, team_scores):
    """Advance `session` by exactly one round: DuelsGame().next() opens it,
    each (team -> score) pair in `team_scores` is recorded as that team's
    guess (bypassing create_guess()/haversine so the score is exact and
    fully controllable), then DuelsGame().update_state(RESULTS) closes it.
    `team_scores` must name every currently-alive team - that's what makes
    update_state()'s `all_guessed` check true unconditionally, so this never
    depends on real wall-clock time. Returns the Round row (querying
    round.duels_state/round.duels_state.multi afterwards reflects the
    already-applied damage)."""
    DuelsGame().next({}, None, session)
    round_ = Round.query.filter_by(session_id=session.id, round_number=session.current_round).first()
    duels_state = round_.duels_state

    for team, score in team_scores.items():
        hp_row = DuelHp.query.filter_by(state_id=duels_state.id, team_id=team.id).first()
        assert hp_row is not None, f"team {team.id} is not alive this round - omit it from team_scores"
        user = team.players[0].user
        guess = Guess(
            user_id=user.id, round_id=round_.id,
            latitude=0.0, longitude=0.0, distance=0.0,
            score=score, time=1,
        )
        db.session.add(guess)
        db.session.flush()
        hp_row.guess_id = guess.id

    db.session.commit()
    DuelsGame().update_state({"state": GameState.RESULTS}, session)
    return round_


def hp_after(round_, team):
    return DuelHp.query.filter_by(state_id=round_.duels_state.id, team_id=team.id).first().hp


# ---------------------------------------------------------------------------
# Multiplier schedule - table-tested across 20 rounds for several rule sets.
# Every round is a tie (equal scores -> 0 damage), so HP never runs out no
# matter how large the multiplier grows - this isolates the multiplier
# schedule from the elimination/finish logic, which gets its own tests below.
# Each literal table was hand-derived from the recurrence in the module
# docstring above (also cross-checked with a scratch calculation, not by
# calling any app code) - not a re-implementation of duels.py's formula.
# ---------------------------------------------------------------------------

MULTI_SCHEDULES = [
    pytest.param(
        1, 1.0, 0.0, 1,
        [1.0] * 20,
        id="mult=1,add=0-stays-constant-forever",
    ),
    pytest.param(
        1, 1.5, 0.5, 1,
        [1.0, 2.0, 3.5, 5.75, 9.125, 14.1875, 21.78125, 33.171875, 50.257812, 75.886719,
         114.330078, 171.995117, 258.492676, 388.239014, 582.858521, 874.787781,
         1312.681671, 1969.522507, 2954.78376, 4432.67564],
        id="grows-geometrically-every-round-from-round-2",
    ),
    pytest.param(
        5, 2.0, 0.0, 3,
        [1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 4.0, 4.0, 4.0, 8.0, 8.0, 8.0,
         16.0, 16.0, 16.0, 32.0, 32.0, 32.0],
        id="gated-by-both-start-round-and-frequency",
    ),
    pytest.param(
        1, 1.0, 2.0, 2,
        [1.0, 3.0, 3.0, 5.0, 5.0, 7.0, 7.0, 9.0, 9.0, 11.0, 11.0, 13.0, 13.0, 15.0,
         15.0, 17.0, 17.0, 19.0, 19.0, 21.0],
        id="purely-additive-every-other-round",
    ),
]


@pytest.mark.parametrize("start_round,mult,add,freq,expected_multis", MULTI_SCHEDULES)
def test_multiplier_schedule_across_20_rounds(db_session, start_round, mult, add, freq, expected_multis):
    session, (team_a, team_b) = make_duels_session(
        damage_multi_start_round=start_round, damage_multi_mult=mult,
        damage_multi_add=add, damage_multi_freq=freq,
        max_rounds=-1, time_limit=-1, start_hp=100,
    )

    for round_number, expected_multi in enumerate(expected_multis, start=1):
        round_ = play_round(session, {team_a: 5000, team_b: 5000})
        assert round_.round_number == round_number
        assert round_.duels_state.multi == pytest.approx(expected_multi, rel=1e-6)
        # Tie every round: nobody ever takes damage.
        assert hp_after(round_, team_a) == 100
        assert hp_after(round_, team_b) == 100


# ---------------------------------------------------------------------------
# HP subtraction: scaled by the round's multiplier, floored, per team.
# ---------------------------------------------------------------------------

def test_hp_subtraction_scales_with_multiplier_and_floors_the_result(db_session):
    # Rule set "grows-geometrically-every-round-from-round-2" above gives
    # multi = 1.0, 2.0, 3.5 for rounds 1-3. A constant 7-point margin every
    # round means round 3's raw damage is 7 * 3.5 = 24.5 - the app's `//1`
    # floors that to 24, which is the specific thing this test pins (not
    # just "damage scales with the multiplier").
    session, (team_a, team_b) = make_duels_session(
        damage_multi_start_round=1, damage_multi_mult=1.5, damage_multi_add=0.5,
        damage_multi_freq=1, max_rounds=-1, time_limit=-1, start_hp=1000,
    )
    margin = 7
    expected_multis = [1.0, 2.0, 3.5]
    expected_damage = [7, 14, 24]  # floor(margin * multi), not round(...)
    hp_b = 1000

    for multi, damage in zip(expected_multis, expected_damage):
        round_ = play_round(session, {team_a: 5000, team_b: 5000 - margin})
        assert round_.duels_state.multi == pytest.approx(multi, rel=1e-6)
        hp_b -= damage
        assert hp_after(round_, team_a) == 1000  # the round's winner always takes 0 damage
        assert hp_after(round_, team_b) == hp_b


def test_tie_round_deals_no_damage_to_either_team(db_session):
    session, (team_a, team_b) = make_duels_session(start_hp=500)

    round_ = play_round(session, {team_a: 4200, team_b: 4200})

    assert hp_after(round_, team_a) == 500
    assert hp_after(round_, team_b) == 500


def test_team_with_no_guess_takes_full_highest_score_damage(db_session):
    # `all_guessed` can never become true here (team_b never guesses), so
    # this specific case has to close the round via the real timeout path
    # instead of play_round()'s all-guessed shortcut - hence freezegun and a
    # finite time_limit, unlike every other test in this file.
    session, (team_a, team_b) = make_duels_session(start_hp=5000, time_limit=10, guess_time_limit=5)

    with freeze_time("2024-01-01 12:00:00"):
        DuelsGame().next({}, None, session)
        round_ = Round.query.filter_by(session_id=session.id, round_number=1).first()
        duels_state = round_.duels_state
        user_a = team_a.players[0].user
        guess = Guess(user_id=user_a.id, round_id=round_.id, latitude=0.0, longitude=0.0,
                      distance=0.0, score=4321, time=1)
        db.session.add(guess)
        db.session.flush()
        DuelHp.query.filter_by(state_id=duels_state.id, team_id=team_a.id).first().guess_id = guess.id
        db.session.commit()
        # team_b deliberately never guesses and never plonks.

    with freeze_time("2024-01-01 12:00:20"):  # well past the 10s time_limit
        DuelsGame().update_state({"state": GameState.RESULTS}, session)

    assert hp_after(round_, team_a) == 5000  # winner, 0 damage
    assert hp_after(round_, team_b) == 5000 - 4321  # full highest_score, no discount
    assert Guess.query.filter_by(round_id=round_.id, user_id=team_b.players[0].user.id).count() == 0


# ---------------------------------------------------------------------------
# Elimination and game-over.
# ---------------------------------------------------------------------------

def test_zero_or_negative_hp_floors_at_zero_and_eliminates_the_team(db_session):
    session, (team_a, team_b) = make_duels_session(start_hp=100, max_rounds=-1, time_limit=-1)

    # Damage (150) exceeds team_b's remaining HP (100) - the raw subtraction
    # would go negative, but the app clamps it at 0.
    round_ = play_round(session, {team_a: 5000, team_b: 5000 - 150})
    assert hp_after(round_, team_a) == 100
    assert hp_after(round_, team_b) == 0

    # Advancing to what would be round 2 finds fewer than 2 teams with
    # hp > 0 in round 1, so it finishes the game instead of creating it.
    DuelsGame().next({}, None, session)

    assert Round.query.filter_by(session_id=session.id).count() == 1
    tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
    assert tracker.state == GameState.FINISHED
