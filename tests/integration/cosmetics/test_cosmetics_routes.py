"""PUT /customize and GET /all cosmetics routes.

Scope:
- PUT /customize: equipping an item you don't own is rejected, and equipping
  one you own persists. Omitting hue/saturation/brightness keeps the
  existing value; sending null for a slot unequips it. Unauthenticated and
  demo requests are rejected (this route is @login_required(), no demo).
- GET /all (allow_demo=True) returns the full catalog split into
  owned/unowned per type, ordered by tier, and the demo user sees
  everything as unowned.

Read from app/api/cosmetics/routes.py:
- `owns_cosmetic(image_name)` returns None for a falsy/absent image (slot
  left unequipped - always allowed), the matching `Cosmetics` row if the
  user owns a cosmetic with that image, or the sentinel `-1` if no such
  owned cosmetic exists. `-1` for any slot short-circuits the whole request
  with 403 *before* anything is written - so a failing slot leaves every
  other field (hue/saturation/brightness and the other slots) untouched.
- Ownership is looked up purely by `Cosmetics.image` - `type` is never
  checked against which slot (face/body/hat) the image is being equipped
  into, so an owned HAT can be equipped into the face slot.
- `cosmetic = user.cosmetics` (the user's `UserCosmetics` row) is used
  unconditionally with no None check - a user with no `UserCosmetics` row
  crashes with AttributeError when the route tries to assign onto it.
"""

import pytest

from models.cosmetics import Cosmetic_Type, Cosmetics, Tier, UserCosmetics
from models.db import db
from tests.factories import make_cosmetic, make_ownership, make_user, make_user_cosmetics
from tests.helpers import assert_json_error, auth_header, demo_header

pytestmark = pytest.mark.integration

CUSTOMIZE_URL = "/api/cosmetics/customize"
ALL_URL = "/api/cosmetics/all"


def _customize(client, user, **kwargs):
    return client.put(CUSTOMIZE_URL, json=kwargs, headers=auth_header(user))


# ---------------------------------------------------------------------------
# PUT /customize - equipping an unowned cosmetic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ["face", "body", "hat"])
def test_customize_equipping_unowned_item_is_rejected(client, slot):
    user = make_user()
    user_cosmetics = make_user_cosmetics(user=user, hue=180, saturation=100, brightness=100)
    cosmetic_type = {"face": Cosmetic_Type.FACE, "body": Cosmetic_Type.BODY, "hat": Cosmetic_Type.HAT}[slot]
    unowned = make_cosmetic(type=cosmetic_type)

    response = _customize(client, user, hue=10, saturation=20, brightness=30, **{slot: {"image": unowned.image}})

    body = assert_json_error(response, 403)
    assert body == {"error": f"You do not own the {slot} cosmetic"}

    # Nothing was persisted - the check runs before any assignment.
    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.hue == 180
    assert refreshed.saturation == 100
    assert refreshed.brightness == 100
    assert refreshed.face_id is None
    assert refreshed.body_id is None
    assert refreshed.hat_id is None


# ---------------------------------------------------------------------------
# PUT /customize - equipping an owned cosmetic persists
# ---------------------------------------------------------------------------

def test_customize_equipping_owned_item_persists(client):
    user = make_user()
    make_user_cosmetics(user=user, hue=180, saturation=100, brightness=100)
    face = make_cosmetic(type=Cosmetic_Type.FACE)
    body = make_cosmetic(type=Cosmetic_Type.BODY)
    hat = make_cosmetic(type=Cosmetic_Type.HAT)
    for cosmetic in (face, body, hat):
        make_ownership(user, cosmetic)

    response = _customize(
        client, user,
        hue=42, saturation=55, brightness=77,
        face={"image": face.image}, body={"image": body.image}, hat={"image": hat.image},
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "Avatar changes saved!"}

    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.hue == 42
    assert refreshed.saturation == 55
    assert refreshed.brightness == 77
    assert refreshed.face_id == face.id
    assert refreshed.body_id == body.id
    assert refreshed.hat_id == hat.id


