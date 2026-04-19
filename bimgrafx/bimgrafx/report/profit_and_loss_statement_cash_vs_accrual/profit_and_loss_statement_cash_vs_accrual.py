import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
    compute_growth_view_data,
    compute_margin_view_data,
    get_columns,
    get_filtered_list_for_consolidated_report,
    get_period_list,
    get_accounts,
    filter_accounts,
    get_appropriate_currency,
    calculate_values,
    accumulate_values_into_parents,
    prepare_data,
    filter_out_zero_value_rows,
    add_total_row,
    set_gl_entries_by_account,
    convert_to_presentation_currency,
    get_currency,
)


# ─────────────────────────────────────────────────────────────────────────────
# CASH BASIS GL FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _set_gl_entries_cash(
    company,
    from_date,
    to_date,
    filters,
    gl_entries_by_account,
    root_lft,
    root_rgt,
    ignore_closing_entries=False,
):
    """
    TWO-STEP cash basis fetch:

    STEP 1 — Find every voucher_no that touched a Bank/Cash account.
             (Payment Entry, Journal Entry, Bank Transaction)

    STEP 2 — Pull the Income/Expense GL legs of those vouchers only.

    Why two steps?
    The old single-query approach filtered voucher_type on the Income/Expense
    GL rows directly. That works for most companies but fails when:
      • The company uses Journal Entries that debit/credit both sides
      • Account tree lft/rgt boundaries differ between companies
      • Payments exist but the income leg account falls outside the root range
    By first finding "which vouchers touched cash/bank" and then fetching
    their income/expense legs, we correctly capture all cash-basis activity.
    """

    # ── base params ───────────────────────────────────────────────────────────
    params = {
        "company": company,
        "to_date": to_date,
        "lft":     root_lft,
        "rgt":     root_rgt,
    }

    # ── date conditions ───────────────────────────────────────────────────────
    from_condition       = ""
    from_condition_cash  = ""
    if from_date:
        from_condition      = " AND gl.posting_date >= %(from_date)s"
        from_condition_cash = " AND gl_cash.posting_date >= %(from_date)s"
        params["from_date"] = from_date

    # ── closing entries ───────────────────────────────────────────────────────
    opening_condition = ""
    if ignore_closing_entries:
        opening_condition = " AND gl.voucher_type != 'Period Closing Voucher'"

    # ── finance book ──────────────────────────────────────────────────────────
    finance_book_condition = ""
    if filters.get("finance_book"):
        finance_book_condition = " AND gl.finance_book = %(finance_book)s"
        params["finance_book"] = filters["finance_book"]
    elif filters.get("include_default_book_entries"):
        finance_book_condition = (
            " AND (gl.finance_book IS NULL OR gl.finance_book = ''"
            "     OR gl.finance_book = (SELECT default_finance_book"
            "                           FROM `tabCompany`"
            "                           WHERE name = %(company)s))"
        )

    # ── cost centre ───────────────────────────────────────────────────────────
    cost_center_condition = ""
    if filters.get("cost_center"):
        cost_center_condition = " AND gl.cost_center = %(cost_center)s"
        params["cost_center"] = filters["cost_center"]

    # ── project ───────────────────────────────────────────────────────────────
    project_condition = ""
    if filters.get("project"):
        project_condition = " AND gl.project = %(project)s"
        params["project"] = filters["project"]

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1: Find all voucher_nos that touched a Bank or Cash account
    # ──────────────────────────────────────────────────────────────────────────
    cash_voucher_rows = frappe.db.sql(
        f"""
        SELECT DISTINCT gl_cash.voucher_no
        FROM `tabGL Entry` gl_cash
        INNER JOIN `tabAccount` cash_acc
            ON cash_acc.name = gl_cash.account
           AND cash_acc.account_type IN ('Bank', 'Cash')
        WHERE
            gl_cash.company      = %(company)s
            AND gl_cash.is_cancelled = 0
            AND gl_cash.posting_date <= %(to_date)s
            AND gl_cash.voucher_type IN (
                'Payment Entry',
                'Journal Entry',
                'Bank Transaction'
            )
            {from_condition_cash}
        """,
        params,
        as_dict=False,
    )

    cash_voucher_nos = [r[0] for r in cash_voucher_rows]

    if not cash_voucher_nos:
        # No cash/bank movements found — nothing to show in Cash mode
        return gl_entries_by_account

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2: Pull Income/Expense GL entries for those vouchers
    # ──────────────────────────────────────────────────────────────────────────
    voucher_placeholders = ", ".join(["%s"] * len(cash_voucher_nos))

    gl_entries = frappe.db.sql(
        f"""
        SELECT
            gl.account,
            gl.debit,
            gl.credit,
            gl.debit_in_account_currency,
            gl.credit_in_account_currency,
            gl.account_currency,
            gl.posting_date,
            gl.is_opening,
            gl.fiscal_year,
            gl.voucher_type,
            gl.voucher_no
        FROM `tabGL Entry` gl
        INNER JOIN `tabAccount` acc
            ON acc.name = gl.account
           AND acc.lft  >= %(lft)s
           AND acc.rgt  <= %(rgt)s
        WHERE
            gl.company      = %(company)s
            AND gl.is_cancelled = 0
            AND gl.posting_date <= %(to_date)s
            AND gl.voucher_no IN ({voucher_placeholders})
            {from_condition}
            {opening_condition}
            {finance_book_condition}
            {cost_center_condition}
            {project_condition}
        ORDER BY gl.posting_date
        """,
        list(params.values()) + cash_voucher_nos,
        as_dict=True,
    )

    # ── presentation currency conversion ─────────────────────────────────────
    if filters and filters.get("presentation_currency"):
        convert_to_presentation_currency(gl_entries, get_currency(filters))

    # ── populate the dict that calculate_values() expects ────────────────────
    for entry in gl_entries:
        gl_entries_by_account.setdefault(entry.account, []).append(entry)

    return gl_entries_by_account


