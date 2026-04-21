# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data, emirates, amounts_by_emirate = get_data(filters)
    return columns, data


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt(value):
    """
    Always renders as 'AED x,xxx.xx'.
    Uses Data fieldtype column — bypasses ERPNext applying INR/rupee symbol
    when system default currency is INR.
    """
    val = flt(value)
    formatted = "{:,.2f}".format(abs(val))
    if val < 0:
        return "AED -{0}".format(formatted)
    return "AED {0}".format(formatted)


def vat5(amount):
    """5% VAT on net amount. e.g. AED 10,16,374.39 × 5% = AED 50,818.72"""
    return flt(flt(amount) * 5 / 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# COLUMNS
# fieldtype=Data for amount columns — Currency would apply INR symbol
# ─────────────────────────────────────────────────────────────────────────────

def get_columns():
    return [
        {
            "fieldname": "no",
            "label":     _("No"),
            "fieldtype": "Data",
            "width":     60,
        },
        {
            "fieldname": "legend",
            "label":     _("Legend"),
            "fieldtype": "Data",
            "width":     400,
        },
        {
            "fieldname": "amount",
            "label":     _("Amount (AED)"),
            "fieldtype": "Data",
            "width":     200,
        },
        {
            "fieldname": "vat_amount",
            "label":     _("VAT Amount (AED)"),
            "fieldtype": "Data",
            "width":     200,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# DATA ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def get_data(filters=None):
    data = []
    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)
    return data, emirates, amounts_by_emirate


def append_data(data, no, legend, amount_raw, vat_raw):
    """
    amount_raw / vat_raw = raw floats (or None for header/separator rows).
    Formatted to AED string via fmt().
    """
    data.append({
        "no":         no,
        "legend":     legend,
        "amount":     fmt(amount_raw) if amount_raw is not None else "",
        "vat_amount": fmt(vat_raw)    if vat_raw    is not None else "",
    })


# ─────────────────────────────────────────────────────────────────────────────
# SALES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_sales(data, filters):
    append_data(data, "", _("VAT on Sales and All Other Outputs"), None, None)

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    # Row 2: Tourist tax refunds
    tourist_total = flt(get_tourist_tax_return_total(filters))
    tourist_tax   = flt(get_tourist_tax_return_tax(filters))
    append_data(
        data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * tourist_total,
        (-1) * tourist_tax,
    )

    # Row 3: Reverse charge supplies
    rc_total = flt(get_reverse_charge_total(filters))
    rc_tax   = flt(get_reverse_charge_tax(filters))
    append_data(data, "3", _("Supplies subject to the reverse charge provision"), rc_total, rc_tax)

    # Row 4: Zero rated — VAT always 0
    append_data(data, "4", _("Zero Rated"), flt(get_zero_rated_total(filters)), 0.0)

    # Row 5: Exempt — VAT always 0
    append_data(data, "5", _("Exempt Supplies"), flt(get_exempt_total(filters)), 0.0)

    append_data(data, "", "", None, None)

    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
    """
    Rows 1a–1g.
    Amount = base_net_amount per emirate.
    VAT    = 5% of amount (calculated in Python — item.tax_amount is 0 in v15).
    """
    total_emiratewise  = get_total_emiratewise(filters)
    emirates           = get_emirates()
    amounts_by_emirate = {}

    for emirate, amount in total_emiratewise:
        net = flt(amount)
        amounts_by_emirate[emirate] = {
            "raw_amount":     net,
            "raw_vat_amount": vat5(net),
        }

    for no, emirate in enumerate(emirates, 97):
        box_no = _("1{0}").format(chr(no))
        legend = _("Standard rated supplies in {0}").format(emirate)

        if emirate in amounts_by_emirate:
            net = amounts_by_emirate[emirate]["raw_amount"]
            vat = amounts_by_emirate[emirate]["raw_vat_amount"]
            amounts_by_emirate[emirate].update({
                "no":         box_no,
                "legend":     legend,
                "amount":     fmt(net),
                "vat_amount": fmt(vat),
            })
            data.append(amounts_by_emirate[emirate])
        else:
            append_data(data, box_no, legend, 0.0, 0.0)

    return emirates, amounts_by_emirate


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_expenses(data, filters):
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), None, None)

    append_data(
        data, "9", _("Standard Rated Expenses"),
        flt(get_standard_rated_expenses_total(filters)),
        flt(get_standard_rated_expenses_tax(filters)),
    )

    append_data(
        data, "10", _("Supplies subject to the reverse charge provision"),
        flt(get_reverse_charge_recoverable_total(filters)),
        flt(get_reverse_charge_recoverable_tax(filters)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# EMIRATEWISE QUERY
# ─────────────────────────────────────────────────────────────────────────────

def get_total_emiratewise(filters):
    conditions = get_conditions(filters)
    try:
        return frappe.db.sql(
            f"""
            SELECT
                s.vat_emirate          AS emirate,
                SUM(i.base_net_amount) AS total_amount
            FROM
                `tabSales Invoice Item` i
                INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE
                s.docstatus       = 1
                AND i.is_exempt    != 1
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
    return [
        "Abu Dhabi", "Dubai", "Sharjah", "Ajman",
        "Umm Al Quwain", "Ras Al Khaimah", "Fujairah",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# FILTER BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def get_conditions(filters):
    """SQL conditions — Sales Invoice aliased as s."""
    conditions = ""
    for field, sql in (
        ("company",   " AND s.company=%(company)s"),
        ("from_date", " AND s.posting_date>=%(from_date)s"),
        ("to_date",   " AND s.posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
    return conditions


def get_conditions_pi(filters):
    """SQL conditions — Purchase Invoice aliased as p."""
    conditions = ""
    for field, sql in (
        ("company",   " AND p.company=%(company)s"),
        ("from_date", " AND p.posting_date>=%(from_date)s"),
        ("to_date",   " AND p.posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
    return conditions


def get_conditions_bare(filters):
    """SQL conditions — no table alias (single-table queries)."""
    conditions = ""
    for field, sql in (
        ("company",   " AND company=%(company)s"),
        ("from_date", " AND posting_date>=%(from_date)s"),
        ("to_date",   " AND posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
    return conditions


# ─────────────────────────────────────────────────────────────────────────────
# REVERSE CHARGE
# FIX: replaced frappe.db.get_all(fields=[{"SUM":...}]) — broken in v15.104
#      with frappe.db.sql() raw queries throughout
# ─────────────────────────────────────────────────────────────────────────────

def get_reverse_charge_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(base_total)
                FROM `tabPurchase Invoice`
                WHERE reverse_charge = 'Y'
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_tax(filters):
    """
    FIX: gl.docstatus = 1 removed — GL Entry has no docstatus in ERPNext v15.
    """
    conditions = get_conditions_pi(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(gl.debit)
                FROM `tabPurchase Invoice` p
                INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
                WHERE
                    p.reverse_charge  = 'Y'
                    AND p.docstatus   = 1
                    AND gl.is_cancelled = 0
                    AND gl.account IN (
                        SELECT account FROM `tabUAE VAT Account`
                        WHERE parent = %(company)s
                    )
                    {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(base_total)
                FROM `tabPurchase Invoice`
                WHERE reverse_charge = 'Y'
                  AND recoverable_reverse_charge > 0
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_reverse_charge_recoverable_tax(filters):
    """FIX: gl.docstatus = 1 removed — not valid in ERPNext v15."""
    conditions = get_conditions_pi(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
                FROM `tabPurchase Invoice` p
                INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
                WHERE
                    p.reverse_charge = 'Y'
                    AND p.docstatus  = 1
                    AND p.recoverable_reverse_charge > 0
                    AND gl.is_cancelled = 0
                    AND gl.account IN (
                        SELECT account FROM `tabUAE VAT Account`
                        WHERE parent = %(company)s
                    )
                    {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD RATED EXPENSES  (Purchase side input VAT)
# ─────────────────────────────────────────────────────────────────────────────

def get_standard_rated_expenses_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(base_total)
                FROM `tabPurchase Invoice`
                WHERE recoverable_standard_rated_expenses > 0
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_standard_rated_expenses_tax(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(recoverable_standard_rated_expenses)
                FROM `tabPurchase Invoice`
                WHERE recoverable_standard_rated_expenses > 0
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST TAX RETURN
# ─────────────────────────────────────────────────────────────────────────────

def get_tourist_tax_return_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(base_total)
                FROM `tabSales Invoice`
                WHERE tourist_tax_return > 0
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_tourist_tax_return_tax(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(tourist_tax_return)
                FROM `tabSales Invoice`
                WHERE tourist_tax_return > 0
                  AND docstatus = 1
                  {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# ZERO RATED & EXEMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_zero_rated_total(filters):
    conditions = get_conditions(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(i.base_net_amount)
                FROM `tabSales Invoice Item` i
                INNER JOIN `tabSales Invoice` s ON i.parent = s.name
                WHERE s.docstatus = 1 AND i.is_zero_rated = 1
                {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0


def get_exempt_total(filters):
    conditions = get_conditions(filters)
    try:
        return flt(
            frappe.db.sql(
                f"""
                SELECT SUM(i.base_net_amount)
                FROM `tabSales Invoice Item` i
                INNER JOIN `tabSales Invoice` s ON i.parent = s.name
                WHERE s.docstatus = 1 AND i.is_exempt = 1
                {conditions}
                """,
                filters,
            )[0][0]
        )
    except (IndexError, TypeError):
        return 0
