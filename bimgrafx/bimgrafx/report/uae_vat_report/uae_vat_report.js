// Copyright (c) 2025, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports["UAE VAT Summary Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Bold rows: Box 6, 9, 10
		if (data && data.bold) {
			value = `<strong>${value}</strong>`;
		}

		// Highlight Box 10 (Net VAT to Pay) row in blue
		if (data && data.box === "10") {
			value = `<span style="color: #1a73e8;">${value}</span>`;
		}

		return value;
	},

	// Custom title showing company + period
	get_datatable_options(options) {
		return Object.assign(options, {
			layout: "fixed",
			noDataMessage: __("No VAT transactions found for the selected period."),
		});
	},

	onload: function (report) {
		// Add a "Generate VAT Return" button in the toolbar
		report.page.add_inner_button(__("Generate VAT Return PDF"), function () {
			let filters = report.get_values();
			if (!filters) return;

			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Company",
					filters: { name: filters.company },
					fieldname: ["company_name", "default_currency"],
				},
				callback: function (r) {
					let company_name = (r.message && r.message.company_name) || filters.company;
					let currency = (r.message && r.message.default_currency) || "AED";

					// Build print URL using standard Frappe print
					let url = frappe.urllib.get_full_url(
						"/api/method/frappe.utils.print_format.download_pdf?" +
							$.param({
								doctype: "Report",
								name: "UAE VAT Summary Report",
								format: "Standard",
								no_letterhead: 0,
								filters: JSON.stringify(filters),
							})
					);
					window.open(url);
				},
			});
		});

		// Auto-set quarter date range helper buttons
		report.page.add_inner_button(
			__("Q1 (Jan–Mar)"),
			function () {
				let year = frappe.datetime.get_today().split("-")[0];
				report.set_filter_value("from_date", `${year}-01-01`);
				report.set_filter_value("to_date", `${year}-03-31`);
				report.refresh();
			},
			__("Quick Select")
		);

		report.page.add_inner_button(
			__("Q2 (Apr–Jun)"),
			function () {
				let year = frappe.datetime.get_today().split("-")[0];
				report.set_filter_value("from_date", `${year}-04-01`);
				report.set_filter_value("to_date", `${year}-06-30`);
				report.refresh();
			},
			__("Quick Select")
		);

		report.page.add_inner_button(
			__("Q3 (Jul–Sep)"),
			function () {
				let year = frappe.datetime.get_today().split("-")[0];
				report.set_filter_value("from_date", `${year}-07-01`);
				report.set_filter_value("to_date", `${year}-09-30`);
				report.refresh();
			},
			__("Quick Select")
		);

		report.page.add_inner_button(
			__("Q4 (Oct–Dec)"),
			function () {
				let year = frappe.datetime.get_today().split("-")[0];
				report.set_filter_value("from_date", `${year}-10-01`);
				report.set_filter_value("to_date", `${year}-12-31`);
				report.refresh();
			},
			__("Quick Select")
		);
	},
};
