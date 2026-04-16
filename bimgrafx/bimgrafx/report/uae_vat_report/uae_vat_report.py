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


def get_columns(filters=None):
    """Creates column headers dynamically based on company currency."""
    currency = get_company_currency(filters)

    return [
        {"fieldname": "no",     "label": _("No"),                        "fieldtype": "Data",     "width": 60},
        {"fieldname": "legend", "label": _("Legend"),                    "fieldtype": "Data",     "width": 380},
        {
            "fieldname": "amount",
            "label":     _("Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options":   currency,
            "width":     160,
        },
        {
            "fieldname": "vat_amount",
            "label":     _("VAT Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options":   currency,
            "width":     160,
        },
    ]


def get_data(filters=None):
    data = []
    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)
    append_summary_boxes(data, filters)          # ← NEW: Box 6–14
    return data, emirates, amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT on Sales
# ---------------------------------------------------------------------------

def append_vat_on_sales(data, filters):
    append_data(data, "", _("VAT on Sales and All Other Outputs"), "", "")

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    append_data(
        data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * get_tourist_tax_return_total(filters),
        (-1) * get_tourist_tax_return_tax(filters),
    )
    append_data(
        data, "3",
        _("Supplies subject to the reverse charge provision"),
        get_reverse_charge_total(filters),
        get_reverse_charge_tax(filters),
    )
    append_data(data, "4", _("Zero Rated"),       get_zero_rated_total(filters),  "-")
    append_data(data, "5", _("Exempt Supplies"),  get_exempt_total(filters),      "-")
    append_data(data, "",  "",                    "",                             "")

    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
    total_emiratewise  = get_total_emiratewise(filters)
    emirates           = get_emirates()
    amounts_by_emirate = {}

    if total_emiratewise:
        for emirate, amount, vat in total_emiratewise:
            # ── FIX: recalculate VAT as 5 % of base_net_amount ──────────────
            correct_vat = round(amount * 0.05, 2)
            amounts_by_emirate[emirate] = {
                "legend":        emirate,
                "raw_amount":    amount,
                "raw_vat_amount": correct_vat,
                "amount":        amount,
                "vat_amount":    correct_vat,
            }

    amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate)
    return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate):
    for no, emirate in enumerate(emirates, 97):
        if emirate in amounts_by_emirate:
            amounts_by_emirate[emirate]["no"]     = _("1{0}").format(chr(no))
            amounts_by_emirate[emirate]["legend"] = _("Standard rated supplies in {0}").format(emirate)
            data.append(amounts_by_emirate[emirate])
        else:
            append_data(
                data,
                _("1{0}").format(chr(no)),
                _("Standard rated supplies in {0}").format(emirate),
                0, 0,
            )
    return amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT on Expenses
# ---------------------------------------------------------------------------

def append_vat_on_expenses(data, filters):
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), "", "")
    append_data(
        data, "9",
        _("Standard Rated Expenses"),
        get_standard_rated_expenses_total(filters),
        get_standard_rated_expenses_tax(filters),
    )
    append_data(
        data, "10",
        _("Supplies subject to the reverse charge provision"),
        get_reverse_charge_recoverable_total(filters),
        get_reverse_charge_recoverable_tax(filters),
    )
    append_data(data, "", "", "", "")


# ---------------------------------------------------------------------------
# Summary Boxes  (NEW)
# ---------------------------------------------------------------------------

