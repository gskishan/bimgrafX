# UAE VAT 201 Report – Fully Working Version with AED Fix + Totals
# Works on ERPNext v14/v15

import frappe
from frappe import _


# -------------------------
# Currency Format Helper
# -------------------------

def fmt(amount):
	"""Force AED formatting with symbol + code"""
	amount = amount or 0
	formatted = frappe.format(amount, {"fieldtype": "Currency", "options": "AED"})
	return f"AED {formatted}"  # Example: AED 1,250.00


# -------------------------
# Report Entry Point
# -------------------------

def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data, totals = get_data(filters)

	# Append Totals Row
	data.append({
		"no": "",
		"legend": "<b>GRAND TOTAL</b>",
		"amount": f"<b>{fmt(totals['amount'])}</b>",
		"vat_amount": f"<b>{fmt(totals['vat_amount'])}</b>",
	})

	return columns, data


# -------------------------
# Columns
# -------------------------

def get_columns():
	return [
		{"fieldname": "no", "label": _("No"), "fieldtype": "Data", "width": 50},
		{"fieldname": "legend", "label": _("Legend"), "fieldtype": "Data", "width": 330},
		{"fieldname": "amount", "label": _("Amount (AED)"), "fieldtype": "Data", "width": 150},
		{"fieldname": "vat_amount", "label": _("VAT Amount (AED)"), "fieldtype": "Data", "width": 150},
	]


# -------------------------
# Main Data Builder
# -------------------------

def get_data(filters):
	data = []
	totals = {"amount": 0, "vat_amount": 0}

	# HEADER
	append_row(data, "", "<b>VAT on Sales and Other Outputs</b>", "", "")

	# 1. Standard rated emirate-wise (1A – 1G)
	emirates = ["Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"]
	emirate_values = get_total_emiratewise(filters)

	emirate_map = {x[0]: x for x in emirate_values}

	code_letter = 97  # 'a'

	for emirate in emirates:
		if emirate in emirate_map:
			_, amount, vat = emirate_map[emirate]
		else:
			amount, vat = 0, 0

		append_row(
			data,
			f"1{chr(code_letter)}",
			f"Standard rated supplies in {emirate}",
			fmt(amount),
			fmt(vat),
		)

		totals["amount"] += amount
		totals["vat_amount"] += vat

		code_letter += 1

	# 2. Tourist Refunds
	amount = get_tourist_tax_return_total(filters)
	vat = get_tourist_tax_return_tax(filters)
	append_and_total(data, totals, "2", "Tax Refunds to Tourists", amount, vat)

	# 3. Reverse Charge (Sales)
	amount = get_reverse_charge_total(filters)
	vat = get_reverse_charge_tax(filters)
	append_and_total(data, totals, "3", "Reverse Charge (Sales)", amount, vat)

	# 4. Zero Rated
	amount = get_zero_rated_total(filters)
	append_and_total(data, totals, "4", "Zero Rated Supplies", amount, 0)

	# 5. Exempt
	amount = get_exempt_total(filters)
	append_and_total(data, totals, "5", "Exempt Supplies", amount, 0)

	# Break
	append_row(data, "", "", "", "")

	# -----------------------
	# VAT on Expenses
	# -----------------------

	append_row(data, "", "<b>VAT on Expenses and Inputs</b>", "", "")

	# 9. Standard Rated Expenses
	amount = get_standard_rated_expenses_total(filters)
	vat = get_standard_rated_expenses_tax(filters)
	append_and_total(data, totals, "9", "Standard Rated Expenses", amount, vat)

	# 10. Reverse Charge Recoverable
	amount = get_reverse_charge_recoverable_total(filters)
	vat = get_reverse_charge_recoverable_tax(filters)
	append_and_total(data, totals, "10", "Reverse Charge Recoverable", amount, vat)

	return data, totals


# -------------------------
# Utility Row Functions
# -------------------------

def append_row(data, no, legend, amount, vat_amount):
	data.append({
		"no": no,
		"legend": legend,
		"amount": amount,
		"vat_amount": vat_amount,
	})


def append_and_total(data, totals, no, legend, amount, vat_amount):
	append_row(data, no, legend, fmt(amount), fmt(vat_amount))
	totals["amount"] += amount
	totals["vat_amount"] += vat_amount


