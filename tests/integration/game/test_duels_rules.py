"""Duels rules configuration: set/get and validation against rules_config.

Driven through the real HTTP API for the party rules routes
(app/api/party/rules/routes.py, registered at /api/party/rules):
  * GET  /api/party/rules?code=<code>        -> DuelsGame.get_rules() dict
  * POST /api/party/rules {"code",...}       -> {"message": "rules updated"}
  * GET  /api/party/rules/config?code=<code> -> DuelsGame.rules_config_list()

set_rules()/get_rules()/rules_config() all live on DuelsGame
(app/api/game/games/duels.py), reached via `game_type[party.rules.type]`
where `party.rules.type` is already GameType.DUELS (tests.factories.make_party
defaults to it) - see test_duels_damage.py's module docstring for a detailed
read of that file if needed; this file only exercises rules, never a round.

check_rule()'s validation (basegame.py) used by both the base and duel rule
sets, confirmed by reading the source:
  - "min" is skipped when value == -1 (an explicit "no minimum" escape hatch)
  - value == -1 is only accepted at all when the rule sets "infinity": True
  - so a rule with no "infinity" flag (every duels-only key: hp, guess_time,
    multi_start, multi_mult, multi_add, mult_freq) rejects -1 outright, and
    rejects anything below its "min" other than -1.
"""

import pytest

from models.db import db
from models.duels import DuelRules
from models.party import PartyRules
from tests.factories import make_user
from tests.helpers import auth_header

# party_with_host lives in tests/integration/party/conftest.py, a sibling
# directory - pytest's conftest scoping only shares fixtures down a
# directory tree, not sideways, so it has to be imported explicitly here to
# be usable as a fixture in this file (a plain Python import; the function
# is already wrapped by @pytest.fixture in its home module).
from tests.integration.party.conftest import party_with_host

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _game_configs_for_every_test(game_configs):
    """DuelsGame.rules_config() (used by set_rules()/rules_config_list(),
    both exercised throughout this file) unconditionally reads several
    GAME_DEFAULT_*/DUELS_DEFAULT_* Configs rows to build its schema's
    "default" fields, even for a request that never uses those defaults."""
    return game_configs


def get_rules(client, user, party):
    return client.get(f"/api/party/rules?code={party.code}", headers=auth_header(user))


def set_rules(client, user, party, **fields):
    payload = {"code": party.code, "type": "duels", **fields}
    return client.post("/api/party/rules", json=payload, headers=auth_header(user))


