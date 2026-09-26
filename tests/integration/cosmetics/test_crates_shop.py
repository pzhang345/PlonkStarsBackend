"""Crate buying, refunds, and the shop listing.

Scope (TESTING_PLAN.md section 2 comment: "buy, refunds, insufficient coins,
shop" and section 3 Phase 1, shared with unit/game/test_crate_roll.py):
- Buying a crate with enough coins subtracts crate.price, grants a
  CosmeticsOwnership, and returns the new balance.
- Not enough coins returns 403 (body key is "message", not "error") and
  leaves the balance unchanged.
- An unknown crate name returns 404.
- Rolling a duplicate cosmetic refunds by the dupe_refund[tier] table, adds
  no second ownership row, and nets -price + refund.
- A rolled tier with no cosmetics refunds and returns a message, tier name,
  and refund/coins.
- A roll that lands past every item in the crate (total_weight greater than
  the sum of item weights) still charges the price and returns just
  {"coins": ...} - no item_rarity, so no refund at all.
- A user with no UserCoins row hits an AttributeError (`_documents_bug`);
  correct behavior would be a clean 4xx or treating it as 0 coins.
- Unauthenticated buy returns 403.
- GET /crates/shop response has the documented shape, ordered by price.

The roll is made deterministic throughout by monkeypatching
`api.cosmetics.crates.routes.random.randint`, and each crate under test is
built with exactly one cosmetic per tier (the route picks a random cosmetic
within a tier via `ORDER BY random()`, which we don't otherwise control).
"""

import pytest

from models.cosmetics import Cosmetics, CosmeticsOwnership, Tier, UserCoins
from api.cosmetics.crates.routes import dupe_refund
from tests.factories import make_cosmetic, make_crate, make_ownership, make_user, make_user_coins
from tests.helpers import assert_json_error, auth_header

pytestmark = pytest.mark.integration

BUY_URL = "/api/cosmetics/crates/buy"
SHOP_URL = "/api/cosmetics/crates/shop"


def _force_roll(monkeypatch, value):
    """Force random.randint(1, total_weight) to always return `value`."""
    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: value)


def _buy(client, user, crate_name):
    return client.post(BUY_URL, json={"crate": crate_name}, headers=auth_header(user))


# ---------------------------------------------------------------------------
# Successful buy
# ---------------------------------------------------------------------------

def test_buy_crate_with_enough_coins_updates_balance_and_response(client, monkeypatch):
    user = make_user()
    coins = make_user_coins(user=user, coins=1000)
    cosmetic = make_cosmetic(tier=Tier.COMMON)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    _force_roll(monkeypatch, 1)  # lands in the only item -> COMMON

    response = _buy(client, user, crate.name)

    assert response.status_code == 200
    body = response.get_json()
    assert body["coins"] == 900
    assert body["cosmetic"] == cosmetic.to_json()

    db_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert db_coins.coins == 900
    assert db_coins is coins or db_coins.id == coins.id


def test_buy_crate_with_enough_coins_grants_a_cosmetics_ownership_row(client, monkeypatch):
    user = make_user()
    make_user_coins(user=user, coins=1000)
    cosmetic = make_cosmetic(tier=Tier.COMMON)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    _force_roll(monkeypatch, 1)

    response = _buy(client, user, crate.name)

    assert response.status_code == 200
    ownership = CosmeticsOwnership.query.filter_by(user_id=user.id, cosmetics_id=cosmetic.id).first()
    assert ownership is not None


# ---------------------------------------------------------------------------
# Insufficient coins
# ---------------------------------------------------------------------------

def test_buy_crate_with_insufficient_coins_returns_403_and_keeps_balance(client, monkeypatch):
    user = make_user()
    make_user_coins(user=user, coins=50)
    make_cosmetic(tier=Tier.COMMON)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    _force_roll(monkeypatch, 1)

    response = _buy(client, user, crate.name)

    assert response.status_code == 403
    body = response.get_json()
    assert body == {"message": "Not enough coins to purchase this crate"}

    db_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert db_coins.coins == 50
    assert CosmeticsOwnership.query.filter_by(user_id=user.id).count() == 0


# ---------------------------------------------------------------------------
# Unknown crate
# ---------------------------------------------------------------------------

def test_buy_unknown_crate_name_returns_404(client):
    user = make_user()
    make_user_coins(user=user, coins=1000)

    response = _buy(client, user, "does-not-exist")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Duplicate roll
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", [Tier.COMMON, Tier.RARE, Tier.LEGENDARY])
def test_rolling_a_duplicate_cosmetic_refunds_and_keeps_one_ownership_row(client, monkeypatch, tier):
    user = make_user()
    make_user_coins(user=user, coins=1000)
    cosmetic = make_cosmetic(tier=tier)
    make_ownership(user, cosmetic)  # user already owns the only cosmetic in this tier
    crate = make_crate(price=100, items=[(tier, 1)])
    _force_roll(monkeypatch, 1)

    response = _buy(client, user, crate.name)

    assert response.status_code == 200
    body = response.get_json()
    refund = dupe_refund[tier]
    assert body["refund"] == refund
    assert body["cosmetic"] == cosmetic.to_json()

    db_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert db_coins.coins == 1000 - 100 + refund
    assert body["coins"] == db_coins.coins
    assert CosmeticsOwnership.query.filter_by(user_id=user.id, cosmetics_id=cosmetic.id).count() == 1