# ---------------------------------------------------------------------------
# PUT /customize - omitting hue keeps it, null unequips
# ---------------------------------------------------------------------------

def test_customize_omitting_hue_keeps_existing_value(client):
    user = make_user()
    make_user_cosmetics(user=user, hue=180, saturation=100, brightness=100)
    hat = make_cosmetic(type=Cosmetic_Type.HAT)
    make_ownership(user, hat)

    # No "hue" key at all in the JSON body.
    response = client.put(
        CUSTOMIZE_URL,
        json={"saturation": 100, "brightness": 100, "hat": {"image": hat.image}},
        headers=auth_header(user),
    )

    assert response.status_code == 200
    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.hue == 180  # unchanged
    assert refreshed.hat_id == hat.id


def test_customize_null_slot_unequips(client):
    user = make_user()
    user_cosmetics = make_user_cosmetics(user=user, hue=180, saturation=100, brightness=100)
    hat = make_cosmetic(type=Cosmetic_Type.HAT)
    make_ownership(user, hat)
    user_cosmetics.hat = hat
    db.session.commit()
    assert UserCosmetics.query.filter_by(user_id=user.id).first().hat_id == hat.id

    response = _customize(client, user, hue=None, saturation=None, brightness=None, hat=None)

    assert response.status_code == 200
    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.hat_id is None
    assert refreshed.hue == 180  # untouched by the null-hue-omission path


# ---------------------------------------------------------------------------
# PUT /customize - no UserCosmetics row (bug: crashes instead of a clean error)
# ---------------------------------------------------------------------------

def test_customize_with_no_user_cosmetics_row_crashes_documents_bug(client):
    # BUG (app/api/cosmetics/routes.py): `cosmetic = user.cosmetics` is used
    # unconditionally. A user with no UserCosmetics row (e.g. never
    # registered through the normal /register flow) gets `cosmetic = None`,
    # and the route crashes with AttributeError on `cosmetic.hue = ...`
    # instead of returning a clean 4xx. Documenting actual behavior, not
    # fixing app code.
    user = make_user()
    assert UserCosmetics.query.filter_by(user_id=user.id).first() is None

    with pytest.raises(AttributeError):
        _customize(client, user, hue=10, saturation=10, brightness=10)


# ---------------------------------------------------------------------------
# PUT /customize - slot type is never validated against the cosmetic's type
# ---------------------------------------------------------------------------

def test_customize_does_not_check_cosmetic_type_matches_slot_documents_bug(client):
    # BUG (app/api/cosmetics/routes.py): `owns_cosmetic` looks up ownership
    # purely by `Cosmetics.image`, never checking that `Cosmetics.type`
    # matches the slot (face/body/hat) it's being equipped into. A HAT
    # cosmetic can be equipped into the face slot and is happily accepted
    # and persisted. Documenting actual behavior, not fixing app code.
    user = make_user()
    make_user_cosmetics(user=user)
    hat = make_cosmetic(type=Cosmetic_Type.HAT)
    make_ownership(user, hat)

    response = _customize(client, user, face={"image": hat.image})

    assert response.status_code == 200
    refreshed = UserCosmetics.query.filter_by(user_id=user.id).first()
    assert refreshed.face_id == hat.id


# ---------------------------------------------------------------------------
# PUT /customize - auth
# ---------------------------------------------------------------------------

def test_customize_requires_auth(client):
    response = client.put(CUSTOMIZE_URL, json={"hue": 1})
    assert_json_error(response, 403)


def test_customize_rejects_demo_token(client):
    # /customize is @login_required() with no allow_demo, so the "demo"
    # literal must be refused even before any DB lookup for a demo user.
    response = client.put(CUSTOMIZE_URL, json={"hue": 1}, headers=demo_header())
    body = assert_json_error(response, 403)
    assert body == {"error": "login required"}


