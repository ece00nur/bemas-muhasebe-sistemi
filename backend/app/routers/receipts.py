from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app import models, schemas

router = APIRouter(prefix="/api/receipts", tags=["receipts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[schemas.ReceiptOut])
def list_receipts(unmatched_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.Receipt)
    if unmatched_only:
        query = query.filter(models.Receipt.transaction_id.is_(None))
    return query.order_by(models.Receipt.uploaded_at.desc()).all()


@router.get("/{receipt_id}", response_model=schemas.ReceiptOut)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.query(models.Receipt).get(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Dekont bulunamadı")
    return receipt


@router.post("/{receipt_id}/confirm", response_model=schemas.TransactionOut)
def confirm_receipt(receipt_id: int, payload: schemas.ReceiptConfirm, db: Session = Depends(get_db)):
    """
    Turns a parsed receipt into a ledger Transaction once a human confirms/corrects
    the auto-extracted company, direction and amount (extraction is heuristic since
    bank receipt layouts are not standardized).
    """
    receipt = db.query(models.Receipt).get(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Dekont bulunamadı")
    if receipt.transaction_id:
        raise HTTPException(status_code=409, detail="Bu dekont zaten bir işlemle ilişkilendirilmiş")

    company = db.query(models.Company).get(payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")

    amount = payload.amount if payload.amount is not None else receipt.parsed_amount
    transaction_date = payload.transaction_date if payload.transaction_date is not None else receipt.parsed_date
    if amount is None or transaction_date is None:
        raise HTTPException(status_code=422, detail="Tutar ve tarih belirtilmeli (otomatik ayrıştırılamadı)")

    counterparty_name = receipt.sender_name if payload.direction == models.TransactionDirection.INFLOW else receipt.receiver_name
    counterparty_iban = receipt.sender_iban if payload.direction == models.TransactionDirection.INFLOW else receipt.receiver_iban

    tx = models.Transaction(
        company_id=company.id,
        direction=payload.direction,
        transaction_date=transaction_date,
        amount=amount,
        currency=receipt.parsed_currency or "TRY",
        counterparty_name=counterparty_name,
        counterparty_iban=counterparty_iban,
        description=payload.description or receipt.description,
        source="receipt_pdf",
        receipt_id=receipt.id,
    )
    db.add(tx)
    db.flush()

    receipt.transaction_id = tx.id
    receipt.matched_company_id = company.id
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{receipt_id}", status_code=204)
def delete_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.query(models.Receipt).get(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Dekont bulunamadı")
    db.delete(receipt)
    db.commit()
    return None
