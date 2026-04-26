# Copyright (c) 2025, BIM and Grafx Engineering Architectural Services
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        filters = {}
    columns = get_columns()
    data, emirates, amounts_by_emirate = get_data(filters)
    return columns, data


# ─────────────────────────────────────────────────────────────────────────────
# COLUMNS
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
            "width":     500,
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
        {
            "fieldname": "rcm_input",
            "label":     _("RCM Input (AED)"),
            "fieldtype": "Data",
            "width":     200,
        },
        {
            "fieldname": "rcm_output",
            "label":     _("RCM Output (AED)"),
            "fieldtype": "Data",
            "width":     200,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# FORMAT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt(value, bold=False, prefix_aed=False):
    if value is None:
        return ""
    val = flt(value)
    formatted = "{:,.2f}".format(abs(val))
    text = "-{0}".format(formatted) if val < 0 else formatted
    if prefix_aed:
        text = "AED {0}".format(text)
    if bold:
        text = "<b>{0}</b>".format(text)
    return text


def vat5(amount):
    return flt(flt(amount) * 5 / 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

def get_data(filters=None):
    data = []
    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)
    return data, emirates, amounts_by_emirate


def append_data(data, no, legend, amount_raw, vat_raw,
                bold=False,
                rcm_input_raw=None, rcm_output_raw=None):
    data.append({
        "no":     no,
        "legend": "<b>{0}</b>".format(legend) if bold and legend else (legend or ""),
        "amount":     fmt(amount_raw,     bold=bold, prefix_aed=True) if amount_raw     is not None else "",
        "vat_amount": fmt(vat_raw,        bold=bold, prefix_aed=True) if vat_raw        is not None else "",
        "rcm_input":  fmt(rcm_input_raw,  bold=bold, prefix_aed=True) if rcm_input_raw  is not None else "",
        "rcm_output": fmt(rcm_output_raw, bold=bold, prefix_aed=True) if rcm_output_raw is not None else "",
    })


# ─────────────────────────────────────────────────────────────────────────────
# SALES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_sales(data, filters):
    append_data(data, "", _("VAT on Sales and All Other Outputs"), None, None, bold=True)

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    # Row 2 — Tourist tax refunds
    tourist_total = flt(get_tourist_tax_return_total(filters))
    tourist_tax   = flt(get_tourist_tax_return_tax(filters))
    append_data(data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * tourist_total, (-1) * tourist_tax)

    # Row 3 — Reverse charge supplies (output side)
    rc_total   = flt(get_reverse_charge_total(filters))
    rc_tax     = flt(get_rcm_tax_from_ptc(filters, "output"))
    rc_rec_tax = flt(get_rcm_tax_from_ptc(filters, "input"))
    append_data(data, "3",
        _("Supplies subject to the reverse charge provisions"),
        rc_total, rc_tax,
        rcm_input_raw=rc_rec_tax,
        rcm_output_raw=rc_tax)

    # Row 4 — Zero rated
    append_data(data, "4", _("Zero rated supplies"),
        flt(get_zero_rated_total(filters)), 0.0)

    # Row 5 — Exempt
    append_data(data, "5", _("Exempt supplies"),
        flt(get_exempt_total(filters)), 0.0)

    # BOX 6 — TOTAL OUTPUT TAX DUE
    output_vat_gl    = flt(get_output_vat_from_gl(filters))
    total_output_vat = output_vat_gl + rc_tax
    append_data(data, "6", _("BOX 6 TOTAL OUTPUT TAX DUE"),
        None, total_output_vat, bold=True)

    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
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
        box_no = "1{0}".format(chr(no))
        legend = "Box {0} Standard rated supplies in {1}".format(box_no, emirate)

        if emirate in amounts_by_emirate:
            net = amounts_by_emirate[emirate]["raw_amount"]
            vat = amounts_by_emirate[emirate]["raw_vat_amount"]
            data.append({
                "no":         box_no,
                "legend":     legend,
                "amount":     fmt(net, prefix_aed=True),
                "vat_amount": fmt(vat, prefix_aed=True),
                "rcm_input":  "",
                "rcm_output": "",
            })
        else:
            data.append({
                "no":         box_no,
                "legend":     legend,
                "amount":     "",
                "vat_amount": "",
                "rcm_input":  "",
                "rcm_output": "",
            })

    return emirates, amounts_by_emirate


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_expenses(data, filters):
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), None, None, bold=True)

    std_tax    = flt(get_standard_rated_expenses_tax(filters))
    rc_rec_tax = flt(get_rcm_tax_from_ptc(filters, "input"))
    rc_tax     = flt(get_rcm_tax_from_ptc(filters, "output"))

    # Box 7 — Standard rated expenses
    append_data(data, "7", _("Box 7 Standard rated expenses"),
        flt(get_standard_rated_expenses_total(filters)), std_tax)

    # Box 8 — Reverse charge purchases
    append_data(data, "8",
        _("Box 8 Supplies subject to the reverse charge provisions"),
        flt(get_reverse_charge_recoverable_total(filters)), rc_rec_tax,
        rcm_input_raw=rc_rec_tax,
        rcm_output_raw=rc_tax)

    # BOX 9 — TOTAL INPUT TAX
    total_input_tax = std_tax + rc_rec_tax
    append_data(data, "9", _("BOX 9 TOTAL INPUT TAX"),
        None, total_input_tax, bold=True)

    # BOX 10 — NET VAT TO PAY
    output_vat_gl    = flt(get_output_vat_from_gl(filters))
    total_output_tax = output_vat_gl + rc_tax
    net_vat          = flt(total_output_tax - total_input_tax)
    append_data(data, "10", _("BOX 10 NET VAT TO PAY (OR RECLAIM)"),
        None, net_vat, bold=True,
        rcm_input_raw=rc_rec_tax,
        rcm_output_raw=rc_tax)

    # Box 11 — Net value of sales
    append_data(data, "11", _("Box 11 Net value of sales"),
        flt(get_net_sales(filters)), None)

    # Box 12 — Net value of purchases
    append_data(data, "12", _("Box 12 Net value of purchases"),
        flt(get_net_purchases(filters)), None)

    # Box 13 — GCC sales
    append_data(data, "13",
        _("Box 13 Net value of sales to other GCC Member States"),
        None, None)

    # Box 14 — GCC purchases
    append_data(data, "14",
        _("Box 14 Net value of purchases from other GCC Member States"),
        None, None)


