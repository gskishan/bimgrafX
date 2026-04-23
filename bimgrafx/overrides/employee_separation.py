import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import unique
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday
from hrms.hr.doctype.employee_separation.employee_separation import EmployeeSeparation


class CustomEmployeeSeparation(EmployeeSeparation):
    def on_submit(self):
        # ------------------------------------------------------------------ #
        # PRE-CREATE the Project with a project_code BEFORE calling super()  #
        # so that the grandparent (EmployeeBoardingController.on_submit)     #
        # never attempts to insert a Project document without one — which    #
        # would fail the naming-series validation.                           #
        # ------------------------------------------------------------------ #
        if not self.project:
            project_name = _("Employee Separation") + " : " + self.employee

            project_code = f"PRJ-{frappe.generate_hash(length=8)}"

            project = frappe.get_doc(
                {
                    "doctype": "Project",
                    "project_name": project_name,
                    "expected_start_date": self.resignation_letter_date,
                    "department": self.department,
                    "company": self.company,
                    "project_code": project_code,
                }
            ).insert(ignore_permissions=True, ignore_mandatory=True)

            # Persist in DB first so every subsequent DB read sees the value.
            self.db_set("project", project.name)

            # Update in-memory so the parent's on_submit sees self.project
            # as already populated and skips its own project-insertion block.
            self.project = project.name

        # Now safe to call the parent chain — self.project is set in both
        # DB and memory, so EmployeeBoardingController will skip its insert.
        super().on_submit()

        # Post-super validation: ensure any pre-linked project has a code.
        project = frappe.get_doc("Project", self.project)
        if not project.project_code:
            frappe.throw(_("The linked Project must have a Project Code."))

    def on_cancel(self):
        # Delete all tasks linked to the project, then remove the project.
        project = self.project

        for task in frappe.get_all("Task", filters={"project": project}):
            frappe.delete_doc("Task", task.name, force=1)

        frappe.delete_doc("Project", project, force=1)
        self.db_set("project", "")

        for activity in self.activities:
            activity.db_set("task", "")

        frappe.msgprint(
            _("Linked Project {} and Tasks deleted.").format(project),
            alert=True,
            indicator="blue",
        )