# ─────────────────────────────────────────────────────────────────────────────
# CORE DATA LOGIC
# ─────────────────────────────────────────────────────────────────────────────

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
    accounts = get_accounts(company, root_type)
    if not accounts:
        return None

    accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)

    gl_entries_by_account = {}

    # ── fetch root account boundaries ────────────────────────────────────────
    roots = frappe.db.sql(
        """
        SELECT lft, rgt
        FROM   `tabAccount`
        WHERE  root_type = %s
          AND  IFNULL(parent_account, '') = ''
          AND  company = %s
        """,
        (root_type, company),
        as_dict=True,
    )

    if not roots:
        frappe.log_error(
            f"Cash P&L: No root accounts found for root_type={root_type}, company={company}",
            "Cash PnL Warning",
        )
        return None

    from_date = (
        period_list[0]["year_start_date"] if only_current_fiscal_year else None
    )
    to_date = period_list[-1]["to_date"]

    for root in roots:
        if accounting_method == "Cash":
            _set_gl_entries_cash(
                company,
                from_date,
                to_date,
                filters or frappe._dict(),
                gl_entries_by_account,
                root.lft,
                root.rgt,
                ignore_closing_entries=ignore_closing_entries,
            )
        else:
            # Standard accrual path — use ERPNext's built-in function
            set_gl_entries_by_account(
                company,
                from_date,
                to_date,
                filters,
                gl_entries_by_account,
                root.lft,
                root.rgt,
                root_type=root_type,
                ignore_closing_entries=ignore_closing_entries,
            )

    # ── standard calculations (same for both modes) ───────────────────────────
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
        accumulated_values=(
            filters.accumulated_values if filters else accumulated_values
        ),
    )

    out = filter_out_zero_value_rows(
        out,
        parent_children_map,
        filters.show_zero_values if filters else False,
    )

    if out and total:
        add_total_row(
            out,
            root_type,
            balance_must_be,
            period_list,
            get_appropriate_currency(company, filters),
        )

    return out


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTE
# ─────────────────────────────────────────────────────────────────────────────

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
        income,
        expense,
        period_list,
        filters.company,
        filters.presentation_currency,
    )

    data = []
    data.extend(income or [])
    data.extend(expense or [])
    if net_profit_loss:
        data.append(net_profit_loss)

    columns = get_columns(
        filters.periodicity,
        period_list,
        filters.accumulated_values,
        filters.company,
    )

    currency = filters.presentation_currency or frappe.get_cached_value(
        "Company", filters.company, "default_currency"
    )

    chart = get_chart_data(
        filters, columns, income, expense, net_profit_loss, currency
    )

    report_summary, primitive_summary = get_report_summary(
        period_list,
        filters.periodicity,
        income,
        expense,
        net_profit_loss,
        currency,
        filters,
    )

    if filters.get("selected_view") == "Growth":
        compute_growth_view_data(data, period_list)

    if filters.get("selected_view") == "Margin":
        compute_margin_view_data(data, period_list, filters.accumulated_values)

    return columns, data, None, chart, report_summary, primitive_summary