# ─────────────────────────────────────────────────────────────────────────────
# ══ CORE FIX ══
# get_rcm_tax_from_ptc()
#
# WHY the old GL-based approach failed:
#   ERPNext RCM posts BOTH RCM Input AND RCM Output as DEBIT entries in GL.
#   Filtering by gl.debit + account name returned the same debit amount for
#   both accounts, making it impossible to separate them correctly.
#
# NEW approach — query `tabPurchase Taxes and Charges` (the child table rows
#   visible in the "Purchase Taxes and Charges" section of the invoice) and
#   match on account_head containing 'RCM Input' or 'RCM Output'.
#   tax_amount on each row is exactly what the user sees on the invoice.
#
# account_type = "input"  → SUM of rows where account_head LIKE '%RCM Input%'
# account_type = "output" → SUM of rows where account_head LIKE '%RCM Output%'
# ─────────────────────────────────────────────────────────────────────────────

def get_rcm_tax_from_ptc(filters, account_type="output"):
    """
    Read RCM tax amounts directly from Purchase Taxes and Charges rows.
    Matches account_head by keyword: 'RCM Input' or 'RCM Output'.
    This is the only reliable method because both accounts post as GL debits.
    """
    keyword = "RCM Input" if account_type == "input" else "RCM Output"
    conditions = get_conditions_pi(filters)
    try:
        result = frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(ptc.tax_amount), 0)
            FROM `tabPurchase Taxes and Charges` ptc
            INNER JOIN `tabPurchase Invoice` p ON ptc.parent = p.name
            WHERE p.reverse_charge = 'Y'
              AND p.docstatus      = 1
              AND ptc.account_head LIKE %(keyword)s
              {conditions}
            """,
            dict(filters, keyword="%{0}%".format(keyword))
        )
        return flt(result[0][0])
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# EMIRATEWISE QUERY
# ─────────────────────────────────────────────────────────────────────────────

def get_total_emiratewise(filters=None, data_filters=None):
    f = data_filters if data_filters is not None else filters
    if f is None:
        f = {}
    conditions = get_conditions(f)
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
                s.docstatus        = 1
                AND COALESCE(i.is_exempt, 0)      != 1
                AND COALESCE(i.is_zero_rated, 0)  != 1
                {conditions}
            GROUP BY
                s.vat_emirate
            """,
            f,
        )
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT VAT FROM GL
# ─────────────────────────────────────────────────────────────────────────────

