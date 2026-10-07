"""Full duels game flow, driven through a two-team party.

Route shapes exercised (confirmed by reading the source, not guessed):
  * POST /api/party/game/start {"code"} -> {"message":"session started"}
      - host-only; requires party.rules.type == DUELS and >= 2 PartyTeam
        rows (DuelsGame.create()); creates the Session, then synchronously
        calls DuelsGame.next(...) to open round 1 (GUESSING) before
        responding - so round 1 is already live by the time this returns.
  * GET  /api/game/state?id=..   -> DuelsGame.get_state() (see duels.py) -
        while GUESSING: {"state","round","multi","start_hp","guess_count",
        "max_guesses","teams":[{...,"hp"}],"user","spectating","can_guess",
        ["plonks","guesses"]}; while RESULTS: {"state","next_round","now"};
        auto-advances the state machine on the caller's behalf when the
        current phase has timed out (RESULTS -> GUESSING after 5s, always;
        GUESSING -> RESULTS if the round's own time_limit elapsed).
  * POST /api/game/guess {"id","lat","lng"} -> {"message":"guess added"} -
        DuelsGame.guess(): once every player on a still-alive team has
        guessed this round, the round closes to RESULTS synchronously, in
        the same request as the last guess.
  * GET  /api/game/results?id=.. -> DuelsGame.results(): {"lat","lng",
        "start_hp","round_number","multi","teams":[{"team","prev_hp","hp",
        "guesses":[...]}]} (teams ordered by hp desc) - only valid while
        RESULTS.
  * GET  /api/game/summary?id=.. -> DuelsGame.summary(): {"teams":[...],
        "start_hp","rounds":[...],"map_bounds"} - only valid once FINISHED;
        `teams` is ordered by `max(round_number) desc, min(hp) desc`, so a
        team still alive through the final round outranks one eliminated
        earlier, and among survivors the highest final HP sorts first.
  * POST /api/game/plonk {"id","lat","lng"} -> provisional marker.

Unlike CHALLENGE/LIVE, DuelsGame.next() raises if called with a real user -
it's *never* reachable through POST /api/game/next (that always 400s for a
DUELS session; see test_game_rules_and_state.py's
test_live_and_duels_types_not_creatable_via_create_route sibling fact for
LIVE/DUELS not being create-able there either). Rounds only ever advance
automatically: RESULTS -> GUESSING happens via GET /api/game/state's own
5-second timeout check, or via the very first `next()` call folded into
POST /api/party/game/start.

Celery is mocked throughout (api.game.games.duels.update_game_state/
stop_current_task, imported by name into duels.py) so no Celery/redis is
touched; every round in this file uses time_limit=-1 (infinite) unless a
test is specifically about timing out, and round transitions are driven via
freezegun + the real state endpoint, per the task's own guidance.
"""

from datetime import timedelta

import pytest
from freezegun import freeze_time

from api.game.games.duels import DuelsGame
from models.db import db
from models.session import GameState, GameStateTracker, GameType, Guess, PlayerPlonk, Session
from tests.factories import make_base_rules, make_bounded_map, make_duel_rules
from tests.helpers import auth_header

# two_team_party (and the fixtures it depends on) lives in
# tests/integration/party/conftest.py, a sibling directory - pytest only
# shares conftest fixtures down a directory tree, not sideways, so the whole
# dependency chain is imported explicitly here (plain Python imports; each
# function is already wrapped by @pytest.fixture in its home module. All
# three have to be imported, not just the leaf: pytest resolves
# two_team_party's own `party_with_members` argument by name from this
# module's fixture closure, which only includes fixtures actually visible
# here).
from tests.integration.party.conftest import party_with_host, party_with_members, two_team_party

pytestmark = pytest.mark.integration

LOCATION_LAT = 42.0
LOCATION_LNG = -71.0
MAX_DISTANCE = 1000.0


