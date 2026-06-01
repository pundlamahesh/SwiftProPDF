import os
import secrets
import smtplib
from email.message import EmailMessage

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


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
        raise EmailOtpError(
            f"Could not send OTP email. SMTP error: {exc}"
        ) from exc


def send_registration_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "verification")


def send_login_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "login")


def send_password_reset_otp(recipient: str, otp: str) -> None:
    send_email_otp(recipient, otp, "password reset")


def verify_recipient_email_with_aws_ses(recipient: str) -> None:
    """Verify recipient email address with AWS SES.
    
    This is required when using AWS SES in sandbox mode to send emails
    to new (unverified) email addresses.
    """
    if not BOTO3_AVAILABLE:
        return
    
    # Only use boto3 if we're using AWS SES (detected by SMTP server)
    smtp_server = os.environ.get("SMTP_SERVER", "").strip()
    if "email" not in smtp_server or "amazonaws" not in smtp_server:
        return
    
    try:
        aws_region = os.environ.get("AWS_REGION", "us-east-1").strip()
        aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
        aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
        
        if not aws_access_key or not aws_secret_key:
            # Try to use default credentials from environment or IAM role
            ses_client = boto3.client("ses", region_name=aws_region)
        else:
            ses_client = boto3.client(
                "ses",
                region_name=aws_region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
            )
        
        # Verify the email identity
        ses_client.verify_email_identity(EmailAddress=recipient)
    except Exception as exc:
        # Log the error but don't fail - the email sending might still work
        # if the email was already verified or if we're not using AWS SES
        import sys
        print(f"Warning: Could not verify email {recipient} with AWS SES: {exc}", file=sys.stderr)
