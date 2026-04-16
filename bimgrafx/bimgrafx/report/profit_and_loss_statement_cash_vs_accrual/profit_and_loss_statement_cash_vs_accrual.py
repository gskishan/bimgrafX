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
    get_data,
    get_filtered_list_for_consolidated_report,
    get_period_list,
)


def execute(filters=None):
    # ── Always ensure filters is a safe dict, never None ─────────────────────
    filters = frappe._dict(filters or {})

    if filters.get("report_template"):
        return FinancialReportEngine().execute(filters)

    # ── Inject cash-basis GL filter when accounting_method = "Cash" ──────────
    if filters.get("accounting_method") == "Cash":
        filters = _apply_cash_basis_filter(filters)

    period_list = get_period_list(
        filters.from_fiscal_year,
        filters.to_fiscal_year,
        filters.period_start_date,
        filters.period_end_date,
        filters.filter_based_on,
        filters.periodicity,
        company=filters.company,
    )

    income = get_data(
        filters.company,
        "Income",
        "Credit",
        period_list,
        filters=filters,
        accumulated_values=filters.accumulated_values,
        ignore_closing_entries=True,
    )

    expense = get_data(
        filters.company,
        "Expense",
        "Debit",
        period_list,
        filters=filters,
        accumulated_values=filters.accumulated_values,
        ignore_closing_entries=True,
    )

    net_profit_loss = get_net_profit_loss(
        income, expense, period_list, filters.company, filters.presentation_currency
    )

    data = []
    data.extend(income or [])
    data.extend(expense or [])
    if net_profit_loss:
        data.append(net_profit_loss)

    columns = get_columns(
        filters.periodicity, period_list, filters.accumulated_values, filters.company
    )

    currency = filters.presentation_currency or frappe.get_cached_value(
        "Company", filters.company, "default_currency"
    )

    # ── Fix: pass `columns` (not `period_list`) to get_chart_data ────────────
    chart = get_chart_data(filters, columns, income, expense, net_profit_loss, currency)

    report_summary, primitive_summary = get_report_summary(
        period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
    )

    if filters.get("selected_view") == "Growth":
        compute_growth_view_data(data, period_list)

    if filters.get("selected_view") == "Margin":
        compute_margin_view_data(data, period_list, filters.accumulated_values)

    return columns, data, None, chart, report_summary, primitive_summary


# ---------------------------------------------------------------------------
# Cash Basis Filter
# ---------------------------------------------------------------------------

def _apply_cash_basis_filter(filters):
    """
    For Cash basis reporting we only want GL Entries that arise from
    actual payment vouchers (Payment Entry / Journal Entry against a
    payment), NOT from Sales/Purchase Invoice posting.

    Strategy
    --------
    Build a list of voucher_no values that represent cash movements
    (Payment Entries + Journal Entries that settle invoices) and pass
    them to the standard get_data pipeline via a custom filter key
    `cash_basis_vouchers`.

    Override filters.accounting_method flag and add the paid-voucher
    list into filters so downstream _get_account_balances can skip
    invoice-sourced GL entries.
    """
    filters = frappe._dict(filters)

    conditions = ""
    params = {"company": filters.company}

    if filters.get("period_start_date"):
        conditions += " AND posting_date >= %(period_start_date)s"
        params["period_start_date"] = filters.period_start_date
    if filters.get("period_end_date"):
        conditions += " AND posting_date <= %(period_end_date)s"
        params["period_end_date"] = filters.period_end_date

    # Payment Entry vouchers
    payment_vouchers = frappe.db.sql_list(
        f"""
        SELECT name FROM `tabPayment Entry`
        WHERE docstatus = 1
          AND company = %(company)s
          {conditions}
        """,
        params,
    )

    # Journal Entries that clear invoices (have a reference to SI/PI)
    je_vouchers = frappe.db.sql_list(
        f"""
        SELECT DISTINCT je.name
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        WHERE je.docstatus = 1
          AND je.company = %(company)s
          AND jea.reference_type IN ('Sales Invoice', 'Purchase Invoice')
          {conditions}
        """,
        params,
    )

    cash_vouchers = list(set(payment_vouchers + je_vouchers))

    filters["cash_basis_vouchers"] = cash_vouchers
    filters["use_cash_basis"] = True

    return filters


def _get_cash_basis_gl_entries(filters, account_list, period_list):
    """
    Returns GL entries restricted to cash payment vouchers only.
    Used when accounting_method == 'Cash'.
    """
    vouchers = filters.get("cash_basis_vouchers") or []
    if not vouchers:
        return []

    voucher_placeholders = ", ".join(["%s"] * len(vouchers))

    conditions = f"gl.voucher_no IN ({voucher_placeholders})"
    params = vouchers[:]

    if account_list:
        acc_placeholders = ", ".join(["%s"] * len(account_list))
        conditions += f" AND gl.account IN ({acc_placeholders})"
        params += account_list

    if filters.get("company"):
        conditions += " AND gl.company = %s"
        params.append(filters.company)

    return frappe.db.sql(
        f"""
        SELECT
            gl.account,
            gl.debit,
            gl.credit,
            gl.posting_date,
            gl.voucher_no,
            gl.voucher_type
        FROM `tabGL Entry` gl
        WHERE gl.docstatus = 1
          AND gl.is_cancelled = 0
          AND {conditions}
        ORDER BY gl.posting_date
        """,
        params,
        as_dict=True,
    )


