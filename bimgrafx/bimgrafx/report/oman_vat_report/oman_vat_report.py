# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data, emirates, amounts_by_emirate = get_data(filters)
    return columns, data


def get_columns():
    """
    Columns for the UAE VAT Return report.
    Using Float for amount and vat_amount so ERPNext renders real numbers
    (not strings) — frappe.format() was converting to text which broke
    sorting, totals and currency display.
    """
    return [
        {
            "fieldname": "no",
            "label": _("No"),
            "fieldtype": "Data",
            "width": 60,
        },
        {
            "fieldname": "legend",
            "label": _("Legend"),
            "fieldtype": "Data",
            "width": 380,
        },
        {
            "fieldname": "amount",
            "label": _("Amount (AED)"),
            "fieldtype": "Float",
            "precision": 2,
            "width": 160,
        },
        {
            "fieldname": "vat_amount",
            "label": _("VAT Amount (AED)"),
            "fieldtype": "Float",
            "precision": 2,
            "width": 160,
        },
        {
            "fieldname": "vat_rate",
            "label": _("VAT Rate %"),
            "fieldtype": "Data",
            "width": 100,
        },
    ]


def get_data(filters=None):
    data = []
    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)
    return data, emirates, amounts_by_emirate


# ─────────────────────────────────────────────────────────────────────────────
# SALES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_sales(data, filters):
    append_data(data, "", _("VAT on Sales and All Other Outputs"), None, None, "")

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    append_data(
        data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        flt((-1) * get_tourist_tax_return_total(filters)),
        flt((-1) * get_tourist_tax_return_tax(filters)),
        "5%",
    )

    append_data(
        data, "3",
        _("Supplies subject to the reverse charge provision"),
        flt(get_reverse_charge_total(filters)),
        flt(get_reverse_charge_tax(filters)),
        "5%",
    )

    append_data(
        data, "4",
        _("Zero Rated"),
        flt(get_zero_rated_total(filters)),
        0.0,
        "0%",
    )

    append_data(
        data, "5",
        _("Exempt Supplies"),
        flt(get_exempt_total(filters)),
        0.0,
        "Exempt",
    )

    append_data(data, "", "", None, None, "")
    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
    total_emiratewise = get_total_emiratewise(filters)
    emirates = get_emirates()
    amounts_by_emirate = {}

    for emirate, amount, vat in total_emiratewise:
        amounts_by_emirate[emirate] = {
            "legend":          emirate,
            "raw_amount":      flt(amount),
            "raw_vat_amount":  flt(vat),
            "amount":          flt(amount),
            "vat_amount":      flt(vat),
        }

    amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate)
    return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate):
    for no, emirate in enumerate(emirates, 97):
        if emirate in amounts_by_emirate:
            amounts_by_emirate[emirate]["no"]     = _("1{0}").format(chr(no))
            amounts_by_emirate[emirate]["legend"] = _("Standard rated supplies in {0}").format(emirate)
            amounts_by_emirate[emirate]["vat_rate"] = "5%"
            data.append(amounts_by_emirate[emirate])
        else:
            append_data(
                data,
                _("1{0}").format(chr(no)),
                _("Standard rated supplies in {0}").format(emirate),
                0.0,
                0.0,
                "5%",
            )
    return amounts_by_emirate


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_expenses(data, filters):
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), None, None, "")

    append_data(
        data, "9",
        _("Standard Rated Expenses"),
        flt(get_standard_rated_expenses_total(filters)),
        flt(get_standard_rated_expenses_tax(filters)),
        "5%",
    )

    append_data(
        data, "10",
        _("Supplies subject to the reverse charge provision"),
        flt(get_reverse_charge_recoverable_total(filters)),
        flt(get_reverse_charge_recoverable_tax(filters)),
        "5%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def append_data(data, no, legend, amount, vat_amount, vat_rate=""):
    data.append({
        "no":         no,
        "legend":     legend,
        "amount":     amount,      # raw float — not frappe.format()
        "vat_amount": vat_amount,  # raw float — not frappe.format()
        "vat_rate":   vat_rate,
    })


# ─────────────────────────────────────────────────────────────────────────────
# EMIRATEWISE TOTALS
# FIX: VAT is stored in tabSales Taxes and Charges, NOT in
#      tabSales Invoice Item.tax_amount (which is often 0 in v15).
#      We join to the tax table and sum base_tax_amount per emirate.
# ─────────────────────────────────────────────────────────────────────────────

def get_total_emiratewise(filters):
    conditions = get_conditions(filters)
    try:
        return frappe.db.sql(
            f"""
            SELECT
                s.vat_emirate                   AS emirate,
                SUM(i.base_net_amount)          AS total_amount,
                COALESCE(
                    (
                        SELECT SUM(stc.base_tax_amount)
                        FROM `tabSales Taxes and Charges` stc
                        WHERE stc.parent = s.name
                          AND stc.charge_type != 'Actual'
                    ), 0
                )                               AS total_vat
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
    return ["Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"]


# ─────────────────────────────────────────────────────────────────────────────
# FILTER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_filters(filters):
    query_filters = []
    if filters.get("company"):
        query_filters.append(["company", "=", filters["company"]])
    if filters.get("from_date"):
        query_filters.append(["posting_date", ">=", filters["from_date"]])
    if filters.get("to_date"):
        query_filters.append(["posting_date", "<=", filters["to_date"]])
    return query_filters


def get_conditions(filters):
    conditions = ""
    for opts in (
        ("company",   " AND s.company=%(company)s"),
        ("from_date", " AND s.posting_date>=%(from_date)s"),
        ("to_date",   " AND s.posting_date<=%(to_date)s"),
    ):
        if filters.get(opts[0]):
            conditions += opts[1]
    return conditions


def get_conditions_join(filters):
    """Conditions for queries that join Purchase Invoice as p."""
    conditions = ""
    for opts in (
        ("company",   " AND p.company=%(company)s"),
        ("from_date", " AND p.posting_date>=%(from_date)s"),
        ("to_date",   " AND p.posting_date<=%(to_date)s"),
    ):
        if filters.get(opts[0]):
            conditions += opts[1]
    return conditions


# ─────────────────────────────────────────────────────────────────────────────
# REVERSE CHARGE
# ─────────────────────────────────────────────────────────────────────────────

def get_reverse_charge_total(filters):
    query_filters = get_filters(filters)
    query_filters.append(["reverse_charge", "=", "Y"])
    query_filters.append(["docstatus", "=", 1])
    try:
        return (
            frappe.db.get_all(
                "Purchase Invoice",
                filters=query_filters,
                fields=[{"SUM": "base_total"}],
                as_list=True,
                limit=1,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_tax(filters):
    """
    FIX: Removed gl.docstatus = 1 — GL Entry has no docstatus in ERPNext v15.
    Use gl.is_cancelled = 0 instead.
    VAT accounts fetched from tabUAE VAT Account linked to company.
    """
    conditions = get_conditions_join(filters)
    try:
        return (
            frappe.db.sql(
                f"""
                SELECT SUM(gl.debit)
                FROM `tabPurchase Invoice` p
                INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
                WHERE
                    p.reverse_charge = 'Y'
                    AND p.docstatus = 1
                    AND gl.is_cancelled = 0
                    AND gl.account IN (
                        SELECT account FROM `tabUAE VAT Account`
                        WHERE parent = %(company)s
                    )
                    {conditions}
                """,
                filters,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_total(filters):
    query_filters = get_filters(filters)
    query_filters.append(["reverse_charge", "=", "Y"])
    query_filters.append(["recoverable_reverse_charge", ">", "0"])
    query_filters.append(["docstatus", "=", 1])
    try:
        return (
            frappe.db.get_all(
                "Purchase Invoice",
                filters=query_filters,
                fields=[{"SUM": "base_total"}],
                as_list=True,
                limit=1,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_tax(filters):
    """
    FIX: Removed gl.docstatus = 1 — not a valid field in GL Entry (ERPNext v15).
    """
    conditions = get_conditions_join(filters)
    try:
        return (
            frappe.db.sql(
                f"""
                SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
                FROM `tabPurchase Invoice` p
                INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
                WHERE
                    p.reverse_charge = 'Y'
                    AND p.docstatus = 1
                    AND p.recoverable_reverse_charge > 0
                    AND gl.is_cancelled = 0
                    AND gl.account IN (
                        SELECT account FROM `tabUAE VAT Account`
                        WHERE parent = %(company)s
                    )
                    {conditions}
                """,
                filters,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD RATED EXPENSES (Purchase side input VAT)
# ─────────────────────────────────────────────────────────────────────────────

def get_standard_rated_expenses_total(filters):
    query_filters = get_filters(filters)
    query_filters.append(["recoverable_standard_rated_expenses", ">", 0])
    query_filters.append(["docstatus", "=", 1])
    try:
        return (
            frappe.db.get_all(
                "Purchase Invoice",
                filters=query_filters,
                fields=[{"SUM": "base_total"}],
                as_list=True,
                limit=1,
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
                "Purchase Invoice",
                filters=query_filters,
                fields=[{"SUM": "recoverable_standard_rated_expenses"}],
                as_list=True,
                limit=1,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST TAX RETURN
# ─────────────────────────────────────────────────────────────────────────────

def get_tourist_tax_return_total(filters):
    query_filters = get_filters(filters)
    query_filters.append(["tourist_tax_return", ">", 0])
    query_filters.append(["docstatus", "=", 1])
    try:
        return (
            frappe.db.get_all(
                "Sales Invoice",
                filters=query_filters,
                fields=[{"SUM": "base_total"}],
                as_list=True,
                limit=1,
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
                "Sales Invoice",
                filters=query_filters,
                fields=[{"SUM": "tourist_tax_return"}],
                as_list=True,
                limit=1,
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# ZERO RATED & EXEMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_zero_rated_total(filters):
    conditions = get_conditions(filters)
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
    conditions = get_conditions(filters)
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
