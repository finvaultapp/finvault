import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..importers import MAX_BYTES, parse_file
from ..importers.presets import public_presets
from ..importers.csvfile import ROLES
from ..models import Account, Category, ImportBatch, Transaction, User
from ..services import receipts, transfers

from ..services.charge_alerts import run_safely as charge_alerts_after_import
from ..services.ledger import Categorizer, commit_import, plan_import
from ..services.reports import f2

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("/presets")
def presets(_: User = Depends(current_user)):
    return {"presets": public_presets(), "roles": ROLES}


async def _parse(file: UploadFile, account: Account, options: str | None):
    opts = json.loads(options) if options else {}
    raw = await file.read(MAX_BYTES + 1)
    try:
        return parse_file(file.filename or "", raw, preset_id=opts.get("preset") or account.import_preset,
                          mapping=opts.get("mapping") or None, date_format=opts.get("date_format") or None,
                          invert=opts.get("invert"), account_type=account.type, account_currency=account.currency)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/preview")
async def preview(account_id: int = Form(...), options: str | None = Form(None), file: UploadFile = File(...),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    result = await _parse(file, account, options)
    planned = plan_import(db, account, result.transactions)
    cat = Categorizer(db, user.id)
    names = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    rows = []
    for p in planned[:300]:
        t = p["txn"]
        cid, payee, source = cat.apply(t.description, t.payee, t.amount, account.id)
        rows.append({"date": t.date.isoformat(), "amount": f2(t.amount), "description": t.description,
                     "duplicate": p["duplicate"], "category": names.get(cid), "category_source": source,
                     "bank_category": t.bank_category})
    new = sum(1 for p in planned if not p["duplicate"])
    blocked_note = None
    if result.currency and result.currency.upper() != account.currency:
        result.warnings.append(f"The file says {result.currency} but this account is {account.currency}.")
    return {
        "format": result.format, "preset": result.preset, "columns": result.columns, "mapping": result.mapping,
        "sample_rows": result.sample_rows, "date_format": result.date_format,
        "date_format_ambiguous": result.date_format_ambiguous, "inverted": result.inverted,
        "total": len(planned), "new": new, "duplicates": len(planned) - new,
        "date_range": [min(t.date for t in result.transactions).isoformat(),
                       max(t.date for t in result.transactions).isoformat()] if result.transactions else None,
        "statement_balance": f2(result.statement_balance) if result.statement_balance is not None else None,
        "rows": rows, "warnings": result.warnings[:20], "note": blocked_note,
    }


@router.post("/commit")
async def commit(account_id: int = Form(...), options: str | None = Form(None), file: UploadFile = File(...),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    result = await _parse(file, account, options)
    if not result.transactions:
        raise HTTPException(422, "Nothing to import. " + " ".join(result.warnings[:3]))
    batch = commit_import(db, user, account, result, file.filename or "upload")
    matched = transfers.auto_match(db, user)
    charge_alerts_after_import(db, user)
    return {"batch_id": batch.id, "imported": batch.imported, "skipped": batch.skipped, "transfers_matched": matched}


@router.get("/batches")
def batches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    accts = {a.id: a.name for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    return [{"id": b.id, "account_id": b.account_id, "account_name": accts.get(b.account_id), "filename": b.filename,
             "format": b.format, "preset": b.preset, "imported": b.imported, "skipped": b.skipped,
             "created_at": b.created_at.isoformat()}
            for b in db.scalars(select(ImportBatch).where(ImportBatch.user_id == user.id)
                                .order_by(ImportBatch.created_at.desc()).limit(50))]


@router.delete("/batches/{batch_id}")
def undo_batch(batch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Undo an import: removes every transaction that came from that file."""
    b = owned(db, ImportBatch, batch_id, user)
    removed = 0
    rows = list(db.scalars(select(Transaction).where(Transaction.import_batch_id == b.id)))
    receipts.unlink_for_transactions(db, [t.id for t in rows])
    for t in rows:
        db.delete(t)
        removed += 1
    db.delete(b)
    db.commit()
    return {"removed": removed}
