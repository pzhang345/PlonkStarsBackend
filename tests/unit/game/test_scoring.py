"""Pure-logic unit tests for api/game/gameutils.py:
- caculate_score(distance, max_distance, max_score)  (note: real typo in prod code)
- timed_out(start_time, time_limit)

No DB/network/app context needed for either function.
"""

import math
from datetime import datetime

import pytest
import pytz
from freezegun import freeze_time

from api.game.gameutils import caculate_score, timed_out

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# caculate_score
# ---------------------------------------------------------------------------

def test_caculate_score_zero_distance_is_exactly_max_score():
    assert caculate_score(0, 1000, 5000) == 5000
    assert caculate_score(0, 1, 1) == 1


@pytest.mark.parametrize("max_distance,max_score", [(1000, 5000), (1, 100), (20000, 1)])
def test_caculate_score_is_monotonically_decreasing(max_distance, max_score):
    # Fractions of max_distance rather than fixed absolute distances, so this
    # holds regardless of scale - and capped at 2x max_distance so none of
    # the resulting scores underflow to an indistinguishable 0.0.
    fractions = [0, 0.01, 0.1, 0.5, 1, 2]
    distances = [f * max_distance for f in fractions]
    scores = [caculate_score(d, max_distance, max_score) for d in distances]
    assert scores == sorted(scores, reverse=True)
    # strictly decreasing (no ties) since e**x is strictly monotonic
    assert len(set(scores)) == len(scores)


def test_caculate_score_decay_value_at_distance_equals_max_distance():
    # distance == max_distance -> exponent is exactly -10, independent of the
    # magnitude of max_distance itself.
    assert caculate_score(500, 500, 1000) == pytest.approx(1000 * math.e ** -10)
    assert caculate_score(500, 500, 1000) == pytest.approx(0.0453999, rel=1e-4)


@pytest.mark.parametrize("scale", [2, 10, 0.5, -1])
def test_caculate_score_scales_linearly_with_max_score(scale):
    base = caculate_score(250, 1000, 100)
    scaled = caculate_score(250, 1000, 100 * scale)
    assert scaled == pytest.approx(base * scale)


def test_caculate_score_far_beyond_max_distance_underflows_to_zero_not_error():
    # exponent becomes hugely negative; math.e ** (very negative) underflows
    # to 0.0 silently rather than raising OverflowError/ValueError.
    result = caculate_score(10_000_000, 1000, 5000)
    assert result == pytest.approx(0.0, abs=1e-12)
    assert result == 0.0


def test_caculate_score_max_distance_zero_raises_zero_division_error():
    # Documented actual behavior: -10*distance/max_distance divides by zero
    # whenever max_distance == 0, regardless of distance (0/0 also raises
    # ZeroDivisionError for floats/ints in Python, it does not produce NaN).
    with pytest.raises(ZeroDivisionError):
        caculate_score(100, 0, 5000)
    with pytest.raises(ZeroDivisionError):
        caculate_score(0, 0, 5000)


# ---------------------------------------------------------------------------
# timed_out
# ---------------------------------------------------------------------------
# Reads carefully: `time_limit != -1 and pytz.utc.localize(start_time) +
# timedelta(seconds=time_limit) < datetime.now(tz=pytz.utc)`.
# pytz.utc.localize() requires a NAIVE datetime (raises ValueError if the
# passed datetime is already tz-aware), so start_time must be naive.
# time_limit == -1 short-circuits the `and` before start_time is even
# touched, so it never times out no matter what start_time is.

def test_timed_out_never_expires_with_negative_one_sentinel():
    # start_time isn't even evaluated due to short-circuiting - pass an
    # obviously-expired naive datetime to prove that.
    start = datetime(2000, 1, 1)
    assert timed_out(start, -1) is False


@freeze_time("2024-06-15 12:00:00")
def test_timed_out_false_when_not_yet_expired():
    start = datetime(2024, 6, 15, 11, 59, 0)  # 60s before "now"
    assert timed_out(start, 120) is False  # would expire at 12:01:00


@freeze_time("2024-06-15 12:00:00")
def test_timed_out_true_when_expired():
    start = datetime(2024, 6, 15, 11, 55, 0)  # 5 minutes before "now"
    assert timed_out(start, 60) is True  # expired at 11:56:00


@freeze_time("2024-06-15 12:00:00")
def test_timed_out_false_exactly_at_boundary():
    # start + time_limit lands exactly on "now" -> comparison is strict `<`,
    # so the exact boundary instant is NOT considered timed out.
    start = datetime(2024, 6, 15, 11, 58, 0)  # exactly 120s before "now"
    assert timed_out(start, 120) is False


@freeze_time("2024-06-15 12:00:00")
def test_timed_out_true_one_microsecond_past_boundary():
    start = datetime(2024, 6, 15, 11, 58, 0)
    assert timed_out(start, 119) is True  # deadline at 11:59:59, before "now"


def test_timed_out_raises_value_error_on_timezone_aware_start_time():
    # Documented actual behavior: passing an already tz-aware start_time
    # blows up inside pytz.utc.localize (not a graceful False/error message).
    aware_start = datetime(2024, 6, 15, 11, 58, 0, tzinfo=pytz.utc)
    with pytest.raises(ValueError):
        timed_out(aware_start, 60)
