import frappe
from frappe.utils import flt


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
            "label": "Invoice Value",
            "fieldname": "invoice_value",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": "Outstanding Amount",
            "fieldname": "outstanding_amount",
            "fieldtype": "Currency",
            "width": 170,
        },
        {
            "label": "Posting Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
    ]


def get_data(filters):
    conditions = "docstatus = 1"

    if filters.get("company"):
        conditions += " AND company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND posting_date <= %(to_date)s"
    if filters.get("customer"):
        conditions += " AND customer = %(customer)s"

    invoices = frappe.db.sql(
        f"""
        SELECT
            name,
            customer,
            company,
            grand_total,
            outstanding_amount,
            posting_date
        FROM `tabSales Invoice`
        WHERE {conditions}
        ORDER BY posting_date DESC
        """,
        filters,
        as_dict=True,
    )

    data = []
    for inv in invoices:
        data.append({
            "name": inv.name,
            "customer": inv.customer,
            "company": inv.company,
            "invoice_value": flt(inv.grand_total),
            "outstanding_amount": flt(inv.outstanding_amount),
            "posting_date": inv.posting_date,
        })

    return data
