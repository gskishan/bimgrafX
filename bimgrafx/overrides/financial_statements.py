# Override for erpnext.accounts.report.financial_statements
# Adds Cash-basis accounting method support to P&L and other financial reports.

import frappe
from erpnext.accounts.report.financial_statements import (
  apply_additional_conditions as _original_apply_additional_conditions,
  get_accounting_entries as _original_get_accounting_entries,
  set_gl_entries_by_account as _original_set_gl_entries_by_account,
  get_data as _original_get_data,
)


def get_data(
  company,
  root_type,
  balance_must_be,
  period_list,
  filters=None,
  accumulated_values=1,
  only_current_fiscal_year=True,
  ignore_closing_entries=False,
  ignore_accumulated_values_for_fy=False,
  total=True,
  accounting_method="Accrual",
):
  """Wrapper that passes accounting_method into the GL query pipeline."""
  from frappe.utils import flt
  from erpnext.accounts.report.financial_statements import (
    get_accounts,
    filter_accounts,
    get_appropriate_currency,
    calculate_values,
    accumulate_values_into_parents,
    prepare_data,
    filter_out_zero_value_rows,
    add_total_row,
  )

  accounts = get_accounts(company, root_type)
  if not accounts:
    return None

  accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)

  gl_entries_by_account = {}
  for root in frappe.db.sql(
    """select lft, rgt from tabAccount
      where root_type=%s and ifnull(parent_account, '') = ''""",
    root_type,
    as_dict=1,
  ):
    set_gl_entries_by_account(
      company,
      period_list[0]["year_start_date"] if only_current_fiscal_year else None,
      period_list[-1]["to_date"],
      filters,
      gl_entries_by_account,
      root.lft,
      root.rgt,
      root_type=root_type,
      ignore_closing_entries=ignore_closing_entries,
      accounting_method=accounting_method,
    )

  calculate_values(
    accounts_by_name,
    gl_entries_by_account,
    period_list,
    accumulated_values,
    ignore_accumulated_values_for_fy,
  )
  accumulate_values_into_parents(accounts, accounts_by_name, period_list)
  out = prepare_data(
    accounts,
    balance_must_be,
    period_list,
    get_appropriate_currency(company, filters),
    accumulated_values=filters.accumulated_values if filters else accumulated_values,
  )
  out = filter_out_zero_value_rows(
    out, parent_children_map, filters.show_zero_values if filters else False
  )

  if out and total:
    add_total_row(out, root_type, balance_must_be, period_list, get_appropriate_currency(company, filters))

  return out


def set_gl_entries_by_account(
  company,
  from_date,
  to_date,
  filters,
  gl_entries_by_account,
  root_lft=None,
  root_rgt=None,
  root_type=None,
  ignore_closing_entries=False,
  ignore_opening_entries=False,
  group_by_account=False,
  accounting_method="Accrual",
):
  """Calls get_accounting_entries with accounting_method awareness."""
  from frappe.utils import add_days
  from erpnext.accounts.report.financial_statements import convert_to_presentation_currency, get_currency

  gl_entries = []

  ignore_closing_balances = frappe.db.get_single_value(
    "Accounts Settings", "ignore_account_closing_balance"
  )
  if not from_date and not ignore_closing_balances:
    last_period_closing_voucher = frappe.db.get_all(
      "Period Closing Voucher",
      filters={
        "docstatus": 1,
        "company": filters.company,
        "period_end_date": ("<", filters["period_start_date"]),
      },
      fields=["period_end_date", "name"],
      order_by="period_end_date desc",
      limit=1,
    )
    if last_period_closing_voucher:
      gl_entries += _original_get_accounting_entries(
        "Account Closing Balance",
        from_date,
        to_date,
        filters,
        root_lft,
        root_rgt,
        root_type,
        ignore_closing_entries,
        last_period_closing_voucher[0].name,
        group_by_account=group_by_account,
      )
      from_date = add_days(last_period_closing_voucher[0].period_end_date, 1)
      ignore_opening_entries = True

  gl_entries += get_accounting_entries(
    "GL Entry",
    from_date,
    to_date,
    filters,
    root_lft,
    root_rgt,
    root_type,
    ignore_closing_entries,
    ignore_opening_entries=ignore_opening_entries,
    group_by_account=group_by_account,
    accounting_method=accounting_method,
  )

  if filters and filters.get("presentation_currency"):
    convert_to_presentation_currency(gl_entries, get_currency(filters))

  for entry in gl_entries:
    gl_entries_by_account.setdefault(entry.account, []).append(entry)

  return gl_entries_by_account


def get_accounting_entries(
  doctype,
  from_date,
  to_date,
  filters,
  root_lft=None,
  root_rgt=None,
  root_type=None,
  ignore_closing_entries=None,
  period_closing_voucher=None,
  ignore_opening_entries=False,
  group_by_account=False,
  accounting_method="Accrual",
):
  """Delegates to original then applies Cash-basis voucher filter if needed."""
  from erpnext.accounts.report.financial_statements import (
    get_account_filter_query,
    apply_additional_conditions,
  )
  from pypika import functions as fn
  from frappe.query_builder.utils import DocType
  from frappe.query_builder.functions import Sum
  from frappe.query_builder import Criterion
  from frappe.utils.nestedset import ExistsCriterion

  # Use original for non-GL doctypes (Account Closing Balance)
  if doctype != "GL Entry":
    return _original_get_accounting_entries(
      doctype,
      from_date,
      to_date,
      filters,
      root_lft,
      root_rgt,
      root_type,
      ignore_closing_entries,
      period_closing_voucher,
      ignore_opening_entries,
      group_by_account,
    )

  gl_entry = frappe.qb.DocType(doctype)
  query = (
    frappe.qb.from_(gl_entry)
    .select(
      gl_entry.account,
      gl_entry.debit if not group_by_account else Sum(gl_entry.debit).as_("debit"),
      gl_entry.credit if not group_by_account else Sum(gl_entry.credit).as_("credit"),
      gl_entry.debit_in_account_currency
      if not group_by_account
      else Sum(gl_entry.debit_in_account_currency).as_("debit_in_account_currency"),
      gl_entry.credit_in_account_currency
      if not group_by_account
      else Sum(gl_entry.credit_in_account_currency).as_("credit_in_account_currency"),
      gl_entry.account_currency,
      gl_entry.posting_date,
      gl_entry.is_opening,
      gl_entry.fiscal_year,
    )
    .where(gl_entry.company == filters.company)
    .where(gl_entry.is_cancelled == 0)
    .where(gl_entry.posting_date <= to_date)
    .force_index("posting_date_company_index")
  )

  ignore_is_opening = frappe.db.get_single_value(
    "Accounts Settings", "ignore_is_opening_check_for_reporting"
  )
  if ignore_opening_entries and not ignore_is_opening:
    query = query.where(gl_entry.is_opening == "No")

  query = apply_additional_conditions(doctype, query, from_date, ignore_closing_entries, filters)

  # ── Cash-basis: only Payment Entry and Journal Entry vouchers ──
  if accounting_method == "Cash":
    query = query.where(
      gl_entry.voucher_type.isin(["Payment Entry", "Journal Entry"])
    )

  if (root_lft and root_rgt) or root_type:
    account_filter_query = get_account_filter_query(root_lft, root_rgt, root_type, gl_entry)
    query = query.where(ExistsCriterion(account_filter_query))

  from frappe.desk.reportview import build_match_conditions

  query, params = query.walk()
  match_conditions = build_match_conditions(doctype)

  if match_conditions:
    query += f" AND {match_conditions}"

  return frappe.db.sql(query, as_dict=True)
 
