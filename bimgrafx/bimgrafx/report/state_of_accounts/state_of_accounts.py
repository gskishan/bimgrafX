import frappe
from frappe.utils import flt, date_diff, today


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


# ---------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------
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

        # ✅ NEW (display only, NOT summed)
        {
            "label": "Customer Total",
            "fieldname": "customer_total",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
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


# ---------------------------------------------------------
# DATA
# ---------------------------------------------------------
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

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name AS invoice,
            si.customer,
            si.company,
            si.grand_total,
            si.outstanding_amount,
            si.posting_date AS invoice_date,
            c.default_currency AS currency,
            pe.name AS payment_entry,
            pe.posting_date AS payment_date,
            IFNULL(per.allocated_amount, 0) AS allocated_amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCompany` c ON c.name = si.company
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_name = si.name
            AND per.reference_doctype = 'Sales Invoice'
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
            AND pe.docstatus = 1
        WHERE {conditions}
        ORDER BY si.customer, si.posting_date, si.name, pe.posting_date
        """,
        filters,
        as_dict=True,
    )

    from collections import OrderedDict

    customers = OrderedDict()

    for r in rows:
        cust = r.customer
        inv = r.invoice

        if cust not in customers:
            customers[cust] = OrderedDict()

        if inv not in customers[cust]:
            customers[cust][inv] = {
                "meta": r,
                "payments": [],
            }

        if r.payment_entry:
            customers[cust][inv]["payments"].append(r)

    data = []

    for cust, invoices in customers.items():

        cust_invoice_value = 0
        cust_paid_amount = 0
        cust_outstanding = 0

        start_index = len(data)

        for inv_name, inv_data in invoices.items():
            meta = inv_data["meta"]
            payments = inv_data["payments"]

            outstanding = flt(meta.outstanding_amount)
            paid_amount = sum(flt(p.allocated_amount) for p in payments)
            grand_total = flt(meta.grand_total)

            if outstanding <= 0:
                payment_status = "Paid"
            elif paid_amount > 0:
                payment_status = "Partly Paid"
            else:
                payment_status = "Unpaid"

            ageing_days = date_diff(today(), meta.invoice_date) if outstanding > 0 else 0

            # ✅ Invoice row
            data.append({
                "name": inv_name,
                "customer": cust,
                "company": meta.company,
                "posting_date": meta.invoice_date,
                "currency": meta.currency,
                "invoice_value": grand_total,
                "paid_amount": paid_amount,
                "outstanding_amount": outstanding,
                "customer_total": None,
                "payment_status": payment_status,
                "indent": 1,
            })

            # ✅ Payment rows
            for pmt in payments:
                data.append({
                    "name": "",
                    "customer": "",
                    "company": "",
                    "posting_date": "",
                    "currency": meta.currency,
                    "invoice_value": None,
                    "paid_amount": flt(pmt.allocated_amount),
                    "outstanding_amount": None,
                    "customer_total": None,
                    "payment_status": "Payment",
                    "payment_entry": pmt.payment_entry,
                    "payment_date": pmt.payment_date,
                    "indent": 2,
                })

            cust_invoice_value += grand_total
            cust_paid_amount += paid_amount
            cust_outstanding += outstanding

        # ✅ Customer row (IMPORTANT FIX)
        data.insert(start_index, {
            "name": "",
            "customer": cust,
            "company": "",
            "posting_date": "",
            "currency": meta.currency,

            # ❌ DO NOT PUT TOTALS HERE
            "invoice_value": None,
            "paid_amount": None,
            "outstanding_amount": None,

            # ✅ SHOW HERE INSTEAD
            "customer_total": cust_invoice_value,

            "payment_status": "",
            "indent": 0,
            "bold": 1,
        })

    return data
