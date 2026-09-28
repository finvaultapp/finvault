"""Once-a-day jobs, called from the hourly scheduler: encrypted backup and audit-log pruning."""
import logging
from datetime import datetime

from .. import config_admin, settings_store
from ..db import SessionLocal
from . import audit, backup

log = logging.getLogger("finvault.nightly")


def run_if_due(now: datetime | None = None) -> bool:
    """Run the daily jobs at the first hourly check at or after BACKUP_HOUR (local time), once per day."""
    now = now or datetime.now()
    today = now.date().isoformat()
    with SessionLocal() as db:
        if settings_store.get(db, "nightly_last_date") == today or now.hour < config_admin.BACKUP_HOUR:
            return False
        settings_store.set(db, "nightly_last_date", today)
        db.commit()
        try:
            audit.prune(db)
        except Exception:  # noqa: BLE001
            log.exception("audit pruning failed")
        enabled = backup.get_enabled(db)
    if enabled:
        try:
            backup.run_backup("nightly")
        except backup.BackupError as exc:
            log.warning("nightly backup skipped: %s", exc)
    return True
