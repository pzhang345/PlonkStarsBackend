# Known bugs

These are bugs the test suite has found but not fixed yet. Each entry points to
the test that pins the current (buggy) behavior. Those tests are named
`..._documents_bug`, or they have a `# BUG:` comment.

**How to fix a bug:** change the app code, turn its pinning test into a normal
assertion of the correct behavior, and delete the entry from this file.

**How to add a bug:** add an entry under the right area with its location, its
symptom, the suggested fix, and the pinning test.

App config has `TESTING=True`, so a "crash" below means the exception
propagates out of the test client. In production the same crash is an
unhandled 500.

---

## Cosmetics and crates

### Crate purchases can double-spend (race condition)
- **Where:** `app/api/cosmetics/crates/routes.py`, `buy_crate`
- **Symptom:** The code reads `UserCoins` without a row lock. When two buys run at the same time, both requests pass the `coins < price` check, and the user gets two crates for the price of one.
- **Fix:** `UserCoins.query.filter_by(user_id=user.id).with_for_update().first()`
- **Pinned by:** `tests/concurrency/test_crate_double_spend.py::test_two_concurrent_buys_with_coins_for_only_one_never_both_succeed_documents_bug`
- **Priority:** High, use fix above.

### Buying a crate with no `UserCoins` row crashes
- **Where:** `app/api/cosmetics/crates/routes.py`, `buy_crate`
- **Symptom:** `user_coins` is `None`, so `user_coins.coins` raises `AttributeError`.
- **Fix:** Treat a missing row as 0 coins (return 403), or create the row on demand.
- **Pinned by:** `tests/integration/cosmetics/test_crates_shop.py::test_buy_crate_with_no_user_coins_row_documents_bug`
- **Priority:** Low, create the row on demand.

### A roll that misses every item charges full price with no refund
- **Where:** `app/api/cosmetics/crates/routes.py`, the `if not item_rarity` branch
- **Symptom:** If `crate.total_weight` is larger than the sum of item weights (for example, `admin/crate/add` with a tier-less item), a roll can land past every item. The user pays and gets nothing. An empty *tier* gets a `dupe_refund`, but this case gets no refund at all.
- **Fix:** Decide the intended behavior: either refund, or prevent `total_weight` from being larger than the sum of item weights.
- **Pinned by:** `tests/integration/cosmetics/test_crates_shop.py::test_roll_past_all_items_still_charges_price_with_no_refund`
- **Priority:** Low, prevent `total_weight` from being larger than the sum of item weights.

### Unknown crate returns an HTML 404, not JSON
- **Where:** `app/api/cosmetics/crates/routes.py`, `first_or_404()`. No JSON error handler is registered.
- **Symptom:** The response is Flask's default HTML page instead of `{"error": ...}`.
- **Pinned by:** `tests/integration/cosmetics/test_crates_shop.py::test_buy_unknown_crate_name_returns_404` (asserts the status only)
- **Priority:** Low, add a JSON error handler for 404.

### `/customize` crashes when the user has no `UserCosmetics` row
- **Where:** `app/api/cosmetics/routes.py`, `avatar_customize`
- **Symptom:** `user.cosmetics` is `None`, so the view raises `AttributeError`.
- **Fix:** Create the row on demand, or return a clean 4xx.
- **Pinned by:** `tests/integration/cosmetics/test_cosmetics_routes.py::test_customize_with_no_user_cosmetics_row_crashes_documents_bug`
- **Priority:** Low, create the row on demand.

### `/customize` doesn't check the cosmetic type against the slot
- **Where:** `app/api/cosmetics/routes.py`, `owns_cosmetic`
- **Symptom:** Ownership is checked by `image` only, so a HAT can be equipped into the face slot and is saved.
- **Fix:** Also filter on `Cosmetics.type == <slot type>`.
- **Pinned by:** `tests/integration/cosmetics/test_cosmetics_routes.py::test_customize_does_not_check_cosmetic_type_matches_slot_documents_bug`
- **Priority:** Medium, add the type check.

---

## Admin