def full_duels_payload(**overrides):
    """A complete, in-bounds payload for every rule set_rules() checks
    (base rules: rounds/time/nmpz; duel rules: hp/guess_time/multi_*) -
    check_rules() falls back to the party's *current* values for anything
    omitted, so a full payload here makes round-trip assertions unambiguous
    about which value came from where."""
    values = {
        "rounds": -1, "time": -1, "nmpz": True,
        "hp": 1234, "guess_time": 20,
        "multi_start": 2, "multi_mult": 1.5, "multi_add": 0.5, "mult_freq": 3,
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------

def test_set_rules_then_get_rules_round_trips(client, party_with_host):
    party, host = party_with_host

    response = set_rules(client, host, party, **full_duels_payload())
    assert response.status_code == 200, response.get_data(as_text=True)

    body = get_rules(client, host, party).get_json()
    assert body["type"] == "DUELS"
    assert body["team_type"] == "team"
    assert body["rounds"] == -1
    assert body["time"] == -1
    assert body["nmpz"] is True
    assert body["hp"] == 1234
    assert body["guess_time"] == 20
    assert body["multi_start"] == 2
    assert body["multi_mult"] == pytest.approx(1.5)
    assert body["multi_add"] == pytest.approx(0.5)
    assert body["mult_freq"] == 3


def test_set_rules_partial_update_keeps_other_fields(client, party_with_host):
    party, host = party_with_host

    first = set_rules(client, host, party, **full_duels_payload(hp=2000, mult_freq=2))
    assert first.status_code == 200, first.get_data(as_text=True)

    # Only change "hp" this time - check_rules() falls back to the party's
    # *current* duel_rules values for everything else omitted.
    second = set_rules(client, host, party, hp=3000)
    assert second.status_code == 200, second.get_data(as_text=True)

    body = get_rules(client, host, party).get_json()
    assert body["hp"] == 3000
    assert body["mult_freq"] == 2  # unchanged from the first call


def test_set_rules_persists_a_new_duel_rules_row(client, party_with_host):
    party, host = party_with_host
    before_id = PartyRules.query.filter_by(party_id=party.id).first().duel_rules_id

    response = set_rules(client, host, party, **full_duels_payload(hp=9999))
    assert response.status_code == 200, response.get_data(as_text=True)

    party_rules = PartyRules.query.filter_by(party_id=party.id).first()
    assert party_rules.duel_rules_id != before_id
    assert db.session.get(DuelRules, party_rules.duel_rules_id).start_hp == 9999


# ---------------------------------------------------------------------------
# out-of-bounds rejection (rules_config()'s min/max/infinity, via check_rule())
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,value,expected_error", [
    ("hp", 0, "Value for HP too low"),           # min=1, and 0 != -1 so the min check isn't skipped
    ("hp", -1, "Invalid value for HP"),          # -1 has no "infinity" escape hatch for hp
    ("mult_freq", 0, "Value for Multi Frequency too low"),
    ("multi_mult", 0.5, "Value for Multi Multiplier too low"),  # min=1
    ("multi_start", 0, "Value for Multi Start Round too low"),
    ("guess_time", -5, "Value for Time After Guess too low"),
])
def test_set_rules_rejects_values_out_of_rules_config_bounds(client, party_with_host, field, value, expected_error):
    party, host = party_with_host
    before_rules_id = PartyRules.query.filter_by(party_id=party.id).first().duel_rules_id

    response = set_rules(client, host, party, **full_duels_payload(**{field: value}))

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}

    # A rejected set_rules() call must not have persisted a new DuelRules row.
    after_rules_id = PartyRules.query.filter_by(party_id=party.id).first().duel_rules_id
    assert after_rules_id == before_rules_id


def test_set_rules_non_host_rejected(client, party_with_host):
    party, host = party_with_host
    stranger = make_user()

    response = set_rules(client, stranger, party, **full_duels_payload())

    assert response.status_code == 403
    assert response.get_json() == {"error": "You are not the host of this party"}


# ---------------------------------------------------------------------------
# BUG: omitting "type" from the set_rules payload crashes
# ---------------------------------------------------------------------------

def test_set_rules_without_type_field_crashes_documents_bug(client, party_with_host):
    """api/party/rules/routes.py's set_rules():

        base_rules = party.rules.base_rules
        type = GameType[data.get("type").upper()] if data.get("type") else base_rules.type

    `base_rules` is a BaseRules row (time_limit/max_rounds/nmpz/map_id) - it
    has no `type` attribute at all. So whenever "type" is omitted from the
    POST body (a natural thing to do for a rules-only update that isn't
    changing the game mode), this raises AttributeError instead of falling
    back to the party's current type as the code clearly intends. Every
    other test in this file works around it by always sending
    "type": "duels" explicitly. Documenting actual behavior; not fixing app
    code."""
    party, host = party_with_host

    payload = {"code": party.code, **full_duels_payload()}
    with pytest.raises(AttributeError):
        client.post("/api/party/rules", json=payload, headers=auth_header(host))


# ---------------------------------------------------------------------------
# rules/config shape (party-scoped; contrast with GET /api/game/rules/config
# which test_game_rules_and_state.py already covers for the non-party path)
# ---------------------------------------------------------------------------

def test_rules_config_endpoint_matches_duels_rules_config(client, party_with_host):
    party, host = party_with_host

    response = client.get(f"/api/party/rules/config?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    keys = {entry["key"] for entry in body}
    assert keys == {
        "rounds", "time", "nmpz", "hp", "guess_time",
        "multi_start", "multi_mult", "multi_add", "mult_freq",
    }
    by_key = {entry["key"]: entry for entry in body}
    assert by_key["hp"]["min"] == 1
    assert "infinity" not in by_key["hp"]
    assert by_key["rounds"]["infinity"] is True
