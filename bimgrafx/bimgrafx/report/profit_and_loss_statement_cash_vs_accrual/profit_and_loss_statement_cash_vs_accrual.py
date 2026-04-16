# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.financial_report_template.financial_report_engine import (
    FinancialReportEngine,
)
from erpnext.accounts.report.financial_statements import (
    compute_growth_view_data,
    compute_margin_view_data,
    get_columns,
    get_filtered_list_for_consolidated_report,
    get_period_list,
    # ✅ DO NOT import get_data from core — we define our own below
    get_accounts,
    filter_accounts,
    get_appropriate_currency,
    calculate_values,
    accumulate_values_into_parents,
    prepare_data,
    filter_out_zero_value_rows,
    add_total_row,
    set_gl_entries_by_account,
    apply_additional_conditions,
    get_account_filter_query,
    convert_to_presentation_currency,
    get_currency,
)
from frappe.utils.nestedset import ExistsCriterion


def _set_gl_entries_cash(
    company, from_date, to_date, filters, gl_entries_by_account,
    root_lft, root_rgt, root_type=None, ignore_closing_entries=False,
):
    """Same as core set_gl_entries_by_account but only Payment Entry / Journal Entry."""
    gl = frappe.qb.DocType("GL Entry")
    query = (
        frappe.qb.from_(gl)
        .select(
            gl.account, gl.debit, gl.credit,
            gl.debit_in_account_currency, gl.credit_in_account_currency,
            gl.account_currency, gl.posting_date, gl.is_opening, gl.fiscal_year,
        )
        .where(gl.company == filters.company)
        .where(gl.is_cancelled == 0)
        .where(gl.posting_date <= to_date)
        .where(gl.voucher_type.isin(["Payment Entry", "Journal Entry"]))  # ✅ Cash-basis
        .force_index("posting_date_company_index")
    )

    query = apply_additional_conditions("GL Entry", query, from_date, ignore_closing_entries, filters)

    if (root_lft and root_rgt) or root_type:
        query = query.where(ExistsCriterion(
            get_account_filter_query(root_lft, root_rgt, root_type, gl)
        ))

    from frappe.desk.reportview import build_match_conditions
    query, params = query.walk()
    match_conditions = build_match_conditions("GL Entry")
    if match_conditions:
        query += f" AND {match_conditions}"

    gl_entries = frappe.db.sql(query, as_dict=True)

    if filters and filters.get("presentation_currency"):
        convert_to_presentation_currency(gl_entries, get_currency(filters))

    for entry in gl_entries:
        gl_entries_by_account.setdefault(entry.account, []).append(entry)


def get_data(
    company, root_type, balance_must_be, period_list,
    filters=None, accumulated_values=1, only_current_fiscal_year=True,
    ignore_closing_entries=False, ignore_accumulated_values_for_fy=False,
    total=True, accounting_method="Accrual",
):
    accounts = get_accounts(company, root_type)
    if not accounts:
        return None

    accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)

    gl_entries_by_account = {}
    for root in frappe.db.sql(
        "SELECT lft, rgt FROM tabAccount WHERE root_type=%s AND ifnull(parent_account,'')=''",
        root_type, as_dict=1,
    ):
        if accounting_method == "Cash":
            _set_gl_entries_cash(
                company,
                period_list[0]["year_start_date"] if only_current_fiscal_year else None,
                period_list[-1]["to_date"],
                filters, gl_entries_by_account,
                root.lft, root.rgt, root_type=root_type,
                ignore_closing_entries=ignore_closing_entries,
            )
        else:
            set_gl_entries_by_account(
                company,
                period_list[0]["year_start_date"] if only_current_fiscal_year else None,
                period_list[-1]["to_date"],
                filters, gl_entries_by_account,
                root.lft, root.rgt, root_type=root_type,
                ignore_closing_entries=ignore_closing_entries,
            )

    calculate_values(
        accounts_by_name, gl_entries_by_account, period_list,
        accumulated_values, ignore_accumulated_values_for_fy,
    )
    accumulate_values_into_parents(accounts, accounts_by_name, period_list)
    out = prepare_data(
        accounts, balance_must_be, period_list,
        get_appropriate_currency(company, filters),
        accumulated_values=filters.accumulated_values if filters else accumulated_values,
    )
    out = filter_out_zero_value_rows(
        out, parent_children_map,
        filters.show_zero_values if filters else False,
    )
    if out and total:
        add_total_row(out, root_type, balance_must_be, period_list,
                      get_appropriate_currency(company, filters))
    return out


