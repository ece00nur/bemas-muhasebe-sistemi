"""
Parses Kolaysoft e-Fatura/e-Arsiv Excel exports (incoming = Accounts Payable,
outgoing = Accounts Receivable) and upserts Company + Invoice rows.

Kolaysoft's actual e-Fatura list export carries BOTH parties of every invoice on
each row - "Gonderen"/"Gonderen URN"/"Gonderen Unvani" (sender) and "Alici"/
"Alici URN"/"Alici Unvani" (receiver) - regardless of whether the row came from
the "gelen" (incoming) or "giden" (outgoing) list. Kolaysoft uses "URN" (not
"Vergi No") as the column holding the party's tax id / VKN-TCKN. Which side is
"us" and which is "the counterparty we track a ledger for" therefore depends on
`direction`:
  - OUTGOING (giden - we are the sender): counterparty = Alici / Alici URN
  - INCOMING (gelen - we are the receiver): counterparty = Gonderen / Gonderen URN
Column names are matched by normalized keyword search (not fixed position) to
tolerate minor template differences, e.g.: Fatura No, Fatura Tarihi, Vade Tarihi,
Alici Unvani / Gonderen Unvani, Alici URN / Gonderen URN, Vergiler Dahil Tutar
(tax-inclusive total) / Vergiler Haric Tutar (tax-exclusive), Para Birimi, ETTN,
Aciklama.
"""
import re
import unicodedata
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app import models
from app.schemas import IngestResult


_TR_FOLD = {
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
}


def _normalize(text: str) -> str:
    text = str(text or "").strip().lower()
    # Fold Turkish-specific letters to ASCII *before* any Unicode normalization -
    # NFKD would otherwise decompose e.g. "ü" into "u" + a combining diaeresis,
    # which the regex below then strips out as a stray separator ("u nvan" bug).
    for src, dst in _TR_FOLD.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


# Each field maps to a list of normalized keyword-sets, tried in priority order; a
# column matches if ALL keywords in a set appear as substrings of its normalized
# header. The first set with any match wins, so more specific sets (e.g. the
# tax-inclusive total) must come before generic fallbacks (bare "tutar"). A
# keyword prefixed with "=" requires the WHOLE normalized header to equal it
# exactly, rather than just contain it as a substring.
def _column_keywords(direction: "models.InvoiceDirection") -> dict:
    # The counterparty is whoever ISN'T us: the buyer (Alici) when we issued the
    # invoice (outgoing), the seller (Gonderen) when we received it (incoming).
    party = "alici" if direction == models.InvoiceDirection.OUTGOING else "gonderen"
    return {
        "invoice_number": [["fatura", "no"], ["fatura", "numara"], ["belge", "no"]],
        "issue_date": [["fatura", "tarih"], ["duzenlenme", "tarih"], ["duzenleme", "tarih"]],
        "due_date": [["vade", "tarih"], ["odeme", "tarih"]],
        "company_name": [[party, "unvan"], ["unvan"], [party], ["musteri"], ["firma", "ad"]],
        "tax_id": [
            # The bare "Alici"/"Gonderen" column holds the actual VKN/TCKN digits.
            # "...URN" is a *different* e-Fatura postbox/routing reference, not a
            # tax id, even though the name looks related - so it is NOT matched
            # here (see the module docstring).
            ["=" + party],
            ["vergi", "no"], ["vergi", "kimlik"], ["tc", "kimlik"], ["vkn"], ["tckn"],
        ],
        "tax_office": [["vergi", "daire"]],
        "amount": [
            ["vergiler", "dahil", "tutar"], ["odenecek", "tutar"], ["genel", "toplam"],
            ["toplam", "tutar"], ["tutar"],
        ],
        "tax_exclusive_amount": [["vergiler", "haric", "tutar"]],
        "tax_amount": [["kdv", "tutar"], ["vergi", "tutar"]],
        "currency": [["para", "birim"], ["doviz"]],
        "ettn": [["ettn"], ["uuid"]],
        "description": [["aciklama"], ["not"], ["urun", "hizmet"]],
    }


@dataclass
class ColumnMap:
    mapping: dict = field(default_factory=dict)

    def get(self, field_name: str) -> Optional[str]:
        return self.mapping.get(field_name)


def _keyword_matches(norm: str, keyword: str) -> bool:
    if keyword.startswith("="):
        return norm == keyword[1:]
    return keyword in norm


