"""Pure-logic unit tests for the crate weighted-roll boundaries.

Scope (shared with integration/cosmetics/test_crates_shop.py):
- Weighted roll: patch `random.randint` to 1, to `total_weight`, and to each
  cumulative boundary, and assert the picked tier each time.
- A total_weight greater than the sum of item weights (as crate creation
  allows) can roll past every item and return None.
- `random.randint` is always called with `(1, total_weight)`.

No DB/app/network needed - pure arithmetic over a crate's weight table. The
routes module is imported directly (no Flask app/context required) to prove
it's importable standalone.
"""

import types

import pytest

from api.cosmetics.crates.routes import roll_crate_item

pytestmark = pytest.mark.unit


def _items(weights):
    return [types.SimpleNamespace(tier=f"tier{i}", weight=w) for i, w in enumerate(weights)]


WEIGHTS = [50, 30, 15, 5]


def test_roll_picks_first_tier_when_randint_returns_one(monkeypatch):
    """Patching random.randint to always return 1 lands in the first tier."""
    items = _items(WEIGHTS)
    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: 1)

    result = roll_crate_item(items, sum(WEIGHTS))

    assert result is items[0]


def test_roll_picks_last_tier_when_randint_returns_total_weight(monkeypatch):
    """Patching random.randint to return total_weight lands in the last tier."""
    items = _items(WEIGHTS)
    total_weight = sum(WEIGHTS)
    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: total_weight)

    result = roll_crate_item(items, total_weight)

    assert result is items[-1]


@pytest.mark.parametrize("boundary_index", range(len(WEIGHTS)))
def test_roll_picks_correct_tier_at_each_cumulative_weight_boundary(monkeypatch, boundary_index):
    """Patching random.randint to each tier's cumulative boundary (c_i) picks
    that tier, and c_i + 1 picks the next tier (except at the very last
    boundary, where c_i + 1 has nothing further to roll into)."""
    items = _items(WEIGHTS)
    total_weight = sum(WEIGHTS)
    cumulative = 0
    for i in range(boundary_index + 1):
        cumulative += WEIGHTS[i]

    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: cumulative)
    assert roll_crate_item(items, total_weight) is items[boundary_index]

    if boundary_index + 1 < len(items):
        monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: cumulative + 1)
        assert roll_crate_item(items, total_weight) is items[boundary_index + 1]


def test_roll_past_sum_of_weights_returns_none(monkeypatch):
    """total_weight greater than the sum of item weights (as make_crate_item
    without updating total_weight, or manual crate editing, can produce) lets
    the roll land past every item, in which case there's no match."""
    items = _items(WEIGHTS)
    total_weight = sum(WEIGHTS) + 10
    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", lambda a, b: total_weight)

    result = roll_crate_item(items, total_weight)

    assert result is None


def test_roll_calls_randint_with_one_and_total_weight():
    items = _items(WEIGHTS)
    total_weight = sum(WEIGHTS)
    calls = []

    import api.cosmetics.crates.routes as routes_module

    original_randint = routes_module.random.randint

    def spy(a, b):
        calls.append((a, b))
        return original_randint(a, b)

    routes_module.random.randint = spy
    try:
        roll_crate_item(items, total_weight)
    finally:
        routes_module.random.randint = original_randint

    assert calls == [(1, total_weight)]


def test_empty_items_returns_none():
    assert roll_crate_item([], 10) is None