### `/admin/coins/init` returns 400 for non-admins
- **Where:** `app/api/admin/routes.py`, `init_coins`
- **Symptom:** It returns 400 where every other admin route returns 403. The request is still rejected.
- **Fix:** Return 403.
- **Pinned by:** `tests/integration/admin/test_admin_authz.py::test_coins_init_non_admin_returns_400_not_403_documents_bug`
- **Priority:** Low, change the status code.

### `/admin/configs/set` accepts a missing key or value
- **Where:** `app/api/admin/routes.py`, `set_config`
- **Symptom:** `str(data.get("key"))` turns `None` into the string `"None"`, so the 400 check can never fire. An empty body creates a `Configs` row with key `"None"` and value `"None"`.
- **Fix:** Validate before calling `str()`.
- **Pinned by:** `tests/integration/admin/test_admin_routes.py::test_configs_set_missing_key_and_value_documents_bug`
- **Priority:** Low, add validation.

### `/admin/scores/recalculate` with a map id always crashes
- **Where:** `app/api/admin/routes.py`, `recalculate_scores`
- **Symptom:** Guesses are filtered by `GameMap.uuid == map_id`, but `MapStats` is filtered by the integer `map_id`. Postgres raises `UndefinedFunction` (no `varchar = integer` operator).
- **Fix:** Pick one identifier (uuid or id) and use it for both filters.
- **Pinned by:** `tests/integration/admin/test_admin_routes.py::test_scores_recalculate_with_map_id_filter_documents_bug`
- **Priority:** Low, use uuid.

### `/admin/rules/config` crashes whenever a session exists
- **Where:** `app/api/admin/routes.py`, `reconfig_rules`
- **Symptom:** It reads `session.time_limit`, `nmpz`, `max_rounds`, and `map_id`, but those live on `BaseRules`, not `Session`. The result is an `AttributeError`.
- **Fix:** Rewrite the route or delete it. It looks like a one-off migration.
- **Pinned by:** `tests/integration/admin/test_admin_routes.py::test_rules_config_crashes_on_existing_sessions_documents_bug`
- **Priority:** Not bug, one time migration. Delete route.

---

## Auth and accounts

### Demo token crashes when no `demo` user exists
- **Where:** `app/api/account/auth.py`, `login_required(allow_demo=True)`
- **Symptom:** `user=None` is passed into the view, which then raises `AttributeError`.
- **Fix:** Return 403 when the demo user is missing.
- **Pinned by:** `tests/integration/account/test_auth.py::test_demo_token_without_demo_user_present`
- **Priority:** Low, generate on demand.

### Registration has no input validation
- **Where:** `app/api/account/routes.py`, register
- **Symptoms:**
  - A missing or blank password raises `ValueError` from bcrypt.
  - A missing username raises `IntegrityError`.
  - A blank username is accepted.
- **Fix:** Validate that username and password are present and non-blank, and return 400.
- **Pinned by:** these tests in `tests/integration/account/test_account_routes.py`:
  - `test_register_missing_password_crashes_instead_of_400`
  - `test_register_blank_password_crashes_instead_of_400`
  - `test_register_missing_username_crashes_with_integrity_error`
  - `test_register_blank_username_is_accepted`
- **Priority:** Medium, add validation.

### Unauthenticated requests return 403, not 401 (design note)
- **Where:** `app/api/account/auth.py`, `login_required`
- **Symptom:** A missing or invalid token gets 403. Tests assert the current 403.
- **Fix:** Optional. If this changes, update the auth and admin authz tests.
- **Priority:** Low, change to 401.

---

## Game and session

### `/game/create` without `map_id` uses a broken default-map lookup
- **Where:** `app/api/game`, the default map lookup filters the wrong column
- **Pinned by:** `tests/integration/game/test_challenge_game.py::test_create_without_map_id_documents_broken_default_lookup`
- **Priority:** High, filter on `GameMap.id` on fallback.

### `/game/create` without `rounds` or `time` falls back to a string default
- **Where:** `app/api/game`, the rule defaults have the wrong type
- **Pinned by:** these tests in `tests/integration/game/test_game_rules_and_state.py`:
  - `test_create_missing_rounds_field_hits_broken_string_default`
  - `test_create_missing_time_field_hits_broken_string_default`