# ---------------------------------------------------------------------------
# GET /all - full catalog, split and ordered correctly
# ---------------------------------------------------------------------------

def test_get_all_returns_the_full_cosmetics_catalog(client):
    user = make_user()

    faces = [
        make_cosmetic(type=Cosmetic_Type.FACE, tier=Tier.LEGENDARY),
        make_cosmetic(type=Cosmetic_Type.FACE, tier=Tier.COMMON),
        make_cosmetic(type=Cosmetic_Type.FACE, tier=Tier.RARE),
    ]
    bodies = [
        make_cosmetic(type=Cosmetic_Type.BODY, tier=Tier.EPIC),
        make_cosmetic(type=Cosmetic_Type.BODY, tier=Tier.UNCOMMON),
    ]
    hats = [
        make_cosmetic(type=Cosmetic_Type.HAT, tier=Tier.COMMON),
        make_cosmetic(type=Cosmetic_Type.HAT, tier=Tier.LEGENDARY),
        make_cosmetic(type=Cosmetic_Type.HAT, tier=Tier.UNCOMMON),
    ]

    # Own one face, no bodies, all hats.
    make_ownership(user, faces[0])
    for hat in hats:
        make_ownership(user, hat)

    response = client.get(ALL_URL, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()

    def _by_tier(cosmetics):
        return sorted(cosmetics, key=lambda c: c.tier.value)

    # Split correctness: owned + unowned per type == the full catalog for
    # that type (compare by image, since to_json() entries aren't hashable).
    face_images = {f.image for f in faces}
    assert {c["image"] for c in body["owned_faces"]} | {c["image"] for c in body["unowned_faces"]} == face_images
    assert {c["image"] for c in body["owned_faces"]} == {faces[0].image}
    assert {c["image"] for c in body["unowned_faces"]} == {faces[1].image, faces[2].image}

    body_images = {b.image for b in bodies}
    assert {c["image"] for c in body["owned_bodies"]} == set()
    assert {c["image"] for c in body["unowned_bodies"]} == body_images

    hat_images = {h.image for h in hats}
    assert {c["image"] for c in body["owned_hats"]} == hat_images
    assert {c["image"] for c in body["unowned_hats"]} == set()

    # Ordering by tier, ascending, within each returned list.
    assert body["unowned_faces"] == [c.to_json() for c in _by_tier([faces[1], faces[2]])]
    assert body["owned_faces"] == [c.to_json() for c in _by_tier([faces[0]])]
    assert body["unowned_bodies"] == [c.to_json() for c in _by_tier(bodies)]
    assert body["owned_hats"] == [c.to_json() for c in _by_tier(hats)]

    # Entries match Cosmetics.to_json() exactly.
    for entry in body["unowned_faces"] + body["owned_faces"]:
        match = Cosmetics.query.filter_by(image=entry["image"]).first()
        assert entry == match.to_json()


def test_get_all_demo_user_sees_everything_as_unowned(client):
    demo_user = make_user(username="demo")
    other_user = make_user()

    face = make_cosmetic(type=Cosmetic_Type.FACE)
    body_cos = make_cosmetic(type=Cosmetic_Type.BODY)
    hat = make_cosmetic(type=Cosmetic_Type.HAT)

    # Someone else owns everything - demo must not "inherit" any of it.
    make_ownership(other_user, face)
    make_ownership(other_user, body_cos)
    make_ownership(other_user, hat)

    response = client.get(ALL_URL, headers=demo_header())

    assert response.status_code == 200
    result = response.get_json()
    assert result["owned_faces"] == []
    assert result["owned_bodies"] == []
    assert result["owned_hats"] == []
    assert {c["image"] for c in result["unowned_faces"]} == {face.image}
    assert {c["image"] for c in result["unowned_bodies"]} == {body_cos.image}
    assert {c["image"] for c in result["unowned_hats"]} == {hat.image}
