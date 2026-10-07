"""Authorization matrix for every /api/admin/* route.

Every admin route is decorated with `@login_required()` (no `allow_demo`),
followed by a hand-rolled `if not user.is_admin: return 403` check in the
view body (see app/api/admin/routes.py). That means:

  * anonymous (no Authorization header) -> rejected by login_required() -> 403
  * the literal "demo" token           -> rejected by login_required()
                                           (allow_demo defaults to False)   -> 403
  * an authenticated non-admin user    -> passes login_required(), rejected
                                           by the view's own is_admin check -> 403
                                           (except /coins/init, see below)

`ADMIN_ROUTES` is a static (method, path) list for every route registered on
`admin_bp`. `test_every_admin_route_is_covered_by_the_authz_matrix` derives
the real set from `app.url_map` and asserts it equals `ADMIN_ROUTES`, so a
newly added admin route fails loudly here until someone adds it to the list
(and, implicitly, thinks about its authz).
"""

import pytest

from models.configs import Configs
from models.cosmetics import Cosmetics, UserCoins, UserCosmetics
from models.crates import Crate
from models.stats import MapStats
from tests.factories import make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# The authz matrix
# ---------------------------------------------------------------------------

ADMIN_ROUTES = [
    ("POST", "/api/admin/usercosmetics/initialize"),
    ("POST", "/api/admin/scores/recalculate"),
    ("POST", "/api/admin/configs/set"),
    ("GET", "/api/admin/configs/get"),
    ("POST", "/api/admin/cosmetic/add"),
    ("POST", "/api/admin/coins/init"),
    ("POST", "/api/admin/crate/add"),
    ("POST", "/api/admin/rules/config"),
]

# A plausible JSON body (or, for GET, query string) for each route - plausible
# enough that a missing authz check would actually mutate something, so the
# "no side effects" assertion below is meaningful rather than vacuous.
ROUTE_BODIES = {
    ("POST", "/api/admin/usercosmetics/initialize"): {},
    ("POST", "/api/admin/scores/recalculate"): {},
    ("POST", "/api/admin/configs/set"): {"key": "authz_probe_key", "value": "authz_probe_value"},
    ("GET", "/api/admin/configs/get"): {"key": "authz_probe_key"},
    ("POST", "/api/admin/cosmetic/add"): {
        "image": "authz_probe.png",
        "item_name": "Authz Probe Cosmetic",
        "type": "hat",
        "tier": "common",
        "top_position": 0.0,
        "left_position": 0.0,
        "scale": 1.0,
    },
    ("POST", "/api/admin/coins/init"): {},
    ("POST", "/api/admin/crate/add"): {
        "name": "authz_probe_crate",
        "price": 10,
        "items": [{"tier": "common", "weight": 1}],
    },
    ("POST", "/api/admin/rules/config"): {},
}

# BUG (app/api/admin/routes.py, init_coins): non-admins get 400
# (`return jsonify({"error":"You are not an admin"}),400`) instead of the 403
# every other admin route uses. It is still rejected (not a security hole),
# just an inconsistent status code - pinned here instead of asserted as a
# strict 403 like everything else.
COINS_INIT = ("POST", "/api/admin/coins/init")

ACTORS = ["anon", "normal", "demo"]


def _real_admin_routes(app):
    """Every (method, rule) pair Flask actually has registered under the
    admin blueprint, keyed off the endpoint prefix nested blueprint
    registration gives it: outer blueprint "api" registered on the app,
    "admin_bp" registered on "api" -> endpoints are "api.admin_bp.<view>"."""
    routes = set()
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("api.admin_bp."):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            routes.add((method, rule.rule))
    return routes


def _snapshot_counts():
    return {
        "configs": Configs.query.count(),
        "user_coins": UserCoins.query.count(),
        "user_cosmetics": UserCosmetics.query.count(),
        "crates": Crate.query.count(),
        "cosmetics": Cosmetics.query.count(),
        "map_stats": MapStats.query.count(),
    }


def _headers_for(actor, normal_user):
    if actor == "anon":
        return {}
    if actor == "normal":
        return auth_header(normal_user)
    if actor == "demo":
        return demo_header()
    raise ValueError(actor)


def _send(client, method, path, headers, body):
    if method == "GET":
        return client.get(path, query_string=body, headers=headers)
    return client.open(path, method=method, json=body, headers=headers)


def test_every_admin_route_is_covered_by_the_authz_matrix(app):
    """No /api/admin/* route is missing from ADMIN_ROUTES. Printed so a
    failure shows exactly what's missing/extra."""
    real_routes = _real_admin_routes(app)
    expected_routes = set(ADMIN_ROUTES)
    print("real admin routes:", sorted(real_routes))
    print("declared ADMIN_ROUTES:", sorted(expected_routes))
    assert real_routes == expected_routes


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_route_rejects_non_admin(client, db_session, method, path, actor):
    # Every route needs a "demo" user present for the demo-token case, and a
    # plain non-admin user for the normal case - create both unconditionally
    # to keep the test uniform (their existence has no bearing on the
    # snapshot counts below).
    normal_user = make_user()
    make_user(username="demo")

    body = ROUTE_BODIES[(method, path)]
    headers = _headers_for(actor, normal_user)

    before = _snapshot_counts()
    resp = _send(client, method, path, headers, body)
    after = _snapshot_counts()

    assert not (200 <= resp.status_code < 300), (
        f"{actor} request to {method} {path} unexpectedly succeeded: {resp.status_code}"
    )

    if (method, path) == COINS_INIT and actor == "normal":
        assert resp.status_code == 400
    else:
        assert resp.status_code == 403

    assert after == before, f"{actor} request to {method} {path} had side effects: {before} -> {after}"


def test_coins_init_non_admin_returns_400_not_403_documents_bug(client, db_session):
    """BUG (app/api/admin/routes.py, init_coins): non-admins get 400 instead
    of the 403 every other admin route returns. Still rejected, just
    inconsistent - pinned explicitly here in addition to the matrix override
    above."""
    normal_user = make_user()

    resp = client.post("/api/admin/coins/init", json={}, headers=auth_header(normal_user))

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "You are not an admin"