# -------------------------
# Filters Builder
# -------------------------

def build_conditions(filters):
	cond = ""

	if filters.get("company"):
		cond += " AND s.company = %(company)s"
	if filters.get("from_date"):
		cond += " AND s.posting_date >= %(from_date)s"
	if filters.get("to_date"):
		cond += " AND s.posting_date <= %(to_date)s"

	return cond


# -------------------------
# SQL Sections
# -------------------------

def get_total_emiratewise(filters):
	return frappe.db.sql(
		f"""
		SELECT s.vat_emirate, SUM(i.base_net_amount), SUM(i.tax_amount)
		FROM `tabSales Invoice Item` i
		JOIN `tabSales Invoice` s ON s.name = i.parent
		WHERE s.docstatus = 1 AND i.is_zero_rated = 0 AND i.is_exempt = 0
		{build_conditions(filters)}
		GROUP BY s.vat_emirate
	""",
		filters,
	)


def get_zero_rated_total(filters):
	return frappe.db.sql(
		f"""
		SELECT SUM(i.base_net_amount)
		FROM `tabSales Invoice Item` i
		JOIN `tabSales Invoice` s ON s.name = i.parent
		WHERE s.docstatus = 1 AND i.is_zero_rated = 1
		{build_conditions(filters)}
	""",
		filters,
	)[0][0] or 0


def get_exempt_total(filters):
	return frappe.db.sql(
		f"""
		SELECT SUM(i.base_net_amount)
		FROM `tabSales Invoice Item` i
		JOIN `tabSales Invoice` s ON s.name = i.parent
		WHERE s.docstatus = 1 AND i.is_exempt = 1
		{build_conditions(filters)}
	""",
		filters,
	)[0][0] or 0


def get_tourist_tax_return_total(filters):
	return frappe.db.get_all(
		"Sales Invoice",
		filters={"tourist_tax_return": (">", 0), "docstatus": 1},
		fields=["SUM(base_total)"],
		as_list=True,
	)[0][0] or 0


def get_tourist_tax_return_tax(filters):
	return frappe.db.get_all(
		"Sales Invoice",
		filters={"tourist_tax_return": (">", 0), "docstatus": 1},
		fields=["SUM(tourist_tax_return)"],
		as_list=True,
	)[0][0] or 0


def get_reverse_charge_total(filters):
	return frappe.db.get_all(
		"Purchase Invoice",
		filters={"reverse_charge": "Y", "docstatus": 1},
		fields=["SUM(base_total)"],
		as_list=True,
	)[0][0] or 0


def get_reverse_charge_tax(filters):
	return frappe.db.sql(
		"""
		SELECT SUM(gl.debit)
		FROM `tabPurchase Invoice` p
		JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
		WHERE p.reverse_charge = 'Y' AND p.docstatus = 1
	""",
	)[0][0] or 0


def get_standard_rated_expenses_total(filters):
	return frappe.db.get_all(
		"Purchase Invoice",
		filters={"recoverable_standard_rated_expenses": (">", 0), "docstatus": 1},
		fields=["SUM(base_total)"],
		as_list=True,
	)[0][0] or 0


def get_standard_rated_expenses_tax(filters):
	return frappe.db.get_all(
		"Purchase Invoice",
		filters={"recoverable_standard_rated_expenses": (">", 0), "docstatus": 1},
		fields=["SUM(recoverable_standard_rated_expenses)"],
		as_list=True,
	)[0][0] or 0


def get_reverse_charge_recoverable_total(filters):
	return frappe.db.get_all(
		"Purchase Invoice",
		filters={"reverse_charge": "Y", "recoverable_reverse_charge": (">", 0), "docstatus": 1},
		fields=["SUM(base_total)"],
		as_list=True,
	)[0][0] or 0


def get_reverse_charge_recoverable_tax(filters):
	return frappe.db.sql(
		"""
		SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
		FROM `tabPurchase Invoice` p
		JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
		WHERE p.reverse_charge = 'Y' AND p.recoverable_reverse_charge > 0 AND p.docstatus = 1
	""",
	)[0][0] or 0
