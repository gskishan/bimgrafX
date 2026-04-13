# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns(filters)
	data, emirates, amounts_by_emirate = get_data(filters)
	return columns, data


def get_company_currency(filters):
	"""Fetch the default currency of the selected company."""
	if filters and filters.get("company"):
		return frappe.db.get_value("Company", filters["company"], "default_currency") or "AED"
	return "AED"


def fmt(value, currency):
	"""Format a value as currency using the company currency."""
	return frappe.format(value, {"fieldtype": "Currency", "options": currency})


def get_columns(filters=None):
	"""Creates column headers dynamically based on company currency."""
	currency = get_company_currency(filters)

	return [
		{"fieldname": "no", "label": _("No"), "fieldtype": "Data", "width": 50},
		{"fieldname": "legend", "label": _("Legend"), "fieldtype": "Data", "width": 300},
		{
			"fieldname": "amount",
			"label": _("Amount ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 125,
		},
		{
			"fieldname": "vat_amount",
			"label": _("VAT Amount ({0})").format(currency),
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
	]


def get_data(filters=None):
	"""Returns the list of dictionaries. Each dictionary is a row in the datatable and chart data."""
	data = []
	emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
	append_vat_on_expenses(data, filters)
	return data, emirates, amounts_by_emirate


def append_vat_on_sales(data, filters):
	"""Appends Sales and All Other Outputs."""
	currency = get_company_currency(filters)

	append_data(data, "", _("VAT on Sales and All Other Outputs"), "", "")

	emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

	append_data(
		data,
		"2",
		_("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
		fmt((-1) * get_tourist_tax_return_total(filters), currency),
		fmt((-1) * get_tourist_tax_return_tax(filters), currency),
	)

	append_data(
		data,
		"3",
		_("Supplies subject to the reverse charge provision"),
		fmt(get_reverse_charge_total(filters), currency),
		fmt(get_reverse_charge_tax(filters), currency),
	)

	append_data(
		data,
		"4",
		_("Zero Rated"),
		fmt(get_zero_rated_total(filters), currency),
		"-",
	)

	append_data(
		data,
		"5",
		_("Exempt Supplies"),
		fmt(get_exempt_total(filters), currency),
		"-",
	)

	append_data(data, "", "", "", "")

	return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
	"""Append emiratewise standard rated expenses and vat."""
	currency = get_company_currency(filters)
	total_emiratewise = get_total_emiratewise(filters)
	emirates = get_emirates()
	amounts_by_emirate = {}

	if total_emiratewise:
		for emirate, amount, vat in total_emiratewise:
			amounts_by_emirate[emirate] = {
				"legend": emirate,
				"raw_amount": amount,
				"raw_vat_amount": vat,
				"amount": fmt(amount, currency),
				"vat_amount": fmt(vat, currency),
			}

	amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate, currency)
	return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate, currency):
	"""Append emiratewise standard rated expenses and vat."""
	for no, emirate in enumerate(emirates, 97):
		if emirate in amounts_by_emirate:
			amounts_by_emirate[emirate]["no"] = _("1{0}").format(chr(no))
			amounts_by_emirate[emirate]["legend"] = _("Standard rated supplies in {0}").format(emirate)
			data.append(amounts_by_emirate[emirate])
		else:
			append_data(
				data,
				_("1{0}").format(chr(no)),
				_("Standard rated supplies in {0}").format(emirate),
				fmt(0, currency),
				fmt(0, currency),
			)
	return amounts_by_emirate


def append_vat_on_expenses(data, filters):
	"""Appends Expenses and All Other Inputs."""
	currency = get_company_currency(filters)

	append_data(data, "", _("VAT on Expenses and All Other Inputs"), "", "")
	append_data(
		data,
		"9",
		_("Standard Rated Expenses"),
		fmt(get_standard_rated_expenses_total(filters), currency),
		fmt(get_standard_rated_expenses_tax(filters), currency),
	)
	append_data(
		data,
		"10",
		_("Supplies subject to the reverse charge provision"),
		fmt(get_reverse_charge_recoverable_total(filters), currency),
		fmt(get_reverse_charge_recoverable_tax(filters), currency),
	)


def append_data(data, no, legend, amount, vat_amount):
	"""Returns data with appended value."""
	data.append({"no": no, "legend": legend, "amount": amount, "vat_amount": vat_amount})


def get_total_emiratewise(filters):
	"""Returns Emiratewise Amount and Taxes."""
	conditions = get_conditions(filters)
	try:
		return frappe.db.sql(
			f"""
			SELECT
				s.vat_emirate AS emirate,
				SUM(i.base_net_amount) AS total,
				SUM(i.tax_amount) AS tax_total
			FROM
				`tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s ON i.parent = s.name
			WHERE
				s.docstatus = 1
				AND i.is_exempt != 1
				AND i.is_zero_rated != 1
				{conditions}
			GROUP BY
				s.vat_emirate
			""",
			filters,
		)
	except (IndexError, TypeError):
		return []


def get_emirates():
	"""Returns a List of emirates in the order that they are to be displayed."""
	return [
		"Abu Dhabi",
		"Dubai",
		"Sharjah",
		"Ajman",
		"Umm Al Quwain",
		"Ras Al Khaimah",
		"Fujairah",
	]


def get_filters(filters):
	"""Build list-style query filters."""
	query_filters = []
	if filters.get("company"):
		query_filters.append(["company", "=", filters["company"]])
	if filters.get("from_date"):
		query_filters.append(["posting_date", ">=", filters["from_date"]])
	if filters.get("to_date"):
		query_filters.append(["posting_date", "<=", filters["to_date"]])
	return query_filters


# ---------------------------------------------------------------------------
# Reverse Charge
# ---------------------------------------------------------------------------

def get_reverse_charge_total(filters):
	"""Returns the sum of base_total for reverse charge Purchase Invoices."""
	query_filters = get_filters(filters)
	query_filters.append(["reverse_charge", "=", "Y"])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Purchase Invoice",
			filters=query_filters,
			fields=["SUM(base_total) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_reverse_charge_tax(filters):
	"""Returns the sum of VAT debit for reverse charge Purchase Invoices."""
	conditions = get_conditions_join(filters)
	try:
		result = frappe.db.sql(
			f"""
			SELECT SUM(gl.debit)
			FROM
				`tabPurchase Invoice` p
				INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
			WHERE
				p.reverse_charge = 'Y'
				AND p.docstatus = 1
				AND gl.docstatus = 1
				AND gl.is_cancelled = 0
				AND gl.account IN (
					SELECT account FROM `tabUAE VAT Account` WHERE parent = %(company)s
				)
				{conditions}
			""",
			filters,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_reverse_charge_recoverable_total(filters):
	"""Returns base_total for recoverable reverse charge Purchase Invoices."""
	query_filters = get_filters(filters)
	query_filters.append(["reverse_charge", "=", "Y"])
	query_filters.append(["recoverable_reverse_charge", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Purchase Invoice",
			filters=query_filters,
			fields=["SUM(base_total) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_reverse_charge_recoverable_tax(filters):
	"""Returns recoverable VAT for reverse charge Purchase Invoices."""
	conditions = get_conditions_join(filters)
	try:
		result = frappe.db.sql(
			f"""
			SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
			FROM
				`tabPurchase Invoice` p
				INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
			WHERE
				p.reverse_charge = 'Y'
				AND p.docstatus = 1
				AND p.recoverable_reverse_charge > 0
				AND gl.docstatus = 1
				AND gl.is_cancelled = 0
				AND gl.account IN (
					SELECT account FROM `tabUAE VAT Account` WHERE parent = %(company)s
				)
				{conditions}
			""",
			filters,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


# ---------------------------------------------------------------------------
# Standard Rated Expenses
# ---------------------------------------------------------------------------

def get_standard_rated_expenses_total(filters):
	"""Returns base_total for Purchase Invoices with recoverable standard rated expenses."""
	query_filters = get_filters(filters)
	query_filters.append(["recoverable_standard_rated_expenses", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Purchase Invoice",
			filters=query_filters,
			fields=["SUM(base_total) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_standard_rated_expenses_tax(filters):
	"""Returns recoverable standard rated expenses tax total."""
	query_filters = get_filters(filters)
	query_filters.append(["recoverable_standard_rated_expenses", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Purchase Invoice",
			filters=query_filters,
			fields=["SUM(recoverable_standard_rated_expenses) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


# ---------------------------------------------------------------------------
# Tourist Tax Return
# ---------------------------------------------------------------------------

def get_tourist_tax_return_total(filters):
	"""Returns base_total for Sales Invoices with tourist tax return."""
	query_filters = get_filters(filters)
	query_filters.append(["tourist_tax_return", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Sales Invoice",
			filters=query_filters,
			fields=["SUM(base_total) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_tourist_tax_return_tax(filters):
	"""Returns tourist tax return total for Sales Invoices."""
	query_filters = get_filters(filters)
	query_filters.append(["tourist_tax_return", ">", 0])
	query_filters.append(["docstatus", "=", 1])
	try:
		result = frappe.db.get_all(
			"Sales Invoice",
			filters=query_filters,
			fields=["SUM(tourist_tax_return) as total"],
			as_list=True,
			limit=1,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


# ---------------------------------------------------------------------------
# Zero Rated & Exempt
# ---------------------------------------------------------------------------

def get_zero_rated_total(filters):
	"""Returns the sum of base_net_amount for zero rated Sales Invoice Items."""
	conditions = get_conditions(filters)
	try:
		result = frappe.db.sql(
			f"""
			SELECT SUM(i.base_net_amount) AS total
			FROM
				`tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s ON i.parent = s.name
			WHERE
				s.docstatus = 1
				AND i.is_zero_rated = 1
				{conditions}
			""",
			filters,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


def get_exempt_total(filters):
	"""Returns the sum of base_net_amount for exempt Sales Invoice Items."""
	conditions = get_conditions(filters)
	try:
		result = frappe.db.sql(
			f"""
			SELECT SUM(i.base_net_amount) AS total
			FROM
				`tabSales Invoice Item` i
				INNER JOIN `tabSales Invoice` s ON i.parent = s.name
			WHERE
				s.docstatus = 1
				AND i.is_exempt = 1
				{conditions}
			""",
			filters,
		)
		return result[0][0] or 0
	except (IndexError, TypeError):
		return 0


# ---------------------------------------------------------------------------
# Condition Builders
# ---------------------------------------------------------------------------

def get_conditions(filters):
	"""SQL conditions for Sales Invoice queries (uses s alias)."""
	conditions = ""
	for key, condition in (
		("company", " AND s.company = %(company)s"),
		("from_date", " AND s.posting_date >= %(from_date)s"),
		("to_date", " AND s.posting_date <= %(to_date)s"),
	):
		if filters.get(key):
			conditions += condition
	return conditions


def get_conditions_join(filters):
	"""SQL conditions for Purchase Invoice join queries (uses p alias)."""
	conditions = ""
	for key, condition in (
		("company", " AND p.company = %(company)s"),
		("from_date", " AND p.posting_date >= %(from_date)s"),
		("to_date", " AND p.posting_date <= %(to_date)s"),
	):
		if filters.get(key):
			conditions += condition
	return conditions
