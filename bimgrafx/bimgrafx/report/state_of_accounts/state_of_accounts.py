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

    # Fetch each payment row individually (no GROUP_CONCAT)
    # so we can render one payment line per invoice below
    rows = frappe.db.sql(
        f"""
        SELECT
            si.name                     AS invoice,
            si.customer,
            si.company,
            si.grand_total,
            si.outstanding_amount,
            si.posting_date             AS invoice_date,
            c.default_currency          AS currency,
            pe.name                     AS payment_entry,
            pe.posting_date             AS payment_date,
            IFNULL(per.allocated_amount, 0) AS allocated_amount
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
        ORDER BY si.customer, si.posting_date, si.name, pe.posting_date
        """,
        filters,
        as_dict=True,
    )

    # ── Group rows: customer → invoice → [payments] ──────────────────────────
    from collections import OrderedDict

    customers = OrderedDict()   # customer → OrderedDict of invoices
    for r in rows:
        cust = r.customer
        inv  = r.invoice

        if cust not in customers:
            customers[cust] = OrderedDict()

        if inv not in customers[cust]:
            customers[cust][inv] = {
                "meta": r,          # first row carries invoice-level fields
                "payments": [],
            }

        if r.payment_entry:
            customers[cust][inv]["payments"].append(r)

    # ── Build flat data list ──────────────────────────────────────────────────
    data = []

    for cust, invoices in customers.items():
        # ── Accumulate customer-level totals ──────────────────────────────────
        cust_invoice_value   = 0
        cust_paid_amount     = 0
        cust_outstanding     = 0

        for inv_name, inv_data in invoices.items():
            meta         = inv_data["meta"]
            payments     = inv_data["payments"]
            outstanding  = flt(meta.outstanding_amount)
            paid_amount  = sum(flt(p.allocated_amount) for p in payments)
            grand_total  = flt(meta.grand_total)

            # Payment status
            if outstanding <= 0:
                payment_status = "Paid"
            elif paid_amount > 0:
                payment_status = "Partly Paid"
            else:
                payment_status = "Unpaid"

            ageing_days = date_diff(today(), meta.invoice_date) if outstanding > 0 else 0

            # ── Invoice header row ────────────────────────────────────────────
            data.append({
                "name":               inv_name,
                "customer":           cust,
                "company":            meta.company,
                "posting_date":       meta.invoice_date,
                "currency":           meta.currency,
                "invoice_value":      grand_total,
                "paid_amount":        paid_amount,
                "outstanding_amount": outstanding,
                "payment_status":     payment_status,
                "payment_entry":      "",
                "payment_date":       "",
                "ageing_days":        ageing_days,
                "indent":             1,           # indent under customer
            })

            # ── One child row per payment ─────────────────────────────────────
            for pmt in payments:
                data.append({
                    "name":               "",
                    "customer":           "",
                    "company":            "",
                    "posting_date":       "",
                    "currency":           meta.currency,
                    "invoice_value":      "",
                    "paid_amount":        flt(pmt.allocated_amount),
                    "outstanding_amount": "",
                    "payment_status":     "Payment",
                    "payment_entry":      pmt.payment_entry,
                    "payment_date":       pmt.payment_date,
                    "ageing_days":        "",
                    "indent":             2,       # indent under invoice
                })

            # Accumulate for customer subtotal
            cust_invoice_value += grand_total
            cust_paid_amount   += paid_amount
            cust_outstanding   += outstanding

        # ── Customer header / subtotal row (inserted BEFORE its invoices) ─────
        # We collect invoice rows first, then prepend the customer group row.
        # Simpler approach: insert customer row before the invoice block.
        # Find where this customer's block starts and insert there.
        insert_pos = next(
            (i for i, row in enumerate(data) if row.get("customer") == cust),
            len(data),
        )
        data.insert(insert_pos, {
            "name":               "",
            "customer":           cust,
            "company":            "",
            "posting_date":       "",
            "currency":           meta.currency,   # last meta is fine for currency
            "invoice_value":      cust_invoice_value,
            "paid_amount":        cust_paid_amount,
            "outstanding_amount": cust_outstanding,
            "payment_status":     "",
            "payment_entry":      "",
            "payment_date":       "",
            "ageing_days":        "",
            "indent":             0,               # top-level customer group
            "bold":               1,
        })

    return data
