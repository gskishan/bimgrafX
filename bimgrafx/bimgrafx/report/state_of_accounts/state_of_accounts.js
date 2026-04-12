frappe.query_reports["State of Accounts"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0,
            "default": frappe.defaults.get_user_default("Company"),
            "on_change": function () {
                frappe.query_report.set_filter_value("customer", "");
            }
        },
        {
            "fieldname": "customer",
            "label": __("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "reqd": 0,
            "get_query": function () {
                var company = frappe.query_report.get_filter_value("company");
                if (!company) return {};

                // Fetch customers who have invoices under this company
                // Uses frappe.db.get_list which is safe and whitelisted in v15
                return new Promise(function (resolve) {
                    frappe.db.get_list("Sales Invoice", {
                        filters: { company: company, docstatus: 1 },
                        fields: ["customer"],
                        limit: 500,
                        group_by: "customer"
                    }).then(function (rows) {
                        var names = [...new Set(rows.map(r => r.customer))];
                        resolve({
                            filters: [["Customer", "name", "in", names]]
                        });
                    });
                });
            }
        },
        {
            "fieldname": "from_date",
            "label": __("Start Date"),
            "fieldtype": "Date",
            "reqd": 0,
            "default": frappe.datetime.year_start()
        },
        {
            "fieldname": "to_date",
            "label": __("End Date"),
            "fieldtype": "Date",
            "reqd": 0,
            "default": frappe.datetime.get_today()
        }
    ]
};
