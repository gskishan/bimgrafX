# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data, emirates, amounts_by_emirate = get_data(filters)
	return columns, data


def get_columns():
	"""Creates a list of dictionaries that are used to generate column headers of the data table."""
	return [
		{"fieldname": "no",         "label": _("No"),               "fieldtype": "Data",     "width": 50},
		{"fieldname": "legend",     "label": _("Legend"),           "fieldtype": "Data",     "width": 300},
		{"fieldname": "amount",     "label": _("Amount (AED)"),     "fieldtype": "Currency", "width": 125},
		{"fieldname": "vat_amount", "label": _("VAT Amount (AED)"), "fieldtype": "Currency", "width": 150},
	]


def get_data(filters=None):
	"""Returns the list of dictionaries. Each dictionary is a row in the datatable and chart data."""
	data = []
	emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
	append_vat_on_expenses(data, filters)
	return data, emirates, amounts_by_emirate


# ── Sales Section ──────────────────────────────────────────────────────────────

def append_vat_on_sales(data, filters):
	"""Appends Sales and All Other Outputs."""
	append_data(data, "", _("VAT on Sales and All Other Outputs"), "", "")

	emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

	# Row 1 — subtotal of all emiratewise standard-rated supplies (1a–1g)
	total_amount = sum(v["raw_amount"]     for v in amounts_by_emirate.values())
	total_vat    = sum(v["raw_vat_amount"] for v in amounts_by_emirate.values())
	append_data(
		data, "1",
		_("Total Standard Rated Supplies (1a to 1g)"),
		frappe.format(total_amount, "Currency"),
		frappe.format(total_vat,    "Currency"),
	)

	append_data(
		data, "2",
		_("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
		frappe.format((-1) * get_tourist_tax_return_total(filters), "Currency"),
		frappe.format((-1) * get_tourist_tax_return_tax(filters),   "Currency"),
	)

	append_data(
		data, "3",
		_("Supplies subject to the reverse charge provision"),
		frappe.format(get_reverse_charge_total(filters), "Currency"),
		frappe.format(get_reverse_charge_tax(filters),   "Currency"),
	)

	append_data(
		data, "4",
		_("Zero Rated"),
		frappe.format(get_zero_rated_total(filters), "Currency"),
		"-",
	)

	append_data(
		data, "5",
		_("Exempt Supplies"),
		frappe.format(get_exempt_total(filters), "Currency"),
		"-",
	)

	append_data(data, "", "", "", "")
	return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
	"""Append emiratewise standard rated expenses and vat."""
	total_emiratewise = get_total_emiratewise(filters)
	emirates = get_emirates()
	amounts_by_emirate = {}

	for emirate, amount, vat in total_emiratewise:
		amounts_by_emirate[emirate] = {
			"legend":         emirate,
			"raw_amount":     amount or 0,
			"raw_vat_amount": vat    or 0,
			"amount":         frappe.format(amount or 0, "Currency"),
			"vat_amount":     frappe.format(vat    or 0, "Currency"),
		}

	amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate)
	return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate):
	"""Append emiratewise standard rated expenses and vat."""
	for no, emirate in enumerate(emirates, 97):   # 97 = ord('a')
		row_no = _("1{0}").format(chr(no))
		label  = _("Standard rated supplies in {0}").format(emirate)
		if emirate in amounts_by_emirate:
			amounts_by_emirate[emirate]["no"]     = row_no
			amounts_by_emirate[emirate]["legend"] = label
			data.append(amounts_by_emirate[emirate])
		else:
			append_data(
				data, row_no, label,
				frappe.format(0, "Currency"),
				frappe.format(0, "Currency"),
			)
	return amounts_by_emirate


def append_vat_on_expenses(data, filters):
	"""Appends Expenses and All Other Inputs."""
	append_data(data, "", _("VAT on Expenses and All Other Inputs"), "", "")
	append_data(
		data, "9",
		_("Standard Rated Expenses"),
		frappe.format(get_standard_rated_expenses_total(filters), "Currency"),
		frappe.format(get_standard_rated_expenses_tax(filters),   "Currency"),
	)
	append_data(
		data, "10",
		_("Supplies subject to the reverse charge provision"),
		frappe.format(get_reverse_charge_recoverable_total(filters), "Currency"),
		frappe.format(get_reverse_charge_recoverable_tax(filters),   "Currency"),
	)


