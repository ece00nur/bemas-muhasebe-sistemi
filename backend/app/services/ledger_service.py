import datetime as dt
from typing import List, Tuple

from sqlalchemy.orm import Session

from app import models
from app.schemas import CompanyBalance, LedgerRow, LedgerResponse, CompanyOut


def compute_balance(db: Session, company: models.Company) -> CompanyBalance:
    outgoing_total = sum(
        inv.amount for inv in company.invoices if inv.direction == models.InvoiceDirection.OUTGOING
    )
    incoming_total = sum(
        inv.amount for inv in company.invoices if inv.direction == models.InvoiceDirection.INCOMING
    )
    inflow_total = sum(
        tx.amount for tx in company.transactions if tx.direction == models.TransactionDirection.INFLOW
    )
    outflow_total = sum(
        tx.amount for tx in company.transactions if tx.direction == models.TransactionDirection.OUTFLOW
    )

    # Accounts Receivable (outgoing invoices) - customer payments = Net Customer Debt
    net_customer_debt = round(outgoing_total - inflow_total, 2)
    # Accounts Payable (incoming invoices) - our payments = Net Company Debt
    net_company_debt = round(incoming_total - outflow_total, 2)

    return CompanyBalance(
        company_id=company.id,
        company_name=company.name,
        tax_id=company.tax_id,
        total_outgoing_invoices=round(outgoing_total, 2),
        total_incoming_invoices=round(incoming_total, 2),
        total_inflow_payments=round(inflow_total, 2),
        total_outflow_payments=round(outflow_total, 2),
        net_customer_debt=net_customer_debt,
        net_company_debt=net_company_debt,
        net_balance=round(net_customer_debt - net_company_debt, 2),
    )


def _build_ledger_rows(
    invoices: List[models.Invoice],
    payments: List[models.Transaction],
) -> List[LedgerRow]:
    events: List[Tuple[dt.date, LedgerRow]] = []

    for inv in invoices:
        events.append((
            inv.issue_date,
            LedgerRow(
                row_type="invoice",
                id=inv.id,
                date=inv.issue_date,
                reference=inv.invoice_number,
                description=inv.description,
                debit=round(inv.amount, 2),
                credit=0.0,
                running_balance=0.0,
            ),
        ))

    for tx in payments:
        events.append((
            tx.transaction_date,
            LedgerRow(
                row_type="payment",
                id=tx.id,
                date=tx.transaction_date,
                reference=f"Ödeme #{tx.id}",
                description=tx.description or tx.counterparty_name,
                debit=0.0,
                credit=round(tx.amount, 2),
                running_balance=0.0,
            ),
        ))

    events.sort(key=lambda e: e[0])

    running = 0.0
    rows = []
    for _, row in events:
        running += row.debit - row.credit
        row.running_balance = round(running, 2)
        rows.append(row)
    return rows


def build_ledger(db: Session, company: models.Company) -> LedgerResponse:
    balance = compute_balance(db, company)

    outgoing_invoices = [i for i in company.invoices if i.direction == models.InvoiceDirection.OUTGOING]
    incoming_invoices = [i for i in company.invoices if i.direction == models.InvoiceDirection.INCOMING]
    inflow_payments = [t for t in company.transactions if t.direction == models.TransactionDirection.INFLOW]
    outflow_payments = [t for t in company.transactions if t.direction == models.TransactionDirection.OUTFLOW]

    receivable_rows = _build_ledger_rows(outgoing_invoices, inflow_payments)
    payable_rows = _build_ledger_rows(incoming_invoices, outflow_payments)

    return LedgerResponse(
        company=CompanyOut.model_validate(company),
        balance=balance,
        receivable_rows=receivable_rows,
        payable_rows=payable_rows,
    )
