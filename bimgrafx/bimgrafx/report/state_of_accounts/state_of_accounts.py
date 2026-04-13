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
            "label": "Paid Amount",
            "fieldname": "paid_amount",
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
            "label": "Payment Entry",
            "fieldname": "payment_entry",
            "fieldtype": "Link",
            "options": "Payment Entry",
            "width": 160,
        },
        {
            "label": "Payment Date",
            "fieldname": "payment_date",
            "fieldtype": "Date",
            "width": 120,
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
            c.default_currency          AS currency,
            GROUP_CONCAT(
                pe.name
                ORDER BY pe.posting_date
                SEPARATOR ', '
            )                           AS payment_entry,
            MAX(pe.posting_date)        AS payment_date,
            SUM(
                IFNULL(per.allocated_amount, 0)
            )                           AS paid_amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCompany` c
            ON c.name = si.company
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_name = si.name
            AND per.reference_doctype = 'Sales Invoice'
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
            AND pe.docstatus = 1
        WHERE {conditions}
        GROUP BY si.name
        ORDER BY si.posting_date DESC
        """,
        filters,
        as_dict=True,
    )

    data = []
    for inv in invoices:
        outstanding = flt(inv.outstanding_amount)
        paid_amount = flt(inv.paid_amount)

        # Payment status
        if outstanding <= 0:
            payment_status = "Paid"
        elif paid_amount > 0:
            payment_status = "Partly Paid"
        else:
            payment_status = "Unpaid"

        # Ageing only for invoices with outstanding balance
        ageing_days = date_diff(today(), inv.posting_date) if outstanding > 0 else 0

        data.append({
            "name":               inv.name,
            "customer":           inv.customer,
            "company":            inv.company,
            "posting_date":       inv.posting_date,
            "currency":           inv.currency,
            "invoice_value":      flt(inv.grand_total),
            "paid_amount":        paid_amount,
            "outstanding_amount": outstanding,
            "payment_status":     payment_status,
            "payment_entry":      inv.payment_entry or "",
            "payment_date":       inv.payment_date or "",
            "ageing_days":        ageing_days,
        })

    return data
