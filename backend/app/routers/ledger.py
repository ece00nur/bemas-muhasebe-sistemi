from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app import models, schemas
from app.services.ledger_service import build_ledger
from app.services.excel_export import export_company_ledger
from app.services.pdf_export import export_company_ledger_pdf

router = APIRouter(prefix="/api/ledger", tags=["ledger"], dependencies=[Depends(get_current_user)])


@router.get("/{company_id}", response_model=schemas.LedgerResponse)
def get_ledger(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    return build_ledger(db, company)


@router.get("/{company_id}/export")
def export_ledger(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    ledger = build_ledger(db, company)
    file_path = export_company_ledger(ledger)
    filename = file_path.split("/")[-1].split("\\")[-1]
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.get("/{company_id}/export-pdf")
def export_ledger_pdf(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    ledger = build_ledger(db, company)
    file_path = export_company_ledger_pdf(ledger)
    filename = file_path.split("/")[-1].split("\\")[-1]
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=filename,
    )
