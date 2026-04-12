import frappe
from frappe.utils import today, date_diff

def execute(filters=None):
    if not filters:
        filters = {}

    company = filters.get("company")
    start = filters.get("start_date")
    end = filters.get("end_date")
    customer = filters.get("customer")

    # ------- 1. Get Sales Invoices ---------
    conditions = """
        si.docstatus = 1
        AND si.company = %(company)s
        AND si.posting_date BETWEEN %(start)s AND %(end)s
    """
    if customer:
        conditions += " AND si.customer = %(customer)s"

    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name AS invoice_no,
            si.customer,
            si.customer_name,
            si.project,
            si.posting_date AS invoice_date,
            si.due_date,
            si.grand_total AS invoice_value
        FROM `tabSales Invoice` si
        WHERE {conditions}
        """,
        {"company": company, "start": start, "end": end, "customer": customer},
        as_dict=True
    )

    # ------- 2. Get Payment Data ---------
    payments = frappe.db.sql(
        """
        SELECT 
            per.reference_name AS invoice_no,
            SUM(per.allocated_amount) AS paid_amount,
            MAX(pe.posting_date) AS paid_date
        FROM `tabPayment Entry Reference` per
            INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE pe.docstatus = 1
            AND per.reference_doctype = 'Sales Invoice'
        GROUP BY per.reference_name
        """,
        as_dict=True
    )

    payment_map = {p.invoice_no: p for p in payments}

    # ------- 3. Get Proposal / Quotation / Opportunity ---------
    proposal_data = frappe.db.sql(
        """
        SELECT 
            q.name AS quotation_no,
            o.name AS opportunity,
            l.name AS proposal_no,
            soi.prevdoc_docname AS so_quotation,
            soi.parent AS so_name
        FROM `tabSales Order Item` soi
            LEFT JOIN `tabQuotation` q ON q.name = soi.prevdoc_docname
            LEFT JOIN `tabOpportunity` o ON q.opportunity = o.name
            LEFT JOIN `tabLead` l ON o.party_name = l.name
        """,
        as_dict=True
    )

    proposal_map = {p.so_quotation: p for p in proposal_data}

    # ------- 4. Prepare Final Data Rows ---------
    data = []

    for inv in invoices:
        pay = payment_map.get(inv.invoice_no, {})
        
        # Get project details
        project_name = frappe.db.get_value("Project", inv.project, "project_name")

        # Get Sales Order from project
        so_name = frappe.db.get_value("Sales Order", {"project": inv.project}, "name")
        so_total = frappe.db.get_value("Sales Order", so_name, "grand_total")

        # Proposal mapping
        quotation_name = frappe.db.get_value("Sales Order Item", {"parent": so_name}, "prevdoc_docname")
        proposal = proposal_map.get(quotation_name, {})
        proposal_no = proposal.get("proposal_no")

        paid_amount = pay.get("paid_amount", 0)
        outstanding = (inv.invoice_value or 0) - paid_amount

        delay_days = 0
        if outstanding > 0 and inv.due_date:
            delay_days = max(date_diff(today(), inv.due_date), 0)

        # Payment status
        if outstanding <= 0:
            status = "Paid"
        elif today() > inv.due_date:
            status = "Overdue"
        else:
            status = "Pending"

        data.append([
            proposal_no,
            inv.customer_name,
            project_name,
            so_total,
            inv.invoice_no,
            inv.invoice_date,
            inv.invoice_value,
            inv.due_date,
            paid_amount,
            pay.get("paid_date"),
            outstanding,
            delay_days,
            status,
        ])

    # ------- 5. Define Columns ---------
    columns = [
        {"label": "Proposal No", "fieldname": "proposal_no", "fieldtype": "Link", "options": "Lead", "width": 150},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Data", "width": 200},
        {"label": "Project No", "fieldname": "project", "fieldtype": "Data", "width": 200},
        {"label": "Contract Value", "fieldname": "contract_value", "fieldtype": "Currency", "width": 220},
        {"label": "INV No", "fieldname": "invoice_no", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
        {"label": "Invoice Submitted Date", "fieldname": "invoice_date", "fieldtype": "Date", "width": 150},
        {"label": "Invoice Value", "fieldname": "invoice_value", "fieldtype": "Currency", "width": 150},
        {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 120},
        {"label": "Paid Amount (₹)", "fieldname": "paid_amount", "fieldtype": "Currency", "width": 150},
        {"label": "Paid Date", "fieldname": "paid_date", "fieldtype": "Date", "width": 120},
        {"label": "Outstanding (₹)", "fieldname": "outstanding", "fieldtype": "Currency", "width": 180},
        {"label": "Delay Days", "fieldname": "delay_days", "fieldtype": "Int", "width": 100},
        {"label": "Payment Status", "fieldname": "payment_status", "fieldtype": "Data", "width": 120},
    ]

    return columns, data
