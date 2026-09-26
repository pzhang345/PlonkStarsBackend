"""Fixtures for tests/integration/party/.

- party_with_host: a Party row with one host member (DUELS-typed rules row,
  pointing at a plain unbounded map - see tests.factories.make_party - since
  most party-route tests never need to actually generate a round; a test
  that does should replace party.rules.base_rule_id/duel_rules_id with rows
  built from tests.factories.make_bounded_map()/make_duel_rules() first).
- party_with_members: party_with_host plus three joined non-host members.
- two_team_party: party_with_members split across two teams (2 members
  each), ready for a duel - DuelsGame.create() requires at least 2 teams.
- game_configs: seeded Configs rows (GAME_DEFAULT_*/DUELS_DEFAULT_*) that
  POST /api/party/create and the rules routes (set_default_rules,
  DuelsGame.rules_config, etc.) read via Configs.get(...). Copied verbatim
  from tests/integration/game/conftest.py, per the task brief, since a
  file-local conftest can't see a sibling directory's fixtures.
"""

import json
from pathlib import Path

import pytest

from models.configs import Configs
from models.db import db
from tests.factories import make_party, make_party_member, make_team, make_user

_CONFIGS_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "configs_default.json"


@pytest.fixture()
def game_configs(db_session):
    values = json.loads(_CONFIGS_DEFAULT_PATH.read_text())
    seeded = {}
    for entry in values:
        db.session.add(Configs(key=entry["key"], value=entry["value"]))
        seeded[entry["key"]] = entry["value"]
    db.session.commit()
    return seeded


@pytest.fixture()
def party_with_host(db_session):
    host = make_user()
    party = make_party(host=host)
    return party, host


@pytest.fixture()
def party_with_members(party_with_host):
    party, host = party_with_host
    members = [make_user() for _ in range(3)]
    for member in members:
        make_party_member(party, member)
    return party, host, members


@pytest.fixture()
def two_team_party(party_with_members):
    party, host, members = party_with_members
    teammate, opponent, opponent_teammate = members

    team_a = make_team(party, users=[host, teammate], leader=host, name="Team A")
    team_b = make_team(party, users=[opponent, opponent_teammate], leader=opponent, name="Team B")

    return {
        "party": party,
        "host": host,
        "team_a": team_a,
        "team_a_users": [host, teammate],
        "team_b": team_b,
        "team_b_users": [opponent, opponent_teammate],
    }
