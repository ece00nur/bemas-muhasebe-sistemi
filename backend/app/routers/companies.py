from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app import models, schemas

router = APIRouter(prefix="/api/companies", tags=["companies"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[schemas.CompanyOut])
def list_companies(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Company)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Company.name.ilike(like)) | (models.Company.tax_id.ilike(like))
        )
    return query.order_by(models.Company.name).all()


@router.post("", response_model=schemas.CompanyOut, status_code=201)
def create_company(payload: schemas.CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Company).filter(models.Company.tax_id == payload.tax_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Bu vergi numarasına sahip firma zaten mevcut")
    company = models.Company(**payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/{company_id}", response_model=schemas.CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    return company


@router.patch("/{company_id}", response_model=schemas.CompanyOut)
def update_company(company_id: int, payload: schemas.CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    db.delete(company)
    db.commit()
    return None


@router.get("/{company_id}/balance", response_model=schemas.CompanyBalance)
def get_company_balance(company_id: int, db: Session = Depends(get_db)):
    from app.services.ledger_service import compute_balance

    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Firma bulunamadı")
    return compute_balance(db, company)


@router.get("/balances/all", response_model=List[schemas.CompanyBalance])
def get_all_balances(db: Session = Depends(get_db)):
    from app.services.ledger_service import compute_balance

    companies = db.query(models.Company).order_by(models.Company.name).all()
    return [compute_balance(db, c) for c in companies]