@pytest.fixture(autouse=True)
def _mock_celery(monkeypatch):
    monkeypatch.setattr("api.game.games.duels.update_game_state", lambda *a, **k: None)
    monkeypatch.setattr("api.game.games.duels.stop_current_task", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    return street_view_mock


# ---------------------------------------------------------------------------
# Local setup/HTTP helpers
# ---------------------------------------------------------------------------

def configure_duels(party, start_hp=6000, time_limit=-1, max_rounds=-1, guess_time_limit=5,
                     damage_multi_start_round=1, damage_multi_mult=1.0, damage_multi_add=0.0,
                     damage_multi_freq=1):
    """two_team_party's default rules point at a blank, unbounded map (see
    tests.factories.make_party) - swap in a real bounded map (so rounds can
    actually generate via street_view_mock) and duel rules sized for a fast
    test."""
    game_map = make_bounded_map(lat=LOCATION_LAT, lng=LOCATION_LNG, max_distance=MAX_DISTANCE)
    base_rules = make_base_rules(game_map=game_map, time_limit=time_limit, max_rounds=max_rounds, nmpz=False)
    duel_rules = make_duel_rules(
        start_hp=start_hp,
        damage_multi_start_round=damage_multi_start_round,
        damage_multi_mult=damage_multi_mult,
        damage_multi_add=damage_multi_add,
        damage_multi_freq=damage_multi_freq,
        guess_time_limit=guess_time_limit,
    )
    party.rules.base_rule_id = base_rules.id
    party.rules.duel_rules_id = duel_rules.id
    db.session.commit()
    return base_rules, duel_rules


def start_duel(client, host, party):
    response = client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(host))
    assert response.status_code == 200, response.get_data(as_text=True)
    session = Session.query.filter_by(host_id=host.id, type=GameType.DUELS).order_by(Session.id.desc()).first()
    return session.uuid


def get_state(client, user, session_uuid):
    return client.get(f"/api/game/state?id={session_uuid}", headers=auth_header(user))


