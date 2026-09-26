"""Admin route behavior: configs, cosmetics/crates, coins, score recalculation.

All requests in this file are made as an admin (`admin_header`), so
`app/api/admin/routes.py`'s `if not user.is_admin` guard never fires here -
that's covered separately in test_admin_authz.py.

A few of these tests are `_documents_bug` tests: they pin genuinely buggy
current behavior (found while writing this suite) rather than the intended
behavior, per this repo's testing convention. Each has a `# BUG:` comment
pointing at the offending line in app/api/admin/routes.py.
"""

import pytest

from models.configs import Configs
from models.cosmetics import Cosmetic_Type, Cosmetics, Tier, UserCoins, UserCosmetics
from models.crates import Crate, CrateItem
from models.session import BaseRules, Guess
from models.stats import MapStats, UserMapStats
from tests.factories import (
    make_base_rules,
    make_map,
    make_round,
    make_session,
    make_user,
    make_user_coins,
    make_user_cosmetics,
)
from models.db import db

pytestmark = pytest.mark.integration


def _make_guess(user, round_, score=100, distance=10.0, time=5, latitude=0.0, longitude=0.0):
    guess = Guess(
        user_id=user.id,
        round_id=round_.id,
        latitude=latitude,
        longitude=longitude,
        distance=distance,
        score=score,
        time=time,
    )
    db.session.add(guess)
    db.session.commit()
    return guess


# ---------------------------------------------------------------------------
# configs/set, configs/get
# ---------------------------------------------------------------------------

def test_configs_set_then_get_round_trips(client, admin_header):
    resp = client.post(
        "/api/admin/configs/set",
        json={"key": "max_players", "value": "10"},
        headers=admin_header,
    )
    assert resp.status_code == 200

    resp = client.get("/api/admin/configs/get", query_string={"key": "max_players"}, headers=admin_header)
    assert resp.status_code == 200
    assert resp.get_json() == {"value": "10"}


def test_configs_set_on_existing_key_updates_it(client, admin_header):
    client.post("/api/admin/configs/set", json={"key": "feature_flag", "value": "off"}, headers=admin_header)
    resp = client.post("/api/admin/configs/set", json={"key": "feature_flag", "value": "on"}, headers=admin_header)
    assert resp.status_code == 200

    assert Configs.query.filter_by(key="feature_flag").count() == 1
    resp = client.get("/api/admin/configs/get", query_string={"key": "feature_flag"}, headers=admin_header)
    assert resp.get_json() == {"value": "on"}


def test_configs_get_unknown_key_returns_404(client, admin_header):
    resp = client.get("/api/admin/configs/get", query_string={"key": "does_not_exist"}, headers=admin_header)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Config not found"


def test_configs_set_missing_key_and_value_documents_bug(client, admin_header):
    """BUG (app/api/admin/routes.py:set_config): `key = str(data.get("key"))`
    and `value = str(data.get("value"))` turn a *missing* key/value into the
    literal string "None" (since str(None) == "None"), which is truthy - so
    `if not key or not value: return 400` can never actually fire. A request
    with no key/value at all succeeds and silently stores a config literally
    named "None"."""
    before = Configs.query.count()

    resp = client.post("/api/admin/configs/set", json={}, headers=admin_header)

    assert resp.status_code == 200
    assert Configs.query.count() == before + 1
    config = Configs.query.filter_by(key="None").first()
    assert config is not None
    assert config.value == "None"


# ---------------------------------------------------------------------------
# cosmetic/add
# ---------------------------------------------------------------------------

def test_cosmetic_add_creates_the_cosmetic(client, admin_header):
    resp = client.post(
        "/api/admin/cosmetic/add",
        json={
            "image": "top_hat.png",
            "item_name": "Top Hat",
            "type": "hat",
            "tier": "rare",
            "top_position": 1.5,
            "left_position": 2.5,
            "scale": 1.2,
        },
        headers=admin_header,
    )
    assert resp.status_code == 200

    cosmetic = Cosmetics.query.filter_by(image="top_hat.png").first()
    assert cosmetic is not None
    assert cosmetic.item_name == "Top Hat"
    assert cosmetic.type == Cosmetic_Type.HAT
    assert cosmetic.tier == Tier.RARE
    assert cosmetic.top_position == 1.5
    assert cosmetic.left_position == 2.5
    assert cosmetic.scale == 1.2


