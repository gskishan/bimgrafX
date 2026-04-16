// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

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
			on_change: function () {
				let filter_based_on =
					frappe.query_report.get_filter_value("filter_based_on");
				frappe.query_report.toggle_filter_display(
					"from_fiscal_year",
					filter_based_on === "Date Range"
				);
				frappe.query_report.toggle_filter_display(
					"to_fiscal_year",
					filter_based_on === "Date Range"
				);
				frappe.query_report.toggle_filter_display(
					"period_start_date",
					filter_based_on === "Fiscal Year"
				);
				frappe.query_report.toggle_filter_display(
					"period_end_date",
					filter_based_on === "Fiscal Year"
				);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "period_start_date",
			label: __("Start Date"),
			fieldtype: "Date",
			hidden: 1,
			reqd: 1,
		},
		{
			fieldname: "period_end_date",
			label: __("End Date"),
			fieldtype: "Date",
			hidden: 1,
			reqd: 1,
		},
		{
			fieldname: "from_fiscal_year",
			label: __("Start Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			reqd: 1,
		},
		{
			fieldname: "to_fiscal_year",
			label: __("End Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			reqd: 1,
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
		// ── NEW: Accounting Method (Cash / Accrual) ───────────────────────────
		{
			fieldname: "accounting_method",
			label: __("Accounting Method"),
			fieldtype: "Select",
			options: [
				{ value: "Accrual", label: __("Accrual") },
				{ value: "Cash",    label: __("Cash")    },
			],
			default: "Accrual",
			reqd: 1,
			description: __(
				"Cash: Only shows income/expenses when payment is received or made. " +
				"Accrual: Shows income/expenses when invoices are raised."
			),
			on_change: function () {
				let method = frappe.query_report.get_filter_value("accounting_method");

				// Visual indicator — highlight filter label when Cash is active
				let $field = frappe.query_report.get_filter("accounting_method");
				if ($field && $field.$input) {
					$field.$input
						.closest(".frappe-control")
						.toggleClass("cash-basis-active", method === "Cash");
				}

				frappe.query_report.refresh();
			},
		},
		// ─────────────────────────────────────────────────────────────────────
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				var company = frappe.query_report.get_filter_value("company");
				return {
					filters: { company: company },
				};
			},
		},
		{
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
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
		},
	],

	// ── Report header: show Cash/Accrual badge next to title ─────────────────
	after_datatable_render: function (datatable_obj) {
		const method =
			frappe.query_report.get_filter_value("accounting_method") || "Accrual";
		const badgeClass = method === "Cash" ? "badge-warning" : "badge-info";
		const badgeText  = method === "Cash"
			? __("Cash Basis")
			: __("Accrual Basis");

		// Remove old badge if present
		frappe.query_report.page.main
			.find(".accounting-method-badge")
			.remove();

		// Inject badge next to report title
		frappe.query_report.page.set_title(
			__("Profit and Loss Statement Cash Vs Accrual") +
			` <span class="badge ${badgeClass} accounting-method-badge"
			        style="font-size:11px; vertical-align:middle; margin-left:8px;">
			    ${badgeText}
			  </span>`
		);
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Bold and colour the Net Profit row
		if (data && data.account === "'" + __("Profit for the year") + "'") {
			if (data[column.fieldname] < 0) {
				value = `<span style="color: var(--red-500); font-weight:600;">${value}</span>`;
			} else {
				value = `<span style="color: var(--green-500); font-weight:600;">${value}</span>`;
			}
		}

		return value;
	},
};