def submit_guess(client, user, session_uuid, lat, lng):
    return client.post("/api/game/guess", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def do_plonk(client, user, session_uuid, lat, lng):
    return client.post("/api/game/plonk", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def get_results(client, user, session_uuid):
    return client.get(f"/api/game/results?id={session_uuid}", headers=auth_header(user))


def get_summary(client, user, session_uuid):
    return client.get(f"/api/game/summary?id={session_uuid}", headers=auth_header(user))


def team_entry(results_or_summary_teams, users):
    usernames = {u.username for u in users}
    for entry in results_or_summary_teams:
        if set(entry["team"]["members"]) == usernames:
            return entry
    raise AssertionError(f"no team with members {usernames} in {results_or_summary_teams}")


def guess_all(client, users, session_uuid, lat, lng):
    for user in users:
        response = submit_guess(client, user, session_uuid, lat, lng)
        assert response.status_code == 200, response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Full flow: two-team party -> start -> repeated rounds -> one team hits 0 HP
# -> summary shows the winner.
# ---------------------------------------------------------------------------

def test_full_duel_flow_ends_with_summary_showing_the_winning_team(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    team_a_users = two_team_party["team_a_users"]
    team_b_users = two_team_party["team_b_users"]

    configure_duels(party, start_hp=6000)

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        session_uuid = start_duel(client, host, party)

        round_number = 1
        hp_b_previous = None
        while True:
            state = get_state(client, host, session_uuid).get_json()
            assert state["state"] == "GUESSING"
            assert state["round"] == round_number

            # Team A always guesses the exact spot (max score); team B
            # always guesses several degrees off (a real, haversine-computed,
            # substantial score deficit) - the last of these 4 HTTP guesses
            # auto-closes the round to RESULTS in the same request.
            guess_all(client, team_a_users, session_uuid, LOCATION_LAT, LOCATION_LNG)
            guess_all(client, team_b_users, session_uuid, LOCATION_LAT + 5, LOCATION_LNG + 5)

            state = get_state(client, host, session_uuid).get_json()
            assert state["state"] == "RESULTS"

            results = get_results(client, host, session_uuid).get_json()
            entry_a = team_entry(results["teams"], team_a_users)
            entry_b = team_entry(results["teams"], team_b_users)

            assert entry_a["hp"] == 6000  # team A has the top score every round: 0 damage
            if hp_b_previous is not None:
                assert entry_b["hp"] < hp_b_previous  # team B strictly loses HP every round
            hp_b_previous = entry_b["hp"]

            # RESULTS is shown for 5s before GET /api/game/state auto-advances.
            frozen_time.tick(timedelta(seconds=10))

            if entry_b["hp"] == 0:
                state = get_state(client, host, session_uuid).get_json()
                assert state["state"] == "FINISHED"
                break

            round_number += 1
            # Guard against an unbounded loop if the scenario is ever
            # mis-tuned (team B should die in well under this many rounds).
            assert round_number <= 20

        summary = get_summary(client, host, session_uuid).get_json()
        assert set(summary["teams"][0]["team"]["members"]) == {u.username for u in team_a_users}
        winner_rounds = summary["teams"][0]["rounds"]
        loser_rounds = summary["teams"][1]["rounds"]
        assert winner_rounds[-1]["hp"] == 6000
        assert loser_rounds[-1]["hp"] == 0
        assert len(winner_rounds) == len(loser_rounds) == round_number


# ---------------------------------------------------------------------------
# update_state: legal transitions only.
# ---------------------------------------------------------------------------

def test_update_state_finished_from_guessing_is_a_no_op(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    configure_duels(party, start_hp=6000)
    session_uuid = start_duel(client, host, party)
    session = Session.query.filter_by(uuid=session_uuid).first()

    tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
    assert tracker.state == GameState.GUESSING

    DuelsGame().update_state({"state": GameState.FINISHED}, session)

    db.session.refresh(tracker)
    assert tracker.state == GameState.GUESSING  # FINISHED only ever applies from RESULTS


def test_update_state_guessing_from_results_advances_to_the_next_round(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    team_a_users = two_team_party["team_a_users"]
    team_b_users = two_team_party["team_b_users"]
    configure_duels(party, start_hp=6000)
    session_uuid = start_duel(client, host, party)
    session = Session.query.filter_by(uuid=session_uuid).first()

    guess_all(client, team_a_users, session_uuid, LOCATION_LAT, LOCATION_LNG)
    guess_all(client, team_b_users, session_uuid, LOCATION_LAT + 5, LOCATION_LNG + 5)

    tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
    assert tracker.state == GameState.RESULTS
    assert session.current_round == 1

    DuelsGame().update_state({"state": GameState.GUESSING}, session)

    db.session.refresh(tracker)
    assert tracker.state == GameState.GUESSING
    assert session.current_round == 2  # next() ran and created round 2


# ---------------------------------------------------------------------------
# Late guess after the round has ended is rejected.
# ---------------------------------------------------------------------------

def test_late_guess_after_round_ends_is_rejected(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    team_a_users = two_team_party["team_a_users"]
    team_b_users = two_team_party["team_b_users"]
    configure_duels(party, start_hp=6000)
    session_uuid = start_duel(client, host, party)

    guess_all(client, team_a_users, session_uuid, LOCATION_LAT, LOCATION_LNG)
    guess_all(client, team_b_users, session_uuid, LOCATION_LAT + 5, LOCATION_LNG + 5)

    state = get_state(client, host, session_uuid).get_json()
    assert state["state"] == "RESULTS"

    response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)

    assert response.status_code == 400
    assert response.get_json() == {"error": "Game is in the wrong state"}


# ---------------------------------------------------------------------------
# Plonk then timeout becomes a Guess with the plonk coords.
# ---------------------------------------------------------------------------

def test_plonk_followed_by_timeout_is_recorded_as_a_guess(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    configure_duels(party, start_hp=6000, time_limit=15, guess_time_limit=5)

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        session_uuid = start_duel(client, host, party)
        session = Session.query.filter_by(uuid=session_uuid).first()
        round_ = session.rounds[0]

        plonk_lat, plonk_lng = LOCATION_LAT + 0.01, LOCATION_LNG + 0.01
        response = do_plonk(client, host, session_uuid, plonk_lat, plonk_lng)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).count() == 1
        # Nobody actually guesses - the round can only close via timeout.

        frozen_time.tick(timedelta(seconds=20))  # past the 15s time_limit

        state = get_state(client, host, session_uuid).get_json()
        assert state["state"] == "RESULTS"

    guess = Guess.query.filter_by(user_id=host.id, round_id=round_.id).first()
    assert guess is not None
    assert guess.latitude == pytest.approx(plonk_lat)
    assert guess.longitude == pytest.approx(plonk_lng)
    assert guess.time == 15  # clamped to the round's time_limit
    assert PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).count() == 0
