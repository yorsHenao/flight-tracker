import os
from unittest import mock

import notifier


class FakeResp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}
        self.text = str(self._data)

    def json(self):
        return self._data


ENV = {"VUELOS_EMAIL_PROVIDER": "brevo", "VUELOS_BREVO_API_KEY": "secret-key-123",
       "VUELOS_SENDER_EMAIL": "remitente@example.com"}


def test_brevo_success_payload():
    with mock.patch.dict(os.environ, ENV), mock.patch("requests.post", return_value=FakeResp(201, {"messageId": "x"})) as post:
        assert notifier.deliver_email("a@example.com", "Asunto", "texto", "<p>h</p>")
    _, kwargs = post.call_args
    assert post.call_args[0][0] == "https://api.brevo.com/v3/smtp/email"
    assert kwargs["headers"]["api-key"] == "secret-key-123"
    assert kwargs["json"]["sender"] == {"name": "Vuelos Economicos", "email": "remitente@example.com"}
    assert kwargs["timeout"] == 15


def test_brevo_failure_logs_without_key_and_falls_back(capsys):
    with mock.patch.dict(os.environ, ENV), \
         mock.patch("requests.post", return_value=FakeResp(401, {"code": "unauthorized", "message": "Key not found"})), \
         mock.patch.object(notifier, "send_smtp_email", return_value=False) as smtp:
        assert not notifier.deliver_email("a@example.com", "s", "t", "h")
    err = capsys.readouterr().err
    assert "[BREVO]" in err and "HTTP 401" in err and "Key not found" in err
    assert "secret-key-123" not in err
    smtp.assert_called_once()


def test_provider_selection():
    with mock.patch.dict(os.environ, {"VUELOS_EMAIL_PROVIDER": "", "VUELOS_BREVO_API_KEY": "k"}):
        assert notifier.get_email_provider() == "brevo"
    with mock.patch.dict(os.environ, {"VUELOS_EMAIL_PROVIDER": "smtp", "VUELOS_BREVO_API_KEY": "k"}):
        assert notifier.get_email_provider() == "smtp"


def test_test_email_uses_same_path():
    with mock.patch.object(notifier, "deliver_email", return_value=True) as se:
        assert notifier.send_test_email("a@example.com")
    assert se.call_args.kwargs["subject"] == "Prueba: correo de alertas de Vuelos Economicos"


def test_notify_lowest_price_flag_does_not_shadow_function():
    search = {"id": 1, "user_id": 1, "notify_email": "a@example.com",
              "origin_label": "Medellín (MDE)", "origin_iata": "MDE",
              "destination_label": "Bogotá (BOG)", "destination_iata": "BOG"}
    offer = {"price": 150000, "is_direct": True, "provider_name": "Google Flights",
             "flight_date": "2026-12-20", "deep_link": "https://example.com"}
    with mock.patch.object(notifier, "deliver_email", return_value=True) as de, \
         mock.patch.object(notifier, "create_alert", side_effect=lambda **kw: kw):
        rec = notifier.notify_lowest_price(search, offer, send_email=True)
        assert rec["email_sent"] is True
        de.assert_called_once()
        rec = notifier.notify_lowest_price(search, offer, send_email=False)
        assert rec["email_sent"] is False
        de.assert_called_once()
