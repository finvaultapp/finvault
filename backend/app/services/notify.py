"""Bill reminders by email (SMTP) or ntfy push. Both optional; nothing is sent unless a member sets it up."""
import logging
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import Account, Recurring, User
from .recurring import occurrences

log = logging.getLogger("finvault.notify")


def smtp_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        if config.SMTP_STARTTLS:
            s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)


def send_ntfy(url: str, title: str, body: str) -> None:
    r = httpx.post(url, content=body.encode(), headers={"Title": title, "Tags": "calendar"}, timeout=15)
    r.raise_for_status()


def deliver(user: User, title: str, body: str) -> list[str]:
    """Send through every channel the member turned on. Returns the channels that worked."""
    sent = []
    if user.notify_ntfy_url:
        try:
            send_ntfy(user.notify_ntfy_url, title, body)
            sent.append("ntfy")
        except Exception as exc:  # noqa: BLE001
            log.warning("ntfy failed for user %s: %s", user.id, exc)
    if user.notify_email and smtp_configured():
        try:
            send_email(user.email, title, body)
            sent.append("email")
        except Exception as exc:  # noqa: BLE001
            log.warning("email failed for user %s: %s", user.id, exc)
    return sent


def bill_line(r: Recurring, when: date, currency: str, hide_amounts: bool) -> str:
    amount = "" if hide_amounts else f" {'-' if r.amount < 0 else ''}{abs(float(r.amount)):,.2f} {currency}"
    days = (when - date.today()).days
    due = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days ({when:%b %d})"
    return f"{r.name}{amount} is due {due}."


def send_due_reminders(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    sent = 0
    for r in db.scalars(select(Recurring).where(Recurring.is_active.is_(True), Recurring.remind_days.is_not(None))):
        user = db.get(User, r.user_id)
        if not user or not user.is_active or not (user.notify_ntfy_url or (user.notify_email and smtp_configured())):
            continue
        acct = db.get(Account, r.account_id)
        for when in occurrences(r, today + timedelta(days=r.remind_days), limit=3):
            if when < today or (r.last_reminded_for and when <= r.last_reminded_for):
                continue
            if (when - today).days <= r.remind_days:
                if deliver(user, "FinVault bill reminder", bill_line(r, when, acct.currency if acct else "", user.notify_hide_amounts)):
                    sent += 1
                r.last_reminded_for = when
    db.commit()
    return sent
