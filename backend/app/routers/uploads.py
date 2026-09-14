import os
import uuid
import shutil

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.config import settings
from app import models, schemas
from app.services.excel_ingest import ingest_invoice_excel
from app.services.pdf_receipt_parser import parse_receipt

router = APIRouter(prefix="/api/uploads", tags=["uploads"], dependencies=[Depends(get_current_user)])

ALLOWED_EXCEL_EXT = {".xlsx", ".xls"}
ALLOWED_PDF_EXT = {".pdf"}


def _save_upload(upload: UploadFile, subdir: str) -> str:
    ext = os.path.splitext(upload.filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest_dir = os.path.join(settings.upload_dir, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, unique_name)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest_path


@router.post("/invoices/excel", response_model=schemas.IngestResult)
def upload_invoice_excel(
    direction: models.InvoiceDirection = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXCEL_EXT:
        raise HTTPException(status_code=400, detail="Sadece .xlsx/.xls dosyaları kabul edilir")

    dest_path = _save_upload(file, "excel")
    try:
        result = ingest_invoice_excel(db, dest_path, file.filename, direction)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Excel işlenemedi: {exc}")
    return result


@router.post("/receipts/pdf", response_model=schemas.ReceiptOut)
def upload_receipt_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_PDF_EXT:
        raise HTTPException(status_code=400, detail="Sadece .pdf dosyaları kabul edilir")

    dest_path = _save_upload(file, "receipts")
    try:
        parsed = parse_receipt(dest_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Dekont işlenemedi: {exc}")

    matched_company = None
    for iban in filter(None, [parsed.sender_iban, parsed.receiver_iban]):
        matched_company = db.query(models.Company).filter(models.Company.iban == iban).first()
        if matched_company:
            break

    receipt = models.Receipt(
        filename=file.filename,
        file_path=dest_path,
        raw_text=parsed.raw_text,
        ocr_used=parsed.ocr_used,
        parsed_amount=parsed.amount,
        parsed_date=parsed.transaction_date,
        parsed_currency=parsed.currency,
        sender_name=parsed.sender_name,
        receiver_name=parsed.receiver_name,
        sender_iban=parsed.sender_iban,
        receiver_iban=parsed.receiver_iban,
        description=parsed.description,
        matched_company_id=matched_company.id if matched_company else None,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt
