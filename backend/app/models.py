import enum
import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey, Enum, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


class InvoiceDirection(str, enum.Enum):
    INCOMING = "incoming"  # bize kesilen fatura -> Accounts Payable (biz borçluyuz)
    OUTGOING = "outgoing"  # bizim kestiğimiz fatura -> Accounts Receivable (bize borçlular)


class TransactionDirection(str, enum.Enum):
    INFLOW = "inflow"    # müşteriden bize gelen tahsilat (customer payment received)
    OUTFLOW = "outflow"  # tedarikçiye bizim yaptığımız ödeme (payment made to supplier)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(128), nullable=True)
    role = Column(String(32), nullable=False, default="admin")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    tax_id = Column(String(32), unique=True, nullable=False, index=True)  # Vergi No / TCKN
    tax_office = Column(String(128), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(128), nullable=True)
    iban = Column(String(34), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    invoices = relationship("Invoice", back_populates="company", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="company", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    direction = Column(Enum(InvoiceDirection), nullable=False, index=True)

    invoice_number = Column(String(64), nullable=False, index=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)

    amount = Column(Float, nullable=False)          # tax-inclusive total
    tax_amount = Column(Float, nullable=True)
    currency = Column(String(8), nullable=False, default="TRY")

    description = Column(Text, nullable=True)
    ettn = Column(String(64), nullable=True)         # e-Fatura ETTN (Kolaysoft)

    source_file = Column(String(255), nullable=True)  # originating Excel filename
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company = relationship("Company", back_populates="invoices")

    __table_args__ = ()


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)

    raw_text = Column(Text, nullable=True)
    ocr_used = Column(Boolean, default=False)

    parsed_amount = Column(Float, nullable=True)
    parsed_date = Column(Date, nullable=True)
    parsed_currency = Column(String(8), nullable=True)
    sender_name = Column(String(255), nullable=True)
    receiver_name = Column(String(255), nullable=True)
    sender_iban = Column(String(34), nullable=True)
    receiver_iban = Column(String(34), nullable=True)
    description = Column(Text, nullable=True)

    matched_company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)

    uploaded_at = Column(DateTime, default=dt.datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    direction = Column(Enum(TransactionDirection), nullable=False, index=True)

    transaction_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="TRY")

    counterparty_name = Column(String(255), nullable=True)
    counterparty_iban = Column(String(34), nullable=True)
    description = Column(Text, nullable=True)

    source = Column(String(32), nullable=False, default="manual")  # manual | receipt_pdf
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company = relationship("Company", back_populates="transactions")
