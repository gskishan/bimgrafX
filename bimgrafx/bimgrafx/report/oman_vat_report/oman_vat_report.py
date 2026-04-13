# UAE VAT Report - Fully Fixed Version (with Correct Currency Handling)

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# EXECUTE
# ---------------------------------------------------------------------------

def execute(filters=None):
    columns = get_columns(filters)
    data, emirates, amounts_by_emirate = get_data(filters)
    return columns, data


# ---------------------------------------------------------------------------
# COMPANY CURRENCY
# ---------------------------------------------------------------------------

def get_company_currency(filters):
    if filters and filters.get("company"):
        return frappe.db.get_value("Company", filters["company"], "default_currency") or "AED"
    return "AED"


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns(filters=None):
    currency = get_company_currency(filters)

    return [
        {"fieldname": "no", "label": _("No"), "fieldtype": "Data", "width": 50},
        {"fieldname": "legend", "label": _("Legend"), "fieldtype": "Data", "width": 300},

        # hidden currency field
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "hidden": 1},

        {
            "fieldname": "amount",
            "label": _("Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 125,
        },
        {
            "fieldname": "vat_amount",
            "label": _("VAT Amount ({0})").format(currency),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
    ]


# ---------------------------------------------------------------------------
# MAIN DATA
# ---------------------------------------------------------------------------

def get_data(filters=None):
    data = []
    currency = get_company_currency(filters)

    emirates, amounts_by_emirate = append_vat_on_sales(data, filters)
    append_vat_on_expenses(data, filters)

    # Inject currency into all rows automatically
    for row in data:
        row["currency"] = currency

    return data, emirates, amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT ON SALES
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


# ----------------------------------------------------------------------------
# EMIRATE-WISE LOGIC
# ----------------------------------------------------------------------------

def standard_rated_expenses_emiratewise(data, filters):
    total_emiratewise = get_total_emiratewise(filters)
    emirates = get_emirates()
    amounts_by_emirate = {}

    if total_emiratewise:
        for emirate, amount, vat in total_emiratewise:
            amounts_by_emirate[emirate] = {
                "legend": emirate,
                "raw_amount": amount,
                "raw_vat_amount": vat,
                "amount": amount,
                "vat_amount": vat,
            }

    amounts_by_emirate = append_emiratewise_expenses(data, emirates, amounts_by_emirate)
    return emirates, amounts_by_emirate


def append_emiratewise_expenses(data, emirates, amounts_by_emirate):
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
                0,
                0,
            )
    return amounts_by_emirate


# ---------------------------------------------------------------------------
# VAT ON EXPENSES
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
# APPEND FUNCTION
# ---------------------------------------------------------------------------

def append_data(data, no, legend, amount, vat_amount):
    data.append({
        "no": no,
        "legend": legend,
        "amount": amount,
        "vat_amount": vat_amount,
    })


# ---------------------------------------------------------------------------
# QUERIES – SALES
# ---------------------------------------------------------------------------

def get_total_emiratewise(filters):
    conditions = get_conditions(filters)
    try:
        return frappe.db.sql(
            f"""
            SELECT
                s.vat_emirate AS emirate,
                SUM(i.base_net_amount),
                SUM(i.tax_amount)
            FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.docstatus = 1
            AND i.is_exempt != 1
            AND i.is_zero_rated != 1
            {conditions}
            GROUP BY s.vat_emirate
            """,
            filters,
        )
    except:
        return []


def get_reverse_charge_total(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
        AND i.reverse_charge = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_reverse_charge_tax(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(tax_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
        AND i.reverse_charge = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_zero_rated_total(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
        AND i.is_zero_rated = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_exempt_total(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(base_net_amount)
        FROM `tabSales Invoice Item` i
        INNER JOIN `tabSales Invoice` s ON i.parent = s.name
        WHERE s.docstatus = 1
        AND i.is_exempt = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


# ---------------------------------------------------------------------------
# TOURIST REFUND
# ---------------------------------------------------------------------------

def get_tourist_tax_return_total(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(grand_total)
        FROM `tabSales Invoice`
        WHERE is_tourist_invoice = 1
        AND docstatus = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_tourist_tax_return_tax(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(total_taxes_and_charges)
        FROM `tabSales Invoice`
        WHERE is_tourist_invoice = 1
        AND docstatus = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


# ---------------------------------------------------------------------------
# EXPENSES QUERIES
# ---------------------------------------------------------------------------

def get_standard_rated_expenses_total(filters):
    conditions = get_conditions_join(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(base_net_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
        AND i.is_exempt != 1
        AND i.is_zero_rated != 1
        AND i.reverse_charge != 1
        AND i.is_non_gcc != 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_standard_rated_expenses_tax(filters):
    conditions = get_conditions_join(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(tax_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
        AND i.is_exempt != 1
        AND i.is_zero_rated != 1
        AND i.reverse_charge != 1
        AND i.is_non_gcc != 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_reverse_charge_recoverable_total(filters):
    conditions = get_conditions_join(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(base_net_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
        AND i.reverse_charge = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


def get_reverse_charge_recoverable_tax(filters):
    conditions = get_conditions_join(filters)
    return frappe.db.sql(
        f"""
        SELECT SUM(tax_amount)
        FROM `tabPurchase Invoice Item` i
        INNER JOIN `tabPurchase Invoice` p ON p.name = i.parent
        WHERE p.docstatus = 1
        AND i.reverse_charge = 1
        {conditions}
        """,
        filters,
    )[0][0] or 0


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
    if filters.get("company"):
        conditions += " AND s.company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND s.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND s.posting_date <= %(to_date)s"
    return conditions


def get_conditions_join(filters):
    conditions = ""
    if filters.get("company"):
        conditions += " AND p.company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND p.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND p.posting_date <= %(to_date)s"
    return conditions