def execute(filters=None):
    if filters and filters.report_template:
        return FinancialReportEngine().execute(filters)

    period_list = get_period_list(
        filters.from_fiscal_year, filters.to_fiscal_year,
        filters.period_start_date, filters.period_end_date,
        filters.filter_based_on, filters.periodicity,
        company=filters.company,
    )

    accounting_method = filters.get("accounting_method", "Accrual")

    income = get_data(
        filters.company, "Income", "Credit", period_list,
        filters=filters, accumulated_values=filters.accumulated_values,
        ignore_closing_entries=True, accounting_method=accounting_method,
    )
    expense = get_data(
        filters.company, "Expense", "Debit", period_list,
        filters=filters, accumulated_values=filters.accumulated_values,
        ignore_closing_entries=True, accounting_method=accounting_method,
    )

    net_profit_loss = get_net_profit_loss(
        income, expense, period_list, filters.company, filters.presentation_currency
    )

    data = []
    data.extend(income or [])
    data.extend(expense or [])
    if net_profit_loss:
        data.append(net_profit_loss)

    columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)
    currency = filters.presentation_currency or frappe.get_cached_value(
        "Company", filters.company, "default_currency"
    )
    chart = get_chart_data(filters, columns, income, expense, net_profit_loss, currency)
    report_summary, primitive_summary = get_report_summary(
        period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
    )

    if filters.get("selected_view") == "Growth":
        compute_growth_view_data(data, period_list)
    if filters.get("selected_view") == "Margin":
        compute_margin_view_data(data, period_list, filters.accumulated_values)

    return columns, data, None, chart, report_summary, primitive_summary


# ── kept identical to core ─────────────────────────────────────────────────

def get_report_summary(
    period_list, periodicity, income, expense, net_profit_loss, currency, filters, consolidated=False
):
    net_income, net_expense, net_profit = 0.0, 0.0, 0.0

    if filters.get("accumulated_in_group_company"):
        period_list = get_filtered_list_for_consolidated_report(filters, period_list)

    if filters.accumulated_values:
        key = period_list[-1].key
        if income:
            net_income = income[-2].get(key)
        if expense:
            net_expense = expense[-2].get(key)
        if net_profit_loss:
            net_profit = net_profit_loss.get(key)
    else:
        for period in period_list:
            key = period if consolidated else period.key
            if income:
                net_income += income[-2].get(key)
            if expense:
                net_expense += expense[-2].get(key)
            if net_profit_loss:
                net_profit += net_profit_loss.get(key)

    if len(period_list) == 1 and periodicity == "Yearly":
        profit_label = _("Profit This Year")
        income_label = _("Total Income This Year")
        expense_label = _("Total Expense This Year")
    else:
        profit_label = _("Net Profit")
        income_label = _("Total Income")
        expense_label = _("Total Expense")

    return [
        {"value": net_income, "label": income_label, "datatype": "Currency", "currency": currency},
        {"value": net_expense, "label": expense_label, "datatype": "Currency", "currency": currency},
        {
            "value": net_profit,
            "indicator": "Green" if net_profit > 0 else "Red",
            "label": profit_label,
            "datatype": "Currency",
            "currency": currency,
        },
    ], net_profit


def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False):
    total = 0
    net_profit_loss = {
        "account_name": "'" + _("Profit for the year") + "'",
        "account": "'" + _("Profit for the year") + "'",
        "warn_if_negative": True,
        "currency": currency or frappe.get_cached_value("Company", company, "default_currency"),
    }
    has_value = False
    for period in period_list:
        key = period if consolidated else period.key
        total_income = flt(income[-2][key], 3) if income else 0
        total_expense = flt(expense[-2][key], 3) if expense else 0
        net_profit_loss[key] = total_income - total_expense
        if net_profit_loss[key]:
            has_value = True
        total += flt(net_profit_loss[key])
        net_profit_loss["total"] = total
    if has_value:
        return net_profit_loss


def get_chart_data(filters, chart_columns, income, expense, net_profit_loss, currency):
    labels = [col.get("label") for col in chart_columns]
    income_data, expense_data, net_profit = [], [], []
    for col in chart_columns:
        key = col.get("key") or col.get("fieldname")
        if income:
            income_data.append(income[-2].get(key))
        if expense:
            expense_data.append(expense[-2].get(key))
        if net_profit_loss:
            net_profit.append(net_profit_loss.get(key))
    datasets = []
    if income_data:
        datasets.append({"name": _("Income"), "values": income_data})
    if expense_data:
        datasets.append({"name": _("Expense"), "values": expense_data})
    if net_profit:
        datasets.append({"name": _("Net Profit/Loss"), "values": net_profit})
    chart = {"data": {"labels": labels, "datasets": datasets}}
    if not filters.accumulated_values:
        chart["type"] = "bar"
    else:
        chart["type"] = "line"
    chart["fieldtype"] = "Currency"
    chart["options"] = "currency"
    chart["currency"] = currency
    return chart
