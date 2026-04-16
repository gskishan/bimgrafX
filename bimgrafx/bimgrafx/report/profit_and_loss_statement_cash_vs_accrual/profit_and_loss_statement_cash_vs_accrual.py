# Copyright (c) 2026
# Cash Basis Profit & Loss (QuickBooks Style)

import frappe
from frappe.utils import flt, getdate


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


# ---------------------------------------------------------
#  COLUMNS
# ---------------------------------------------------------
def get_columns():
    return [
        {"label": "Account", "fieldname": "account", "fieldtype": "Data", "width": 250},
        {"label": "Type", "fieldname": "type", "fieldtype": "Data", "width": 120},
        {"label": "Cash Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 160},
    ]


# ---------------------------------------------------------
#  MAIN DATA BUILDER
# ---------------------------------------------------------
def get_data(filters):

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Fetch paid invoices in cash-basis mode
    si = get_sales_invoice_cash_basis(from_date, to_date)
    pi = get_purchase_invoice_cash_basis(from_date, to_date)

    report = []

    # Income Section
    income_total = sum([d["amount"] for d in si])
    report.append({"account": "Income", "type": "Section", "amount": income_total})

    for row in si:
        report.append(row)

    # Expense Section
    expense_total = sum([d["amount"] for d in pi])
    report.append({"account": "Expenses", "type": "Section", "amount": expense_total})

    for row in pi:
        report.append(row)

    # Net Profit
    net_profit = income_total - expense_total

    report.append({
        "account": "Net Profit",
        "type": "Total",
        "amount": net_profit
    })

    return report


# ---------------------------------------------------------
#   SALES INVOICE (INCOME) - Cash Basis
# ---------------------------------------------------------
def get_sales_invoice_cash_basis(from_date, to_date):
    invoices = frappe.db.sql(
        """
        SELECT si.name, si.posting_date, si.base_grand_total
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.posting_date <= %s
        """,
        (to_date,),
        as_dict=True,
    )

    results = []

    for inv in invoices:
        paid_amount = get_payment_for_invoice(inv.name, "Sales Invoice", from_date, to_date)

        if paid_amount <= 0:
            continue

        allocation_ratio = paid_amount / inv.base_grand_total if inv.base_grand_total else 0

        # Fetch income accounts aggregated
        income_rows = frappe.db.sql(
            """
            SELECT account, SUM(base_amount) AS amt
            FROM `tabSales Invoice Item`
            WHERE parent=%s
            GROUP BY account
            """,
            inv.name,
            as_dict=True,
        )

        for r in income_rows:
            results.append({
                "account": r.account,
                "type": "Income",
                "amount": flt(r.amt) * allocation_ratio,
            })

    return results


# ---------------------------------------------------------
#   PURCHASE INVOICE (EXPENSE) - Cash Basis
# ---------------------------------------------------------
def get_purchase_invoice_cash_basis(from_date, to_date):
    invoices = frappe.db.sql(
        """
        SELECT pi.name, pi.posting_date, pi.base_grand_total
        FROM `tabPurchase Invoice` pi
        WHERE pi.docstatus = 1
          AND pi.posting_date <= %s
        """,
        (to_date,),
        as_dict=True,
    )

    results = []

    for inv in invoices:
        paid_amount = get_payment_for_invoice(inv.name, "Purchase Invoice", from_date, to_date)

        if paid_amount <= 0:
            continue

        allocation_ratio = paid_amount / inv.base_grand_total if inv.base_grand_total else 0

        expense_rows = frappe.db.sql(
            """
            SELECT account, SUM(base_amount) AS amt
            FROM `tabPurchase Invoice Item`
            WHERE parent=%s
            GROUP BY account
            """,
            inv.name,
            as_dict=True,
        )

        for r in expense_rows:
            results.append({
                "account": r.account,
                "type": "Expense",
                "amount": flt(r.amt) * allocation_ratio,
            })

    return results


# ---------------------------------------------------------
#   PAYMENT AGGREGATION FOR CASH BASIS
# ---------------------------------------------------------
def get_payment_for_invoice(invoice, doctype, from_date, to_date):

    # Fetch payments from Payment Entry (PE)
    amount = frappe.db.sql(
        """
        SELECT SUM(allocated_amount)
        FROM `tabPayment Entry Reference`
        WHERE reference_doctype=%s
          AND reference_name=%s
          AND docstatus=1
          AND parent IN (
                SELECT name FROM `tabPayment Entry`
                WHERE posting_date BETWEEN %s AND %s
                AND docstatus=1
          )
        """,
        (doctype, invoice, from_date, to_date),
    )[0][0]

    return flt(amount or 0)
