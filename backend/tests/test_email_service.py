from unittest.mock import MagicMock, patch
import pytest

from app.services.email import (
    EmailConfigurationError,
    EmailDeliveryError,
    EmailService,
)


@pytest.mark.asyncio
async def test_email_service_send_success():
    service = EmailService()
    service.api_key = "re_test_dummy_key"

    with patch("resend.Emails.send", return_value={"id": "email_12345"}) as mock_send:
        result = await service.send_password_reset_email(
            to_email="developer@tarkai.com",
            reset_url="http://localhost:5173/reset-password?token=testtoken123",
            user_name="Alex Mercer",
        )
        assert result["id"] == "email_12345"
        mock_send.assert_called_once()
        params = mock_send.call_args[0][0]
        assert "developer@tarkai.com" in params["to"]
        assert "Reset your TARK AI password" in params["subject"]
        assert "http://localhost:5173/reset-password?token=testtoken123" in params["html"]


@pytest.mark.asyncio
async def test_email_service_missing_api_key():
    service = EmailService()
    service.api_key = None

    with pytest.raises(EmailConfigurationError):
        await service.send_password_reset_email(
            to_email="developer@tarkai.com",
            reset_url="http://localhost:5173/reset-password?token=testtoken123",
        )


@pytest.mark.asyncio
async def test_email_service_delivery_failure():
    service = EmailService()
    service.api_key = "re_test_key"

    with patch("resend.Emails.send", side_effect=Exception("Resend API 403 Forbidden")):
        with pytest.raises(EmailDeliveryError):
            await service.send_password_reset_email(
                to_email="developer@tarkai.com",
                reset_url="http://localhost:5173/reset-password?token=testtoken123",
            )


@pytest.mark.asyncio
async def test_verification_email_template():
    service = EmailService()
    service.api_key = "re_test_key"

    with patch("resend.Emails.send", return_value={"id": "email_verify_123"}) as mock_send:
        result = await service.send_verification_email(
            to_email="developer@tarkai.com",
            verification_url="http://localhost:5173/verify-email?token=veriftoken123",
            user_name="Developer",
        )
        assert result["id"] == "email_verify_123"
        params = mock_send.call_args[0][0]
        assert "Verify your TARK AI email" in params["subject"]
        assert "http://localhost:5173/verify-email?token=veriftoken123" in params["html"]
