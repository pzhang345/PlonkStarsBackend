"""Fixtures for tests/integration/game/.

- game_configs: seeded Configs rows that game/session code depends on,
  loaded from tests/data/configs_default.json. Covers both the
  GAME_DEFAULT_*/DUELS_DEFAULT_* keys BaseGame/ChallengeGame/DuelsGame read
  for their rules_config()/check_rules() defaults (see basegame.py,
  duels.py), AND the DUELS_DEFAULT_START_HP key POST /api/party/create reads
  for the same value under a different name (api/party/routes.py) - both are
  seeded so either code path works. test_challenge_game.py and
  test_game_rules_and_state.py each still define their own smaller, file-
  local `game_configs`/`duels_configs` fixtures (predating this one); a
  file-local fixture of the same name shadows this one for that file, so
  there's no conflict.
- started_challenge: not implemented - no Phase 2 duels test needs it, left
  as a TODO for whichever future test does.
"""

import json
from pathlib import Path

import pytest

from models.configs import Configs
from models.db import db

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


# TODO: implement started_challenge fixture (an already-started challenge game).