def append_data(data, no, legend, amount, vat_amount):
	"""Returns data with appended value."""
	data.append({"no": no, "legend": legend, "amount": amount, "vat_amount": vat_amount})


# ── Emiratewise VAT — uses UAE VAT Account lookup via GL Entry ─────────────────

def get_total_emiratewise(filters):
	"""
	Returns emiratewise (amount, vat) where VAT is sourced from GL Entry debits
	against accounts listed in tabUAE VAT Account — consistent with how
	get_reverse_charge_tax works, but grouped by vat_emirate on the Sales Invoice.
	"""
	conditions = get_conditions_with_alias(filters, "s")
	try:
		return frappe.db.sql(
			f"""
			SELECT
				s.vat_emirate                  AS emirate,
				SUM(i.base_net_amount)         AS total_amount,
				SUM(gl.debit)                  AS vat_amount
			FROM
				`tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s  ON i.parent = s.name
				INNER JOIN `tabGL Entry` gl       ON gl.voucher_no = s.name
			WHERE
				s.docstatus = 1
				AND gl.docstatus = 1
				AND i.is_exempt    != 1
				AND i.is_zero_rated != 1
				AND gl.account IN (
					SELECT account FROM `tabUAE VAT Account`
					WHERE parent = %(company)s
				)
				{conditions}
			GROUP BY
				s.vat_emirate
			""",
			filters,
		)
	except (IndexError, TypeError):
		return []   # FIX: was returning 0, which broke the for-loop unpacking


# ── Condition Helpers ──────────────────────────────────────────────────────────

def get_emirates():
	"""Returns a list of emirates in display order."""
	return ["Abu Dhabi", "Dubai", "Sharjah", "Ajman",
	        "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"]


def get_filters(filters):
	"""
	Build ORM-style filter list.
	FIX: original checked `from_date` twice — second condition now correctly
	     checks `to_date` before appending the <= clause.
	"""
	query_filters = []
	if filters.get("company"):
		query_filters.append(["company", "=", filters["company"]])
	if filters.get("from_date"):
		query_filters.append(["posting_date", ">=", filters["from_date"]])
	if filters.get("to_date"):                                          # ← was from_date (bug)
		query_filters.append(["posting_date", "<=", filters["to_date"]])
	return query_filters


def get_conditions(filters):
	"""
	SQL condition string — unqualified column names.
	Use only when the query's main table has no alias.
	FIX: original used bare 'company' / 'posting_date' even inside aliased
	     queries, causing ambiguous-column errors. Use get_conditions_with_alias
	     for any query that aliases its tables.
	"""
	conditions = ""
	for key, clause in (
		("company",   " and company=%(company)s"),
		("from_date", " and posting_date>=%(from_date)s"),
		("to_date",   " and posting_date<=%(to_date)s"),
	):
		if filters.get(key):
			conditions += clause
	return conditions


def get_conditions_with_alias(filters, alias):
	"""
	SQL condition string with a table alias prefix (e.g. 's', 'p').
	Fixes the ambiguous-column bug that occurred in all aliased JOIN queries.
	"""
	conditions = ""
	for key, clause in (
		("company",   f" and {alias}.company=%(company)s"),
		("from_date", f" and {alias}.posting_date>=%(from_date)s"),
		("to_date",   f" and {alias}.posting_date<=%(to_date)s"),
	):
		if filters.get(key):
			conditions += clause
	return conditions


def get_conditions_join(filters):
	"""Alias 'p' — kept for backward compat with purchase invoice join queries."""
	return get_conditions_with_alias(filters, "p")


# ── Reverse Charge ─────────────────────────────────────────────────────────────

