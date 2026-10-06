"""Concurrent crate purchases racing against a single user's coin balance.

Scope:
- Two concurrent buys should never both succeed when the user has coins for
  only one. They can today, because the balance is read without
  SELECT ... FOR UPDATE.
"""

import threading

import pytest

from models.cosmetics import Tier, UserCoins
from tests.factories import make_crate, make_user, make_user_coins
from tests.helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_two_concurrent_buys_with_coins_for_only_one_never_both_succeed_documents_bug(
    app, committed_db, monkeypatch
):
    """Two threads buying simultaneously with coins for exactly one purchase can both succeed today (pins the race)."""
    # Set up a user with coins for exactly one crate purchase, and a crate
    # whose roll always lands on "no item" (total_weight=2 but the only
    # CrateItem has weight=1, so a roll of 2 hits `if not item_rarity`) - that
    # keeps the race focused on the coins race, with no cosmetic-selection or
    # unique-constraint noise from both threads rolling the same item.
    user = make_user()
    make_user_coins(user, coins=100)
    crate = make_crate(price=100, items=[(Tier.COMMON, 1)])
    crate.total_weight = 2
    committed_db.commit()

    # Force the roll to land on "no item" (crate.total_weight, i.e. 2), and
    # make it rendezvous both threads on a barrier first. random.randint runs
    # after buy_crate has already read UserCoins and decremented the balance
    # in Python, but before it commits - so pausing both threads there
    # guarantees both read coins=100 before either thread's commit is visible
    # to the other. Target api.cosmetics.crates.routes.random.randint (rather
    # than random.randint via a different import path) so this keeps working
    # whether buy_crate calls it directly or via a helper like
    # roll_crate_item(items, total_weight) that also does `import random`
    # and calls random.randint - both resolve to the same random module
    # object.
    #
    # If the route is later fixed with `.with_for_update()` on the UserCoins
    # query, the second thread will block on that SELECT and never reach
    # randint at all, so only one thread would ever arrive at the barrier.
    # Catch BrokenBarrierError (raised on the lone waiter once its wait()
    # times out) so the test fails on a bad assertion instead of hanging.
    barrier = threading.Barrier(2, timeout=5)

    def racy_randint(a, b):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return 2

    monkeypatch.setattr("api.cosmetics.crates.routes.random.randint", racy_randint)

    # Resolve everything ORM-backed on the main thread (which holds the app
    # context committed_db pushed) before spawning workers: db.session
    # expires objects after commit, and touching an expired attribute from a
    # worker thread with no app context of its own would blow up with
    # "working outside of application context" instead of exercising the
    # race.
    crate_name = crate.name
    header = auth_header(user)

    results = [None, None]

    def worker(index):
        try:
            test_client = app.test_client()
            response = test_client.post(
                "/api/cosmetics/crates/buy",
                json={"crate": crate_name},
                headers=header,
            )
            results[index] = (response.status_code, None)
        except Exception as exc:  # noqa: BLE001 - we want to see any thread failure
            results[index] = (None, exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not any(thread.is_alive() for thread in threads), "a worker thread hung"

    exceptions = [exc for _status, exc in results if exc is not None]
    assert not exceptions, f"worker thread(s) raised: {exceptions}"

    statuses = sorted(status for status, _exc in results)

    # BUG: pins the current (buggy) behavior. Both requests see coins=100
    # before either commits, so both pass the `coins < price` check and both
    # succeed - the user gets two crates for the price of one, and the
    # balance goes negative-by-omission (clamped at 0 here since price==coins).
    # Correct behavior is exactly one 200 and one 403, with the final balance
    # left at 0 (only one purchase applied). Fix: take the UserCoins row with
    # `UserCoins.query.filter_by(user_id=user.id).with_for_update().first()`
    # in buy_crate so the second thread's read blocks until the first
    # thread's commit, and then re-checks a balance that already reflects the
    # first purchase.
    assert statuses == [200, 200]

    committed_db.expire_all()
    final_coins = UserCoins.query.filter_by(user_id=user.id).first()
    assert final_coins.coins == 0