def test_cosmetic_add_same_image_updates_instead_of_duplicating(client, admin_header):
    client.post(
        "/api/admin/cosmetic/add",
        json={"image": "visor.png", "item_name": "Visor", "type": "face", "tier": "common"},
        headers=admin_header,
    )
    before = Cosmetics.query.count()

    resp = client.post(
        "/api/admin/cosmetic/add",
        json={"image": "visor.png", "item_name": "Golden Visor", "type": "face", "tier": "legendary"},
        headers=admin_header,
    )
    assert resp.status_code == 200

    assert Cosmetics.query.count() == before
    cosmetic = Cosmetics.query.filter_by(image="visor.png").first()
    assert cosmetic.item_name == "Golden Visor"
    assert cosmetic.tier == Tier.LEGENDARY


# ---------------------------------------------------------------------------
# crate/add
# ---------------------------------------------------------------------------

def test_crate_add_integer_weights_sum_into_total_weight(client, admin_header):
    resp = client.post(
        "/api/admin/crate/add",
        json={
            "name": "starter_crate",
            "price": 100,
            "items": [
                {"tier": "common", "weight": 70},
                {"tier": "rare", "weight": 30},
            ],
        },
        headers=admin_header,
    )
    assert resp.status_code == 200

    crate = Crate.query.filter_by(name="starter_crate").first()
    assert crate is not None
    assert crate.total_weight == 100

    items = {item.tier: item.weight for item in CrateItem.query.filter_by(crate_id=crate.id).all()}
    assert items == {Tier.COMMON: 70, Tier.RARE: 30}


def test_crate_add_decimal_weights_are_scaled_by_max_decimals(client, admin_header):
    resp = client.post(
        "/api/admin/crate/add",
        json={
            "name": "decimal_crate",
            "price": 50,
            "items": [
                {"tier": "common", "weight": 0.5},
                {"tier": "rare", "weight": 1.25},
            ],
        },
        headers=admin_header,
    )
    assert resp.status_code == 200

    crate = Crate.query.filter_by(name="decimal_crate").first()
    assert crate.total_weight == 175

    items = {item.tier: item.weight for item in CrateItem.query.filter_by(crate_id=crate.id).all()}
    assert items == {Tier.COMMON: 50, Tier.RARE: 125}


def test_crate_add_item_without_tier_adds_weight_but_no_crate_item(client, admin_header):
    resp = client.post(
        "/api/admin/crate/add",
        json={
            "name": "mystery_crate",
            "price": 20,
            "items": [
                {"tier": "common", "weight": 70},
                {"weight": 30},
            ],
        },
        headers=admin_header,
    )
    assert resp.status_code == 200

    crate = Crate.query.filter_by(name="mystery_crate").first()
    assert crate.total_weight == 100
    assert CrateItem.query.filter_by(crate_id=crate.id).count() == 1


def test_crate_add_duplicate_name_returns_400(client, admin_header):
    client.post(
        "/api/admin/crate/add",
        json={"name": "dup_crate", "price": 10, "items": [{"tier": "common", "weight": 1}]},
        headers=admin_header,
    )
    before = Crate.query.count()

    resp = client.post(
        "/api/admin/crate/add",
        json={"name": "dup_crate", "price": 999, "items": [{"tier": "epic", "weight": 5}]},
        headers=admin_header,
    )

    assert resp.status_code == 400
    assert Crate.query.count() == before


def test_crate_add_missing_price_or_items_returns_400(client, admin_header):
    before = Crate.query.count()

    resp_no_price = client.post(
        "/api/admin/crate/add",
        json={"name": "no_price_crate", "items": [{"tier": "common", "weight": 1}]},
        headers=admin_header,
    )
    assert resp_no_price.status_code == 400

    resp_no_items = client.post(
        "/api/admin/crate/add",
        json={"name": "no_items_crate", "price": 10},
        headers=admin_header,
    )
    assert resp_no_items.status_code == 400

    assert Crate.query.count() == before


# ---------------------------------------------------------------------------
# coins/init
# ---------------------------------------------------------------------------

def test_coins_init_creates_zero_balance_for_users_without_one(client, admin_header, admin_user):
    user = make_user()

    resp = client.post("/api/admin/coins/init", json={}, headers=admin_header)
    assert resp.status_code == 200

    user_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert user_coins is not None
    assert user_coins.coins == 0


