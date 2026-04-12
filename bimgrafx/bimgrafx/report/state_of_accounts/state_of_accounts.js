frappe.query_reports["State of Accounts"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company"
        },
        {
            "fieldname": "customer",
            "label": "Customer",
            "fieldtype": "Link"
        },
        {
            "fieldname": "start_date",
            "label": "Start Date",
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            "fieldname": "end_date",
            "label": "End Date",
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        }
    ]
};
