// profit_and_loss_statement.js
frappe.query_reports["Profit and Loss Statement Cash Vs Accrual"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "filter_based_on",
            label: __("Filter Based On"),
            fieldtype: "Select",
            options: ["Fiscal Year", "Date Range"],
            default: "Fiscal Year",
            reqd: 1,
            on_change: function() {
                let filter_based_on = frappe.query_report.get_filter_value("filter_based_on");
                frappe.query_report.toggle_filter_display("from_fiscal_year", filter_based_on === "Date Range");
                frappe.query_report.toggle_filter_display("to_fiscal_year", filter_based_on === "Date Range");
                frappe.query_report.toggle_filter_display("period_start_date", filter_based_on === "Fiscal Year");
                frappe.query_report.toggle_filter_display("period_end_date", filter_based_on === "Fiscal Year");
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            hidden: 1,
            reqd: 0,
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            hidden: 1,
            reqd: 0,
        },
        {
            fieldname: "from_fiscal_year",
            label: __("Start Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
            reqd: 0,
        },
        {
            fieldname: "to_fiscal_year",
            label: __("End Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
            reqd: 0,
        },
        {
            fieldname: "periodicity",
            label: __("Periodicity"),
            fieldtype: "Select",
            options: [
                { value: "Monthly", label: __("Monthly") },
                { value: "Quarterly", label: __("Quarterly") },
                { value: "Half-Yearly", label: __("Half-Yearly") },
                { value: "Yearly", label: __("Yearly") },
            ],
            default: "Yearly",
            reqd: 1,
        },
        {
            fieldname: "accounting_method",
            label: __("Accounting Method"),
            fieldtype: "Select",
            options: ["Accrual", "Cash"],
            default: "Accrual",
        },
        {
            fieldname: "accumulated_values",
            label: __("Accumulated Values"),
            fieldtype: "Check",
            default: 1,
        },
        {
            fieldname: "include_default_book_entries",
            label: __("Include Default FB Entries"),
            fieldtype: "Check",
            default: 1,
        },
        {
            fieldname: "show_zero_values",
            label: __("Show zero values"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "selected_view",
            label: __("Select View"),
            fieldtype: "Select",
            options: [
                { value: "Report", label: __("Report") },
                { value: "Growth", label: __("Growth") },
                { value: "Margin", label: __("Margin") },
            ],
            default: "Report",
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "MultiSelectList",
            options: "Cost Center",
            get_data: function(txt) {
                return frappe.db.get_link_options("Cost Center", txt, {
                    company: frappe.query_report.get_filter_value("company"),
                });
            },
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "MultiSelectList",
            options: "Project",
            get_data: function(txt) {
                return frappe.db.get_link_options("Project", txt, {
                    company: frappe.query_report.get_filter_value("company"),
                });
            },
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book",
        },
        {
            fieldname: "presentation_currency",
            label: __("Currency"),
            fieldtype: "Select",
            options: erpnext.get_presentation_currency_list(),
        },
        {
            fieldname: "include_default_book_entries",
            label: __("Include Default Book Entries"),
            fieldtype: "Check",
            default: 1,
        },
    ],

    // ── Auto-run on page load with default filter values ──────────────────────
    onload: function(report) {
        frappe.query_report.refresh();
    },

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.warn_if_negative && data[column.fieldname] < 0) {
            value = "<span style='color:red;'>" + value + "</span>";
        }
        return value;
    },
};
