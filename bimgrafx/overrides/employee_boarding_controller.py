import frappe
from frappe import _
from hrms.controllers.employee_boarding_controller import EmployeeBoardingController

class CustomEmployeeBoardingController(EmployeeBoardingController):
    def on_submit(self):
	    # Ensure Project field is set
	    if not self.project:
	        # Generate a default Project Name if not provided
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
	            }
	        ).insert(ignore_permissions=True, ignore_mandatory=True)
	
	        # Set the generated project name in the Employee Onboarding document
	        self.db_set("project", project.name)
	
	    # Ensure the linked Project has a Project Code
	    project = frappe.get_doc("Project", self.project)
	    if not project.project_code:
	        frappe.throw(_("The linked Project must have a Project Code."))
	
	    # Update the boarding status
	    self.db_set("boarding_status", "Pending")
	    self.reload()
	    self.create_task_and_notify_user()
