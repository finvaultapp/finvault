import csv
import io
import json
import datetime as dt
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Attachment, Category, Share, Transaction, TransactionSplit, User
from ..services import receipts
from ..services.ledger import Categorizer
from ..services.reports import f2

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def tx_out(t: Transaction) -> dict:
    return {"id": t.id, "account_id": t.account_id, "account_name": t.account.name, "currency": t.account.currency,
            "date": t.date.isoformat(), "amount": f2(t.amount), "description": t.description, "payee": t.payee,
            "notes": t.notes, "category_id": t.category_id,
            "category_name": t.category.name if t.category else None,
            "category_color": t.category.color if t.category else None,
            "recurring_id": t.recurring_id, "import_batch_id": t.import_batch_id,
            "transfer_id": t.transfer_id, "tax_tag": t.tax_tag}


def add_flags(db: Session, items: list[dict]) -> list[dict]:
    """Mark which transactions have receipts, splits or shares, without one query per row."""
    ids = [i["id"] for i in items]
    if not ids:
        return items
    att = dict(db.execute(select(Attachment.transaction_id, func.count(Attachment.id))
                          .where(Attachment.transaction_id.in_(ids)).group_by(Attachment.transaction_id)).all())
    spl = dict(db.execute(select(TransactionSplit.transaction_id, func.count(TransactionSplit.id))
                          .where(TransactionSplit.transaction_id.in_(ids)).group_by(TransactionSplit.transaction_id)).all())
    shr = dict(db.execute(select(Share.transaction_id, func.coalesce(func.sum(Share.amount), 0))
                          .where(Share.transaction_id.in_(ids)).group_by(Share.transaction_id)).all())
    for i in items:
        i["attachments"] = att.get(i["id"], 0)
        i["split"] = spl.get(i["id"], 0) > 0
        i["shared"] = f2(Decimal(str(shr[i["id"]]))) if i["id"] in shr else 0
    return items


def _filtered(user: User, q: str | None, account_id: list[int] | None, category_id: list[int] | None,
              uncategorized: bool, start: date | None, end: date | None, min_amount: Decimal | None,
              max_amount: Decimal | None, kind: str | None):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if q:
        like = f"%{q.strip()}%"
        in_receipts = select(Attachment.transaction_id).where(Attachment.ocr_text.ilike(like))
        stmt = stmt.where(or_(Transaction.description.ilike(like), Transaction.payee.ilike(like),
                              Transaction.notes.ilike(like), Transaction.id.in_(in_receipts)))
    if account_id:
        stmt = stmt.where(Transaction.account_id.in_(account_id))
    if uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    elif category_id:
        stmt = stmt.where(Transaction.category_id.in_(category_id))
    if start:
        stmt = stmt.where(Transaction.date >= start)
    if end:
        stmt = stmt.where(Transaction.date <= end)
    if min_amount is not None:
        stmt = stmt.where(func.abs(Transaction.amount) >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(func.abs(Transaction.amount) <= max_amount)
    if kind == "income":
        stmt = stmt.where(Transaction.amount > 0)
    elif kind == "expense":
        stmt = stmt.where(Transaction.amount < 0)
    return stmt


def _filters(q: str | None = None, account_id: list[int] | None = Query(None), category_id: list[int] | None = Query(None),
             uncategorized: bool = False, start: date | None = None, end: date | None = None,
             min_amount: Decimal | None = None, max_amount: Decimal | None = None, kind: str | None = None):
    return dict(q=q, account_id=account_id, category_id=category_id, uncategorized=uncategorized, start=start,
                end=end, min_amount=min_amount, max_amount=max_amount, kind=kind)


@router.get("")
def list_transactions(f: dict = Depends(_filters), page: int = 1, page_size: int = Query(50, le=500),
                      sort: str = "-date", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = _filtered(user, **f)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    amounts = stmt.with_only_columns(Transaction.amount).subquery()
    inflow, outflow = db.execute(select(
        func.coalesce(func.sum(case((amounts.c.amount > 0, amounts.c.amount), else_=0)), 0),
        func.coalesce(func.sum(case((amounts.c.amount < 0, amounts.c.amount), else_=0)), 0))).one()
    col = {"date": Transaction.date, "amount": Transaction.amount, "description": Transaction.description}.get(sort.lstrip("-"), Transaction.date)
    order = col.desc() if sort.startswith("-") else col.asc()
    rows = list(db.scalars(stmt.order_by(order, Transaction.id.desc()).offset((page - 1) * page_size).limit(page_size)).unique())
    items = add_flags(db, [tx_out(t) for t in rows])
    if f.get("uncategorized"):
        cat = Categorizer(db, user.id)
        kinds = dict(db.execute(select(Category.id, Category.kind).where(Category.user_id == user.id)).all())
        for item, t in zip(items, rows):
            item["suggestions"] = cat.suggest(t.description, Decimal(t.amount), kinds)
    # Sums mix currencies when several accounts are selected; the UI labels them as raw totals.
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "inflow": f2(Decimal(str(inflow))), "outflow": f2(Decimal(str(outflow)))}


class TxIn(BaseModel):
    account_id: int
    date: dt.date
    amount: Decimal
    description: str = Field(max_length=500)
    payee: str = Field(default="", max_length=200)
    notes: str = ""
    category_id: int | None = None


class TxPatch(BaseModel):
    account_id: int | None = None
    date: dt.date | None = None
    amount: Decimal | None = None
    description: str | None = Field(default=None, max_length=500)
    payee: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    category_id: int | None = None


def _check_refs(db: Session, user: User, account_id: int | None, category_id: int | None):
    if account_id is not None:
        owned(db, Account, account_id, user)
    if category_id is not None:
        owned(db, Category, category_id, user)


@router.post("")
def create_transaction(body: TxIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check_refs(db, user, body.account_id, body.category_id)
    t = Transaction(user_id=user.id, **body.model_dump(exclude={"amount"}), amount=body.amount)
    db.add(t)
    db.commit()
    db.refresh(t)
    return tx_out(t)


@router.patch("/{tx_id}")
def update_transaction(tx_id: int, body: TxPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tx_id, user)
    data = body.model_dump(exclude_unset=True)
    _check_refs(db, user, data.get("account_id"), data.get("category_id"))
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return tx_out(t)


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tx_id, user)
    receipts.unlink_for_transactions(db, [t.id])
    db.delete(t)
    db.commit()
    return {"ok": True}


class BulkIn(BaseModel):
    ids: list[int]
    action: str = Field(pattern="^(categorize|delete)$")
    category_id: int | None = None


@router.post("/bulk")
def bulk(body: BulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category_id is not None:
        owned(db, Category, body.category_id, user)
    rows = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.id.in_(body.ids))))
    if body.action == "delete":
        receipts.unlink_for_transactions(db, [t.id for t in rows])
    for t in rows:
        if body.action == "delete":
            db.delete(t)
        else:
            t.category_id = body.category_id
    db.commit()
    return {"updated": len(rows)}


