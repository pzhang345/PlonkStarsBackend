"""Pure-logic unit tests for BaseGame.check_rule / BaseGame.check_rules
(app/api/game/games/basegame.py:126 and :141).

Both methods are stateless validators - they don't touch self at all beyond
calling check_rule from check_rules. To instantiate BaseGame (an ABC with
several @abstractmethod hooks unrelated to rule validation) we define a
minimal local stub subclass implementing the abstract methods as no-ops.

check_rules() only touches `configs` (an explicit dict passed by the
caller) and `data`/`rules_default` - it never reaches into Configs/the DB
itself. rules_config() (a *different*, non-abstract method on BaseGame) is
the one that calls Configs.get(...) for its defaults - we avoid calling that
method entirely and instead build our own literal config dicts shaped like
its output, keeping these tests fully DB-free.
"""

import pytest

from api.game.games.basegame import BaseGame

pytestmark = pytest.mark.unit


class _StubGame(BaseGame):
    """Minimal concrete subclass - only rule validation is under test."""

    def next(self, data, user, session):
        pass

    def get_round(self, data, user, session):
        pass

    def guess(self, data, user, session):
        pass

    def results(self, data, user, session):
        pass

    def summary(self, data, user, session):
        pass

    def get_state(self, data, user, session):
        pass


@pytest.fixture
def game():
    return _StubGame()


# Literal stand-ins for the shape BaseGame.rules_config() normally builds
# from Configs.get(...) - same keys/semantics, no DB involved.
ROUNDS_RULE = {"name": "Number of Rounds", "type": "integer", "min": 5, "max": 20, "default": 10}
TIME_RULE = {
    "name": "Time Limit", "type": "integer", "min": 5, "max": 300,
    "infinity": True, "default": 60,
}
NMPZ_RULE = {"name": "NMPZ", "type": "boolean", "default": False}
CONFIGS = {"rounds": ROUNDS_RULE, "time": TIME_RULE, "nmpz": NMPZ_RULE}


# ---------------------------------------------------------------------------
# check_rule
# ---------------------------------------------------------------------------

def test_check_rule_accepts_value_within_range(game):
    assert game.check_rule(ROUNDS_RULE, 10) is None


def test_check_rule_rejects_value_below_min(game):
    with pytest.raises(Exception, match="Value for Number of Rounds too low"):
        game.check_rule(ROUNDS_RULE, 3)


def test_check_rule_rejects_value_above_max(game):
    with pytest.raises(Exception, match="Value for Number of Rounds too high"):
        game.check_rule(ROUNDS_RULE, 25)


def test_check_rule_rejects_negative_one_sentinel_when_infinity_not_allowed(game):
    # -1 is exempted from the "too low" check specifically, but then caught
    # by the final "must not be -1 unless infinity" check instead.
    with pytest.raises(Exception, match="Invalid value for Number of Rounds"):
        game.check_rule(ROUNDS_RULE, -1)


def test_check_rule_accepts_negative_one_sentinel_when_infinity_allowed(game):
    assert game.check_rule(TIME_RULE, -1) is None


def test_check_rule_accepts_time_rule_within_normal_range(game):
    assert game.check_rule(TIME_RULE, 60) is None


@pytest.mark.parametrize(
    "rule,value",
    [
        (ROUNDS_RULE, 3.5),  # type "integer" but a float
        (ROUNDS_RULE, "10"),  # type "integer" but a string
        (NMPZ_RULE, 1),  # type "boolean" but an int (non-bool)
        (NMPZ_RULE, "true"),  # type "boolean" but a string
    ],
)
def test_check_rule_rejects_type_mismatch(game, rule, value):
    with pytest.raises(Exception, match=f"Invalid value for {rule['name']}"):
        game.check_rule(rule, value)


def test_check_rule_bool_is_treated_as_int_for_integer_type():
    # Documented actual (surprising) behavior: Python's bool is a subclass of
    # int, so isinstance(True, int) is True - an "integer"-typed rule does
    # NOT reject a bool value on the type check. It still gets caught by the
    # min check here since True == 1 < 5.
    game = _StubGame()
    with pytest.raises(Exception, match="Value for Number of Rounds too low"):
        game.check_rule(ROUNDS_RULE, True)


# ---------------------------------------------------------------------------
# check_rules
# ---------------------------------------------------------------------------

def test_check_rules_maps_rule_names_to_db_names_using_provided_values(game):
    data = {"rounds": 15, "time": 90, "nmpz": True}
    values = game.check_rules(
        data, CONFIGS, ["rounds", "time", "nmpz"], ["max_rounds", "time_limit", "nmpz"]
    )
    assert values == {"max_rounds": 15, "time_limit": 90, "nmpz": True}


def test_check_rules_falls_back_to_config_defaults_when_data_missing_keys(game):
    values = game.check_rules(
        {}, CONFIGS, ["rounds", "time", "nmpz"], ["max_rounds", "time_limit", "nmpz"]
    )
    assert values == {"max_rounds": 10, "time_limit": 60, "nmpz": False}


def test_check_rules_uses_explicit_rules_default_over_config_defaults(game):
    # rules_default overrides the configs[...]["default"] lookup entirely.
    values = game.check_rules(
        {}, CONFIGS, ["rounds", "nmpz"], ["max_rounds", "nmpz"], rules_default=[7, True]
    )
    assert values == {"max_rounds": 7, "nmpz": True}


def test_check_rules_partial_override_leaves_other_fields_at_default(game):
    data = {"rounds": 12}
    values = game.check_rules(
        data, CONFIGS, ["rounds", "time", "nmpz"], ["max_rounds", "time_limit", "nmpz"]
    )
    assert values == {"max_rounds": 12, "time_limit": 60, "nmpz": False}


def test_check_rules_propagates_check_rule_exception_and_message(game):
    data = {"rounds": 999}  # above max
    with pytest.raises(Exception, match="Value for Number of Rounds too high"):
        game.check_rules(
            data, CONFIGS, ["rounds", "time", "nmpz"], ["max_rounds", "time_limit", "nmpz"]
        )


def test_check_rules_stops_at_first_invalid_field(game):
    # "rounds" is validated before "time" (rule_names order), so an invalid
    # first field raises before the second field is ever looked at - a
    # bogus/impossible "time" value here would never surface as an error.
    data = {"rounds": 999, "time": 99999}
    with pytest.raises(Exception, match="Number of Rounds"):
        game.check_rules(
            data, CONFIGS, ["rounds", "time"], ["max_rounds", "time_limit"]
        )


def test_check_rules_allows_time_limit_never_expire_sentinel(game):
    data = {"time": -1}
    values = game.check_rules(
        data, CONFIGS, ["rounds", "time", "nmpz"], ["max_rounds", "time_limit", "nmpz"]
    )
    assert values["time_limit"] == -1