def append_summary_boxes(data, filters):
    """Append Box 6 – 14 summary section as required by UAE VAT 201 form."""

    # ── Gather all component values ──────────────────────────────────────────
    # Sales-side VAT
    emirate_vat   = get_total_emiratewise_vat(filters)          # Box 1 total
    emirate_amt   = get_total_emiratewise_amount(filters)       # Box 1 amount

    tourist_tax   = get_tourist_tax_return_tax(filters)         # Box 2 VAT
    tourist_amt   = get_tourist_tax_return_total(filters)       # Box 2 amount

    rev_chg_tax   = get_reverse_charge_tax(filters)             # Box 3 VAT
    rev_chg_amt   = get_reverse_charge_total(filters)           # Box 3 amount

    zero_rated    = get_zero_rated_total(filters)               # Box 4
    exempt        = get_exempt_total(filters)                   # Box 5

    # Box 6  — Total value of declared supplies
    box6_amount   = emirate_amt - tourist_amt + rev_chg_amt + zero_rated + exempt
    box6_vat      = emirate_vat - tourist_tax + rev_chg_tax

    # Expense-side VAT
    std_exp_amt   = get_standard_rated_expenses_total(filters)  # Box 7 amount
    std_exp_tax   = get_standard_rated_expenses_tax(filters)    # Box 7 VAT

    rec_rev_amt   = get_reverse_charge_recoverable_total(filters)   # Box 8 amount
    rec_rev_tax   = get_reverse_charge_recoverable_tax(filters)     # Box 8 VAT

    # Box 9  — Total Input Tax
    box9_vat      = std_exp_tax + rec_rev_tax

    # Box 10 — Net VAT to Pay (or Reclaim)
    box10_vat     = box6_vat - box9_vat

    # Box 11 — Net value of sales (standard + zero + exempt − tourist refunds)
    box11_amount  = emirate_amt - tourist_amt + zero_rated + exempt

    # Box 12 — Net value of purchases
    box12_amount  = std_exp_amt + rec_rev_amt

    # Box 13/14 — GCC inter-emirate (not tracked in standard ERPNext; show 0)
    box13_amount  = 0
    box14_amount  = 0

    # ── Append rows ──────────────────────────────────────────────────────────
    append_data(data, "", _("Summary"), "", "")

    append_data(data, "6",
        _("Total value of declared supplies and all other outputs"),
        box6_amount, box6_vat)

    append_data(data, "7",
        _("Standard Rated Expenses"),
        std_exp_amt, std_exp_tax)

    append_data(data, "8",
        _("Supplies subject to the reverse charge provisions (Input)"),
        rec_rev_amt, rec_rev_tax)

    append_data(data, "BOX 9",
        _("TOTAL INPUT TAX"),
        "",  box9_vat)

    append_data(data, "BOX 10",
        _("NET VAT TO PAY (OR RECLAIM)"),
        "",  box10_vat)

    append_data(data, "11",
        _("Net value of sales"),
        box11_amount, "")

    append_data(data, "12",
        _("Net value of purchases"),
        box12_amount, "")

    append_data(data, "13",
        _("Net value of sales to other GCC Member States"),
        box13_amount, "")

    append_data(data, "14",
        _("Net value of purchases from other GCC Member States"),
        box14_amount, "")


# ---------------------------------------------------------------------------
# Helper: aggregate emiratewise totals (for summary boxes)
# ---------------------------------------------------------------------------

def get_total_emiratewise_vat(filters):
    """Returns total corrected VAT (5 % of base_net_amount) across all emirates."""
    conditions = get_conditions(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(i.base_net_amount) * 0.05
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND i.is_exempt    != 1
              AND i.is_zero_rated != 1
              {conditions}
            """,
            filters,
        )
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_total_emiratewise_amount(filters):
    """Returns total base_net_amount across all emirates."""
    conditions = get_conditions(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(i.base_net_amount)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND i.is_exempt    != 1
              AND i.is_zero_rated != 1
              {conditions}
            """,
            filters,
        )
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def append_data(data, no, legend, amount, vat_amount):
    data.append({"no": no, "legend": legend, "amount": amount, "vat_amount": vat_amount})


def get_total_emiratewise(filters):
    conditions = get_conditions(filters)
    try:
        return frappe.db.sql(
            f"""
            SELECT
                s.vat_emirate              AS emirate,
                SUM(i.base_net_amount)     AS total,
                SUM(i.tax_amount)          AS tax_total      -- kept for reference only
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND i.is_exempt    != 1
              AND i.is_zero_rated != 1
              {conditions}
            GROUP BY s.vat_emirate
            """,
            filters,
        )
    except (IndexError, TypeError):
        return []


def get_emirates():
    return ["Abu Dhabi", "Dubai", "Sharjah", "Ajman",
            "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"]


def get_filters(filters):
    query_filters = []
    if filters.get("company"):
        query_filters.append(["company",      "=",  filters["company"]])
    if filters.get("from_date"):
        query_filters.append(["posting_date", ">=", filters["from_date"]])
    if filters.get("to_date"):
        query_filters.append(["posting_date", "<=", filters["to_date"]])
    return query_filters


