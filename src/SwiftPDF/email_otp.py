import os
import secrets
import smtplib
from email.message import EmailMessage


class EmailOtpError(Exception):
    """Raised when an email OTP cannot be sent."""


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_email_otp(recipient: str, otp: str, purpose: str = "verification") -> None:
    smtp_server = os.environ.get("SMTP_SERVER", "").strip()
    sender_email = os.environ.get("SENDER_EMAIL", "").strip()
    if not smtp_server or not sender_email:
        raise EmailOtpError("Email OTP is not configured. Set SMTP_SERVER and SENDER_EMAIL.")

    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as exc:
        raise EmailOtpError("SMTP_PORT must be a number.") from exc
    smtp_username = os.environ.get("SMTP_USERNAME", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_use_tls = os.environ.get("SMTP_USE_TLS", "1") == "1"

    message = EmailMessage()
    message["Subject"] = f"Your SwiftPDF {purpose} code"
    message["From"] = sender_email
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                f"Your SwiftPDF {purpose} code is:",
                "",
                otp,
                "",
                "This code expires soon. If you did not request it, you can ignore this email.",
            ]
        )
    )

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as smtp:
            if smtp_use_tls:
                smtp.starttls()
            if smtp_username or smtp_password:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailOtpError("Could not send OTP email. Check SMTP settings.") from exc


def send_registration_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "verification")


def send_login_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "login")


def send_password_reset_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "password reset")