def _ofx_export(rows: list[Transaction]) -> str:
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    lines = ["OFXHEADER:100", "DATA:OFXSGML", "VERSION:102", "SECURITY:NONE", "ENCODING:USASCII", "CHARSET:1252",
             "COMPRESSION:NONE", "OLDFILEUID:NONE", "NEWFILEUID:NONE", "", "<OFX>", "<BANKMSGSRSV1>"]
    by_acct: dict[int, list[Transaction]] = {}
    for t in rows:
        by_acct.setdefault(t.account_id, []).append(t)
    for acct_rows in by_acct.values():
        a = acct_rows[0].account
        lines += ["<STMTTRNRS>", "<TRNUID>0", "<STMTRS>", f"<CURDEF>{a.currency}", "<BANKACCTFROM>",
                  f"<ACCTID>FINVAULT-{a.id}", "<ACCTTYPE>CHECKING", "</BANKACCTFROM>", "<BANKTRANLIST>",
                  f"<DTSTART>{min(t.date for t in acct_rows):%Y%m%d}", f"<DTEND>{max(t.date for t in acct_rows):%Y%m%d}"]
        for t in acct_rows:
            lines += ["<STMTTRN>", f"<TRNTYPE>{'CREDIT' if t.amount > 0 else 'DEBIT'}", f"<DTPOSTED>{t.date:%Y%m%d}",
                      f"<TRNAMT>{Decimal(t.amount):.2f}", f"<FITID>{t.external_id or f'FV{t.id}'}",
                      f"<NAME>{escape((t.payee or t.description)[:32])}", f"<MEMO>{escape(t.description[:255])}", "</STMTTRN>"]
        lines += ["</BANKTRANLIST>", "</STMTRS>", "</STMTTRNRS>"]
    lines += ["</BANKMSGSRSV1>", "</OFX>", f"<!-- exported by FinVault {now} -->"]
    return "\r\n".join(lines)


@router.get("/export")
def export(f: dict = Depends(_filters), format: str = Query("csv", pattern="^(csv|ofx|json)$"),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(_filtered(user, **f).order_by(Transaction.date, Transaction.id)).unique())
    stamp = date.today().isoformat()
    if format == "json":
        body = json.dumps([tx_out(t) for t in rows], indent=2)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="finvault-{stamp}.json"'})
    if format == "ofx":
        return Response(_ofx_export(rows), media_type="application/x-ofx",
                        headers={"Content-Disposition": f'attachment; filename="finvault-{stamp}.ofx"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Account", "Description", "Payee", "Category", "Amount", "Currency", "Notes"])
    for t in rows:
        w.writerow([t.date.isoformat(), t.account.name, t.description, t.payee,
                    t.category.name if t.category else "", f"{Decimal(t.amount):.2f}", t.account.currency, t.notes])
    return Response("﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="finvault-{stamp}.csv"'})
