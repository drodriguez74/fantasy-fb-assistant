"""
Tests for EmailService's config-driven configured/dev-log split.

Covers the fix for the bug where EmailService.__init__ read SMTP settings via
getattr(settings, 'SMTP_SERVER', ...) against a Settings class that never
declared those fields -- so extra="ignore" silently dropped any real .env
value and the service could never leave dev-log mode. Settings now declares
SMTP_SERVER/SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD/FROM_EMAIL for real, and
EmailService reads them directly (no getattr defaults hiding a config gap).

No real SMTP server is available in this environment, so the "configured"
path is verified by mocking smtplib.SMTP itself and asserting it would be
invoked with the right arguments -- never by attempting a real network send.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services.email_service import EmailService


@pytest.fixture
def clear_smtp_settings(monkeypatch):
    """Ensure a clean slate: no SMTP config, matching this environment today."""
    monkeypatch.setattr(settings, "SMTP_SERVER", None)
    monkeypatch.setattr(settings, "SMTP_PORT", None)
    monkeypatch.setattr(settings, "SMTP_USERNAME", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(settings, "FROM_EMAIL", None)


def test_no_smtp_config_stays_in_dev_log_mode(clear_smtp_settings):
    """With no SMTP settings configured (this environment's real state today),
    EmailService must degrade honestly to dev-log mode rather than crash or
    silently pretend to be ready."""
    service = EmailService()

    assert service.smtp_username is None
    assert service.development_mode is True


@pytest.mark.asyncio
async def test_dev_log_mode_logs_instead_of_sending(clear_smtp_settings):
    """In dev-log mode, _send_email must return True without ever touching
    smtplib -- no real network call, no crash."""
    service = EmailService()

    with patch("app.services.email_service.smtplib.SMTP") as mock_smtp:
        result = await service._send_email(
            "user@example.com", "Test Subject", "Test body"
        )

    assert result is True
    mock_smtp.assert_not_called()


def test_fake_but_present_smtp_config_resolves_as_configured(monkeypatch):
    """Supplying real-shaped (fake) SMTP_SERVER/SMTP_USERNAME/etc. via Settings
    must flip EmailService out of dev-log mode -- this is the actual bug fix:
    before, getattr(settings, 'SMTP_USERNAME', None) always returned None
    because Settings never declared the field, so this could never happen in
    any environment, real or fake."""
    monkeypatch.setattr(settings, "SMTP_SERVER", "smtp.fake-test-host.example")
    monkeypatch.setattr(settings, "SMTP_PORT", 2525)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "fake-test-user@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "fake-test-password")
    monkeypatch.setattr(settings, "FROM_EMAIL", "fake-noreply@example.com")

    service = EmailService()

    assert service.smtp_server == "smtp.fake-test-host.example"
    assert service.smtp_port == 2525
    assert service.smtp_username == "fake-test-user@example.com"
    assert service.smtp_password == "fake-test-password"
    assert service.from_email == "fake-noreply@example.com"
    assert service.development_mode is False


@pytest.mark.asyncio
async def test_configured_service_attempts_real_smtp_send_path(monkeypatch):
    """With fake-but-present credentials, _send_email must take the real SMTP
    branch and drive smtplib.SMTP the way a genuine send would (context
    manager, starttls, login, send_message) -- with smtplib itself mocked out
    so no actual network connection is attempted."""
    monkeypatch.setattr(settings, "SMTP_SERVER", "smtp.fake-test-host.example")
    monkeypatch.setattr(settings, "SMTP_PORT", 2525)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "fake-test-user@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "fake-test-password")
    monkeypatch.setattr(settings, "FROM_EMAIL", "fake-noreply@example.com")

    service = EmailService()

    mock_server = MagicMock()
    mock_server.__enter__.return_value = mock_server
    mock_server.__exit__.return_value = False

    with patch(
        "app.services.email_service.smtplib.SMTP", return_value=mock_server
    ) as mock_smtp_cls:
        result = await service._send_email(
            "user@example.com", "Test Subject", "Test body", "<p>Test body</p>"
        )

    assert result is True
    mock_smtp_cls.assert_called_once_with("smtp.fake-test-host.example", 2525)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with(
        "fake-test-user@example.com", "fake-test-password"
    )
    mock_server.send_message.assert_called_once()

    sent_msg = mock_server.send_message.call_args[0][0]
    assert sent_msg["From"] == "fake-noreply@example.com"
    assert sent_msg["To"] == "user@example.com"
    assert sent_msg["Subject"] == "Test Subject"


def test_frontend_url_fallback_matches_real_dev_port(monkeypatch):
    """frontend_url's fallback must match this repo's real Vite dev port
    (3001, per vite.config.ts / CLAUDE.md) -- not the Vite default (5173),
    which this app doesn't use."""
    monkeypatch.delattr(settings, "FRONTEND_URL", raising=False)
    from app.core import config as config_module

    frontend_url = getattr(config_module.settings, "FRONTEND_URL", "http://localhost:3001")
    assert frontend_url == "http://localhost:3001"