- **Priority:** High, use int() on the Configs values.

### `/session/default` raises `TypeError` when configs are missing
- **Where:** `app/api/session`, `int(Configs.get(...))` on `None`
- **Pinned by:** `tests/integration/session/test_session_routes.py::test_session_default_missing_configs_raises_unhandled_typeerror`
- **Priority:** Low, validate configs before calling int().

### Celery `__update_game_state__` crashes if its session is gone when the task fires
- **Where:** `app/api/game/tasks.py`, `__update_game_state__`
- **Symptom:** `Session.query.filter_by(id=session_id).first()` can return `None` (the session was deleted between when the task was scheduled via `apply_async` and when it actually fired), and `game_type[session.type]` then raises `AttributeError: 'NoneType' object has no attribute 'type'`.
- **Fix:** Return early (no-op) when the session lookup comes back `None`.
- **Pinned by:** `tests/integration/game/test_game_tasks.py::test_task_fired_after_session_deleted_raises_attribute_error_documents_bug`
- **Priority:** Low, return early when session is gone.

### `POST /api/game/ping` always fails with a `TypeError`
- **Where:** `app/api/game/routes.py`, `ping` calls `game_type[session.type].ping(data, user, session)`, but `BaseGame.ping` and `ChallengeGame.ping` take only `(user, session)`
- **Symptom:** Every request 400s with `ping() takes 3 positional arguments but 4 were given`, for every game type and state. The timeout handling in `ping()` (scoring a no-show as 0, turning a provisional plonk into a real guess) never runs through this route. It does still run when `next`/`results`/`summary` call `self.ping(user, session)` internally.
- **Fix:** Drop `data` from the call in the route.
- **Pinned by:** these tests in `tests/integration/game/test_game_rules_and_state.py`:
  - `test_ping_after_timeout_with_no_plonk_hits_signature_mismatch_documents_bug`
  - `test_ping_after_timeout_with_plonk_hits_signature_mismatch_documents_bug`
- **Priority:** Low, delete the ping route,  we don't use it.

