# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_company_currency(filters):
	"""Fetch the default currency of the selected company."""
	if filters and filters.get("company"):
		return frappe.db.get_value("Company", filters["company"], "default_currency") or "AED"
	return "AED"


def get_columns(filters=None):
	"""Creates column headers dynamically based on company currency."""
	currency = get_company_currency(filters)

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
		{
			"fieldname": "accrual_debit",
			"label": _("Accrual Debit ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"fieldname": "accrual_credit",
			"label": _("Accrual Credit ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"fieldname": "accrual_balance",
			"label": _("Accrual Balance ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"fieldname": "cash_debit",
			"label": _("Cash Debit ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"fieldname": "cash_credit",
			"label": _("Cash Credit ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"fieldname": "cash_balance",
			"label": _("Cash Balance ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"fieldname": "difference",
			"label": _("Difference ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
	]


def get_data(filters=None):
	"""Merge accrual and cash data by account and return rows."""
	data = []

	accrual_data = get_accrual_data(filters)
	cash_data = get_cash_data(filters)

	all_accounts = set(list(accrual_data.keys()) + list(cash_data.keys()))

	for account in sorted(all_accounts):
		accrual = accrual_data.get(account, {"debit": 0, "credit": 0, "account_type": ""})
		cash    = cash_data.get(account,    {"debit": 0, "credit": 0, "account_type": ""})

		accrual_debit   = accrual.get("debit", 0)  or 0
		accrual_credit  = accrual.get("credit", 0) or 0
		accrual_balance = accrual_debit - accrual_credit

		cash_debit      = cash.get("debit", 0)  or 0
		cash_credit     = cash.get("credit", 0) or 0
		cash_balance    = cash_debit - cash_credit

		difference      = accrual_balance - cash_balance
		account_type    = accrual.get("account_type") or cash.get("account_type") or ""

		data.append({
			"account":         account,
			"account_type":    account_type,
			"accrual_debit":   accrual_debit,
			"accrual_credit":  accrual_credit,
			"accrual_balance": accrual_balance,
			"cash_debit":      cash_debit,
			"cash_credit":     cash_credit,
			"cash_balance":    cash_balance,
			"difference":      difference,
		})

	# Totals row
	if data:
		data.append({
			"account":         _("Total"),
			"account_type":    "",
			"accrual_debit":   sum(r["accrual_debit"]   for r in data),
			"accrual_credit":  sum(r["accrual_credit"]  for r in data),
			"accrual_balance": sum(r["accrual_balance"] for r in data),
			"cash_debit":      sum(r["cash_debit"]      for r in data),
			"cash_credit":     sum(r["cash_credit"]     for r in data),
			"cash_balance":    sum(r["cash_balance"]    for r in data),
			"difference":      sum(r["difference"]      for r in data),
		})

	return data


# ---------------------------------------------------------------------------
# ACCRUAL BASIS
# ---------------------------------------------------------------------------

def get_accrual_data(filters):
	"""
	Accrual basis: reads GL Entry by posting_date regardless of payment status.
	Covers Sales Invoice, Purchase Invoice, Journal Entry, Payment Entry.
	"""
	conditions = get_gl_conditions(filters)
	voucher_types = (
		"Sales Invoice",
		"Purchase Invoice",
		"Journal Entry",
		"Payment Entry",
	)
	voucher_type_str = ", ".join([f"'{v}'" for v in voucher_types])

	rows = frappe.db.sql(
		f"""
		SELECT
			gl.account,
			ac.account_type,
			SUM(gl.debit)  AS debit,
			SUM(gl.credit) AS credit
		FROM
			`tabGL Entry` gl
		LEFT JOIN
			`tabAccount` ac ON ac.name = gl.account
		WHERE
			gl.is_cancelled = 0
			AND gl.voucher_type IN ({voucher_type_str})
			{conditions}
		GROUP BY
			gl.account
		ORDER BY
			gl.account
		""",
		filters,
		as_dict=True,
	)

	return {r["account"]: r for r in rows}


# ---------------------------------------------------------------------------
# CASH BASIS
# ---------------------------------------------------------------------------

def get_cash_data(filters):
	"""
	Cash basis:
	- Payment Entry      → direct GL entries
	- Journal Entry      → only those touching a cash/bank account
	- Sales Invoice      → only invoices with actual payments via Payment Ledger Entry
	- Purchase Invoice   → only invoices with actual payments via Payment Ledger Entry
	"""
	result = {}
	_merge(result, get_payment_entry_cash_data(filters))
	_merge(result, get_journal_entry_cash_data(filters))
	_merge(result, get_invoice_cash_data(filters, "Sales Invoice"))
	_merge(result, get_invoice_cash_data(filters, "Purchase Invoice"))
	return result


def get_payment_entry_cash_data(filters):
	"""GL entries from Payment Entry vouchers."""
	conditions = get_gl_conditions(filters)
	rows = frappe.db.sql(
		f"""
		SELECT
			gl.account,
			ac.account_type,
			SUM(gl.debit)  AS debit,
			SUM(gl.credit) AS credit
		FROM
			`tabGL Entry` gl
		LEFT JOIN
			`tabAccount` ac ON ac.name = gl.account
		WHERE
			gl.is_cancelled = 0
			AND gl.voucher_type = 'Payment Entry'
			{conditions}
		GROUP BY
			gl.account
		""",
		filters,
		as_dict=True,
	)
	return {r["account"]: r for r in rows}


def get_journal_entry_cash_data(filters):
	"""Journal Entries that touch a cash or bank account."""
	conditions = get_gl_conditions(filters)
	rows = frappe.db.sql(
		f"""
		SELECT
			gl.account,
			ac.account_type,
			SUM(gl.debit)  AS debit,
			SUM(gl.credit) AS credit
		FROM
			`tabGL Entry` gl
		LEFT JOIN
			`tabAccount` ac ON ac.name = gl.account
		WHERE
			gl.is_cancelled = 0
			AND gl.voucher_type = 'Journal Entry'
			AND gl.voucher_no IN (
				SELECT DISTINCT gl2.voucher_no
				FROM `tabGL Entry` gl2
				LEFT JOIN `tabAccount` ac2 ON ac2.name = gl2.account
				WHERE
					ac2.account_type IN ('Cash', 'Bank')
					AND gl2.is_cancelled = 0
			)
			{conditions}
		GROUP BY
			gl.account
		""",
		filters,
		as_dict=True,
	)
	return {r["account"]: r for r in rows}


def get_invoice_cash_data(filters, doctype):
	"""
	For Sales/Purchase Invoices use Payment Ledger Entry to find
	invoices that have received/made payment, then pull their GL entries.
	"""
	conditions     = get_gl_conditions(filters)
	ple_conditions = get_ple_conditions(filters)

	rows = frappe.db.sql(
		f"""
		SELECT
			gl.account,
			ac.account_type,
			SUM(gl.debit)  AS debit,
			SUM(gl.credit) AS credit
		FROM
			`tabGL Entry` gl
		LEFT JOIN
			`tabAccount` ac ON ac.name = gl.account
		WHERE
			gl.is_cancelled = 0
			AND gl.voucher_type = %(voucher_type)s
			AND gl.voucher_no IN (
				SELECT DISTINCT ple.against_voucher_no
				FROM `tabPayment Ledger Entry` ple
				WHERE
					ple.docstatus = 1
					AND ple.voucher_type != %(voucher_type)s
					AND ple.against_voucher_type = %(voucher_type)s
					{ple_conditions}
			)
			{conditions}
		GROUP BY
			gl.account
		""",
		{**filters, "voucher_type": doctype},
		as_dict=True,
	)
	return {r["account"]: r for r in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge(target, source):
	"""Merge source account dict into target, summing debit/credit."""
	for account, vals in source.items():
		if account not in target:
			target[account] = {
				"debit":        0,
				"credit":       0,
				"account_type": vals.get("account_type", ""),
			}
		target[account]["debit"]  = (target[account].get("debit",  0) or 0) + (vals.get("debit",  0) or 0)
		target[account]["credit"] = (target[account].get("credit", 0) or 0) + (vals.get("credit", 0) or 0)
		if not target[account].get("account_type"):
			target[account]["account_type"] = vals.get("account_type", "")


def get_gl_conditions(filters):
	"""SQL conditions for GL Entry queries."""
	conditions = ""
	if filters.get("company"):
		conditions += " AND gl.company = %(company)s"
	if filters.get("from_date"):
		conditions += " AND gl.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND gl.posting_date <= %(to_date)s"
	if filters.get("finance_book"):
		conditions += " AND (gl.finance_book = %(finance_book)s OR gl.finance_book IS NULL OR gl.finance_book = '')"
	if filters.get("cost_center"):
		conditions += " AND gl.cost_center = %(cost_center)s"
	return conditions


def get_ple_conditions(filters):
	"""SQL conditions for Payment Ledger Entry queries."""
	conditions = ""
	if filters.get("company"):
		conditions += " AND ple.company = %(company)s"
	if filters.get("from_date"):
		conditions += " AND ple.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND ple.posting_date <= %(to_date)s"
	return conditions
