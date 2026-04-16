# Override for erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
  compute_growth_view_data,
  compute_margin_view_data,
  get_columns,
  get_period_list,
)
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
  get_net_profit_loss,
  get_chart_data,
  get_report_summary,
)

# Use our override get_data that supports accounting_method
from helpdesk_overrides.overrides.financial_statements import get_data


def execute(filters=None):
  period_list = get_period_list(
    filters.from_fiscal_year,
    filters.to_fiscal_year,
    filters.period_start_date,
    filters.period_end_date,
    filters.filter_based_on,
    filters.periodicity,
    company=filters.company,
  )

  accounting_method = filters.get("accounting_method", "Accrual")

  income = get_data(
    filters.company,
    "Income",
    "Credit",
    period_list,
    filters=filters,
    accumulated_values=filters.accumulated_values,
    ignore_closing_entries=True,
    accounting_method=accounting_method,
  )

  expense = get_data(
    filters.company,
    "Expense",
    "Debit",
    period_list,
    filters=filters,
    accumulated_values=filters.accumulated_values,
    ignore_closing_entries=True,
    accounting_method=accounting_method,
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
 
