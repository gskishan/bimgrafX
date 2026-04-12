frappe.query_reports["State of Accounts"] = {
  filters: [
    {
      fieldname: "company",
      label: __("Company"),
      fieldtype: "Link",
      options: "Company",
      reqd: 1,
      default: frappe.defaults.get_user_default("Company"),
      on_change: function () {
        // Clear customer when company changes
        frappe.query_report.set_filter_value("customer", "");
        frappe.query_report.refresh();
      },
    },
    {
      fieldname: "customer",
      label: __("Customer"),
      fieldtype: "Link",
      options: "Customer",
      // Dynamically filter customers by selected company
      get_query: function () {
        const company = frappe.query_report.get_filter_value("company");
        return {
          query: "frappe.client.get_list",
          filters: {
            // Only customers who have invoices in this company
          },
          // Use doctype meta filter to limit by company via Sales Invoice
          doctype: "Customer",
          // Filter customers linked to the selected company
          filters: company
            ? [["Customer", "name", "in",
                frappe.call({
                  // Inline approach: filter via Customer's default_company field
                  // or fall back to all customers (filtered server-side in py)
                })
              ]]
            : [],
        };
      },
      // Better approach: use get_query with a server-side custom method
      get_query: function () {
        const company = frappe.query_report.get_filter_value("company");
        if (!company) return {};
        return {
          query: "frappe.client.get_list",
          doctype: "Customer",
          // Filter customers who have at least one Sales Invoice in this company
          filters: [
            ["Sales Invoice", "company", "=", company],
            ["Sales Invoice", "docstatus", "=", 1],
          ],
        };
      },
    },
    {
      fieldname: "start_date",
      label: __("From Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
    },
    {
      fieldname: "end_date",
      label: __("To Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.get_today(),
    },
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (column.fieldname === "payment_status") {
      if (data && data.payment_status === "Overdue") {
        value = `${data.payment_status}`;
      } else if (data && data.payment_status === "Paid") {
        value = `${data.payment_status}`;
      } else if (data && data.payment_status === "Pending") {
        value = `${data.payment_status}`;
      }
    }
    return value;
  },
};
