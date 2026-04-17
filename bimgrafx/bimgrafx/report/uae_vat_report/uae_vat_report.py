# Copyright (c) 2025, Your Company and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def validate_filters(filters):
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Please set From Date and To Date"))

    if getdate(filters.get("from_date")) > getdate(filters.get("to_date")):
        frappe.throw(_("From Date cannot be greater than To Date"))


def format_aed(value):
    """Format number as AED string — completely bypasses ERPNext currency symbol rendering."""
    val = flt(value)
    formatted = "{:,.2f}".format(abs(val))
    if val < 0:
        return "AED -{0}".format(formatted)
    return "AED {0}".format(formatted)


def get_columns():
    return [
        {
            "fieldname": "box",
            "label": _("Box"),
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "fieldname": "description",
            "label": _("Description"),
            "fieldtype": "Data",
            "width": 460,
        },
        {
            "fieldname": "total",
            "label": _("Total (AED)"),
            "fieldtype": "Data",    # KEY FIX: Data type — ERPNext cannot override with INR symbol
            "width": 200,
        },
    ]


def get_data(filters):
    company = filters.get("company")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # ------------------------------------------------------------------
    # Compute sales (output VAT) per emirate — Box 1a to 1g
    # ------------------------------------------------------------------

    def get_taxable_sales_by_emirate(emirate_keyword):
        result = frappe.db.sql(
            """
            SELECT SUM(sii.base_net_amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND stc.account_head LIKE %(keyword)s
              AND stc.charge_type != 'Actual'
            """,
            {
                "company": company,
                "from_date": from_date,
                "to_date": to_date,
                "keyword": f"%{emirate_keyword}%",
            },
        )
        return flt(result[0][0]) if result else 0.0

    def get_taxable_sales_generic():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND si.taxes_and_charges NOT LIKE '%%Zero%%'
              AND si.taxes_and_charges NOT LIKE '%%Exempt%%'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Output VAT (Box 6)
    # ------------------------------------------------------------------

    def get_total_output_vat():
        result = frappe.db.sql(
            """
            SELECT SUM(stc.base_tax_amount)
            FROM `tabSales Taxes and Charges` stc
            JOIN `tabSales Invoice` si ON si.name = stc.parent
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND stc.charge_type != 'Actual'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Reverse Charge Sales (Box 2)
    # ------------------------------------------------------------------

    def get_reverse_charge_sales():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND si.is_reverse_charge = 1
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Zero-rated supplies (Box 3)
    # ------------------------------------------------------------------

    def get_zero_rated_sales():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND si.taxes_and_charges LIKE '%%Zero%%'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        result2 = frappe.db.sql(
            """
            SELECT SUM(sii.base_net_amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND stc.rate = 0
              AND stc.charge_type != 'Actual'
              AND si.taxes_and_charges LIKE '%%Zero%%'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        val1 = flt(result[0][0]) if result else 0.0
        val2 = flt(result2[0][0]) if result2 else 0.0
        return val1 or val2

    # ------------------------------------------------------------------
    # Exempt supplies (Box 5)
    # ------------------------------------------------------------------

    def get_exempt_sales():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND si.taxes_and_charges LIKE '%%Exempt%%'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Supplies to registered customers outside UAE (Box 4)
    # ------------------------------------------------------------------

    def get_supplies_to_registered_customers():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND c.tax_id IS NOT NULL AND c.tax_id != ''
              AND si.customer_address NOT LIKE '%%UAE%%'
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Input VAT — Box 7 Standard rated expenses
    # ------------------------------------------------------------------

    def get_standard_rated_expenses():
        result = frappe.db.sql(
            """
            SELECT SUM(ptc.base_tax_amount)
            FROM `tabPurchase Taxes and Charges` ptc
            JOIN `tabPurchase Invoice` pi ON pi.name = ptc.parent
            WHERE pi.company = %(company)s
              AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND pi.docstatus = 1
              AND ptc.charge_type != 'Actual'
              AND ptc.rate > 0
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Reverse charge purchases (Box 8)
    # ------------------------------------------------------------------

    def get_reverse_charge_purchases():
        result = frappe.db.sql(
            """
            SELECT SUM(pi.base_net_total)
            FROM `tabPurchase Invoice` pi
            WHERE pi.company = %(company)s
              AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND pi.docstatus = 1
              AND pi.is_reverse_charge = 1
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Total input tax (Box 9)
    # ------------------------------------------------------------------

    def get_total_input_vat():
        standard_input = get_standard_rated_expenses()
        rc_purchases = get_reverse_charge_purchases()
        rc_vat = flt(rc_purchases * 0.05)
        return flt(standard_input + rc_vat)

    # ------------------------------------------------------------------
    # Net Sales (Box 11) and Purchases (Box 12)
    # ------------------------------------------------------------------

    def get_net_sales():
        result = frappe.db.sql(
            """
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    def get_net_purchases():
        result = frappe.db.sql(
            """
            SELECT SUM(pi.base_net_total)
            FROM `tabPurchase Invoice` pi
            WHERE pi.company = %(company)s
              AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND pi.docstatus = 1
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # GCC inter-state sales / purchases (Box 13 & 14)
    # ------------------------------------------------------------------

    def get_gcc_sales():
        gcc_countries = ("Bahrain", "Kuwait", "Oman", "Qatar", "Saudi Arabia")
        placeholders = ", ".join([frappe.db.escape(c) for c in gcc_countries])
        result = frappe.db.sql(
            f"""
            SELECT SUM(si.base_net_total)
            FROM `tabSales Invoice` si
            JOIN `tabAddress` addr ON addr.name = si.shipping_address_name
            WHERE si.company = %(company)s
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.docstatus = 1
              AND addr.country IN ({placeholders})
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    def get_gcc_purchases():
        gcc_countries = ("Bahrain", "Kuwait", "Oman", "Qatar", "Saudi Arabia")
        placeholders = ", ".join([frappe.db.escape(c) for c in gcc_countries])
        result = frappe.db.sql(
            f"""
            SELECT SUM(pi.base_net_total)
            FROM `tabPurchase Invoice` pi
            JOIN `tabAddress` addr ON addr.name = pi.supplier_address
            WHERE pi.company = %(company)s
              AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND pi.docstatus = 1
              AND addr.country IN ({placeholders})
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
        )
        return flt(result[0][0]) if result else 0.0

    # ------------------------------------------------------------------
    # Compute all box values
    # ------------------------------------------------------------------

    box1a = get_taxable_sales_by_emirate("Abu Dhabi")
    box1b = get_taxable_sales_by_emirate("Dubai")
    box1c = get_taxable_sales_by_emirate("Sharjah")
    box1d = get_taxable_sales_by_emirate("Ajman")
    box1e = get_taxable_sales_by_emirate("Umm Al Quwain")
    box1f = get_taxable_sales_by_emirate("Ras Al Khaimah")
    box1g = get_taxable_sales_by_emirate("Fujairah")

    total_emirate_sales = box1a + box1b + box1c + box1d + box1e + box1f + box1g
    if total_emirate_sales == 0:
        box1b = get_taxable_sales_generic()

    box2  = get_reverse_charge_sales()
    box3  = get_zero_rated_sales()
    box4  = get_supplies_to_registered_customers()
    box5  = get_exempt_sales()
    box6  = get_total_output_vat()
    box7  = get_standard_rated_expenses()
    box8  = get_reverse_charge_purchases()
    box9  = get_total_input_vat()
    box10 = flt(box6 - box9)
    box11 = get_net_sales()
    box12 = get_net_purchases()
    box13 = get_gcc_sales()
    box14 = get_gcc_purchases()

    # ------------------------------------------------------------------
    # Build rows — always show AED 0.00 for zero values (never blank)
    # ------------------------------------------------------------------

    def row(box_no, description, amount, bold=False):
        return {
            "box": box_no,
            "description": description,
            "total": format_aed(amount),  # Always renders AED x,xxx.xx — never blank
            "bold": 1 if bold else 0,
        }

    data = [
        row("1a", _("Standard rated supplies in Abu Dhabi"),                               box1a),
        row("1b", _("Standard rated supplies in Dubai"),                                   box1b),
        row("1c", _("Standard rated supplies in Sharjah"),                                 box1c),
        row("1d", _("Standard rated supplies in Ajman"),                                   box1d),
        row("1e", _("Standard rated supplies in Umm Al Quwain"),                           box1e),
        row("1f", _("Standard rated supplies in Ras Al Khaimah"),                          box1f),
        row("1g", _("Standard rated supplies in Fujairah"),                                box1g),
        row("2",  _("Supplies subject to the reverse charge provisions"),                  box2),
        row("3",  _("Zero rated supplies"),                                                box3),
        row("4",  _("Supplies of goods and services to registered customers outside UAE"), box4),
        row("5",  _("Exempt supplies"),                                                    box5),
        row("6",  _("TOTAL OUTPUT TAX DUE"),                                               box6,  bold=True),
        row("7",  _("Standard rated expenses"),                                            box7),
        row("8",  _("Supplies subject to the reverse charge provisions"),                  box8),
        row("9",  _("TOTAL INPUT TAX"),                                                    box9,  bold=True),
        row("10", _("NET VAT TO PAY (OR RECLAIM)"),                                        box10, bold=True),
        row("11", _("Net value of sales"),                                                 box11),
        row("12", _("Net value of purchases"),                                             box12),
        row("13", _("Net value of sales to other GCC Member States"),                      box13),
        row("14", _("Net value of purchases from other GCC Member States"),                box14),
    ]

    return data