def get_output_vat_from_gl(filters):
    conditions = get_conditions_gl_si(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(gl.credit - gl.debit), 0)
            FROM `tabGL Entry` gl
            INNER JOIN `tabSales Invoice` s ON gl.voucher_no = s.name
            WHERE s.docstatus      = 1
              AND gl.is_cancelled  = 0
              AND gl.account IN (
                  SELECT account FROM `tabUAE VAT Account`
                  WHERE parent = %(company)s
              )
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_conditions_gl_si(filters):
    conditions = ""
    for field, sql in (
        ("company",   " AND s.company=%(company)s"),
        ("from_date", " AND s.posting_date>=%(from_date)s"),
        ("to_date",   " AND s.posting_date<=%(to_date)s"),
    ):
        if filters.get(field):
            conditions += sql
    return conditions


def get_emirates():
    return [
        "Abu Dhabi", "Dubai", "Sharjah", "Ajman",
        "Umm Al Quwain", "Ras Al Khaimah", "Fujairah",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# NET SALES / PURCHASES
# ─────────────────────────────────────────────────────────────────────────────

def get_net_sales(filters):
    conditions = get_conditions(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(s.base_net_total), 0)
            FROM `tabSales Invoice` s
            WHERE s.docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_net_purchases(filters):
    conditions = get_conditions_pi(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(p.base_net_total), 0)
            FROM `tabPurchase Invoice` p
            WHERE p.docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# CONDITION BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def get_conditions(filters):
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
# REVERSE CHARGE — base totals
# ─────────────────────────────────────────────────────────────────────────────

def get_reverse_charge_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(base_total), 0)
            FROM `tabPurchase Invoice`
            WHERE reverse_charge = 'Y' AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_reverse_charge_recoverable_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(base_total), 0)
            FROM `tabPurchase Invoice`
            WHERE reverse_charge = 'Y'
              AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD RATED EXPENSES
# ─────────────────────────────────────────────────────────────────────────────

def get_standard_rated_expenses_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(base_total), 0)
            FROM `tabPurchase Invoice`
            WHERE recoverable_standard_rated_expenses > 0
              AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_standard_rated_expenses_tax(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(recoverable_standard_rated_expenses), 0)
            FROM `tabPurchase Invoice`
            WHERE recoverable_standard_rated_expenses > 0
              AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# TOURIST TAX RETURN
# ─────────────────────────────────────────────────────────────────────────────

def get_tourist_tax_return_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(base_total), 0)
            FROM `tabSales Invoice`
            WHERE tourist_tax_return > 0 AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_tourist_tax_return_tax(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(tourist_tax_return), 0)
            FROM `tabSales Invoice`
            WHERE tourist_tax_return > 0 AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# ZERO RATED & EXEMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_zero_rated_total(filters):
    conditions = get_conditions(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(i.base_net_amount), 0)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND COALESCE(i.is_zero_rated, 0) = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_exempt_total(filters):
    conditions = get_conditions(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(i.base_net_amount), 0)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND COALESCE(i.is_exempt, 0) = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0
