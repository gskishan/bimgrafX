# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    return EmployeeHoursReport(filters).run()


def minutes_to_hhmm(total_minutes):
    """Convert total minutes (int/float) to H:MM string format"""
    total_minutes = int(round(flt(total_minutes)))
    hours = total_minutes // 60
    mins = total_minutes % 60
    return f"{hours}:{str(mins).zfill(2)}"


def hours_to_hhmm(hours_float):
    """Convert float hours to H:MM string format"""
    total_minutes = round(flt(hours_float) * 60)
    return minutes_to_hhmm(total_minutes)


class EmployeeHoursReport:
    """Employee Hours Utilization Report Based On Timesheet"""

    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})

        self.from_date = getdate(self.filters.from_date)
        self.to_date = getdate(self.filters.to_date)

        self.validate_dates()
        self.validate_standard_working_hours()

    def validate_dates(self):
        self.day_span = (self.to_date - self.from_date).days

        if self.day_span <= 0:
            frappe.throw(_("From Date must come before To Date"))

    def validate_standard_working_hours(self):
        self.standard_working_hours = frappe.db.get_single_value("HR Settings", "standard_working_hours")
        if not self.standard_working_hours:
            msg = _("The metrics for this report are calculated based on {0}. Please set {0} in {1}.").format(
                frappe.bold(_("Standard Working Hours")),
                frappe.utils.get_link_to_form("HR Settings", "HR Settings"),
            )
            frappe.throw(msg)

    def run(self):
        self.generate_columns()
        self.generate_data()
        self.generate_report_summary()
        self.generate_chart_data()

        return self.columns, self.data, None, self.chart, self.report_summary

    def generate_columns(self):
        self.columns = [
            {
                "label": _("Employee"),
                "options": "Employee",
                "fieldname": "employee",
                "fieldtype": "Link",
                "width": 230,
            },
            {
                "label": _("Department"),
                "options": "Department",
                "fieldname": "department",
                "fieldtype": "Link",
                "width": 120,
            },
            # ✅ Changed from Float to Data for H:MM format
            {
                "label": _("Total Hours (T)"),
                "fieldname": "total_hours",
                "fieldtype": "Data",
                "width": 130,
            },
            {
                "label": _("Billed Hours (B)"),
                "fieldname": "billed_hours",
                "fieldtype": "Data",
                "width": 150,
            },
            {
                "label": _("Non-Billed Hours (NB)"),
                "fieldname": "non_billed_hours",
                "fieldtype": "Data",
                "width": 170,
            },
            {
                "label": _("Untracked Hours (U)"),
                "fieldname": "untracked_hours",
                "fieldtype": "Data",
                "width": 170,
            },
            {
                "label": _("% Utilization (B + NB) / T"),
                "fieldname": "per_util",
                "fieldtype": "Percentage",
                "width": 200,
            },
            {
                "label": _("% Utilization (B / T)"),
                "fieldname": "per_util_billed_only",
                "fieldtype": "Percentage",
                "width": 200,
            },
        ]

    def generate_data(self):
        self.generate_filtered_time_logs()
        self.generate_stats_by_employee()
        self.set_employee_department_and_name()

        if self.filters.department:
            self.filter_stats_by_department()

        self.calculate_utilizations()

        self.data = []

        for emp, data in self.stats_by_employee.items():
            row = frappe._dict()
            row["employee"] = emp
            row.update(data)
            self.data.append(row)

        # Sort by descending order of percentage utilization
        self.data.sort(key=lambda x: x["per_util"], reverse=True)

    def filter_stats_by_department(self):
        filtered_data = frappe._dict()
        for emp, data in self.stats_by_employee.items():
            if data["department"] == self.filters.department:
                filtered_data[emp] = data

        self.stats_by_employee = filtered_data

    def generate_filtered_time_logs(self):
        additional_filters = ""

        filter_fields = ["employee", "project", "company"]

        for field in filter_fields:
            if self.filters.get(field):
                if field == "project":
                    additional_filters += f" AND ttd.{field} = {self.filters.get(field)!r}"
                else:
                    additional_filters += f" AND tt.{field} = {self.filters.get(field)!r}"

        # ✅ Use TIMESTAMPDIFF to get exact minutes from from_time/to_time
        # instead of relying on the float `hours` field
        self.filtered_time_logs = frappe.db.sql(
            f"""
            SELECT
                tt.employee AS employee,
                TIMESTAMPDIFF(MINUTE, ttd.from_time, ttd.to_time) AS minutes,
                ttd.is_billable AS is_billable,
                ttd.project AS project
            FROM `tabTimesheet Detail` AS ttd
            JOIN `tabTimesheet` AS tt
                ON ttd.parent = tt.name
            WHERE tt.employee IS NOT NULL
            AND tt.start_date BETWEEN '{self.filters.from_date}' AND '{self.filters.to_date}'
            AND tt.end_date BETWEEN '{self.filters.from_date}' AND '{self.filters.to_date}'
            AND ttd.from_time IS NOT NULL
            AND ttd.to_time IS NOT NULL
            AND ttd.to_time > ttd.from_time
            {additional_filters}
            """
        )

    def generate_stats_by_employee(self):
        self.stats_by_employee = frappe._dict()

        # ✅ Now using minutes instead of float hours
        for emp, minutes, is_billable, __ in self.filtered_time_logs:
            self.stats_by_employee.setdefault(emp, frappe._dict()).setdefault("billed_minutes", 0)
            self.stats_by_employee[emp].setdefault("non_billed_minutes", 0)

            if is_billable:
                self.stats_by_employee[emp]["billed_minutes"] += int(minutes or 0)
            else:
                self.stats_by_employee[emp]["non_billed_minutes"] += int(minutes or 0)

    def set_employee_department_and_name(self):
        for emp in self.stats_by_employee:
            emp_name = frappe.db.get_value("Employee", emp, "employee_name")
            emp_dept = frappe.db.get_value("Employee", emp, "department")

            self.stats_by_employee[emp]["department"] = emp_dept
            self.stats_by_employee[emp]["employee_name"] = emp_name

    def calculate_utilizations(self):
        # ✅ Total hours in minutes
        TOTAL_MINUTES = int(self.standard_working_hours * self.day_span * 60)
        TOTAL_HOURS_FLOAT = flt(self.standard_working_hours * self.day_span, 2)

        for __, data in self.stats_by_employee.items():
            billed_min = data.get("billed_minutes", 0)
            non_billed_min = data.get("non_billed_minutes", 0)
            tracked_min = billed_min + non_billed_min
            untracked_min = max(TOTAL_MINUTES - tracked_min, 0)  # no negative

            # ✅ Store H:MM formatted strings for display
            data["total_hours"] = hours_to_hhmm(TOTAL_HOURS_FLOAT)
            data["billed_hours"] = minutes_to_hhmm(billed_min)
            data["non_billed_hours"] = minutes_to_hhmm(non_billed_min)
            data["untracked_hours"] = minutes_to_hhmm(untracked_min)

            # ✅ Keep float values separately for utilization % calculation
            data["billed_hours_float"] = flt(billed_min / 60, 2)
            data["non_billed_hours_float"] = flt(non_billed_min / 60, 2)

            data["per_util"] = flt((tracked_min / TOTAL_MINUTES) * 100, 2) if TOTAL_MINUTES else 0.0
            data["per_util_billed_only"] = flt((billed_min / TOTAL_MINUTES) * 100, 2) if TOTAL_MINUTES else 0.0

    def generate_report_summary(self):
        self.report_summary = []

        if not self.data:
            return

        avg_utilization = 0.0
        avg_utilization_billed_only = 0.0
        total_billed_min = 0
        total_non_billed_min = 0

        for row in self.data:
            avg_utilization += row["per_util"]
            avg_utilization_billed_only += row["per_util_billed_only"]
            # ✅ Use float values for summary calculations
            total_billed_min += int(round(row.get("billed_hours_float", 0) * 60))
            total_non_billed_min += int(round(row.get("non_billed_hours_float", 0) * 60))

        avg_utilization /= len(self.data)
        avg_utilization = flt(avg_utilization, 2)

        avg_utilization_billed_only /= len(self.data)
        avg_utilization_billed_only = flt(avg_utilization_billed_only, 2)

        THRESHOLD_PERCENTAGE = 70.0

        self.report_summary = [
            {
                "value": f"{avg_utilization}%",
                "indicator": "Red" if avg_utilization < THRESHOLD_PERCENTAGE else "Green",
                "label": _("Avg Utilization"),
                "datatype": "Percentage",
            },
            {
                "value": f"{avg_utilization_billed_only}%",
                "indicator": "Red" if avg_utilization_billed_only < THRESHOLD_PERCENTAGE else "Green",
                "label": _("Avg Utilization (Billed Only)"),
                "datatype": "Percentage",
            },
            # ✅ Show H:MM format in summary cards too
            {
                "value": minutes_to_hhmm(total_billed_min),
                "label": _("Total Billed Hours"),
                "datatype": "Data",
            },
            {
                "value": minutes_to_hhmm(total_non_billed_min),
                "label": _("Total Non-Billed Hours"),
                "datatype": "Data",
            },
        ]

    def generate_chart_data(self):
        self.chart = {}

        labels = []
        billed_hours = []
        non_billed_hours = []
        untracked_hours = []

        for row in self.data:
            labels.append(row.get("employee_name"))
            # ✅ Chart still uses float values for rendering bars correctly
            billed_hours.append(row.get("billed_hours_float", 0))
            non_billed_hours.append(row.get("non_billed_hours_float", 0))
            untracked_hours.append(
                flt(
                    (row.get("non_billed_hours_float", 0) + row.get("billed_hours_float", 0)),
                    2
                )
            )

        self.chart = {
            "data": {
                "labels": labels[:30],
                "datasets": [
                    {"name": _("Billed Hours"), "values": billed_hours[:30]},
                    {"name": _("Non-Billed Hours"), "values": non_billed_hours[:30]},
                    {"name": _("Untracked Hours"), "values": untracked_hours[:30]},
                ],
            },
            "type": "bar",
            "barOptions": {"stacked": True},
        }