# ─────────────────────────────────────────────────────────────────────────────
# REPORT SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def get_report_summary(
    period_list,
    periodicity,
    income,
    expense,
    net_profit_loss,
    currency,
    filters,
    consolidated=False,
):
    net_income, net_expense, net_profit = 0.0, 0.0, 0.0

    if filters.get("accumulated_in_group_company"):
        period_list = get_filtered_list_for_consolidated_report(
            filters, period_list
        )

    if filters.accumulated_values:
        key = period_list[-1].key
        if income:
            net_income = income[-2].get(key) or 0.0
        if expense:
            net_expense = expense[-2].get(key) or 0.0
        if net_profit_loss:
            net_profit = net_profit_loss.get(key) or 0.0
    else:
        for period in period_list:
            key = period if consolidated else period.key
            if income:
                net_income  += income[-2].get(key)  or 0.0
            if expense:
                net_expense += expense[-2].get(key) or 0.0
            if net_profit_loss:
                net_profit  += net_profit_loss.get(key) or 0.0

    if len(period_list) == 1 and periodicity == "Yearly":
        profit_label  = _("Profit This Year")
        income_label  = _("Total Income This Year")
        expense_label = _("Total Expense This Year")
    else:
        profit_label  = _("Net Profit")
        income_label  = _("Total Income")
        expense_label = _("Total Expense")

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


# ─────────────────────────────────────────────────────────────────────────────
# NET PROFIT / LOSS
# ─────────────────────────────────────────────────────────────────────────────

def get_net_profit_loss(
    income, expense, period_list, company, currency=None, consolidated=False
):
    total = 0
    net_profit_loss = {
        "account_name":     "'" + _("Profit for the year") + "'",
        "account":          "'" + _("Profit for the year") + "'",
        "warn_if_negative": True,
        "currency":         currency
            or frappe.get_cached_value("Company", company, "default_currency"),
    }

    has_value = False

    for period in period_list:
        key           = period if consolidated else period.key
        total_income  = flt(income[-2][key],  3) if income  else 0
        total_expense = flt(expense[-2][key], 3) if expense else 0

        net_profit_loss[key] = total_income - total_expense

        if net_profit_loss[key]:
            has_value = True

        total += flt(net_profit_loss[key])
        net_profit_loss["total"] = total

    if has_value:
        return net_profit_loss


# ─────────────────────────────────────────────────────────────────────────────
# CHART
# ─────────────────────────────────────────────────────────────────────────────

def get_chart_data(
    filters, chart_columns, income, expense, net_profit_loss, currency
):
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
        datasets.append({"name": _("Income"),          "values": income_data})
    if expense_data:
        datasets.append({"name": _("Expense"),         "values": expense_data})
    if net_profit:
        datasets.append({"name": _("Net Profit/Loss"), "values": net_profit})

    chart             = {"data": {"labels": labels, "datasets": datasets}}
    chart["type"]     = "bar" if not filters.accumulated_values else "line"
    chart["fieldtype"]= "Currency"
    chart["options"]  = "currency"
    chart["currency"] = currency

    return chart