# ---------------------------------------------------------------------------
# Report Summary
# ---------------------------------------------------------------------------

def get_report_summary(
    period_list, periodicity, income, expense, net_profit_loss, currency, filters, consolidated=False
):
    net_income, net_expense, net_profit = 0.0, 0.0, 0.0

    # Ensure filters is always a safe dict
    filters = frappe._dict(filters or {})

    if filters.get("accumulated_in_group_company"):
        period_list = get_filtered_list_for_consolidated_report(filters, period_list)

    if filters.get("accumulated_values"):
        key = period_list[-1].key
        if income:
            net_income = flt(income[-2].get(key), 3)
        if expense:
            net_expense = flt(expense[-2].get(key), 3)
        if net_profit_loss:
            net_profit = flt(net_profit_loss.get(key), 3)
    else:
        for period in period_list:
            key = period if consolidated else period.key
            if income:
                net_income += flt(income[-2].get(key), 3)
            if expense:
                net_expense += flt(expense[-2].get(key), 3)
            if net_profit_loss:
                net_profit += flt(net_profit_loss.get(key), 3)

    if len(period_list) == 1 and periodicity == "Yearly":
        profit_label  = _("Profit This Year")
        income_label  = _("Total Income This Year")
        expense_label = _("Total Expense This Year")
    else:
        profit_label  = _("Net Profit")
        income_label  = _("Total Income")
        expense_label = _("Total Expense")

    # Append Cash/Accrual badge to summary labels
    method = filters.get("accounting_method", "Accrual")
    suffix = _(" (Cash Basis)") if method == "Cash" else _(" (Accrual Basis)")
    income_label  += suffix
    expense_label += suffix
    profit_label  += suffix

    return [
        {
            "value":    net_income,
            "label":    income_label,
            "datatype": "Currency",
            "currency": currency,
        },
        {
            "value":    net_expense,
            "label":    expense_label,
            "datatype": "Currency",
            "currency": currency,
        },
        {
            "value":     net_profit,
            "indicator": "Green" if net_profit > 0 else "Red",
            "label":     profit_label,
            "datatype":  "Currency",
            "currency":  currency,
        },
    ], net_profit


# ---------------------------------------------------------------------------
# Net Profit / Loss
# ---------------------------------------------------------------------------

def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False):
    total = 0
    net_profit_loss = {
        "account_name":     "'" + _("Profit for the year") + "'",
        "account":          "'" + _("Profit for the year") + "'",
        "warn_if_negative": True,
        "currency":         currency or frappe.get_cached_value("Company", company, "default_currency"),
    }

    has_value = False

    for period in period_list:
        key           = period if consolidated else period.key
        total_income  = flt(income[-2][key],  3) if income  else 0.0
        total_expense = flt(expense[-2][key], 3) if expense else 0.0

        net_profit_loss[key] = flt(total_income - total_expense, 3)

        if net_profit_loss[key]:
            has_value = True

        total += net_profit_loss[key]
        net_profit_loss["total"] = flt(total, 3)

    if has_value:
        return net_profit_loss


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def get_chart_data(filters, columns, income, expense, net_profit_loss, currency):
    # `columns` is the list returned by get_columns() — each has 'label' and 'fieldname'
    labels         = []
    income_data    = []
    expense_data   = []
    net_profit     = []

    for col in columns:
        # period columns carry a 'key' added by get_columns(); fall back to fieldname
        key = col.get("key") or col.get("fieldname")
        if not key:
            continue

        labels.append(col.get("label"))

        if income:
            income_data.append(flt(income[-2].get(key), 3))
        if expense:
            expense_data.append(flt(expense[-2].get(key), 3))
        if net_profit_loss:
            net_profit.append(flt(net_profit_loss.get(key), 3))

    datasets = []
    if income_data:
        datasets.append({"name": _("Income"),        "values": income_data})
    if expense_data:
        datasets.append({"name": _("Expense"),       "values": expense_data})
    if net_profit:
        datasets.append({"name": _("Net Profit/Loss"), "values": net_profit})

    if not datasets:
        return {}

    chart = {"data": {"labels": labels, "datasets": datasets}}

    # Ensure filters is safe
    filters = frappe._dict(filters or {})

    chart["type"]      = "line" if filters.get("accumulated_values") else "bar"
    chart["fieldtype"] = "Currency"
    chart["options"]   = "currency"
    chart["currency"]  = currency

    # Tag chart title with accounting basis
    method        = filters.get("accounting_method", "Accrual")
    chart["title"] = _("Profit and Loss — {0} Basis").format(method)

    return chart
