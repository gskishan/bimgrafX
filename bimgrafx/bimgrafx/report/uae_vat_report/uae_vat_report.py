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
# COLUMNS — 6 columns (added rcm_input and rcm_output)
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
        # ── NEW: Column 5 – RCM Input (recoverable reverse-charge VAT)
        {
            "fieldname": "rcm_input",
            "label":     _("RCM Input (AED)"),
            "fieldtype": "Data",
            "width":     200,
        },
        # ── NEW: Column 6 – RCM Output (reverse-charge output VAT due)
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
    """
    Format a float as [AED]x,xxx.xx
    bold=True   → wraps in <b> for summary rows (BOX 6, 9, 10)
    prefix_aed  → adds 'AED' before the number (summary rows only)
    """
    if value is None:
        return ""
    val = flt(value)
    formatted = "{:,.2f}".format(abs(val))
    if val < 0:
        text = "-{0}".format(formatted)
    else:
        text = formatted

    if prefix_aed:
        text = "AED{0}".format(text)

    if bold:
        text = "<b>{0}</b>".format(text)

    return text


def vat5(amount):
    """5% VAT on net amount."""
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
                bold=False, prefix_aed=False,
                rcm_input_raw=None, rcm_output_raw=None):
    """
    Append one row.  rcm_input_raw / rcm_output_raw populate the two new columns.
    """
    data.append({
        "no":         no,
        "legend":     "<b>{0}</b>".format(legend) if bold and legend else (legend or ""),
        "amount":     fmt(amount_raw,     bold=bold, prefix_aed=prefix_aed) if amount_raw     is not None else "",
        "vat_amount": fmt(vat_raw,        bold=bold, prefix_aed=prefix_aed) if vat_raw        is not None else "",
        # RCM columns — only bold/prefixed on summary rows if caller requests it
        "rcm_input":  fmt(rcm_input_raw,  bold=bold, prefix_aed=prefix_aed) if rcm_input_raw  is not None else "",
        "rcm_output": fmt(rcm_output_raw, bold=bold, prefix_aed=prefix_aed) if rcm_output_raw is not None else "",
    })


# ─────────────────────────────────────────────────────────────────────────────
# SALES SECTION
# ─────────────────────────────────────────────────────────────────────────────

