import datetime as dt
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from app.models import InvoiceDirection, TransactionDirection


# ---------- Auth ----------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: Optional[str] = None
    role: str


# ---------- Company ----------

class CompanyBase(BaseModel):
    name: str
    tax_id: str
    tax_office: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    iban: Optional[str] = None
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    tax_office: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    iban: Optional[str] = None
    notes: Optional[str] = None


class CompanyOut(CompanyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: dt.datetime


class CompanyBalance(BaseModel):
    company_id: int
    company_name: str
    tax_id: str
    total_outgoing_invoices: float   # we billed them (they owe us)
    total_incoming_invoices: float   # they billed us (we owe them)
    total_inflow_payments: float     # payments received from them
    total_outflow_payments: float    # payments we made to them
    net_customer_debt: float         # outgoing invoices - inflow payments (they owe us)
    net_company_debt: float          # incoming invoices - outflow payments (we owe them)
    net_balance: float               # net_customer_debt - net_company_debt (positive = they owe us overall)


# ---------- Invoice ----------

class InvoiceBase(BaseModel):
    direction: InvoiceDirection
    invoice_number: str
    issue_date: dt.date
    due_date: Optional[dt.date] = None
    amount: float
    tax_amount: Optional[float] = None
    currency: str = "TRY"
    description: Optional[str] = None
    ettn: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    company_id: int


class InvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    issue_date: Optional[dt.date] = None
    due_date: Optional[dt.date] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    ettn: Optional[str] = None


class InvoiceOut(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    source_file: Optional[str] = None
    created_at: dt.datetime


# ---------- Transaction ----------

class TransactionBase(BaseModel):
    direction: TransactionDirection
    transaction_date: dt.date
    amount: float
    currency: str = "TRY"
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    description: Optional[str] = None


class TransactionCreate(TransactionBase):
    company_id: int


class TransactionUpdate(BaseModel):
    transaction_date: Optional[dt.date] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    description: Optional[str] = None


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    source: str
    receipt_id: Optional[int] = None
    created_at: dt.datetime


# ---------- Receipt ----------

class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    ocr_used: bool
    parsed_amount: Optional[float] = None
    parsed_date: Optional[dt.date] = None
    parsed_currency: Optional[str] = None
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_iban: Optional[str] = None
    receiver_iban: Optional[str] = None
    description: Optional[str] = None
    matched_company_id: Optional[int] = None
    transaction_id: Optional[int] = None
    uploaded_at: dt.datetime


class ReceiptConfirm(BaseModel):
    company_id: int
    direction: TransactionDirection
    amount: Optional[float] = None
    transaction_date: Optional[dt.date] = None
    description: Optional[str] = None


# ---------- Ingestion results ----------

class IngestResult(BaseModel):
    filename: str
    direction: InvoiceDirection
    rows_read: int
    invoices_created: int
    invoices_skipped_duplicate: int
    companies_created: int
    errors: List[str] = []


class LedgerRow(BaseModel):
    row_type: str  # "invoice" | "payment"
    id: int  # the underlying Invoice.id or Transaction.id, per row_type
    date: dt.date
    reference: str
    description: Optional[str] = None
    debit: float = 0.0    # increases what the company owes / is owed depending on context
    credit: float = 0.0
    running_balance: float


class LedgerResponse(BaseModel):
    company: CompanyOut
    balance: CompanyBalance
    receivable_rows: List[LedgerRow]  # outgoing invoices vs inflow payments
    payable_rows: List[LedgerRow]     # incoming invoices vs outflow payments
