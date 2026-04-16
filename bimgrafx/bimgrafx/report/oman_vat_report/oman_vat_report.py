# UAE VAT 201 Report - Corrected (AED currency + correct VAT from tax table)

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# EXECUTE
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)
    data, emirates, amounts_by_emirate = get_data(filters)
    return columns, data


# ---------------------------------------------------------------------------
# COMPANY CURRENCY
# ---------------------------------------------------------------------------

def get_company_currency(filters):
    if filters and filters.get("company"):
        return (
            frappe.db.get_value("Company", filters["company"], "default_currency") or "AED"
        )
    return "AED"


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns(filters=None):
    currency = get_company_currency(filters)

    return [
        {
            "fieldname": "no",
            "label": _("No"),
            "fieldtype": "Data",
            "width": 50,
        },
        {
            "fieldname": "legend",
            "label": _("Legend"),
            "fieldtype": "Data",
            "width": 300,
        },
        # ── Hidden currency carrier — ERPNext reads this per-row ──────────────
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
            "width": 0,
        },
        {
            "fieldname": "amount",
            "label": _("Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options": "currency",   # points at the hidden currency column
            "width": 160,
        },
        {
            "fieldname": "vat_amount",
            "label": _("VAT Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
    ]


# ---------------------------------------------------------------------------
# MAIN DATA
# ---------------------------------------------------------------------------

def get_data(filters=None):
    filters = frappe._dict(filters or {})
    data = []
    currency = get_company_currency(filters)

    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)

    # ── Stamp currency on every row so the Currency fieldtype renders AED ────
    for row in data:
        row["currency"] = currency

    return data, emirates, amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT ON SALES SECTION
# ---------------------------------------------------------------------------

def append_vat_on_sales(data, filters):
    append_data(data, "", _("VAT on Sales and All Other Outputs"), "", "")

    emirates, amounts_by_emirate = standard_rated_expenses_emiratewise(data, filters)

    append_data(
        data,
        "2",
        _("Tax Refunds provided to Tourists under the Tax Refunds for Tourists Scheme"),
        (-1) * get_tourist_tax_return_total(filters),
        (-1) * get_tourist_tax_return_tax(filters),
    )

    append_data(
        data,
        "3",
        _("Supplies subject to the reverse charge provision"),
        get_reverse_charge_total(filters),
        get_reverse_charge_tax(filters),
    )

    append_data(
        data,
        "4",
        _("Zero Rated Supplies"),
        get_zero_rated_total(filters),
        0,
    )

    append_data(
        data,
        "5",
        _("Exempt Supplies"),
        get_exempt_total(filters),
        0,
    )

    append_data(data, "", "", "", "")

    return emirates, amounts_by_emirate


# ---------------------------------------------------------------------------
# EMIRATE-WISE LOGIC
# ---------------------------------------------------------------------------

def standard_rated_expenses_emiratewise(data, filters):
    total_emiratewise = get_total_emiratewise(filters)
    emirates = get_emirates()
    amounts_by_emirate = {}

    if total_emiratewise:
        for emirate, amount, vat in total_emiratewise:
            if emirate:
                amounts_by_emirate[emirate] = {
                    "legend": emirate,
                    "amount": amount or 0,
                    "vat_amount": vat or 0,
                }

    amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate)
    return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate):
    for no, emirate in enumerate(emirates, 97):   # 97 = ord('a')
        label = _("Standard rated supplies in {0}").format(emirate)
        row_no = _("1{0}").format(chr(no))
        if emirate in amounts_by_emirate:
            amounts_by_emirate[emirate]["no"] = row_no
            amounts_by_emirate[emirate]["legend"] = label
            data.append(amounts_by_emirate[emirate])
        else:
            append_data(data, row_no, label, 0, 0)
    return amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT ON EXPENSES SECTION
# ---------------------------------------------------------------------------

def append_vat_on_expenses(data, filters):
    append_data(data, "", _("VAT on Expenses and All Other Inputs"), "", "")

    append_data(
        data,
        "9",
        _("Standard Rated Expenses"),
        get_standard_rated_expenses_total(filters),
        get_standard_rated_expenses_tax(filters),
    )

    append_data(
        data,
        "10",
        _("Supplies subject to the reverse charge provision"),
        get_reverse_charge_recoverable_total(filters),
        get_reverse_charge_recoverable_tax(filters),
    )


# ---------------------------------------------------------------------------
# APPEND HELPER
# ---------------------------------------------------------------------------

def append_data(data, no, legend, amount, vat_amount):
    data.append({
        "no": no,
        "legend": legend,
        "amount": amount,
        "vat_amount": vat_amount,
    })


# ---------------------------------------------------------------------------
# QUERIES — SALES
# ---------------------------------------------------------------------------