def _detect_columns(columns, direction: "models.InvoiceDirection") -> ColumnMap:
    normalized_cols = {col: _normalize(col) for col in columns}
    mapping = {}
    used_columns = set()
    for field_name, keyword_sets in _column_keywords(direction).items():
        for keywords in keyword_sets:
            found = None
            for original_col, norm in normalized_cols.items():
                # Skip columns already claimed by an earlier (higher-priority) field -
                # e.g. "vergi" is a substring of "vergiler", so a loose tax_amount
                # keyword set could otherwise re-match "Vergiler Dahil/Haric Tutar"
                # after "amount"/"tax_exclusive_amount" already claimed them.
                if original_col in used_columns:
                    continue
                if all(_keyword_matches(norm, kw) for kw in keywords):
                    found = original_col
                    break
            if found:
                mapping[field_name] = found
                used_columns.add(found)
                break
    return ColumnMap(mapping=mapping)


_DATE_FORMATS = ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y %H:%M:%S"]


def _parse_date(value) -> Optional[dt.date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _parse_amount(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if "," in text and "." in text:
        # Turkish format: 1.234,56 -> thousands '.', decimal ','
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _clean_tax_id(value) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = re.sub(r"\D", "", str(value))
    return text or None


def ingest_invoice_excel(
    db: Session,
    file_path: str,
    filename: str,
    direction: models.InvoiceDirection,
) -> IngestResult:
    df = pd.read_excel(file_path, dtype=object)
    df = df.dropna(how="all")

    col_map = _detect_columns(df.columns, direction)
    errors = []
    invoices_created = 0
    invoices_skipped = 0
    companies_created = 0

    required = ["invoice_number", "issue_date", "company_name", "tax_id", "amount"]
    missing = [f for f in required if col_map.get(f) is None]
    if missing:
        errors.append(
            f"Could not detect required columns: {missing}. "
            f"Detected headers: {list(df.columns)}"
        )
        return IngestResult(
            filename=filename,
            direction=direction,
            rows_read=len(df),
            invoices_created=0,
            invoices_skipped_duplicate=0,
            companies_created=0,
            errors=errors,
        )

    for idx, row in df.iterrows():
        try:
            invoice_number = str(row[col_map.get("invoice_number")]).strip()
            if not invoice_number or invoice_number.lower() == "nan":
                continue

            company_name = str(row[col_map.get("company_name")]).strip()
            tax_id = _clean_tax_id(row[col_map.get("tax_id")])
            if not tax_id:
                errors.append(f"Row {idx + 2}: missing/invalid tax id for '{company_name}', skipped.")
                continue

            issue_date = _parse_date(row[col_map.get("issue_date")])
            if issue_date is None:
                errors.append(f"Row {idx + 2}: unparseable issue date, skipped.")
                continue

            amount = _parse_amount(row[col_map.get("amount")])
            if amount is None:
                errors.append(f"Row {idx + 2}: unparseable amount, skipped.")
                continue

            due_date = _parse_date(row[col_map.get("due_date")]) if col_map.get("due_date") else None
            tax_amount = _parse_amount(row[col_map.get("tax_amount")]) if col_map.get("tax_amount") else None
            if tax_amount is None and col_map.get("tax_exclusive_amount"):
                tax_exclusive = _parse_amount(row[col_map.get("tax_exclusive_amount")])
                if tax_exclusive is not None:
                    tax_amount = round(amount - tax_exclusive, 2)
            currency = str(row[col_map.get("currency")]).strip().upper() if col_map.get("currency") else "TRY"
            if not currency or currency.lower() == "nan":
                currency = "TRY"
            ettn = str(row[col_map.get("ettn")]).strip() if col_map.get("ettn") else None
            if ettn and ettn.lower() == "nan":
                ettn = None
            description = str(row[col_map.get("description")]).strip() if col_map.get("description") else None
            if description and description.lower() == "nan":
                description = None

            company = db.query(models.Company).filter(models.Company.tax_id == tax_id).first()
            if company is None:
                company = models.Company(name=company_name or tax_id, tax_id=tax_id)
                db.add(company)
                db.flush()
                companies_created += 1

            duplicate = db.query(models.Invoice).filter(
                models.Invoice.company_id == company.id,
                models.Invoice.invoice_number == invoice_number,
                models.Invoice.direction == direction,
            ).first()
            if duplicate is not None:
                invoices_skipped += 1
                continue

            invoice = models.Invoice(
                company_id=company.id,
                direction=direction,
                invoice_number=invoice_number,
                issue_date=issue_date,
                due_date=due_date,
                amount=amount,
                tax_amount=tax_amount,
                currency=currency,
                description=description,
                ettn=ettn,
                source_file=filename,
            )
            db.add(invoice)
            invoices_created += 1
        except Exception as exc:  # noqa: BLE001 - keep ingesting remaining rows
            errors.append(f"Row {idx + 2}: {exc}")

    db.commit()

    return IngestResult(
        filename=filename,
        direction=direction,
        rows_read=len(df),
        invoices_created=invoices_created,
        invoices_skipped_duplicate=invoices_skipped,
        companies_created=companies_created,
        errors=errors,
    )
