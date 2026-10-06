"""Party rules routes: GET/POST per game type.

Scope:
- Rules: GET/POST per game type, validated against rules_config.

Route shapes confirmed by reading app/api/party/rules/routes.py and
app/api/game/games/{duels,party_game,basegame}.py:
  * GET  ""        -> game_type[party.rules.type].get_rules(party, data);
                       for DUELS this includes "team_type":"team" plus the
                       duel-specific keys (hp, multi_start, ...).
  * POST ""        -> host-only (403 otherwise). If "type" is given and
                       differs from the party's current type, it switches
                       type and applies THAT type's *default* rules
                       (set_default_rules) rather than the posted values;
                       otherwise it applies set_rules() with the posted
                       values, validated against rules_config() via
                       BaseGame.check_rule (min/max/type checks).
                       BUG: when "type" is omitted entirely, the route does
                       `base_rules.type` to fall back to the current type -
                       but BaseRules (models/session.py) has no `type`
                       column at all, so every POST /party/rules call that
                       doesn't include "type" raises an unhandled
                       AttributeError (a real 500 in production; the test
                       client re-raises it directly since TESTING=True).
                       Every other test below therefore always passes
                       "type" explicitly to reach the working code path.
  * GET  /config   -> rules_config_list(): a list of {"key": ..., **rule}.
"""

import pytest

from tests.factories import make_user
from tests.helpers import auth_header, demo_header
from models.session import GameType

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/party/rules?code=AAAA", None),
    ("post", "/api/party/rules", {"code": "AAAA"}),
    ("get", "/api/party/rules/config?code=AAAA", None),
])
def test_rules_routes_reject_anonymous_and_demo_callers_with_403(client, method, path, body):
    call = getattr(client, method)
    kwargs = {} if body is None else {"json": body}

    assert call(path, **kwargs).status_code == 403
    assert call(path, headers=demo_header(), **kwargs).status_code == 403


# ---------------------------------------------------------------------------
# GET rules
# ---------------------------------------------------------------------------

def test_get_rules_returns_current_rules_for_the_game_type(client, party_with_host, game_configs):
    party, host = party_with_host  # make_party() defaults to GameType.DUELS

    response = client.get(f"/api/party/rules?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    assert body["type"] == "DUELS"
    assert body["team_type"] == "team"
    assert body["hp"] == party.rules.duel_rules.start_hp
    assert body["rounds"] == party.rules.base_rules.max_rounds
    assert body["time"] == party.rules.base_rules.time_limit


def test_get_rules_unknown_code_returns_404(client):
    user = make_user()

    response = client.get("/api/party/rules?code=ZZZZ", headers=auth_header(user))

    assert response.status_code == 404


def test_rules_config_returns_a_list_of_rule_definitions(client, party_with_host, game_configs):
    party, host = party_with_host

    response = client.get(f"/api/party/rules/config?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    keys = {entry["key"] for entry in body}
    # DUELS-specific rules_config() extends BaseGame's rounds/time/nmpz.
    assert {"rounds", "time", "nmpz", "hp", "multi_start", "multi_mult", "multi_add", "mult_freq", "guess_time"} <= keys


# ---------------------------------------------------------------------------
# POST rules
# ---------------------------------------------------------------------------

def test_post_rules_updates_the_rules_for_the_game_type(client, party_with_host, game_configs):
    party, host = party_with_host

    response = client.post(
        "/api/party/rules",
        json={"code": party.code, "type": "duels", "hp": 1234, "rounds": 10, "time": 30, "nmpz": False},
        headers=auth_header(host),
    )

    assert response.status_code == 200
    from models.db import db
    db.session.refresh(party.rules)
    assert party.rules.duel_rules.start_hp == 1234
    assert party.rules.base_rules.max_rounds == 10
    assert party.rules.base_rules.time_limit == 30


def test_post_rules_without_type_field_crashes_documents_bug(client, party_with_host, game_configs):
    """BUG: omitting "type" makes set_rules() do `base_rules.type`, and
    BaseRules has no such column - AttributeError propagates straight out
    of the view function (TESTING=True re-raises it into the test instead of
    turning it into an HTTP response, which is exactly what would otherwise
    be an unhandled 500 in production)."""
    party, host = party_with_host

    with pytest.raises(AttributeError):
        client.post(
            "/api/party/rules",
            json={"code": party.code, "hp": 1234},
            headers=auth_header(host),
        )


def test_post_rules_requires_host(client, party_with_members, game_configs):
    party, host, members = party_with_members

    response = client.post(
        "/api/party/rules",
        json={"code": party.code, "hp": 1234},
        headers=auth_header(members[0]),
    )

    assert response.status_code == 403


def test_post_rules_rejects_values_outside_rules_config(client, party_with_host, game_configs):
    """hp's rules_config entry has min=1 (and no "infinity" flag), so 0 is
    rejected by BaseGame.check_rule()."""
    party, host = party_with_host
    original_hp = party.rules.duel_rules.start_hp

    response = client.post(
        "/api/party/rules",
        json={"code": party.code, "type": "duels", "hp": 0},
        headers=auth_header(host),
    )

    assert response.status_code == 400
    from models.db import db
    db.session.refresh(party.rules)
    assert party.rules.duel_rules.start_hp == original_hp


def test_post_rules_rejects_wrong_type(client, party_with_host, game_configs):
    party, host = party_with_host

    response = client.post(
        "/api/party/rules",
        json={"code": party.code, "type": "duels", "hp": "not-a-number"},
        headers=auth_header(host),
    )

    assert response.status_code == 400


def test_post_rules_switching_type_applies_the_new_types_defaults(client, party_with_host, game_configs):
    """Switching "type" applies the target type's *defaults*
    (set_default_rules), not the posted rule values - posting hp alongside a
    type change has no effect since HP isn't part of set_default_rules()."""
    party, host = party_with_host
    assert party.rules.type == GameType.DUELS

    response = client.post(
        "/api/party/rules",
        json={"code": party.code, "type": "live"},
        headers=auth_header(host),
    )

    assert response.status_code == 200
    from models.db import db
    db.session.refresh(party.rules)
    assert party.rules.type == GameType.LIVE
    assert party.rules.base_rules.max_rounds == int(game_configs["GAME_DEFAULT_ROUNDS"])


def test_post_rules_unknown_code_returns_404(client):
    user = make_user()

    response = client.post("/api/party/rules", json={"code": "ZZZZ"}, headers=auth_header(user))

    assert response.status_code == 404
