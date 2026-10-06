"""Feedback submission route.

Scope:
- Submitting a valid body works and an empty body is rejected. Mail sending
  is blocked by `_no_network`, so mock it where the route sends mail.

Note on where mail is actually sent: POST /api/feedback/submit
(app/api/feedback/routes.py:submit_feedback) only writes an unsent Feedback
row - it never calls mail.send itself. The mail send happens later, in a
batch, from api.feedback.feedback.send_feedback() (wired up as the
`send-feedback` CLI command in app/cli/cli.py), which queries every unsent
Feedback row and emails them as one digest. So "mock it where the route
sends mail" is done here by mocking mail.mail.mail.send and calling
send_feedback() after submitting - the closest observable equivalent, since
the HTTP route itself has no mail call to intercept.
"""

from unittest.mock import MagicMock

import pytest

from tests.helpers import assert_json_error

pytestmark = pytest.mark.integration


def test_submitting_valid_feedback_body_succeeds(client):
    resp = client.post("/api/feedback/submit", json={"message": "Great app, thanks!"})

    assert resp.status_code == 200
    assert resp.get_json() == {"message": "Feedback submitted successfully"}


def test_submitting_empty_feedback_body_is_rejected(client):
    resp = client.post("/api/feedback/submit", json={})

    assert_json_error(resp, 400)


def test_submitting_feedback_sends_mail_via_mocked_mailer(client, monkeypatch, db_session):
    import mail.mail as mail_module
    from api.feedback.feedback import send_feedback
    from models.feedback import Feedback

    resp = client.post("/api/feedback/submit", json={"message": "please forward this"})
    assert resp.status_code == 200

    mock_send = MagicMock()
    monkeypatch.setattr(mail_module.mail, "send", mock_send)

    send_feedback()

    mock_send.assert_called_once()
    feedback = Feedback.query.filter_by(message="please forward this").first()
    assert feedback.sent is True
