"""Pure-logic unit tests for map location sampling helpers.

Scope: weighted bound selection and in-bounds checks - the underlying
pure-logic sampling helpers used by generate_location, as opposed to the
integration/map/* route tests that exercise it end-to-end.

No DB/app/network needed: `get_random_bounds` (app/api/location/generate.py)
is exercised with `MapBound` stubbed out to a plain in-memory list (it's only
ever used for `MapBound.query.filter_by(map_id=...).all()`), so the weighted
selection arithmetic can be tested with no real database. `randomize` is
pure arithmetic over a bound-like object and needs no stubbing at all.
"""

import random
from types import SimpleNamespace

import pytest

import api.location.generate as generate_module
from api.location.generate import get_random_bounds, randomize

pytestmark = pytest.mark.unit


class _FakeQuery:
    """Stand-in for `MapBound.query`: returns a fixed list of fake
    "map bound" rows regardless of the filter_by() kwargs, so
    get_random_bounds can be driven with no DB at all."""

    def __init__(self, bounds):
        self._bounds = bounds

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self._bounds


def _patch_bounds(monkeypatch, bounds):
    """Replace api.location.generate.MapBound with a stub exposing only the
    `.query.filter_by(...).all()` surface get_random_bounds actually uses."""
    monkeypatch.setattr(generate_module, "MapBound", SimpleNamespace(query=_FakeQuery(bounds)))


def _patch_uniform(monkeypatch, value):
    """Force random.uniform(0, total_weight) inside get_random_bounds to
    always return a fixed, known value."""
    monkeypatch.setattr(generate_module.random, "uniform", lambda a, b: value)


def _map_bound(weight, bound):
    """A fake MapBound row: get_random_bounds only ever reads .weight and
    returns .bound, so any sentinel works for `bound`."""
    return SimpleNamespace(weight=weight, bound=bound)


# ---------------------------------------------------------------------------
# Weighted selection
# ---------------------------------------------------------------------------

def test_bound_selection_is_weighted_by_bound_weight(monkeypatch):
    """get_random_bounds walks the bound list, subtracting each weight from
    the draw until it goes negative. With weights 1, 2, 3 (total 6) that
    gives bound A the slice [0, 1), bound B [1, 3), and bound C [3, 6) -
    i.e. each bound's share of the draw is exactly proportional to its
    weight."""
    bound_a, bound_b, bound_c = "A", "B", "C"
    bounds = [_map_bound(1, bound_a), _map_bound(2, bound_b), _map_bound(3, bound_c)]
    _patch_bounds(monkeypatch, bounds)
    fake_map = SimpleNamespace(id=1, total_weight=6)

    cases = [
        (0.0, bound_a),
        (0.999, bound_a),
        (1.0, bound_b),
        (2.999, bound_b),
        (3.0, bound_c),
        (5.999, bound_c),
    ]
    for draw, expected in cases:
        _patch_uniform(monkeypatch, draw)
        assert get_random_bounds(fake_map) == expected


def test_zero_weight_bound_is_never_selected(monkeypatch):
    """A bound with weight 0 contributes an empty interval to the draw
    (subtracting 0 never makes the running total go negative), so no value
    of random.uniform(0, total_weight) can ever land on it - verified by
    sweeping the entire draw range in fine steps."""
    bound_a, bound_zero, bound_c = "A", "ZERO", "C"
    bounds = [_map_bound(1, bound_a), _map_bound(0, bound_zero), _map_bound(3, bound_c)]
    _patch_bounds(monkeypatch, bounds)
    fake_map = SimpleNamespace(id=1, total_weight=4)

    picks = set()
    draw = 0.0
    while draw < 4.0:
        _patch_uniform(monkeypatch, draw)
        picks.add(get_random_bounds(fake_map))
        draw += 0.01

    assert bound_zero not in picks
    assert picks == {bound_a, bound_c}


# ---------------------------------------------------------------------------
# In-bounds sampling
# ---------------------------------------------------------------------------

def test_sampled_point_falls_within_the_bound_lat_lon_range():
    """randomize() draws a uniform point whose latitude and longitude both
    stay within the bound's start/end range."""
    bound = SimpleNamespace(
        start_latitude=10.0, end_latitude=20.0,
        start_longitude=-5.0, end_longitude=5.0,
    )
    random.seed(12345)
    for _ in range(200):
        lat, lng = randomize(bound)
        assert 10.0 <= lat <= 20.0
        assert -5.0 <= lng <= 5.0


def test_sampled_point_on_a_degenerate_point_bound_equals_that_point():
    """A degenerate bound (start == end corner, used for single-point
    locations) always samples exactly that point since uniform(x, x) == x."""
    bound = SimpleNamespace(
        start_latitude=42.0, end_latitude=42.0,
        start_longitude=-71.0, end_longitude=-71.0,
    )
    random.seed(1)
    lat, lng = randomize(bound)
    assert lat == 42.0
    assert lng == -71.0
