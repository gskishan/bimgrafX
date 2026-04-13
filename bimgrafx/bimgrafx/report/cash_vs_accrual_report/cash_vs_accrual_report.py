# Copyright (c) 2024, Frappe Technologies Pvt. Ltd.
# License: MIT

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


# ---------------------------------------------------------------------------
# COMPANY CURRENCY
# ---------------------------------------------------------------------------

def get_company_currency(filters):
    if filters and filters.get("company"):
        return frappe.db.get_value("Company", filters["company"], "default_currency") or "INR"
    return "INR"


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns(filters=None):
    return [
        {
            "fieldname": "account",
            "label": _("Account"),
            "fieldtype": "Link",
            "options": "Account",
            "width": 250,
        },
        {
            "fieldname": "account_type",
            "label": _("Account Type"),
            "fieldtype": "Data",
            "width": 120,
        },

        # Hidden currency field (IMPORTANT)
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Data",
            "hidden": 1,
        },

        {
            "fieldname": "accrual_debit",
            "label": _("Accrual Debit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "fieldname": "accrual_credit",
            "label": _("Accrual Credit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "fieldname": "accrual_balance",
            "label": _("Accrual Balance"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "fieldname": "cash_debit",
            "label": _("Cash Debit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "cash_credit",
            "label": _("Cash Credit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "cash_balance",
            "label": _("Cash Balance"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "difference",
            "label": _("Difference"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
    ]


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------

def get_data(filters=None):
    data = []
    currency = get_company_currency(filters)

    accrual_data = get_accrual_data(filters)
    cash_data = get_cash_data(filters)

    all_accounts = set(list(accrual_data.keys()) + list(cash_data.keys()))

    for account in sorted(all_accounts):
        accrual = accrual_data.get(account, {"debit": 0, "credit": 0, "account_type": ""})
        cash = cash_data.get(account, {"debit": 0, "credit": 0, "account_type": ""})

        accrual_debit = accrual.get("debit", 0) or 0
        accrual_credit = accrual.get("credit", 0) or 0
        accrual_balance = accrual_debit - accrual_credit

        cash_debit = cash.get("debit", 0) or 0
        cash_credit = cash.get("credit", 0) or 0
        cash_balance = cash_debit - cash_credit

        difference = accrual_balance - cash_balance
        account_type = accrual.get("account_type") or cash.get("account_type") or ""

        data.append({
            "account": account,
            "account_type": account_type,
            "accrual_debit": accrual_debit,
            "accrual_credit": accrual_credit,
            "accrual_balance": accrual_balance,
            "cash_debit": cash_debit,
            "cash_credit": cash_credit,
            "cash_balance": cash_balance,
            "difference": difference,
            "currency": currency,
        })

    # TOTAL ROW
    if data:
        data.append({
            "account": _("Total"),
            "account_type": "",
            "accrual_debit": sum(r["accrual_debit"] for r in data),
            "accrual_credit": sum(r["accrual_credit"] for r in data),
            "accrual_balance": sum(r["accrual_balance"] for r in data),
            "cash_debit": sum(r["cash_debit"] for r in data),
            "cash_credit": sum(r["cash_credit"] for r in data),
            "cash_balance": sum(r["cash_balance"] for r in data),
            "difference": sum(r["difference"] for r in data),
            "currency": currency,
        })

    return data


# ---------------------------------------------------------------------------
# ACCRUAL BASIS
# ---------------------------------------------------------------------------

def get_accrual_data(filters):
    conditions = get_gl_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            gl.account,
            ac.account_type,
            SUM(gl.debit) AS debit,
            SUM(gl.credit) AS credit
        FROM `tabGL Entry` gl
        LEFT JOIN `tabAccount` ac ON ac.name = gl.account
        WHERE
            gl.is_cancelled = 0
            {conditions}
        GROUP BY gl.account
        """,
        filters,
        as_dict=True,
    )

    return {r["account"]: r for r in rows}


# ---------------------------------------------------------------------------
# CASH BASIS
# ---------------------------------------------------------------------------

def get_cash_data(filters):
    result = {}
    _merge(result, get_payment_entry_cash_data(filters))
    _merge(result, get_journal_entry_cash_data(filters))
    return result


def get_payment_entry_cash_data(filters):
    conditions = get_gl_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            gl.account,
            ac.account_type,
            SUM(gl.debit) AS debit,
            SUM(gl.credit) AS credit
        FROM `tabGL Entry` gl
        LEFT JOIN `tabAccount` ac ON ac.name = gl.account
        WHERE
            gl.is_cancelled = 0
            AND gl.voucher_type = 'Payment Entry'
            {conditions}
        GROUP BY gl.account
        """,
        filters,
        as_dict=True,
    )

    return {r["account"]: r for r in rows}


def get_journal_entry_cash_data(filters):
    conditions = get_gl_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            gl.account,
            ac.account_type,
            SUM(gl.debit) AS debit,
            SUM(gl.credit) AS credit
        FROM `tabGL Entry` gl
        LEFT JOIN `tabAccount` ac ON ac.name = gl.account
        WHERE
            gl.is_cancelled = 0
            AND gl.voucher_type = 'Journal Entry'
            {conditions}
        GROUP BY gl.account
        """,
        filters,
        as_dict=True,
    )

    return {r["account"]: r for r in rows}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _merge(target, source):
    for account, vals in source.items():
        if account not in target:
            target[account] = {
                "debit": 0,
                "credit": 0,
                "account_type": vals.get("account_type", ""),
            }

        target[account]["debit"] += vals.get("debit", 0) or 0
        target[account]["credit"] += vals.get("credit", 0) or 0

        if not target[account].get("account_type"):
            target[account]["account_type"] = vals.get("account_type", "")


def get_gl_conditions(filters):
    conditions = ""

    if filters.get("company"):
        conditions += " AND gl.company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND gl.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND gl.posting_date <= %(to_date)s"

    return conditions
