"""Plain builder functions for test data.

No factory_boy dependency: each `make_*` function builds a model instance
with sensible defaults, commits it to `db.session`, and returns it. A shared
monotonic counter keeps repeated calls from colliding on unique columns
(usernames, map names, lat/lng pairs, ...).

All functions assume they are called inside an active Flask app context with
`db.session` already bound to the current test's isolated transaction (see
`tests/conftest.py::db_session`).
"""

import itertools

from api.account.routes import bcrypt
from models.cosmetics import Cosmetic_Type, Cosmetics, CosmeticsOwnership, Tier, UserCoins, UserCosmetics
from models.crates import Crate, CrateItem
from models.db import db
from models.duels import DuelRules, GameTeam, TeamPlayer
from models.location import SVLocation
from models.map import Bound, GameMap, MapBound
from models.party import Party, PartyMember, PartyRules, PartyTeam
from models.session import BaseRules, GameType, Round, Session
from models.user import User

_counter = itertools.count(1)
_round_numbers = {}  # session.id -> last round_number handed out


def _next(prefix):
    return f"{prefix}{next(_counter)}"


def make_user(username=None, password="password123", is_admin=False):
    """Create and commit a User. Password is bcrypt-hashed the same way
    api/account/routes.py does it, so the result can log in via
    POST /api/account/login with the plaintext `password`."""
    username = username or _next("user")
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username, password=hashed_password, is_admin=is_admin)
    db.session.add(user)
    db.session.commit()
    return user


def make_map(creator=None, name=None, start_latitude=0.0, start_longitude=0.0,
             end_latitude=0.0, end_longitude=0.0, total_weight=1,
             max_distance=1000.0, description=None):
    creator = creator or make_user()
    name = name or _next("map")
    game_map = GameMap(
        name=name,
        creator_id=creator.id,
        start_latitude=start_latitude,
        start_longitude=start_longitude,
        end_latitude=end_latitude,
        end_longitude=end_longitude,
        total_weight=total_weight,
        max_distance=max_distance,
        description=description,
    )
    db.session.add(game_map)
    db.session.commit()
    return game_map


def make_location(latitude=None, longitude=None):
    n = next(_counter)
    latitude = latitude if latitude is not None else 10.0 + n * 0.001
    longitude = longitude if longitude is not None else 20.0 + n * 0.001
    location = SVLocation(latitude=latitude, longitude=longitude)
    db.session.add(location)
    db.session.commit()
    return location


def make_base_rules(game_map=None, time_limit=-1, max_rounds=5, nmpz=False):
    game_map = game_map or make_map()
    rules = BaseRules(
        map_id=game_map.id,
        time_limit=time_limit,
        max_rounds=max_rounds,
        nmpz=nmpz,
    )
    db.session.add(rules)
    db.session.commit()
    return rules


def make_session(host=None, base_rules=None, game_type=GameType.CHALLENGE, current_round=0):
    host = host or make_user()
    base_rules = base_rules or make_base_rules()
    session = Session(
        host_id=host.id,
        base_rule_id=base_rules.id,
        type=game_type,
        current_round=current_round,
    )
    db.session.add(session)
    db.session.commit()
    return session


def make_round(session=None, location=None, base_rules=None, round_number=None):
    session = session or make_session()
    base_rules = base_rules or session.base_rules
    location = location or make_location()

    if round_number is None:
        round_number = _round_numbers.get(session.id, 0) + 1
    _round_numbers[session.id] = round_number

    round_ = Round(
        location_id=location.id,
        session_id=session.id,
        round_number=round_number,
        base_rule_id=base_rules.id,
    )
    db.session.add(round_)
    db.session.commit()
    return round_


def make_bounded_map(creator=None, lat=None, lng=None, max_distance=1000.0):
    """A map with exactly one point Bound, so - combined with the
    street_view_mock fixture (which always returns a bound's start corner) -
    every round generated on it lands at exactly (lat, lng). Generalizes the
    identical helper duplicated locally in test_challenge_game.py and
    test_game_rules_and_state.py. `lat`/`lng` default to unique-but
    -deterministic values (like make_location) so repeated calls in the same
    test don't collide on Bound's unique constraint; pass fixed values when a
    test needs to assert against a known location."""
    n = next(_counter)
    lat = lat if lat is not None else 10.0 + n * 0.001
    lng = lng if lng is not None else 20.0 + n * 0.001
    game_map = make_map(creator=creator, max_distance=max_distance, total_weight=1)
    bound = Bound(start_latitude=lat, start_longitude=lng, end_latitude=lat, end_longitude=lng)
    db.session.add(bound)
    db.session.flush()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=1))
    db.session.commit()
    return game_map


def make_duel_rules(start_hp=5000, damage_multi_start_round=1, damage_multi_mult=1.0,
                     damage_multi_add=0.0, damage_multi_freq=1, guess_time_limit=15):
    """Get-or-create a DuelRules row. DuelRules has a UniqueConstraint across
    every one of these six columns together (see models/duels.py), so two
    calls with identical values reuse the same row rather than colliding on
    that constraint - mirrors the get-or-create pattern
    api/party/routes.py and api/game/games/duels.py themselves use."""
    values = dict(
        start_hp=start_hp,
        damage_multi_start_round=damage_multi_start_round,
        damage_multi_mult=damage_multi_mult,
        damage_multi_add=damage_multi_add,
        damage_multi_freq=damage_multi_freq,
        guess_time_limit=guess_time_limit,
    )
    rules = DuelRules.query.filter_by(**values).first()
    if not rules:
        rules = DuelRules(**values)
        db.session.add(rules)
        db.session.commit()
    return rules


