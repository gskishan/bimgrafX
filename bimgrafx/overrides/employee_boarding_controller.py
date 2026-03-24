import frappe
from frappe import _
from hrms.controllers.employee_boarding_controller import EmployeeBoardingController

class CustomEmployeeBoardingController(EmployeeBoardingController):
    def on_submit(self):
        # Ensure Project Code is set
        if not self.project_code:
            frappe.throw(_("Project Code is required"))

        # Create the project for the given employee onboarding
        project_name = _(self.doctype) + " : "
        if self.doctype == "Employee Onboarding":
            project_name += self.job_applicant
        else:
            project_name += self.employee

        project = frappe.get_doc(
            {
                "doctype": "Project",
                "project_name": project_name,
                "expected_start_date": self.date_of_joining
                if self.doctype == "Employee Onboarding"
                else self.resignation_letter_date,
                "department": self.department,
                "company": self.company,
                "project_code": self.project_code,  # Ensure Project Code is passed here
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)

        self.db_set("project", project.name)
        self.db_set("boarding_status", "Pending")
        self.reload()
        self.create_task_and_notify_user()