def append_vat_on_sales(data, filters):
    # Section header
    append_data(data, "", _("VAT on Sales and All Other Outputs"), None, None, bold=True)

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    # Row 2 — Tourist tax refunds
    tourist_total = flt(get_tourist_tax_return_total(filters))
    tourist_tax   = flt(get_tourist_tax_return_tax(filters))
    append_data(data, "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * tourist_total, (-1) * tourist_tax)

    # Row 3 — Reverse charge supplies (sales / output side)
    rc_total = flt(get_reverse_charge_total(filters))
    rc_tax   = flt(get_reverse_charge_tax(filters))
    append_data(data, "3",
        _("Supplies subject to the reverse charge provisions"),
        rc_total, rc_tax)

    # Row 4 — Zero rated
    append_data(data, "4", _("Zero rated supplies"),
        flt(get_zero_rated_total(filters)), 0.0)

    # Row 5 — Exempt
    append_data(data, "5", _("Exempt supplies"),
        flt(get_exempt_total(filters)), 0.0)

    # BOX 6 — TOTAL OUTPUT TAX DUE
    # ── FIX: use actual GL credits (captures credit-note reversals)
    #    instead of re-deriving 5 % from net amounts.
    output_vat_gl = flt(get_output_vat_from_gl(filters))
    total_output_vat = output_vat_gl + rc_tax
    append_data(data, "6", _("BOX 6 TOTAL OUTPUT TAX DUE"),
        None, total_output_vat, bold=True, prefix_aed=True)

    return emirates, amounts_by_emirate


def standard_rated_expenses_emiratewise(data, filters):
    """Rows 1a–1g: Box 1a Standard rated supplies in Abu Dhabi, etc."""
    total_emiratewise  = get_total_emiratewise(filters)
    emirates           = get_emirates()
    amounts_by_emirate = {}

    for emirate, amount in total_emiratewise:
        # ── FIX: amount already nets regular invoices + credit notes because
        #    credit notes have is_return=1 and negative base_net_amount values,
        #    so SUM() naturally reduces the taxable base.
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
                "amount":     fmt(net),
                "vat_amount": fmt(vat),
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
    # Section header
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), None, None, bold=True)

    std_tax    = flt(get_standard_rated_expenses_tax(filters))
    rc_rec_tax = flt(get_reverse_charge_recoverable_tax(filters))   # RCM Input
    rc_tax     = flt(get_reverse_charge_tax(filters))               # RCM Output

    # Box 7 — Standard rated expenses
    append_data(data, "7", _("Box 7 Standard rated expenses"),
        flt(get_standard_rated_expenses_total(filters)), std_tax)

    # Box 8 — Reverse charge purchases
    # ── NEW: also populates rcm_input and rcm_output columns
    append_data(data, "8",
        _("Box 8 Supplies subject to the reverse charge provisions"),
        flt(get_reverse_charge_recoverable_total(filters)), rc_rec_tax,
        rcm_input_raw=rc_rec_tax,
        rcm_output_raw=rc_tax)

    # BOX 9 — TOTAL INPUT TAX (bold, AED prefix)
    total_input_tax = std_tax + rc_rec_tax
    append_data(data, "9", _("BOX 9 TOTAL INPUT TAX"),
        None, total_input_tax, bold=True, prefix_aed=True)

    # BOX 10 — NET VAT TO PAY
    # ── FIX: use GL-based output VAT so credit notes are already included.
    output_vat_gl    = flt(get_output_vat_from_gl(filters))
    total_output_tax = output_vat_gl + rc_tax
    net_vat          = flt(total_output_tax - total_input_tax)

    # ── NEW: BOX 10 row also shows RCM breakdown in the two new columns
    append_data(data, "10", _("BOX 10 NET VAT TO PAY (OR RECLAIM)"),
        None, net_vat, bold=True, prefix_aed=True,
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
# EMIRATEWISE QUERY
# ─────────────────────────────────────────────────────────────────────────────

def get_total_emiratewise(filters=None, data_filters=None):
    """
    Sum base_net_amount by emirate for standard-rated (non-exempt, non-zero-rated)
    sales invoice lines.

    Credit notes (is_return = 1) are NOT excluded — their negative base_net_amount
    values automatically reduce the taxable base for each emirate, which is the
    correct VAT-201 treatment.
    """
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
# OUTPUT VAT FROM GL  (FIX for credit-note-aware Box 6 / Box 10)
# ─────────────────────────────────────────────────────────────────────────────

def get_output_vat_from_gl(filters):
    """
    Pull the net output VAT posted to UAE VAT accounts via Sales Invoices
    (including credit notes, which post credits that reduce the balance).

    Uses credit - debit so that:
      • Regular invoices  → credit entry  → positive VAT
      • Credit notes      → debit entry   → negative VAT (reduces total)
    Net result = actual VAT liability, matching the ledger.
    """
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
    """Conditions joining through Sales Invoice alias 's'."""
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
# NET SALES / PURCHASES (Box 11, 12)
# ─────────────────────────────────────────────────────────────────────────────

def get_net_sales(filters):
    """
    Net value of all submitted Sales Invoices including credit notes.
    Credit notes carry negative base_net_total so they reduce the total automatically.
    """
    conditions = get_conditions(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(s.base_net_total)
            FROM `tabSales Invoice` s
            WHERE s.docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_net_purchases(filters):
    """
    Net value of all submitted Purchase Invoices including debit notes (returns).
    """
    conditions = get_conditions_pi(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(p.base_net_total)
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
# REVERSE CHARGE  (RCM Output = liability; RCM Input = recoverable)
# ─────────────────────────────────────────────────────────────────────────────

def get_reverse_charge_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(base_total)
            FROM `tabPurchase Invoice`
            WHERE reverse_charge = 'Y' AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_reverse_charge_tax(filters):
    """
    RCM Output — VAT debited (liability) on reverse-charge purchases.
    Debit entries represent the output-VAT the company owes on behalf of
    the supplier.
    """
    conditions = get_conditions_pi(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(gl.debit)
            FROM `tabPurchase Invoice` p
            INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
            WHERE p.reverse_charge = 'Y'
              AND p.docstatus = 1
              AND gl.is_cancelled = 0
              AND gl.account IN (
                  SELECT account FROM `tabUAE VAT Account`
                  WHERE parent = %(company)s
              )
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_reverse_charge_recoverable_total(filters):
    conditions = get_conditions_bare(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(base_total)
            FROM `tabPurchase Invoice`
            WHERE reverse_charge = 'Y'
              AND recoverable_reverse_charge > 0
              AND docstatus = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0


def get_reverse_charge_recoverable_tax(filters):
    """
    RCM Input — the portion of reverse-charge VAT the company can reclaim
    as input tax (proportional to recoverable_reverse_charge %).
    """
    conditions = get_conditions_pi(filters)
    try:
        return flt(frappe.db.sql(
            f"""
            SELECT SUM(gl.debit * p.recoverable_reverse_charge / 100)
            FROM `tabPurchase Invoice` p
            INNER JOIN `tabGL Entry` gl ON gl.voucher_no = p.name
            WHERE p.reverse_charge = 'Y'
              AND p.docstatus = 1
              AND p.recoverable_reverse_charge > 0
              AND gl.is_cancelled = 0
              AND gl.account IN (
                  SELECT account FROM `tabUAE VAT Account`
                  WHERE parent = %(company)s
              )
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
            SELECT SUM(base_total)
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
            SELECT SUM(recoverable_standard_rated_expenses)
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
            SELECT SUM(base_total)
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
            SELECT SUM(tourist_tax_return)
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
            SELECT SUM(i.base_net_amount)
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
            SELECT SUM(i.base_net_amount)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND COALESCE(i.is_exempt, 0) = 1
              {conditions}
            """, filters)[0][0])
    except Exception:
        return 0