# ---------------------------------------------------------------------------
# Reverse Charge
# ---------------------------------------------------------------------------

def get_reverse_charge_total(filters):
    query_filters = get_filters(filters)
    query_filters += [["reverse_charge", "=", "Y"], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Purchase Invoice", filters=query_filters,
                                   fields=["SUM(base_total) as total"], as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_tax(filters):
    conditions = get_conditions_join(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(gl.debit)
            FROM `tabPurchase Invoice` p
            INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
            WHERE p.reverse_charge = 'Y'
              AND p.docstatus = 1
              AND gl.docstatus = 1
              AND gl.is_cancelled = 0
              AND gl.account IN (
                  SELECT account FROM `tabUAE VAT Account` WHERE parent = %(company)s
              )
              {conditions}
            """, filters)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_total(filters):
    query_filters = get_filters(filters)
    query_filters += [["reverse_charge", "=", "Y"],
                      ["recoverable_reverse_charge", ">", 0], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Purchase Invoice", filters=query_filters,
                                   fields=["SUM(base_total) as total"], as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_tax(filters):
    conditions = get_conditions_join(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
            FROM `tabPurchase Invoice` p
            INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
            WHERE p.reverse_charge = 'Y'
              AND p.docstatus = 1
              AND p.recoverable_reverse_charge > 0
              AND gl.docstatus = 1
              AND gl.is_cancelled = 0
              AND gl.account IN (
                  SELECT account FROM `tabUAE VAT Account` WHERE parent = %(company)s
              )
              {conditions}
            """, filters)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Standard Rated Expenses
# ---------------------------------------------------------------------------

def get_standard_rated_expenses_total(filters):
    query_filters = get_filters(filters)
    query_filters += [["recoverable_standard_rated_expenses", ">", 0], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Purchase Invoice", filters=query_filters,
                                   fields=["SUM(base_total) as total"], as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_standard_rated_expenses_tax(filters):
    query_filters = get_filters(filters)
    query_filters += [["recoverable_standard_rated_expenses", ">", 0], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Purchase Invoice", filters=query_filters,
                                   fields=["SUM(recoverable_standard_rated_expenses) as total"],
                                   as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Tourist Tax Return
# ---------------------------------------------------------------------------

def get_tourist_tax_return_total(filters):
    query_filters = get_filters(filters)
    query_filters += [["tourist_tax_return", ">", 0], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Sales Invoice", filters=query_filters,
                                   fields=["SUM(base_total) as total"], as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_tourist_tax_return_tax(filters):
    query_filters = get_filters(filters)
    query_filters += [["tourist_tax_return", ">", 0], ["docstatus", "=", 1]]
    try:
        result = frappe.db.get_all("Sales Invoice", filters=query_filters,
                                   fields=["SUM(tourist_tax_return) as total"],
                                   as_list=True, limit=1)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Zero Rated & Exempt
# ---------------------------------------------------------------------------

def get_zero_rated_total(filters):
    conditions = get_conditions(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(i.base_net_amount)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1 AND i.is_zero_rated = 1
              {conditions}
            """, filters)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


def get_exempt_total(filters):
    conditions = get_conditions(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT SUM(i.base_net_amount)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1 AND i.is_exempt = 1
              {conditions}
            """, filters)
        return result[0][0] or 0
    except (IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Condition Builders
# ---------------------------------------------------------------------------

def get_conditions(filters):
    conditions = ""
    for key, cond in (
        ("company",   " AND s.company = %(company)s"),
        ("from_date", " AND s.posting_date >= %(from_date)s"),
        ("to_date",   " AND s.posting_date <= %(to_date)s"),
    ):
        if filters.get(key):
            conditions += cond
    return conditions


def get_conditions_join(filters):
    conditions = ""
    for key, cond in (
        ("company",   " AND p.company = %(company)s"),
        ("from_date", " AND p.posting_date >= %(from_date)s"),
        ("to_date",   " AND p.posting_date <= %(to_date)s"),
    ):
        if filters.get(key):
            conditions += cond
    return conditions
