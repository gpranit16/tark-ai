"""Resend Email Service for TARK AI Authentication & Transactional Messages.

Provides luxury HTML & plain-text templates for:
- Password Reset
- Email Verification

Security & Privacy:
- Never logs API keys, raw tokens, or sensitive credential URLs.
- Uses official Resend SDK / API client.
"""
from __future__ import annotations

import logging
from typing import Any

import resend

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when email dispatch fails via the provider."""
    pass


class EmailConfigurationError(Exception):
    """Raised when email service is missing required API keys or sender info."""
    pass


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.resend_api_key
        if self.api_key:
            resend.api_key = self.api_key

    def _get_sender(self) -> str:
        name = self.settings.resend_from_name or "TARK AI"
        email = self.settings.resend_from_email or "onboarding@resend.dev"
        return f"{name} <{email}>"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def send_email(
        self,
        to: str | list[str],
        subject: str,
        html_content: str,
        text_content: str,
        email_type: str = "general",
    ) -> dict[str, Any]:
        """Send an email via Resend with safe error handling and structured diagnostics."""
        if not self.is_configured():
            logger.warning(
                "[AUTH] email_dispatch_skipped provider=resend type=%s reason=missing_api_key",
                email_type,
            )
            raise EmailConfigurationError(
                "Resend email service is not configured. Please set RESEND_API_KEY."
            )

        recipient_list = [to] if isinstance(to, str) else to
        sender = self._get_sender()

        params: resend.Emails.SendParams = {
            "from": sender,
            "to": recipient_list,
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }

        try:
            # Resend python SDK non-blocking async thread execution
            import asyncio
            response = await asyncio.to_thread(resend.Emails.send, params)
            
            # Log success safely (log only recipient domains, never full email/token)
            domains = [r.split("@")[-1] for r in recipient_list if "@" in r]
            logger.info(
                "[AUTH] email_sent_success provider=resend type=%s recipient_domains=%s email_id=%s",
                email_type,
                domains,
                response.get("id") if isinstance(response, dict) else "ok",
            )
            return response if isinstance(response, dict) else {"id": str(response)}
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "[AUTH] email_send_failed provider=resend type=%s error_type=%s reason=%s",
                email_type,
                type(e).__name__,
                error_msg,
            )
            # Remove any potential sensitive auth header mentions if present
            safe_msg = error_msg if "Bearer" not in error_msg and "re_" not in error_msg else "Email delivery provider rejected request."
            raise EmailDeliveryError(safe_msg) from e

    async def send_password_reset_email(
        self,
        to_email: str,
        reset_url: str,
        user_name: str | None = None,
    ) -> dict[str, Any]:
        """Send a password reset instructions email with luxury TARK aesthetic."""
        display_name = user_name or "Developer"
        subject = "Reset your TARK AI password"
        expire_mins = self.settings.password_reset_token_expire_minutes

        text_content = (
            f"TARK AI\n\n"
            f"Hello {display_name},\n\n"
            f"We received a request to reset your TARK AI password.\n\n"
            f"Click the link below to set a new password:\n"
            f"{reset_url}\n\n"
            f"This link expires in {expire_mins} minutes.\n"
            f"If you did not request this password reset, you can safely ignore this email.\n\n"
            f"— TARK AI Team"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #050505;
      color: #F2F0EB;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    .container {{
      max-width: 540px;
      margin: 40px auto;
      background-color: #0B0B0C;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      padding: 40px 36px;
    }}
    .logo {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 2px;
      color: #F2F0EB;
      margin-bottom: 30px;
    }}
    .logo span {{
      color: #C9A86A;
      font-style: italic;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 500;
      color: #F2F0EB;
      margin: 0 0 16px 0;
      letter-spacing: -0.5px;
    }}
    p {{
      font-size: 14px;
      line-height: 1.6;
      color: #A3A09A;
      margin: 0 0 24px 0;
    }}
    .btn-container {{
      margin: 32px 0;
    }}
    .btn {{
      display: inline-block;
      background: linear-gradient(135deg, #C9A86A 0%, #B08D4C 100%);
      color: #050505 !important;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 1px;
      text-transform: uppercase;
      padding: 14px 28px;
      border-radius: 10px;
    }}
    .footer {{
      margin-top: 36px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      font-size: 12px;
      color: #74716C;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">TARK <span>AI</span></div>
    <h1>Reset your password</h1>
    <p>Hello {display_name},</p>
    <p>We received a request to reset your TARK AI account password. Click the button below to choose a new secure password:</p>
    <div class="btn-container">
      <a href="{reset_url}" class="btn" target="_blank">Reset Password</a>
    </div>
    <p>This password reset link expires in <strong>{expire_mins} minutes</strong>.</p>
    <p>If you did not request this change, no action is needed and your account remains secure.</p>
    <div class="footer">
      TARK AI Workstation &middot; End-to-End Encrypted Session<br>
      If the button above does not work, copy and paste this URL into your browser:<br>
      <span style="color: #C9A86A; word-break: break-all;">{reset_url}</span>
    </div>
  </div>
</body>
</html>"""

        return await self.send_email(
            to=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            email_type="password_reset",
        )

    async def send_verification_email(
        self,
        to_email: str,
        verification_url: str,
        user_name: str | None = None,
    ) -> dict[str, Any]:
        """Send an email verification message to activate new accounts."""
        display_name = user_name or "Developer"
        subject = "Verify your TARK AI email"
        expire_hours = self.settings.email_verification_token_expire_hours

        text_content = (
            f"TARK AI\n\n"
            f"Welcome to TARK AI, {display_name}.\n\n"
            f"Please verify your email address to activate your account:\n"
            f"{verification_url}\n\n"
            f"This verification link expires in {expire_hours} hours.\n\n"
            f"— TARK AI Team"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #050505;
      color: #F2F0EB;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    .container {{
      max-width: 540px;
      margin: 40px auto;
      background-color: #0B0B0C;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      padding: 40px 36px;
    }}
    .logo {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 2px;
      color: #F2F0EB;
      margin-bottom: 30px;
    }}
    .logo span {{
      color: #C9A86A;
      font-style: italic;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 500;
      color: #F2F0EB;
      margin: 0 0 16px 0;
      letter-spacing: -0.5px;
    }}
    p {{
      font-size: 14px;
      line-height: 1.6;
      color: #A3A09A;
      margin: 0 0 24px 0;
    }}
    .btn-container {{
      margin: 32px 0;
    }}
    .btn {{
      display: inline-block;
      background: linear-gradient(135deg, #C9A86A 0%, #B08D4C 100%);
      color: #050505 !important;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 1px;
      text-transform: uppercase;
      padding: 14px 28px;
      border-radius: 10px;
    }}
    .footer {{
      margin-top: 36px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      font-size: 12px;
      color: #74716C;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">TARK <span>AI</span></div>
    <h1>Welcome to TARK AI</h1>
    <p>Hello {display_name},</p>
    <p>Thank you for creating your TARK AI account. Please confirm your email address to activate your intelligence workstation:</p>
    <div class="btn-container">
      <a href="{verification_url}" class="btn" target="_blank">Verify Email</a>
    </div>
    <p>This link expires in <strong>{expire_hours} hours</strong>.</p>
    <div class="footer">
      TARK AI Workstation &middot; End-to-End Encrypted Session<br>
      If the button above does not work, copy and paste this URL into your browser:<br>
      <span style="color: #C9A86A; word-break: break-all;">{verification_url}</span>
    </div>
  </div>
</body>
</html>"""

        return await self.send_email(
            to=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            email_type="email_verification",
        )


email_service = EmailService()
