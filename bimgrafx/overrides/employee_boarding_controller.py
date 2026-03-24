import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.model.document import Document
from frappe.utils import add_days, flt, unique
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday
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

            # Generate a default Project Code if not provided
            project_code = f"PRJ-{frappe.generate_hash(length=8)}"

            project = frappe.get_doc(
                {
                    "doctype": "Project",
                    "project_name": project_name,
                    "expected_start_date": self.date_of_joining
                    if self.doctype == "Employee Onboarding"
                    else self.resignation_letter_date,
                    "department": self.department,
                    "company": self.company,
                    "project_code": project_code,  # Set the Project Code here
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

    def create_task_and_notify_user(self):
        # Create the task for the given project and assign to the concerned person
        holiday_list = self.get_holiday_list()

        for activity in self.activities:
            if activity.task:
                continue

            dates = self.get_task_dates(activity, holiday_list)

            task = frappe.get_doc(
                {
                    "doctype": "Task",
                    "project": self.project,
                    "subject": activity.activity_name + " : " + self.employee_name,
                    "description": activity.description,
                    "department": self.department,
                    "company": self.company,
                    "task_weight": activity.task_weight,
                    "exp_start_date": dates[0],
                    "exp_end_date": dates[1],
                }
            ).insert(ignore_permissions=True)
            activity.db_set("task", task.name)

            users = [activity.user] if activity.user else []
            if activity.role:
                user_list = frappe.db.sql_list(
                    """
                    SELECT
                        DISTINCT(has_role.parent)
                    FROM
                        `tabHas Role` has_role
                            LEFT JOIN `tabUser` user
                                ON has_role.parent = user.name
                    WHERE
                        has_role.parenttype = 'User'
                            AND user.enabled = 1
                            AND has_role.role = %s
                """,
                    activity.role,
                )
                users = unique(users + user_list)

                if "Administrator" in users:
                    users.remove("Administrator")

            # Assign the task to the users
            if users:
                self.assign_task_to_users(task, users)

    def get_holiday_list(self):
        if self.doctype == "Employee Separation":
            return get_holiday_list_for_employee(self.employee)
        else:
            if self.project:
                # Fetch the Holiday List from the linked Project
                project = frappe.get_doc("Project", self.project)
                if project.holiday_list:
                    return project.holiday_list
                else:
                    # Use a default Holiday List if none is set in the Project
                    default_holiday_list = frappe.db.get_single_value("HR Settings", "default_holiday_list")
                    if default_holiday_list:
                        return default_holiday_list
                    else:
                        frappe.throw(_("The linked Project does not have a Holiday List set, and no default Holiday List is configured."), frappe.MandatoryError)
            else:
                frappe.throw(_("Please link a Project with a Holiday List to the Employee Onboarding document."), frappe.MandatoryError)

    def get_task_dates(self, activity, holiday_list):
        start_date = end_date = None

        if activity.begin_on is not None:
            start_date = add_days(self.boarding_begins_on, activity.begin_on)
            start_date = self.update_if_holiday(start_date, holiday_list)

            if activity.duration is not None:
                end_date = add_days(self.boarding_begins_on, activity.begin_on + activity.duration)
                end_date = self.update_if_holiday(end_date, holiday_list)

        return [start_date, end_date]

    def update_if_holiday(self, date, holiday_list):
        while is_holiday(holiday_list, date):
            date = add_days(date, 1)
        return date

    def assign_task_to_users(self, task, users):
        for user in users:
            args = {
                "assign_to": [user],
                "doctype": task.doctype,
                "name": task.name,
                "description": task.description or task.subject,
                "notify": self.notify_users_by_email,
            }
            assign_to.add(args)

    def on_cancel(self):
        # Delete task project
        project = self.project
        for task in frappe.get_all("Task", filters={"project": project}):
            frappe.delete_doc("Task", task.name, force=1)
        frappe.delete_doc("Project", project, force=1)
        self.db_set("project", "")
        for activity in self.activities:
            activity.db_set("task", "")

        frappe.msgprint(
            _("Linked Project {} and Tasks deleted.").format(project), alert=True, indicator="blue"
        )