def get_total_emiratewise(filters):
    """
    Sum base_net_amount per emirate from Sales Invoice Items (standard-rated only).
    VAT is fetched from tabSales Taxes and Charges, apportioned by invoice,
    to match what ERPNext's own VAT Summary Report shows.
    """
    conditions = get_conditions(filters, alias="s")
    try:
        return frappe.db.sql(
            f"""
            SELECT
                s.vat_emirate                   AS emirate,
                SUM(i.base_net_amount)          AS amount,
                SUM(
                    IFNULL(
                        (
                            SELECT SUM(stc.base_tax_amount_after_discount_amount)
                            FROM `tabSales Taxes and Charges` stc
                            WHERE stc.parent = s.name
                              AND stc.charge_type != 'Actual'
                        ), 0
                    ) * i.base_net_amount
                    / NULLIF(s.base_net_total, 0)
                )                               AS vat_amount
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
              AND IFNULL(i.is_exempt, 0)      != 1
              AND IFNULL(i.is_zero_rated, 0)  != 1
              AND IFNULL(i.reverse_charge, 0) != 1
              {conditions}
            GROUP BY s.vat_emirate
            """,
            filters,
        )
    except Exception:
        return []


def get_reverse_charge_total(filters):
    conditions = get_conditions(filters, alias="s")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(i.base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
          AND IFNULL(i.reverse_charge, 0) = 1
          {conditions}
        """,
        filters,
    ))


def get_reverse_charge_tax(filters):
    conditions = get_conditions(filters, alias="s")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(stc.base_tax_amount_after_discount_amount)
        FROM `tabSales Taxes and Charges` stc
        INNER JOIN `tabSales Invoice` s ON stc.parent = s.name
        WHERE s.docstatus = 1
          AND stc.charge_type != 'Actual'
          {conditions}
        """,
        filters,
    ))


def get_zero_rated_total(filters):
    conditions = get_conditions(filters, alias="s")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(i.base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
          AND IFNULL(i.is_zero_rated, 0) = 1
          {conditions}
        """,
        filters,
    ))


def get_exempt_total(filters):
    conditions = get_conditions(filters, alias="s")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(i.base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
          AND IFNULL(i.is_exempt, 0) = 1
          {conditions}
        """,
        filters,
    ))


# ---------------------------------------------------------------------------
# TOURIST REFUND
# ---------------------------------------------------------------------------

def get_tourist_tax_return_total(filters):
    conditions = get_conditions(filters, alias="si", no_alias=True)
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(grand_total)
        FROM `tabSales Invoice` si
        WHERE IFNULL(is_tourist_invoice, 0) = 1
          AND docstatus = 1
          {conditions}
        """,
        filters,
    ))


def get_tourist_tax_return_tax(filters):
    conditions = get_conditions(filters, alias="si", no_alias=True)
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(total_taxes_and_charges)
        FROM `tabSales Invoice` si
        WHERE IFNULL(is_tourist_invoice, 0) = 1
          AND docstatus = 1
          {conditions}
        """,
        filters,
    ))


# ---------------------------------------------------------------------------
# EXPENSE QUERIES
# ---------------------------------------------------------------------------

def get_standard_rated_expenses_total(filters):
    conditions = get_conditions(filters, alias="p")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(i.base_net_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
          AND IFNULL(i.is_exempt, 0)      != 1
          AND IFNULL(i.is_zero_rated, 0)  != 1
          AND IFNULL(i.reverse_charge, 0) != 1
          AND IFNULL(i.is_non_gcc, 0)     != 1
          {conditions}
        """,
        filters,
    ))


def get_standard_rated_expenses_tax(filters):
    conditions = get_conditions(filters, alias="p")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(ptc.base_tax_amount_after_discount_amount)
        FROM `tabPurchase Taxes and Charges` ptc
        INNER JOIN `tabPurchase Invoice` p ON ptc.parent = p.name
        WHERE p.docstatus = 1
          AND ptc.charge_type != 'Actual'
          {conditions}
        """,
        filters,
    ))


def get_reverse_charge_recoverable_total(filters):
    conditions = get_conditions(filters, alias="p")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(i.base_net_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
          AND IFNULL(i.reverse_charge, 0) = 1
          {conditions}
        """,
        filters,
    ))


def get_reverse_charge_recoverable_tax(filters):
    conditions = get_conditions(filters, alias="p")
    return _scalar(frappe.db.sql(
        f"""
        SELECT SUM(ptc.base_tax_amount_after_discount_amount)
        FROM `tabPurchase Taxes and Charges` ptc
        INNER JOIN `tabPurchase Invoice` p ON ptc.parent = p.name
        WHERE p.docstatus = 1
          AND ptc.charge_type != 'Actual'
          {conditions}
        """,
        filters,
    ))


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def get_emirates():
    return [
        "Abu Dhabi",
        "Dubai",
        "Sharjah",
        "Ajman",
        "Umm Al Quwain",
        "Ras Al Khaimah",
        "Fujairah",
    ]


def _scalar(result):
    """Safely extract a single value from a db.sql result."""
    try:
        return result[0][0] or 0
    except Exception:
        return 0


def get_conditions(filters, alias="s", no_alias=False):
    """
    Build SQL WHERE conditions.
    `alias` is the table alias used in the query (s, p, si …).
    `no_alias` skips the alias prefix (for single-table queries).
    """
    prefix = "" if no_alias else f"{alias}."
    conditions = ""
    if filters.get("company"):
        conditions += f" AND {prefix}company = %(company)s"
    if filters.get("from_date"):
        conditions += f" AND {prefix}posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += f" AND {prefix}posting_date <= %(to_date)s"
    return conditions
