import frappe
from frappe.utils import flt, date_diff, today


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": "Invoice",
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 150,
        },
        {
            "label": "Customer",
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 180,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 140,
        },
        {
            "label": "Posting Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Currency",
            "fieldname": "currency",
            "fieldtype": "Link",
            "options": "Currency",
            "width": 80,
            "hidden": 1,
        },
        {
            "label": "Invoice Value",
            "fieldname": "invoice_value",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": "Outstanding Amount",
            "fieldname": "outstanding_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 170,
        },
        {
            "label": "Payment Status",
            "fieldname": "payment_status",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": "Ageing (Days)",
            "fieldname": "ageing_days",
            "fieldtype": "Int",
            "width": 120,
        },
    ]


def get_data(filters):
    conditions = "si.docstatus = 1"

    if filters.get("company"):
        conditions += " AND si.company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND si.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND si.posting_date <= %(to_date)s"
    if filters.get("customer"):
        conditions += " AND si.customer = %(customer)s"

    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer,
            si.company,
            si.grand_total,
            si.outstanding_amount,
            si.posting_date,
            si.status,
            c.default_currency AS currency
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCompany` c ON c.name = si.company
        WHERE {conditions}
        ORDER BY si.posting_date DESC
        """,
        filters,
        as_dict=True,
    )

    data = []
    for inv in invoices:
        outstanding = flt(inv.outstanding_amount)

        # Payment status derived from outstanding amount
        if outstanding <= 0:
            payment_status = "Paid"
        elif outstanding < flt(inv.grand_total):
            payment_status = "Partly Paid"
        else:
            payment_status = "Unpaid"

        # Ageing only applies to invoices with outstanding amount
        ageing_days = date_diff(today(), inv.posting_date) if outstanding > 0 else 0

        data.append({
            "name":               inv.name,
            "customer":           inv.customer,
            "company":            inv.company,
            "posting_date":       inv.posting_date,
            "currency":           inv.currency,
            "invoice_value":      flt(inv.grand_total),
            "outstanding_amount": outstanding,
            "payment_status":     payment_status,
            "ageing_days":        ageing_days,
        })

    return data