def get_reverse_charge_total(filters):
	"""Returns the sum of the total of each Purchase invoice with reverse charge."""
	query_filters = get_filters(filters)
	query_filters.append(["reverse_charge", "=", "Y"])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Purchase Invoice", filters=query_filters,
				fields=[{"SUM": "base_total"}], as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


def get_reverse_charge_tax(filters):
	"""Returns the VAT on reverse charge purchases via GL Entry / UAE VAT Accounts."""
	conditions = get_conditions_join(filters)
	return (
		frappe.db.sql(
			f"""
			SELECT SUM(debit) FROM `tabPurchase Invoice` p
			INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
			WHERE
				p.reverse_charge = "Y"
				AND p.docstatus  = 1
				AND gl.docstatus = 1
				AND gl.account IN (
					SELECT account FROM `tabUAE VAT Account` WHERE parent=%(company)s
				)
				{conditions}
			""",
			filters,
		)[0][0] or 0
	)


def get_reverse_charge_recoverable_total(filters):
	"""Returns the total of Purchase invoices with recoverable reverse charge."""
	query_filters = get_filters(filters)
	query_filters.append(["reverse_charge", "=", "Y"])
	query_filters.append(["recoverable_reverse_charge", ">", "0"])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Purchase Invoice", filters=query_filters,
				fields=[{"SUM": "base_total"}], as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


def get_reverse_charge_recoverable_tax(filters):
	"""Returns recoverable VAT on reverse charge purchases."""
	conditions = get_conditions_join(filters)
	return (
		frappe.db.sql(
			f"""
			SELECT SUM(debit * p.recoverable_reverse_charge / 100)
			FROM `tabPurchase Invoice` p
			INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
			WHERE
				p.reverse_charge = "Y"
				AND p.docstatus = 1
				AND p.recoverable_reverse_charge > 0
				AND gl.docstatus = 1
				AND gl.account IN (
					SELECT account FROM `tabUAE VAT Account` WHERE parent=%(company)s
				)
				{conditions}
			""",
			filters,
		)[0][0] or 0
	)


# ── Standard Rated Expenses ────────────────────────────────────────────────────

def get_standard_rated_expenses_total(filters):
	query_filters = get_filters(filters)
	query_filters.append(["recoverable_standard_rated_expenses", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Purchase Invoice", filters=query_filters,
				fields=[{"SUM": "base_total"}], as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


def get_standard_rated_expenses_tax(filters):
	query_filters = get_filters(filters)
	query_filters.append(["recoverable_standard_rated_expenses", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Purchase Invoice", filters=query_filters,
				fields=[{"SUM": "recoverable_standard_rated_expenses"}],
				as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


# ── Tourist Tax Return ─────────────────────────────────────────────────────────

def get_tourist_tax_return_total(filters):
	query_filters = get_filters(filters)
	query_filters.append(["tourist_tax_return", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Sales Invoice", filters=query_filters,
				fields=[{"SUM": "base_total"}], as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


def get_tourist_tax_return_tax(filters):
	query_filters = get_filters(filters)
	query_filters.append(["tourist_tax_return", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		return (
			frappe.db.get_all(
				"Sales Invoice", filters=query_filters,
				fields=[{"SUM": "tourist_tax_return"}],
				as_list=True, limit=1,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


# ── Zero Rated / Exempt ────────────────────────────────────────────────────────

def get_zero_rated_total(filters):
	conditions = get_conditions_with_alias(filters, "s")
	try:
		return (
			frappe.db.sql(
				f"""
				SELECT SUM(i.base_net_amount)
				FROM `tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s ON i.parent = s.name
				WHERE s.docstatus = 1 AND i.is_zero_rated = 1
				{conditions}
				""",
				filters,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0


def get_exempt_total(filters):
	conditions = get_conditions_with_alias(filters, "s")
	try:
		return (
			frappe.db.sql(
				f"""
				SELECT SUM(i.base_net_amount)
				FROM `tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s ON i.parent = s.name
				WHERE s.docstatus = 1 AND i.is_exempt = 1
				{conditions}
				""",
				filters,
			)[0][0] or 0
		)
	except (IndexError, TypeError):
		return 0
