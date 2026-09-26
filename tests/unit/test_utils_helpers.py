"""Tests for app/utils.py helpers: float_equals and return_400_on_error.

float_equals is pure logic (no I/O) so it's marked `unit`.

return_400_on_error calls flask.jsonify() internally, which needs an active
Flask app context to read JSON config from `current_app` - so those tests
are marked `integration` instead per the task instructions, using the
existing session-scoped `app` fixture (no DB/client needed, just
`app.app_context()`).
"""

import pytest

from utils import float_equals, return_400_on_error

pytestmark_unit = pytest.mark.unit


# ---------------------------------------------------------------------------
# float_equals (tolerance is 1e-7)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "num1,num2",
    [
        (1.0, 1.0),  # exact equality
        (1.0, 1.0 + 5e-8),  # just inside tolerance
        (-1.0, -1.0 - 5e-8),  # negatives, just inside
        (0.0, 1e-8),  # zero vs tiny, just inside
        (0.0, 0.0),
    ],
)
def test_float_equals_true_within_tolerance(num1, num2):
    assert float_equals(num1, num2) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "num1,num2",
    [
        (1.0, 1.0 + 2e-7),  # just outside tolerance
        (-1.0, -1.0 - 2e-7),  # negatives, just outside
        (0.0, 2e-7),  # zero vs not-quite-so-tiny
        (1.0, 1.1),
    ],
)
def test_float_equals_false_outside_tolerance(num1, num2):
    assert float_equals(num1, num2) is False


@pytest.mark.unit
def test_float_equals_exactly_at_tolerance_boundary_is_false():
    # Comparison is strict `<`, so a delta of exactly the tolerance itself
    # is NOT considered equal.
    assert float_equals(0.0, 1e-7) is False


# ---------------------------------------------------------------------------
# return_400_on_error(method, *args, json=False, **kwargs)
# ---------------------------------------------------------------------------
# Branches (read from source):
#   1. method raises -> (jsonify({"error": str(e)}), 400)
#   2. method returns falsy (None, 0, False, "", [], (), {}) ->
#        (jsonify(success=True), 200)   <- checked BEFORE the tuple check,
#        so even a falsy empty tuple takes this branch, not ret[0].
#   3. method returns a non-tuple truthy value:
#        - json=True  -> returned as-is (assumed to already be a response)
#        - json=False -> (jsonify(ret), 200)
#   4. method returns a tuple (any truthy tuple) ->
#        jsonify(ret[0]), *ret[1:]   (falls through the try, after the block)

@pytest.mark.integration
def test_return_400_on_error_converts_exception_to_400_json(app):
    def boom():
        raise ValueError("nope")

    with app.app_context():
        response, status = return_400_on_error(boom)
        assert status == 400
        assert response.get_json() == {"error": "nope"}


@pytest.mark.integration
@pytest.mark.parametrize("falsy_value", [None, 0, False, "", [], {}, ()])
def test_return_400_on_error_falsy_return_becomes_success_true(app, falsy_value):
    with app.app_context():
        response, status = return_400_on_error(lambda: falsy_value)
        assert status == 200
        assert response.get_json() == {"success": True}


@pytest.mark.integration
def test_return_400_on_error_non_tuple_truthy_wraps_in_jsonify_by_default(app):
    with app.app_context():
        response, status = return_400_on_error(lambda: {"hello": "world"})
        assert status == 200
        assert response.get_json() == {"hello": "world"}


@pytest.mark.integration
def test_return_400_on_error_json_flag_returns_value_unwrapped(app):
    from flask import jsonify

    with app.app_context():
        preformed = jsonify({"already": "a response"})
        result = return_400_on_error(lambda: preformed, json=True)
        # Returned as-is - no (body, status) tuple wrapping happens.
        assert result is preformed
        assert result.get_json() == {"already": "a response"}


@pytest.mark.integration
def test_return_400_on_error_tuple_return_is_unpacked_with_status_code(app):
    with app.app_context():
        response, status = return_400_on_error(lambda: ({"error": "bad"}, 422))
        assert status == 422
        assert response.get_json() == {"error": "bad"}


@pytest.mark.integration
def test_return_400_on_error_tuple_return_with_extra_elements_passed_through(app):
    # A 3-tuple (body, status, headers) - Flask's own convention - should
    # pass the trailing elements through untouched via `*ret[1:]`.
    with app.app_context():
        result = return_400_on_error(lambda: ({"ok": True}, 201, {"X-Custom": "1"}))
        response, status, headers = result
        assert status == 201
        assert headers == {"X-Custom": "1"}
        assert response.get_json() == {"ok": True}


@pytest.mark.integration
def test_return_400_on_error_forwards_args_and_kwargs_to_method(app):
    def add(a, b, extra=0):
        return {"total": a + b + extra}

    with app.app_context():
        response, status = return_400_on_error(add, 2, 3, extra=10)
        assert status == 200
        assert response.get_json() == {"total": 15}
