"""
Email sender via SMTP (supports Gmail App Passwords and generic SMTP).

Credentials are read exclusively from environment variables — no secrets in code.

Required env vars:
  SMTP_USER     sending account (e.g. you@gmail.com)
  SMTP_PASSWORD app password or SMTP password

Optional env vars:
  SMTP_HOST  default: smtp.gmail.com
  SMTP_PORT  default: 587  (STARTTLS)
  SMTP_FROM  default: same as SMTP_USER
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(to_addr: str, subject: str, body: str) -> None:
    """
    Send a plain-text email via SMTP STARTTLS.

    Raises RuntimeError if credentials are missing.
    Raises smtplib.SMTPException (or subclass) on delivery failure.
    """
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not user or not password:
        raise RuntimeError(
            "SMTP_USER and SMTP_PASSWORD must be set as environment variables."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())

    logger.info("Email sent to %s  subject: %s", to_addr, subject)