def make_party(host=None, game_type=GameType.DUELS, base_rules=None, duel_rules=None):
    """Create and commit a Party with `host` as its sole member, plus a
    PartyRules row of the given `game_type` (DUELS by default, since this
    suite is duels-focused) pointing at `base_rules`/`duel_rules` (built with
    plain defaults if not given - a blank, unbounded map with no locations;
    pass base_rules=make_base_rules(game_map=make_bounded_map(...)) for a
    party that can actually generate rounds).

    Every real Party row has exactly one PartyRules row (see POST
    /api/party/create in api/party/routes.py) - this mirrors that shape via
    the ORM directly rather than the route, so tests aren't coupled to that
    route's own Configs-dependent defaults."""
    host = host or make_user()
    base_rules = base_rules or make_base_rules()
    duel_rules = duel_rules or make_duel_rules()

    party = Party(host_id=host.id)
    db.session.add(party)
    db.session.flush()

    party_rules = PartyRules(
        party_id=party.id,
        type=game_type,
        base_rule_id=base_rules.id,
        duel_rules_id=duel_rules.id,
    )
    db.session.add(party_rules)
    db.session.add(PartyMember(party_id=party.id, user_id=host.id, in_lobby=True))
    db.session.commit()
    return party


def make_party_member(party, user=None, in_lobby=True):
    user = user or make_user()
    member = PartyMember(party_id=party.id, user_id=user.id, in_lobby=in_lobby)
    db.session.add(member)
    db.session.commit()
    return member


def make_team(party, users=None, name=None, leader=None, color=None):
    """Build a PartyTeam (+ backing GameTeam/TeamPlayer rows) for `users` (a
    new solo user if not given), mirroring the shape
    api/party/teams/teams.py:get_team()/create_team() build. `leader`
    defaults to the first user. `color` defaults to a monotonic, always-
    unique value (PartyTeam has a UniqueConstraint on (party_id, color),
    unlike the route's own random.randint default which could theoretically
    collide)."""
    users = users or [make_user()]
    leader = leader or users[0]
    ids = sorted(u.id for u in users)
    team_hash = ",".join(str(i) for i in ids)

    team = GameTeam.query.filter_by(hash=team_hash).first()
    if not team:
        team = GameTeam(hash=team_hash)
        db.session.add(team)
        db.session.flush()
        for user in users:
            db.session.add(TeamPlayer(user_id=user.id, team_id=team.id))

    party_team = PartyTeam(
        team_id=team.id,
        party_id=party.id,
        leader_id=leader.id,
        name=name or f"{leader.username}'s Team",
        color=color if color is not None else next(_counter),
    )
    db.session.add(party_team)
    db.session.commit()
    return party_team


def make_cosmetic(image=None, item_name=None, type=Cosmetic_Type.HAT, tier=Tier.COMMON,
                  top_position=0.0, left_position=0.0, scale=1.0):
    n = next(_counter)
    cosmetic = Cosmetics(
        image=image or f"cosmetic{n}.png",
        item_name=item_name or f"Cosmetic {n}",
        type=type,
        tier=tier,
        top_position=top_position,
        left_position=left_position,
        scale=scale,
    )
    db.session.add(cosmetic)
    db.session.commit()
    return cosmetic


def make_ownership(user, cosmetic):
    ownership = CosmeticsOwnership(user_id=user.id, cosmetics_id=cosmetic.id)
    db.session.add(ownership)
    db.session.commit()
    return ownership


def make_user_coins(user=None, coins=0):
    user = user or make_user()
    user_coins = UserCoins(user_id=user.id, coins=coins)
    db.session.add(user_coins)
    db.session.commit()
    return user_coins


def make_user_cosmetics(user=None, hue=180, saturation=100, brightness=100):
    user = user or make_user()
    user_cosmetics = UserCosmetics(user_id=user.id, hue=hue, saturation=saturation, brightness=brightness)
    db.session.add(user_cosmetics)
    db.session.commit()
    return user_cosmetics


def make_crate(name=None, price=100, description="", image=None, items=None):
    """Create and commit a Crate. `items` is a list of (Tier, weight) pairs;
    a CrateItem is created for each and total_weight is set to their sum,
    in list order (the order buy_crate iterates them in)."""
    items = items if items is not None else [(Tier.COMMON, 1)]
    crate = Crate(
        name=name or _next("crate"),
        price=price,
        description=description,
        image=image,
        total_weight=sum(weight for _, weight in items),
    )
    db.session.add(crate)
    db.session.flush()
    for tier, weight in items:
        make_crate_item(crate, tier, weight, commit=False)
    db.session.commit()
    return crate


def make_crate_item(crate, tier, weight, commit=True):
    """Add a CrateItem to `crate`. Does NOT update crate.total_weight - use
    make_crate(items=...) for a consistent crate."""
    item = CrateItem(crate_id=crate.id, tier=tier, weight=weight)
    db.session.add(item)
    if commit:
        db.session.commit()
    return item
