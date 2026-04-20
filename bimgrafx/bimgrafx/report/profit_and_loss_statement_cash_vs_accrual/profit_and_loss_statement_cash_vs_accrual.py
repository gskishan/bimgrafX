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
    CASH BASIS: Income/Expense is recognised on the date cash actually moves.

    KEY FIX — Cross-year payments:
    ───────────────────────────────
    Invoice raised 2022, Payment received 2023.

    Old bug: fetched invoice GL rows and filtered by posting_date >= from_date.
             Invoice GL row has posting_date = 2022. So when filtering for 2023,
             the row is excluded → income shows as ZERO in 2023. WRONG.

    Correct: For invoice-linked GL entries, REPLACE posting_date with the
             Payment Entry's posting_date (2023). This way the income appears
             in the period when cash was actually received, not when billed.

    How it works:
    ─────────────
    Step 1a — Find Payment Entry / Journal Entry vouchers that touched Bank/Cash
              within the requested date range.
    Step 1b — From those Payment Entries, find linked invoices via
              Payment Entry Reference table. Also record the payment_date
              for each invoice so we can stamp it onto the GL rows.
    Step 1c — Combine all voucher_nos (payments + invoices).
    Step 2  — Fetch Income/Expense GL entries for all vouchers WITHOUT
              the from_date filter (we need old invoice rows too).
    Step 3  — For each GL row that belongs to an invoice voucher,
              override posting_date → payment_date before returning.
              Then filter by date in Python after the override.

    Uses ONLY %s positional params — no %(key)s dict style.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1a — Find vouchers that touched Bank/Cash in the date range
    # ─────────────────────────────────────────────────────────────────────────
    step1_values = [company, to_date]
    from_cond_step1 = ""
    if from_date:
        from_cond_step1 = " AND gl_cash.posting_date >= %s"
        step1_values.append(from_date)

    cash_rows = frappe.db.sql(
        f"""
        SELECT DISTINCT
            gl_cash.voucher_no,
            gl_cash.voucher_type,
            gl_cash.posting_date AS payment_date
        FROM `tabGL Entry` gl_cash
        INNER JOIN `tabAccount` cash_acc
            ON  cash_acc.name         = gl_cash.account
            AND cash_acc.account_type IN ('Bank', 'Cash')
        WHERE
            gl_cash.company         = %s
            AND gl_cash.is_cancelled = 0
            AND gl_cash.posting_date <= %s
            AND gl_cash.voucher_type IN (
                'Payment Entry',
                'Journal Entry',
                'Bank Transaction'
            )
            {from_cond_step1}
        """,
        step1_values,
        as_dict=True,
    )

    if not cash_rows:
        return gl_entries_by_account

    # Map: voucher_no → payment_date (for direct JE/Payment vouchers)
    payment_date_map = {r.voucher_no: r.payment_date for r in cash_rows}

    cash_voucher_nos  = list(payment_date_map.keys())
    payment_entry_nos = [r.voucher_no for r in cash_rows if r.voucher_type == "Payment Entry"]

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1b — Find invoices settled by those Payment Entries
    #           Record invoice_name → payment_date mapping
    # ─────────────────────────────────────────────────────────────────────────
    # invoice_payment_date_map: invoice voucher_no → payment_date
    invoice_payment_date_map = {}

    if payment_entry_nos:
        pe_placeholders = ", ".join(["%s"] * len(payment_entry_nos))
        invoice_rows = frappe.db.sql(
            f"""
            SELECT
                per.reference_name  AS invoice_no,
                per.parent          AS payment_entry_no
            FROM `tabPayment Entry Reference` per
            WHERE per.parent IN ({pe_placeholders})
              AND per.reference_doctype IN (
                  'Sales Invoice',
                  'Purchase Invoice',
                  'Journal Entry'
              )
            """,
            payment_entry_nos,
            as_dict=True,
        )
        for row in invoice_rows:
            # Use the payment entry's date for this invoice
            pay_date = payment_date_map.get(row.payment_entry_no)
            if pay_date:
                # If same invoice paid by multiple payments, use latest payment date
                existing = invoice_payment_date_map.get(row.invoice_no)
                if not existing or pay_date > existing:
                    invoice_payment_date_map[row.invoice_no] = pay_date

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1c — Combine: cash vouchers + their linked invoices
    # ─────────────────────────────────────────────────────────────────────────
    all_voucher_nos = list(set(cash_voucher_nos + list(invoice_payment_date_map.keys())))

    if not all_voucher_nos:
        return gl_entries_by_account

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2 — Fetch Income/Expense GL entries for ALL vouchers
    #          NOTE: No from_date filter here — we need 2022 invoice rows too.
    #          We will apply date filtering in Python after overriding dates.
    # ─────────────────────────────────────────────────────────────────────────
    voucher_placeholders = ", ".join(["%s"] * len(all_voucher_nos))

    # positional values: lft, rgt, company, to_date, then voucher_nos
    step2_values = [root_lft, root_rgt, company, to_date]
    step2_values.extend(all_voucher_nos)

    opening_condition = ""
    finance_book_cond = ""
    cost_center_cond  = ""
    project_cond      = ""

    if ignore_closing_entries:
        opening_condition = " AND gl.voucher_type != 'Period Closing Voucher'"

    if filters.get("finance_book"):
        finance_book_cond = " AND gl.finance_book = %s"
        step2_values.append(filters["finance_book"])
    elif filters.get("include_default_book_entries"):
        finance_book_cond = (
            " AND (gl.finance_book IS NULL OR gl.finance_book = ''"
            "     OR gl.finance_book = ("
            "         SELECT default_finance_book FROM `tabCompany` WHERE name = %s"
            "     ))"
        )
        step2_values.append(company)

    if filters.get("cost_center"):
        cost_center_cond = " AND gl.cost_center = %s"
        step2_values.append(filters["cost_center"])

    if filters.get("project"):
        project_cond = " AND gl.project = %s"
        step2_values.append(filters["project"])

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
            ON  acc.name = gl.account
            AND acc.lft  >= %s
            AND acc.rgt  <= %s
        WHERE
            gl.company         = %s
            AND gl.is_cancelled = 0
            AND gl.posting_date <= %s
            AND gl.voucher_no IN ({voucher_placeholders})
            {opening_condition}
            {finance_book_cond}
            {cost_center_cond}
            {project_cond}
        ORDER BY gl.posting_date
        """,
        step2_values,
        as_dict=True,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3 — Override posting_date for invoice GL rows → use payment_date
    #          Then apply from_date filter in Python after the override
    # ─────────────────────────────────────────────────────────────────────────
    filtered_entries = []
    for entry in gl_entries:
        # If this GL row belongs to an invoice that was paid, override its date
        if entry.voucher_no in invoice_payment_date_map:
            entry.posting_date = invoice_payment_date_map[entry.voucher_no]

        # Now apply the from_date filter (after date override)
        if from_date and entry.posting_date < from_date:
            continue

        filtered_entries.append(entry)

    # ── presentation currency conversion ─────────────────────────────────────
    if filters and filters.get("presentation_currency"):
        convert_to_presentation_currency(filtered_entries, get_currency(filters))

    # ── populate the dict that calculate_values() expects ────────────────────
    for entry in filtered_entries:
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

    # ── fetch root account boundaries ─────────────────────────────────────────
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
