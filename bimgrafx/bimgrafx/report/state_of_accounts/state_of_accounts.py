import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "proposal_no",
            "label": _("Proposal No"),
            "fieldtype": "Link",
            "options": "Lead",
            "width": 150,
        },
        {
            "fieldname": "customer_name",
            "label": _("Customer"),
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "project_name",
            "label": _("Project No"),
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "contract_value",
            "label": _("Contract Value with Variations"),
            "fieldtype": "Currency",
            "width": 220,
        },
        {
            "fieldname": "invoice_no",
            "label": _("INV No"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 150,
        },
        {
            "fieldname": "invoice_date",
            "label": _("Invoice Submitted Date"),
            "fieldtype": "Date",
            "width": 150,
        },
        {
            "fieldname": "invoice_value",
            "label": _("Invoice Value"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "due_date",
            "label": _("Due Date"),
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "paid_amount",
            "label": _("Paid Amount (₹)"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "paid_date",
            "label": _("Paid Date"),
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "outstanding_payment",
            "label": _("Outstanding Payment (₹)"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "delay_days",
            "label": _("Delay Days"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "payment_status",
            "label": _("Payment Status"),
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_data(filters):
    # Build optional customer condition
    customer_condition = ""
    if filters.get("customer"):
        customer_condition = "AND si.customer = %(customer)s"

    return frappe.db.sql(
        f"""
        WITH invoice_data AS (
            SELECT
                si.name         AS invoice_no,
                si.customer,
                si.customer_name,
                si.project,
                si.posting_date AS invoice_date,
                si.due_date,
                si.grand_total  AS invoice_value
            FROM `tabSales Invoice` si
            WHERE
                si.docstatus = 1
                AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
                AND si.company = %(company)s
                {customer_condition}
        ),
        payment_data AS (
            SELECT
                per.reference_name        AS invoice_no,
                SUM(per.allocated_amount) AS paid_amount,
                MAX(pe.posting_date)      AS paid_date
            FROM `tabPayment Entry Reference` per
            INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
            WHERE
                pe.docstatus = 1
                AND per.reference_doctype = 'Sales Invoice'
            GROUP BY per.reference_name
        ),
        proposal_data AS (
            SELECT
                q.name AS quotation_no,
                l.name AS proposal_no
            FROM `tabQuotation` q
            LEFT JOIN `tabOpportunity` o ON q.opportunity = o.name
            LEFT JOIN `tabLead`        l ON o.party_name  = l.name
            WHERE q.docstatus = 1
        )
        SELECT
            pd.proposal_no                              AS proposal_no,
            i.customer_name                             AS customer_name,
            pr.project_name                             AS project_name,
            so.grand_total                              AS contract_value,
            i.invoice_no                                AS invoice_no,
            i.invoice_date                              AS invoice_date,
            i.invoice_value                             AS invoice_value,
            i.due_date                                  AS due_date,
            IFNULL(p.paid_amount, 0)                    AS paid_amount,
            p.paid_date                                 AS paid_date,
            (i.invoice_value - IFNULL(p.paid_amount,0)) AS outstanding_payment,
            CASE
                WHEN (i.invoice_value - IFNULL(p.paid_amount,0)) > 0
                THEN GREATEST(DATEDIFF(CURDATE(), i.due_date), 0)
                ELSE 0
            END                                         AS delay_days,
            CASE
                WHEN (i.invoice_value - IFNULL(p.paid_amount,0)) <= 0
                    THEN 'Paid'
                WHEN CURDATE() > i.due_date
                    THEN 'Overdue'
                ELSE 'Pending'
            END                                         AS payment_status
        FROM invoice_data i
        LEFT JOIN payment_data p            ON p.invoice_no    = i.invoice_no
        LEFT JOIN `tabProject` pr           ON pr.name         = i.project
        LEFT JOIN `tabSales Order` so       ON so.project      = pr.name
        LEFT JOIN `tabSales Order Item` soi ON soi.parent      = so.name
        LEFT JOIN proposal_data pd          ON pd.quotation_no = soi.prevdoc_docname
        GROUP BY i.invoice_no
        ORDER BY i.invoice_date DESC
        """,
        filters,
        as_dict=True,
    )
