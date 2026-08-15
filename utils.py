import re
import secrets
import smtplib
import string
from datetime import datetime
from email.mime.text import MIMEText

from flask import current_app
from models import db, EmailOutbox, Student


def validate_password(pwd: str) -> str | None:
    """Returns an error message, or None if the password is acceptable.
    Rule from the spec: 12 characters, a combination of numbers and
    letters."""
    if len(pwd) != 12:
        return "Password must be exactly 12 characters long."
    if not re.search(r"[A-Za-z]", pwd):
        return "Password must include at least one letter."
    if not re.search(r"[0-9]", pwd):
        return "Password must include at least one number."
    if not re.fullmatch(r"[A-Za-z0-9]{12}", pwd):
        return "Password may only contain letters and numbers."
    return None


def generate_temp_password(length: int = 12) -> str:
    """Generates a random password that satisfies validate_password()."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if validate_password(pwd) is None:
            return pwd


def generate_registration_number() -> str:
    year = datetime.utcnow().year
    count = Student.query.count() + 1
    candidate = f"WASKO/{year}/{count:04d}"
    # Guard against gaps left by deleted students causing a collision.
    while Student.query.filter_by(registration_number=candidate).first():
        count += 1
        candidate = f"WASKO/{year}/{count:04d}"
    return candidate


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Sends an email via SMTP if credentials are configured. Either way,
    a copy is logged to EmailOutbox so it can be reviewed from the admin
    dashboard — useful for local testing without a mail server."""
    cfg = current_app.config
    sent_via_smtp = False

    if cfg.get("SMTP_HOST") and cfg.get("SMTP_USER"):
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = cfg["SMTP_FROM"]
            msg["To"] = to_email
            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"]) as server:
                server.starttls()
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                server.sendmail(cfg["SMTP_FROM"], [to_email], msg.as_string())
            sent_via_smtp = True
        except Exception as exc:  # noqa: BLE001 - prototype-level logging
            current_app.logger.warning("SMTP send failed: %s", exc)

    db.session.add(
        EmailOutbox(
            to_email=to_email,
            subject=subject,
            body=body,
            sent_via_smtp=sent_via_smtp,
        )
    )
    db.session.commit()
    return sent_via_smtp
