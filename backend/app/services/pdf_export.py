"""
Generates the same per-company ledger statement as excel_export.py, but as a
single, print-ready PDF page (landscape) - so it never needs to be produced by
printing the .xlsx to PDF, which is what caused the "kayma": Excel/LibreOffice
splitting the sheet's wide table across two PDF pages (Borc/Alacak/Bakiye
columns landing on a second page, detached from their Tarih/Referans row).
Every cell here is wrapped in a Paragraph so long text wraps within its own
column instead of overflowing into - or forcing a break onto - another page.
"""
import os
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.config import settings
from app.schemas import LedgerResponse

NAVY = colors.HexColor("#1F4E78")
LINE = colors.HexColor("#CCCCCC")
MUTED = colors.HexColor("#666666")

# Base-14 PDF fonts (Helvetica) use WinAnsi encoding, which has no glyphs for
# Turkish i-dotless/g-breve/etc. and silently renders them as the wrong letter.
# Register a real Unicode TTF (Windows' bundled Arial) so Turkish text is
# correct; fall back to Helvetica if it isn't present (e.g. non-Windows host).
_WIN_FONTS_DIR = r"C:\Windows\Fonts"
try:
    pdfmetrics.registerFont(TTFont("BodyFont", os.path.join(_WIN_FONTS_DIR, "arial.ttf")))
    pdfmetrics.registerFont(TTFont("BodyFont-Bold", os.path.join(_WIN_FONTS_DIR, "arialbd.ttf")))
    _FONT = "BodyFont"
    _FONT_BOLD = "BodyFont-Bold"
except Exception:  # noqa: BLE001 - non-Windows host without Arial available
    _FONT = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"

# NOTE: ParagraphStyle's default `leading` is a flat 12pt, NOT scaled to
# fontSize - left as-is, a 16pt title's line box is shorter than its own
# glyphs, so the next paragraph visually overlaps it. Every style below sets
# `leading` explicitly (~1.3x fontSize) to avoid that.
_CELL_STYLE = ParagraphStyle("cell", fontName=_FONT, fontSize=8, leading=10)
_CELL_STYLE_RIGHT = ParagraphStyle("cell_right", parent=_CELL_STYLE, alignment=2)
_HEADER_STYLE = ParagraphStyle("header", fontName=_FONT_BOLD, fontSize=8, leading=10, textColor=colors.white)
_TITLE_STYLE = ParagraphStyle("title", fontName=_FONT_BOLD, fontSize=16, leading=20, textColor=NAVY, spaceAfter=4)
_SUBTITLE_STYLE = ParagraphStyle("subtitle", fontName=_FONT, fontSize=9, leading=13, textColor=MUTED)
_SECTION_STYLE = ParagraphStyle("section", fontName=_FONT_BOLD, fontSize=11, leading=14, textColor=NAVY, spaceBefore=12, spaceAfter=4)
_TOTAL_LABEL_STYLE = ParagraphStyle("total_label", fontName=_FONT_BOLD, fontSize=9, leading=12)
_TOTAL_VALUE_STYLE = ParagraphStyle("total_value", fontName=_FONT_BOLD, fontSize=9, leading=12, alignment=2)
_NET_LABEL_STYLE = ParagraphStyle("net_label", fontName=_FONT_BOLD, fontSize=12, leading=16)
_NET_VALUE_STYLE = ParagraphStyle("net_value", fontName=_FONT_BOLD, fontSize=12, leading=16, alignment=2)

_COL_WIDTHS = [22 * mm, 18 * mm, 30 * mm, 95 * mm, 28 * mm, 28 * mm, 30 * mm]  # sums well under A4-landscape width
_TOTAL_LABEL_WIDTH = sum(_COL_WIDTHS) - 45 * mm
_TOTAL_VALUE_WIDTH = 45 * mm  # wide enough for bold 12pt "696,500.00 TRY" without wrapping


def _money(value: float) -> str:
    return f'{value:,.2f} TRY'


def _p(text: str, style=_CELL_STYLE) -> Paragraph:
    return Paragraph(text if text else "", style)


def _section_table(rows, row_type_labels) -> Table:
    header = [_p(h, _HEADER_STYLE) for h in ["Tarih", "Tür", "Referans", "Açıklama", "Borç", "Alacak", "Bakiye"]]
    data = [header]
    for row in rows:
        data.append([
            _p(row.date.strftime("%d.%m.%Y")),
            _p(row_type_labels.get(row.row_type, row.row_type)),
            _p(row.reference),
            _p(row.description or ""),
            _p(_money(row.debit) if row.debit else "", _CELL_STYLE_RIGHT),
            _p(_money(row.credit) if row.credit else "", _CELL_STYLE_RIGHT),
            _p(_money(row.running_balance), _CELL_STYLE_RIGHT),
        ])
    if len(data) == 1:
        data.append([_p("Kayıt yok."), _p(""), _p(""), _p(""), _p(""), _p(""), _p("")])

    table = Table(data, colWidths=_COL_WIDTHS, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def export_company_ledger_pdf(ledger: LedgerResponse) -> str:
    safe_name = "".join(c for c in ledger.company.name if c.isalnum() or c in (" ", "-", "_")).strip()
    filename = f"{safe_name}_cari_hesap_{dt.date.today().isoformat()}.pdf"
    file_path = os.path.join(settings.export_dir, filename)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"{ledger.company.name} - Cari Hesap Ekstresi",
    )

    row_type_labels = {"invoice": "Fatura", "payment": "Ödeme"}
    story = [
        Paragraph("BEMAS TREYLER - Cari Hesap Ekstresi", _TITLE_STYLE),
        Paragraph(f"Firma: {ledger.company.name}  |  Vergi No: {ledger.company.tax_id}", _SUBTITLE_STYLE),
        Paragraph(f"Rapor Tarihi: {dt.date.today().strftime('%d.%m.%Y')}", _SUBTITLE_STYLE),

        Paragraph("MÜŞTERİ HESABI (Satış Faturaları / Tahsilatlar)", _SECTION_STYLE),
        _section_table(ledger.receivable_rows, row_type_labels),
        Spacer(1, 6),
        Table(
            [[_p("Net Müşteri Borcu:", _TOTAL_LABEL_STYLE), _p(_money(ledger.balance.net_customer_debt), _TOTAL_VALUE_STYLE)]],
            colWidths=[_TOTAL_LABEL_WIDTH, _TOTAL_VALUE_WIDTH],
        ),

        Paragraph("TEDARİKÇİ HESABI (Alış Faturaları / Ödemeler)", _SECTION_STYLE),
        _section_table(ledger.payable_rows, row_type_labels),
        Spacer(1, 6),
        Table(
            [[_p("Net Firma Borcu:", _TOTAL_LABEL_STYLE), _p(_money(ledger.balance.net_company_debt), _TOTAL_VALUE_STYLE)]],
            colWidths=[_TOTAL_LABEL_WIDTH, _TOTAL_VALUE_WIDTH],
        ),

        Spacer(1, 12),
        Table(
            [[_p("GENEL NET BAKİYE", _NET_LABEL_STYLE), _p(_money(ledger.balance.net_balance), _NET_VALUE_STYLE)]],
            colWidths=[_TOTAL_LABEL_WIDTH, _TOTAL_VALUE_WIDTH],
        ),
    ]

    doc.build(story)
    return file_path