### `create_daily()`'s default date argument is frozen at import time
- **Where:** `app/api/session/daily.py`, `def create_daily(date=datetime.now(tz=pytz.utc).date() + timedelta(days=1))`
- **Symptom:** The default is evaluated once, when the module is first imported (process startup) - not on every call. `create_daily()` called with no arguments (as `app/cli/cli.py`'s `daily-tasks`/`create-daily` commands do, from what looks like a daily cron/scheduler) always targets "tomorrow relative to when the process started", not "tomorrow relative to now". `GET /api/session/daily` itself is unaffected - it always calls `create_daily(today)` with an explicit date.
- **Fix:** Use a sentinel default (`date=None`) and compute `datetime.now(tz=pytz.utc).date() + timedelta(days=1)` inside the function body when `date is None`.
- **Pinned by:** `tests/integration/session/test_daily_challenge.py::test_create_daily_default_date_is_frozen_at_import_time_documents_bug`
- **Priority:** High, use a sentinel default.

### `create_daily()` crashes when no matching `BaseRules` row exists
- **Where:** `app/api/session/daily.py`, `create_daily`
- **Symptom:** Unlike `app/api/game/games/basegame.py`'s `BaseGame.create()` (which creates a `BaseRules` row on the fly if none matches), `create_daily()` assumes one already exists: `rules = BaseRules.query.filter_by(map_id=..., time_limit=..., max_rounds=..., nmpz=...).first()` can be `None`, and `Session(..., base_rule_id=rules.id)` then raises `AttributeError`.
- **Fix:** Create the missing `BaseRules` row on demand (mirroring `BaseGame.create()`), or validate the Configs combination up front and fail cleanly.
- **Pinned by:** `tests/integration/session/test_daily_challenge.py::test_create_daily_without_matching_base_rules_crashes_documents_bug`
- **Priority:** Medium, create the missing `BaseRules` row on demand.
---

## Maps and geo

### `haversine` can raise `math domain error` for antipodal points
- **Where:** `app/api/map/map.py`
- **Symptom:** Float rounding pushes `a` slightly above 1.0, so `sqrt(1 - a)` fails.
- **Fix:** Clamp `a` to `[0, 1]`.
- **Pinned by:** `tests/unit/game/test_geo.py::test_haversine_antipodal_points_can_raise_domain_error_due_to_float_rounding` (xfail)
- **Priority:** Fixed, in `app/api/map/map.py` with `min(1.0, max(0.0, a))`.

### Flat bound shape skips lat/lng range validation
- **Where:** `app/api/map`, `get_new_bound`, the flat `s_lat/s_lng/e_lat/e_lng` branch
- **Symptom:** Out-of-range coordinates are accepted. The nested `start`/`end` shape rejects them.
- **Pinned by:** `tests/unit/map/test_bound_parsing.py::test_get_new_bound_flat_shape_does_not_validate_lat_lng_range`
- **Priority:** High, validate lat/lng range for the flat shape.

### `GET /api/map/stats?nmpz=...` crashes when no `MapStats` row exists for that nmpz value
- **Where:** `app/api/map/map.py`, `get_stats`, called from `app/api/map/routes.py`, `get_map_info`
- **Symptom:** The `filter_by(map_id=..., nmpz=nmpz).first()` returns `None`, and the route reads `stats.total_score` without a check, which raises `AttributeError`. `user_stats` a few lines later has the same problem.
- **Fix:** Handle `None` (a zeroed stats block, or a 404).
- **Pinned by:** `tests/integration/map/test_map_stats.py::test_stats_route_with_nmpz_filter_and_no_matching_mapstats_documents_bug`
- **Priority:** Low, generate MapStats on demand.

### `POST /api/map/edit/bound/reweight` always crashes
- **Where:** `app/api/map/edit/route.py`, `reweight_bound`
- **Symptom:** It calls `mapedit.get_bound(data)` with 1 argument, but the signature is `get_bound(data, map)`, so it raises `TypeError`. The route also imports `bound_recalculate` rather than the real `mapedit.reweight_bound(...)`, which is never used.
- **Fix:** Pass the map to `get_bound` and call `mapedit.reweight_bound`. Once it works, validate that the weight is > 0.
- **Pinned by:** `tests/integration/map/test_map_edit_routes.py::test_bound_reweight_route_crashes_documents_bug`
- **Priority:** High, fix the signature and call the right function.

### `bound/add` silently replaces zero or negative weights instead of rejecting them
- **Where:** `app/api/map/edit/mapedit.py`, `map_add_bound`
- **Symptom:** A weight of 0 or less becomes 1 or a computed default. The request succeeds.
- **Fix:** Return 400 for weights of 0 or less (or document the clamping as intended).
- **Pinned by:** `tests/integration/map/test_map_edit_routes.py::test_bound_add_documents_zero_and_negative_weight_are_not_rejected_bug`
- **Priority:** Medium, reject zero or negative weights.

### `POST /api/map/edit/name` has no validation
- **Where:** `app/api/map/edit/route.py`, the name route
- **Symptom:** A missing `name` raises `IntegrityError` (NOT NULL) on commit. A blank `""` is saved, even though `/create` rejects empty names.
- **Fix:** Reject a missing or blank (after `.strip()`) name with 400.
- **Pinned by:** `tests/integration/map/test_map_edit_routes.py::test_name_missing_field_crashes_documents_bug`, `::test_name_accepts_a_blank_name_documents_bug`
- **Priority:** Medium, add validation.

### `POST /api/map/edit/create` accepts a whitespace-only name
- **Where:** `app/api/map/edit/route.py`, create route
- **Symptom:** `" "` passes the truthiness check.
- **Fix:** Check `name.strip()`.
- **Pinned by:** `tests/integration/map/test_map_edit_routes.py::test_create_map_with_whitespace_only_name_documents_bug`
- **Priority:** Medium, add validation.

### `POST /api/map/edit/editor/add` crashes when `permission` is missing
- **Where:** `app/api/map/edit/route.py`, editor add route
- **Symptom:** It compares `int <= None`, which raises `TypeError`.
- **Fix:** Validate `permission` (required, int, in range) and return 400.
- **Pinned by:** `tests/integration/map/test_map_edit_routes.py::test_editor_add_missing_permission_field_crashes_documents_bug`
- **Priority:** Medium, add validation.

### Socket connect with no auth payload crashes (party and map edit)
- **Where:** `app/api/party/socket.py`, `handle_connect`, and `app/api/map/edit/socket.py`, `handle_connect`
- **Symptom:** python-socketio passes `data=None` when there's no `auth`, so `data.get("token")` raises `AttributeError`. It should cleanly reject, the way an invalid token does.
- **Fix:** `data = data or {}` before `.get("token")`, in both handlers.
- **Pinned by:** `tests/integration/party/test_party_socket.py::test_connect_without_auth_documents_bug` (the map edit handler has the same code but no separate test)
- **Priority:** Medium, add the `data = data or {}` line.

---

## Parties

### The host can't leave their party
- **Where:** `app/api/party/users/users.py`, `remove_user_from_party` (used by `/party/leave` and `/party/users/remove`)
- **Symptom:** It raises "Cannot remove the host" even when the host removes themselves. There's no host transfer, so the host's only way out is `/party/delete`, which ends the party for everyone.
- **Fix:** Decide the intended behavior: transfer host to the next member, or delete the party when the host leaves.
- **Pinned by:** `tests/integration/party/test_party_routes.py::test_host_leaving_the_party_is_rejected_documents_bug`, `tests/integration/party/test_party_users.py::test_host_removing_self_is_rejected_documents_bug`
- **Priority:** Not bug, design decision.

### `POST /api/party/teams/create` returns 200 on its error path
- **Where:** `app/api/party/teams/routes.py`, `create_team`
- **Symptom:** `return jsonify({"error": "not in party"})` has no status code, so it returns 200.
- **Fix:** Add `, 400` (or 403).
- **Pinned by:** `tests/integration/party/test_party_teams.py::test_create_team_without_membership_returns_200_documents_bug`
- **Priority:** Medium, add a status code.

---

## Duels

### `POST /api/party/rules` crashes if "type" is omitted from the body
- **Where:** `app/api/party/rules/routes.py`, `set_rules`
- **Symptom:** `base_rules = party.rules.base_rules; type = GameType[data.get("type").upper()] if data.get("type") else base_rules.type` - `base_rules` is a `BaseRules` row (time_limit/max_rounds/nmpz/map_id), which has no `type` attribute at all. So a rules-only update that isn't changing the game mode (a natural thing to send, and what the fallback clearly intends to support) raises `AttributeError` instead of falling back to the party's current type.
- **Fix:** Use `party.rules.type` for the fallback, not `party.rules.base_rules.type`.
- **Pinned by:** `tests/integration/game/test_duels_rules.py::test_set_rules_without_type_field_crashes_documents_bug`, `tests/integration/party/test_party_rules.py::test_post_rules_without_type_field_crashes_documents_bug`
- - **Priority:** Low, use `party.rules.type` for the fallback.

---

## Other observations (not yet pinned)
- `/api/feedback` has no `login_required`, and the feedback tests submit anonymously and succeed. Confirm that anonymous feedback is intended.
  - Intended behavior
- Party behaviors that may be surprising (asserted as-is, not bugs unless you decide otherwise): 
  - a team leader can kick their own teammates, not just the host 
    - Intended behavior
  - (`test_team_leader_can_also_kick_their_own_teammate`). Joining a second team moves the user instead of rejecting the join 
    - Intended behavior
  - (`test_joining_a_second_team_moves_the_user`). Joining the same party twice returns 403 instead of being a no-op 
    - **Priority:** Low, making it a no-op instead of returning 403.
  - (`test_joining_twice_returns_403_without_duplicate_membership`). `/party/game/join` is a no-op for DUELS, and `joined` is always False there.
    - Intended behavior
- Map editors can add or remove editors with a strictly lower permission level. This is intended according to a source comment, but it contradicts the idea that "only the owner manages editors".
  - Intended behavior
