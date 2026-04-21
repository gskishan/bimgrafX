# Copyright (c) 2025, BIM and Grafx Engineering Architectural Services
# For license information, please see license.txt

import frappe
from frappe import _
from hrms.hr.doctype.employee_separation.employee_separation import EmployeeSeparation as _EmployeeSeparation


class EmployeeSeparation(_EmployeeSeparation):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from frappe.types import DF
        from hrms.hr.doctype.employee_boarding_activity.employee_boarding_activity import (
            EmployeeBoardingActivity,
        )
        activities: DF.Table[EmployeeBoardingActivity]
        amended_from: DF.Link | None
        boarding_begins_on: DF.Date
        boarding_status: DF.Literal["Pending", "In Process", "Completed"]
        company: DF.Link
        department: DF.Link | None
        designation: DF.Link | None
        employee: DF.Link
        employee_grade: DF.Link | None
        employee_name: DF.Data | None
        employee_separation_template: DF.Link | None
        exit_interview: DF.TextEditor | None
        notify_users_by_email: DF.Check
        project: DF.Link | None
        resignation_letter_date: DF.Date | None
    # end: auto-generated types

    def validate(self):
        super().validate()

    def on_submit(self):
        """
        The HRMS parent on_submit() → EmployeeBoardingController.on_submit()
        tries to insert a Project using naming series that requires `project_code`.
        Fix: pre-create the Project with a generated project_code and set self.project
        BEFORE calling super() so the parent skips its own project creation entirely.
        """
        if not self.project:
            self._create_separation_project()

        super().on_submit()

    def on_update_after_submit(self):
        self.create_task_and_notify_user()

    def on_cancel(self):
        super().on_cancel()

    # ─────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _create_separation_project(self):
        """
        Create a Project for this Employee Separation and link it back to self.project
        so the parent on_submit() detects it is already set and skips creation.
        """
        project_name = "{0} : {1}".format(_("Employee Separation"), self.employee)
        project_code = "PRJ-SEP-{0}".format(frappe.generate_hash(length=8).upper())

        project = frappe.get_doc({
            "doctype":             "Project",
            "project_name":        project_name,
            "project_code":        project_code,
            "expected_start_date": self.resignation_letter_date or self.boarding_begins_on,
            "department":          self.department,
            "company":             self.company,
        }).insert(ignore_permissions=True, ignore_mandatory=True)

        # Set on both in-memory object and DB so super() sees a linked project
        self.project = project.name
        self.db_set("project", project.name)
