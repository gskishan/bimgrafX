import frappe
from frappe import _
from frappe.utils import flt, format_currency

def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data, totals = get_data(filters)

    # add totals row
    data.append({
        "emirate": "<b>Total</b>",
        "taxable_amount": totals["taxable_amount"],
        "vat_amount": totals["vat_amount"],
        "total_amount": totals["total_amount"],
    })

    return columns, data


# --------------------------
# Columns
# --------------------------
def get_columns():
    return [
        {
            "label": _("Emirate"),
            "fieldname": "emirate",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Taxable Amount (AED)"),
            "fieldname": "taxable_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "label": _("VAT Amount (AED)"),
            "fieldname": "vat_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
        {
            "label": _("Total Amount (AED)"),
            "fieldname": "total_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 160,
        },
    ]


# --------------------------
# Main Data Logic
# --------------------------
def get_data(filters):
    company_currency = "AED"   # Force AED symbol

    emirates_map = {
        "Abu Dhabi": ["Abu Dhabi"],
        "Dubai": ["Dubai"],
        "Sharjah": ["Sharjah"],
        "Ajman": ["Ajman"],
        "Umm Al Quwain": ["Umm Al Quwain"],
        "Ras Al Khaimah": ["Ras Al Khaimah"],
        "Fujairah": ["Fujairah"],
    }

    results = []
    totals = {"taxable_amount": 0, "vat_amount": 0, "total_amount": 0}

    for emirate, cities in emirates_map.items():
        taxable, vat = get_values_for_emirate(cities, filters)
        total = taxable + vat

        results.append({
            "emirate": emirate,
            "taxable_amount": format_currency(taxable, company_currency),
            "vat_amount": format_currency(vat, company_currency),
            "total_amount": format_currency(total, company_currency),
        })

        totals["taxable_amount"] += taxable
        totals["vat_amount"] += vat
        totals["total_amount"] += total

    return results, totals


# --------------------------
# DB Query for each Emirate
# --------------------------
def get_values_for_emirate(cities, filters):
    conditions = ""
    values = {"company": filters.get("company")}

    if filters.get("from_date"):
        conditions += " AND si.posting_date >= %(from_date)s"
        values["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions += " AND si.posting_date <= %(to_date)s"
        values["to_date"] = filters.get("to_date")

    taxable = frappe.db.sql("""
        SELECT SUM(sii.base_net_amount)
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.company = %(company)s
        AND si.docstatus = 1
        AND si.customer_address IN (
            SELECT name FROM `tabAddress`
            WHERE city IN %(cities)s
        )
        {conditions}
    """.format(conditions=conditions), {**values, "cities": tuple(cities)})[0][0] or 0

    vat = frappe.db.sql("""
        SELECT SUM(sii.base_tax_amount_after_discount_amount)
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.company = %(company)s
        AND si.docstatus = 1
        AND si.customer_address IN (
            SELECT name FROM `tabAddress`
            WHERE city IN %(cities)s
        )
        {conditions}
    """.format(conditions=conditions), {**values, "cities": tuple(cities)})[0][0] or 0

    return flt(taxable), flt(vat)
