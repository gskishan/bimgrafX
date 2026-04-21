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
    Always renders as 'AED x,xxx.xx' — never uses system currency symbol.
    This bypasses ERPNext using INR/rupee symbol when system currency is INR.
    """
    val = flt(value)
    formatted = "{:,.2f}".format(abs(val))
    if val < 0:
        return "AED -{0}".format(formatted)
    return "AED {0}".format(formatted)


def vat5(amount):
    """
    5% VAT on net amount.
    Example: AED 10,16,374.39 × 5% = AED 50,818.72
    """
    return flt(flt(amount) * 5 / 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# COLUMNS
# fieldtype = Data for amount columns — Currency fieldtype would apply
# the system default currency symbol (INR/rupee) overriding AED
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
    Appends one row.
    amount_raw / vat_raw → raw floats, formatted to AED string via fmt().
    Pass None for header/separator rows to leave the cell blank.
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
    # ── Section header ────────────────────────────────────────────────────────
    append_data(data, "", _("VAT on Sales and All Other Outputs"), None, None)

    # ── Rows 1a–1g: emiratewise standard rated supplies ───────────────────────
    # VAT = 5% of net amount (calculated here — item.tax_amount is unreliable)
    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    # ── Row 2: Tourist tax refunds ────────────────────────────────────────────
    tourist_total = flt(get_tourist_tax_return_total(filters))
    tourist_tax   = flt(get_tourist_tax_return_tax(filters))
    append_data(
        data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * tourist_total,
        (-1) * tourist_tax,
    )

    # ── Row 3: Reverse charge supplies ───────────────────────────────────────
    rc_total = flt(get_reverse_charge_total(filters))
    rc_tax   = flt(get_reverse_charge_tax(filters))
    append_data(
        data, "3",
        _("Supplies subject to the reverse charge provision"),
        rc_total,
        rc_tax,
    )

    # ── Row 4: Zero rated — VAT is always 0 ──────────────────────────────────
    zero_total = flt(get_zero_rated_total(filters))
    append_data(data, "4", _("Zero Rated"), zero_total, 0.0)

    # ── Row 5: Exempt — VAT is always 0 ──────────────────────────────────────
    exempt_total = flt(get_exempt_total(filters))
    append_data(data, "5", _("Exempt Supplies"), exempt_total, 0.0)

    # ── Blank separator ───────────────────────────────────────────────────────
    append_data(data, "", "", None, None)

    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
    """
    Builds rows 1a–1g.
    Amount  = sum of base_net_amount per emirate from Sales Invoice Items.
    VAT     = 5% of that amount (calculated in Python, not from item.tax_amount
              which is often 0 in ERPNext v15).
    """
    total_emiratewise = get_total_emiratewise(filters)
    emirates          = get_emirates()
    amounts_by_emirate = {}

    for emirate, amount in total_emiratewise:
        net = flt(amount)
        vat = vat5(net)                  # ← 5% calculated here
        amounts_by_emirate[emirate] = {
            "raw_amount":     net,
            "raw_vat_amount": vat,
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
            # Emirate has no invoices — show AED 0.00
            append_data(data, box_no, legend, 0.0, 0.0)

    return emirates, amounts_by_emirate


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_expenses(data, filters):
    # ── Section header ────────────────────────────────────────────────────────
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), None, None)

    # ── Row 9: Standard rated expenses ───────────────────────────────────────
    std_total = flt(get_standard_rated_expenses_total(filters))
    std_tax   = flt(get_standard_rated_expenses_tax(filters))
    append_data(data, "9", _("Standard Rated Expenses"), std_total, std_tax)

    # ── Row 10: Recoverable reverse charge ───────────────────────────────────
    rc_rec_total = flt(get_reverse_charge_recoverable_total(filters))
    rc_rec_tax   = flt(get_reverse_charge_recoverable_tax(filters))
    append_data(
        data, "10",
        _("Supplies subject to the reverse charge provision"),
        rc_rec_total,
        rc_rec_tax,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EMIRATEWISE QUERY
# Returns (emirate, net_amount) — only 2 columns now, VAT done in Python
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
                s.docstatus      = 1
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

def get_filters(filters):
    """
    FIX: Original code checked from_date twice and never checked to_date,
    so the to_date filter was silently ignored — causing all-time totals
    regardless of the date range selected.
    """
    query_filters = []
    if filters.get("company"):
        query_filters.append(["company", "=", filters["company"]])
    if filters.get("from_date"):
        query_filters.append(["posting_date", ">=", filters["from_date"]])
    if filters.get("to_date"):                  # ← was: if filters.get("from_date") — BUG
        query_filters.append(["posting_date", "<=", filters["to_date"]])
    return query_filters


def get_conditions(filters):
    """SQL conditions for queries aliasing Sales Invoice as s."""
    conditions = ""
    for field, sql in (
        ("company",   " AND s.company=%(company)s"),
        ("from_date", " AND s.posting_date>=%(from_date)s"),
        ("to_date",   " AND s.posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
    return conditions


def get_conditions_join(filters):
    """SQL conditions for queries aliasing Purchase Invoice as p."""
    conditions = ""
    for field, sql in (
        ("company",   " AND p.company=%(company)s"),
        ("from_date", " AND p.posting_date>=%(from_date)s"),
        ("to_date",   " AND p.posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
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
    FIX: gl.docstatus = 1 removed — GL Entry has no docstatus in ERPNext v15.
    Replaced with gl.is_cancelled = 0.
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
    FIX: gl.docstatus = 1 removed — not valid in ERPNext v15.
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
            )[0][0] or 0
        )
    except (IndexError, TypeError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD RATED EXPENSES  (Purchase side input VAT)
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
