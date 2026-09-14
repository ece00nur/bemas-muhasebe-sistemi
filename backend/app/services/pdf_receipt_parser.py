"""
Extracts transaction data from bank transfer / EFT / havale receipt PDFs.

Strategy:
 1. Try text extraction with pdfplumber (works for the vast majority of bank-generated
    e-receipts, which are digitally created, not scanned).
 2. If no text layer is found (scanned/photographed receipt), rasterize pages with
    pdf2image and run Tesseract OCR (pytesseract) on each page image.
 3. Run regex heuristics tuned to common Turkish bank receipt phrasing to pull out
    amount, date, IBANs, and sender/receiver names.

This is heuristic by nature (banks do not share one receipt layout) but it is a real,
working extraction pipeline - no bank-specific templates were hardcoded, so it degrades
gracefully to "field not found" (None) rather than raising, letting a human confirm the
remaining fields via the /receipts/{id}/confirm endpoint.
"""
import re
import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pdfplumber

from app.config import settings

try:
    import pytesseract
    from pdf2image import convert_from_path

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    _OCR_AVAILABLE = True
except Exception:  # noqa: BLE001 - OCR deps are optional at runtime
    _OCR_AVAILABLE = False


IBAN_RE = re.compile(r"\bTR\d{2}(?:[\s]?\d){22}\b", re.IGNORECASE)  # TR + 24 digits total
AMOUNT_RE = re.compile(
    # "tutar\w*" also matches the common Turkish suffix forms ("Tutarı", "Tutarim")
    # so e.g. "ISLEM TUTARI :72.000,00" matches - without \w* the trailing "i/i"
    # blocks the ":" that follows, and the whole label fails to match at all.
    r"(?:tutar\w*|meblağ\w*|meblag\w*|amount\w*)\s*[:\-]?\s*"
    r"([\d.,]+)\s*(TL|TRY|₺|USD|EUR|\$|€)?",
    re.IGNORECASE,
)
# Fallback for receipts with no recognizable "tutar/amount" label. Requires the
# match to NOT be immediately followed by another separator+digit, otherwise a
# dd.mm.yyyy date (e.g. "04.09.2026") gets misread as an amount "04.09" followed
# by a rejected ".2026" tail - the very bug that produced "4,09 TRY" from a real
# 72.000,00 TL receipt.
GENERIC_AMOUNT_RE = re.compile(
    r"([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})(?![.,]\d)\s*(TL|TRY|₺|USD|EUR|\$|€)?"
)
DATE_RE = re.compile(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})")
SENDER_RE = re.compile(r"(?:gönderen|gonderen|hesap\s*sahibi|ödeyen|odeyen)\s*[:\-]?\s*(.+)", re.IGNORECASE)
RECEIVER_RE = re.compile(r"(?:alıcı|alici|lehdar|hesabına|hesabina)\s*[:\-]?\s*(.+)", re.IGNORECASE)
DESCRIPTION_RE = re.compile(r"(?:açıklama|aciklama|description)\s*[:\-]?\s*(.+)", re.IGNORECASE)


@dataclass
class ParsedReceipt:
    raw_text: str
    ocr_used: bool
    amount: Optional[float] = None
    currency: Optional[str] = None
    transaction_date: Optional[dt.date] = None
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_iban: Optional[str] = None
    receiver_iban: Optional[str] = None
    description: Optional[str] = None


def _extract_text_pdfplumber(file_path: str) -> str:
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def _extract_text_ocr(file_path: str) -> str:
    if not _OCR_AVAILABLE:
        return ""
    images = convert_from_path(file_path, dpi=300)
    text_parts = [pytesseract.image_to_string(img, lang="tur+eng") for img in images]
    return "\n".join(text_parts).strip()


def _to_float(raw: str) -> Optional[float]:
    raw = raw.strip()
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_currency(symbol: Optional[str]) -> str:
    if not symbol:
        return "TRY"
    symbol = symbol.strip().upper()
    return {"₺": "TRY", "TL": "TRY", "$": "USD", "€": "EUR"}.get(symbol, symbol)


def _parse_date(raw: str) -> Optional[dt.date]:
    raw = raw.strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _first_line(match_text: str) -> str:
    return match_text.split("\n")[0].strip(" \t:-")[:255]


def parse_receipt(file_path: str) -> ParsedReceipt:
    text = _extract_text_pdfplumber(file_path)
    ocr_used = False

    if len(text) < 20:  # essentially empty -> likely a scanned image PDF
        ocr_text = _extract_text_ocr(file_path)
        if len(ocr_text) > len(text):
            text = ocr_text
            ocr_used = True

    result = ParsedReceipt(raw_text=text, ocr_used=ocr_used)

    ibans = IBAN_RE.findall(text)
    ibans = [re.sub(r"\s+", "", i).upper() for i in ibans]
    if len(ibans) >= 1:
        result.sender_iban = ibans[0]
    if len(ibans) >= 2:
        result.receiver_iban = ibans[1]

    amount_match = AMOUNT_RE.search(text)
    if amount_match:
        result.amount = _to_float(amount_match.group(1))
        result.currency = _normalize_currency(amount_match.group(2))
    else:
        # Strip dd.mm.yyyy-style dates before the unlabeled fallback search, so a
        # date like "04.09.2026" can't be misread as an amount "04.09" (or, after
        # the first segment is rejected, backtrack into "09.20") when no "tutar"
        # label was found anywhere in the document.
        text_without_dates = DATE_RE.sub(" ", text)
        generic_match = GENERIC_AMOUNT_RE.search(text_without_dates)
        if generic_match:
            result.amount = _to_float(generic_match.group(1))
            result.currency = _normalize_currency(generic_match.group(2))

    date_match = DATE_RE.search(text)
    if date_match:
        result.transaction_date = _parse_date(date_match.group(1))

    sender_match = SENDER_RE.search(text)
    if sender_match:
        result.sender_name = _first_line(sender_match.group(1))

    receiver_match = RECEIVER_RE.search(text)
    if receiver_match:
        result.receiver_name = _first_line(receiver_match.group(1))

    description_match = DESCRIPTION_RE.search(text)
    if description_match:
        result.description = _first_line(description_match.group(1))

    return result
