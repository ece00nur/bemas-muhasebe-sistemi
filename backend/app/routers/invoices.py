from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app import models, schemas

router = APIRouter(prefix="/api/invoices", tags=["invoices"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[schemas.InvoiceOut])
def list_invoices(
    company_id: Optional[int] = None,
    direction: Optional[models.InvoiceDirection] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Invoice)
    if company_id:
        query = query.filter(models.Invoice.company_id == company_id)
    if direction:
        query = query.filter(models.Invoice.direction == direction)
    return query.order_by(models.Invoice.issue_date.desc()).all()


@router.post("", response_model=schemas.InvoiceOut, status_code=201)
def create_invoice(payload: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    invoice = models.Invoice(**payload.model_dump())
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).get(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    db.delete(invoice)
    db.commit()
    return None


@router.post("/transactions", response_model=schemas.TransactionOut, status_code=201)
def create_transaction(payload: schemas.TransactionCreate, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    tx = models.Transaction(**payload.model_dump(), source="manual")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.get("/transactions/list", response_model=List[schemas.TransactionOut])
def list_transactions(
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Transaction)
    if company_id:
        query = query.filter(models.Transaction.company_id == company_id)
    return query.order_by(models.Transaction.transaction_date.desc()).all()


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.query(models.Transaction).get(transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail="İşlem bulunamadı")
    db.delete(tx)
    db.commit()
    return None