def test_coins_init_leaves_existing_balance_untouched(client, admin_header):
    user = make_user()
    make_user_coins(user, coins=500)

    resp = client.post("/api/admin/coins/init", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCoins.query.filter_by(user_id=user.id).first().coins == 500


def test_coins_init_is_idempotent_no_duplicates(client, admin_header):
    user = make_user()

    client.post("/api/admin/coins/init", json={}, headers=admin_header)
    resp = client.post("/api/admin/coins/init", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCoins.query.filter_by(user_id=user.id).count() == 1


def test_coins_init_skips_the_demo_user(client, admin_header):
    demo_user = make_user(username="demo")

    resp = client.post("/api/admin/coins/init", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCoins.query.filter_by(user_id=demo_user.id).first() is None


# ---------------------------------------------------------------------------
# usercosmetics/initialize
# ---------------------------------------------------------------------------

def test_usercosmetics_initialize_creates_missing_rows(client, admin_header):
    user = make_user()

    resp = client.post("/api/admin/usercosmetics/initialize", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCosmetics.query.filter_by(user_id=user.id).first() is not None


def test_usercosmetics_initialize_skips_the_demo_user(client, admin_header):
    demo_user = make_user(username="demo")

    resp = client.post("/api/admin/usercosmetics/initialize", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCosmetics.query.filter_by(user_id=demo_user.id).first() is None


def test_usercosmetics_initialize_leaves_existing_rows_alone(client, admin_header):
    user = make_user()
    existing = make_user_cosmetics(user, hue=42, saturation=99, brightness=88)

    resp = client.post("/api/admin/usercosmetics/initialize", json={}, headers=admin_header)
    assert resp.status_code == 200

    assert UserCosmetics.query.filter_by(user_id=user.id).count() == 1
    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.id == existing.id
    assert refreshed.hue == 42
    assert refreshed.saturation == 99
    assert refreshed.brightness == 88


# ---------------------------------------------------------------------------
# scores/recalculate
# ---------------------------------------------------------------------------

@pytest.fixture()
def score_scenario(db_session):
    """Two users x two maps, including one nmpz base rule and a demo-user
    guess that must be excluded from every total.

    map1 (nmpz=False): u1 scores 100/10/5, u2 scores 80/20/8
    map1 (nmpz=True):  u1 scores 90/15/6
    map2 (nmpz=False): u2 scores 70/25/10
    demo guesses on map1 (nmpz=False): score 999/1/1 - must be excluded
    """
    u1 = make_user()
    u2 = make_user()
    demo_user = make_user(username="demo")

    map1 = make_map()
    map2 = make_map()

    rules1 = make_base_rules(game_map=map1, nmpz=False)
    rules1_nmpz = make_base_rules(game_map=map1, nmpz=True)
    rules2 = make_base_rules(game_map=map2, nmpz=False)

    session1 = make_session(host=u1, base_rules=rules1)
    session1_nmpz = make_session(host=u1, base_rules=rules1_nmpz)
    session2 = make_session(host=u2, base_rules=rules2)

    round1 = make_round(session=session1, base_rules=rules1)
    round1_nmpz = make_round(session=session1_nmpz, base_rules=rules1_nmpz)
    round2 = make_round(session=session2, base_rules=rules2)

    _make_guess(u1, round1, score=100, distance=10, time=5)
    _make_guess(u2, round1, score=80, distance=20, time=8)
    _make_guess(u1, round1_nmpz, score=90, distance=15, time=6)
    _make_guess(u2, round2, score=70, distance=25, time=10)
    _make_guess(demo_user, round1, score=999, distance=1, time=1)

    return {
        "u1": u1,
        "u2": u2,
        "demo_user": demo_user,
        "map1": map1,
        "map2": map2,
    }


def test_scores_recalculate_produces_expected_map_stats(client, admin_header, score_scenario):
    map1 = score_scenario["map1"]
    map2 = score_scenario["map2"]

    resp = client.post("/api/admin/scores/recalculate", headers=admin_header)
    assert resp.status_code == 200

    map1_false = MapStats.query.filter_by(map_id=map1.id, nmpz=False).first()
    assert map1_false is not None
    assert map1_false.total_score == 180
    assert map1_false.total_distance == 30
    assert map1_false.total_time == 13
    assert map1_false.total_guesses == 2

    map1_true = MapStats.query.filter_by(map_id=map1.id, nmpz=True).first()
    assert map1_true is not None
    assert map1_true.total_score == 90
    assert map1_true.total_distance == 15
    assert map1_true.total_time == 6
    assert map1_true.total_guesses == 1

    map2_false = MapStats.query.filter_by(map_id=map2.id, nmpz=False).first()
    assert map2_false is not None
    assert map2_false.total_score == 70
    assert map2_false.total_distance == 25
    assert map2_false.total_time == 10
    assert map2_false.total_guesses == 1


def test_scores_recalculate_produces_expected_user_map_stats(client, admin_header, score_scenario):
    u1 = score_scenario["u1"]
    u2 = score_scenario["u2"]
    map1 = score_scenario["map1"]
    map2 = score_scenario["map2"]

    resp = client.post("/api/admin/scores/recalculate", headers=admin_header)
    assert resp.status_code == 200

    u1_map1_false = UserMapStats.query.filter_by(user_id=u1.id, map_id=map1.id, nmpz=False).first()
    assert u1_map1_false.total_score == 100
    assert u1_map1_false.total_distance == 10
    assert u1_map1_false.total_time == 5
    assert u1_map1_false.total_guesses == 1

    u2_map1_false = UserMapStats.query.filter_by(user_id=u2.id, map_id=map1.id, nmpz=False).first()
    assert u2_map1_false.total_score == 80
    assert u2_map1_false.total_distance == 20
    assert u2_map1_false.total_time == 8
    assert u2_map1_false.total_guesses == 1

    u1_map1_true = UserMapStats.query.filter_by(user_id=u1.id, map_id=map1.id, nmpz=True).first()
    assert u1_map1_true.total_score == 90
    assert u1_map1_true.total_distance == 15
    assert u1_map1_true.total_time == 6
    assert u1_map1_true.total_guesses == 1

    u2_map2_false = UserMapStats.query.filter_by(user_id=u2.id, map_id=map2.id, nmpz=False).first()
    assert u2_map2_false.total_score == 70
    assert u2_map2_false.total_distance == 25
    assert u2_map2_false.total_time == 10
    assert u2_map2_false.total_guesses == 1

    # demo guesses never produce a UserMapStats row
    demo_user = score_scenario["demo_user"]
    assert UserMapStats.query.filter_by(user_id=demo_user.id).first() is None


def test_scores_recalculate_deletes_stale_user_map_stats_with_no_guesses(client, admin_header, score_scenario):
    u2 = score_scenario["u2"]
    map1 = score_scenario["map1"]

    # u2 never guessed on map1 with nmpz=True - a leftover row here has no
    # backing guesses and should be deleted by the recalculation.
    stale = UserMapStats(
        user_id=u2.id, map_id=map1.id, nmpz=True,
        total_score=1, total_guesses=1, total_time=1, total_distance=1,
    )
    db.session.add(stale)
    db.session.commit()
    stale_id = stale.id

    resp = client.post("/api/admin/scores/recalculate", headers=admin_header)
    assert resp.status_code == 200

    assert db.session.get(UserMapStats, stale_id) is None


def test_scores_recalculate_is_idempotent(client, admin_header, score_scenario):
    map1 = score_scenario["map1"]

    client.post("/api/admin/scores/recalculate", headers=admin_header)
    first_total = MapStats.query.filter_by(map_id=map1.id, nmpz=False).first().total_score

    resp = client.post("/api/admin/scores/recalculate", headers=admin_header)
    assert resp.status_code == 200

    second_total = MapStats.query.filter_by(map_id=map1.id, nmpz=False).first().total_score
    assert second_total == first_total == 180


def test_scores_recalculate_with_map_id_filter_documents_bug(client, admin_header, score_scenario):
    """BUG (app/api/admin/routes.py:recalculate_scores): when a `map_id`
    filter is passed in the request body, guesses are filtered by
    `GameMap.uuid == map_id` (the map's *string* uuid column) while the
    MapStats reset query is filtered by `MapStats.map_id == map_id` (the
    map's *integer* primary key) - `map_query.filter_by(map_id=map_id)` vs
    `all_scores.filter(GameMap.uuid == map_id)`. The only `map_id` a caller
    can plausibly obtain from MapStats/UserMapStats rows is the integer
    primary key, but binding that integer against the `uuid` varchar column
    isn't just wrong, it's not even valid SQL on Postgres: comparing
    `character varying = integer` has no operator, so the query raises
    `psycopg2.errors.UndefinedFunction` instead of returning zero rows.
    Every filtered recalculate() call crashes."""
    map1 = score_scenario["map1"]

    with pytest.raises(Exception) as exc_info:
        client.post("/api/admin/scores/recalculate", json={"id": map1.id}, headers=admin_header)
    assert "operator does not exist" in str(exc_info.value)


# ---------------------------------------------------------------------------
# rules/config
# ---------------------------------------------------------------------------

def test_rules_config_crashes_on_existing_sessions_documents_bug(client, admin_header):
    """BUG (app/api/admin/routes.py:reconfig_rules): the view reads
    `session.time_limit`, `session.nmpz`, `session.max_rounds`, and
    `session.map_id` directly off a `Session` row, but none of those columns
    exist on `Session` (models/session.py) - they live on `BaseRules`
    (reachable via `session.base_rules.time_limit` etc.). Any call to this
    route while at least one Session row exists raises AttributeError, which
    - because TESTING=True propagates unhandled exceptions - surfaces
    straight out of the test client instead of a 500 response."""
    make_session()

    with pytest.raises(AttributeError):
        client.post("/api/admin/rules/config", json={}, headers=admin_header)