# ---------------------------------------------------------------------------
# Rolled tier with no cosmetics
# ---------------------------------------------------------------------------

def test_rolled_tier_with_no_items_refunds_and_returns_tier_name(client, monkeypatch):
    user = make_user()
    make_user_coins(user=user, coins=1000)
    # No cosmetic created for RARE at all.
    crate = make_crate(price=100, items=[(Tier.RARE, 1)])
    _force_roll(monkeypatch, 1)

    response = _buy(client, user, crate.name)

    assert response.status_code == 200
    body = response.get_json()
    refund = dupe_refund[Tier.RARE]
    assert body["tier"] == Tier.RARE.name
    assert body["refund"] == refund
    assert "message" in body

    db_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert db_coins.coins == 1000 - 100 + refund
    assert body["coins"] == db_coins.coins


# ---------------------------------------------------------------------------
# Roll lands past all items
# ---------------------------------------------------------------------------

def test_roll_past_all_items_still_charges_price_with_no_refund(client, monkeypatch):
    """total_weight > sum(item weights) (e.g. via make_crate_item without
    updating total_weight, or a stale total_weight after crate edits) lets
    the roll land past every item. roll_crate_item then returns None, so
    buy_crate short-circuits straight to `{"coins": ...}` with the price
    already deducted and NO refund of any kind - unlike the "tier with no
    cosmetics" case above, which does refund. This looks like unintended
    inconsistency: a roll that misses every tier is treated worse (no
    refund) than a roll that hits an empty tier (dupe_refund applied). We
    are only pinning current behavior, not asserting it's correct."""
    user = make_user()
    make_user_coins(user=user, coins=1000)
    make_cosmetic(tier=Tier.COMMON)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    crate.total_weight = 100  # inflate past the sum of item weights (1)
    from models.db import db
    db.session.commit()
    _force_roll(monkeypatch, 100)  # roll to the max, past the only item's weight

    response = _buy(client, user, crate.name)

    assert response.status_code == 200
    body = response.get_json()
    assert set(body.keys()) == {"coins"}
    assert body["coins"] == 900

    db_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert db_coins.coins == 900
    assert CosmeticsOwnership.query.filter_by(user_id=user.id).count() == 0


# ---------------------------------------------------------------------------
# Missing UserCoins row
# ---------------------------------------------------------------------------

def test_buy_crate_with_no_user_coins_row_documents_bug(client, monkeypatch):
    # BUG: buy_crate does `UserCoins.query.filter_by(user_id=user.id).first()`
    # with no None-check, then immediately does `user_coins.coins < crate.price`
    # -> AttributeError on None.coins. Correct behavior would be a clean 4xx
    # or treating the user as having 0 coins. Documenting actual behavior
    # rather than fixing app code. TESTING is True, so the exception
    # propagates out of client.post(...) instead of becoming a 500 response.
    user = make_user()
    # No make_user_coins() call - no UserCoins row exists for this user.
    make_cosmetic(tier=Tier.COMMON)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    _force_roll(monkeypatch, 1)

    with pytest.raises(AttributeError):
        _buy(client, user, crate.name)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_buy_crate_unauthenticated_returns_403(client):
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])

    response = client.post(BUY_URL, json={"crate": crate.name})

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


def test_get_crates_shop_unauthenticated_returns_403(client):
    response = client.get(SHOP_URL)

    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# GET /crates/shop shape
# ---------------------------------------------------------------------------

def test_get_crates_shop_response_has_expected_shape(client):
    user = make_user()
    cheap = make_crate(name="cheap-crate", price=50, description="cheap", image="cheap.png",
                        items=[(Tier.COMMON, 3), (Tier.RARE, 1)])
    pricey = make_crate(name="pricey-crate", price=500, description="pricey", image="pricey.png",
                         items=[(Tier.LEGENDARY, 1)])

    response = client.get(SHOP_URL, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body, list)
    assert len(body) == 2
    # ordered by price ascending
    assert [entry["name"] for entry in body] == ["cheap-crate", "pricey-crate"]

    cheap_entry = body[0]
    assert cheap_entry["name"] == "cheap-crate"
    assert cheap_entry["description"] == "cheap"
    assert cheap_entry["image"] == "cheap.png"
    assert cheap_entry["price"] == 50
    items_by_tier = {item["tier"]: item["weight"] for item in cheap_entry["items"]}
    assert items_by_tier == {"COMMON": 3 / 4, "RARE": 1 / 4}

    pricey_entry = body[1]
    assert pricey_entry["name"] == "pricey-crate"
    assert pricey_entry["price"] == 500
    assert pricey_entry["items"] == [{"tier": "LEGENDARY", "weight": 1.0}]
