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
        # Pre-create the Project WITH project_code BEFORE calling super(),
        # so the parent's on_submit doesn't try to insert a Project without one
        # (which would fail the naming series validation).
        if not self.project:
            # Build a human-readable project name
            project_name = _(self.doctype) + " : "
            if self.doctype == "Employee Onboarding":
                project_name += self.job_applicant
            else:
                project_name += self.employee

            # Generate a unique Project Code
            project_code = f"PRJ-{frappe.generate_hash(length=8)}"

            # Determine the expected start date based on doctype
            expected_start_date = (
                self.date_of_joining
                if self.doctype == "Employee Onboarding"
                else self.resignation_letter_date
            )

            project = frappe.get_doc(
                {
                    "doctype": "Project",
                    "project_name": project_name,
                    "expected_start_date": expected_start_date,
                    "department": self.department,
                    "company": self.company,
                    "project_code": project_code,
                }
            ).insert(ignore_permissions=True, ignore_mandatory=True)

            # Persist the project link in the DB so parent's on_submit sees it
            # and skips its own project-creation block entirely.
            self.db_set("project", project.name)

            # Also update in-memory so all subsequent logic in this call uses
            # the correct project name without needing a reload.
            self.project = project.name

        # Now call the parent's on_submit. Because self.project is already set
        # (both in DB and in memory), the parent will skip its project-insertion
        # block and proceed directly to task creation and notifications.
        super().on_submit()

        # After the parent completes, validate that the linked project has a
        # project_code. This covers cases where a project was pre-linked by the
        # user before submission (i.e., self.project was already set above).
        project = frappe.get_doc("Project", self.project)
        if not project.project_code:
            frappe.throw(_("The linked Project must have a Project Code."))

    def create_task_and_notify_user(self):
        # Create tasks for the given project and assign to the concerned person.
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

            if users:
                self.assign_task_to_users(task, users)

    def get_holiday_list(self):
        if self.doctype == "Employee Separation":
            return get_holiday_list_for_employee(self.employee)

        # For Employee Onboarding (and other doctypes), derive the holiday list
        # from the linked Project, falling back to the HR Settings default.
        if self.project:
            project = frappe.get_doc("Project", self.project)

            if project.holiday_list:
                return project.holiday_list

            # Fall back to the system-wide default holiday list
            default_holiday_list = frappe.db.get_single_value(
                "HR Settings", "default_holiday_list"
            )
            if default_holiday_list:
                return default_holiday_list

            frappe.throw(
                _(
                    "The linked Project does not have a Holiday List set, "
                    "and no default Holiday List is configured in HR Settings."
                ),
                frappe.MandatoryError,
            )
        else:
            frappe.throw(
                _(
                    "Please link a Project with a Holiday List to the "
                    "Employee Onboarding document."
                ),
                frappe.MandatoryError,
            )

    def get_task_dates(self, activity, holiday_list):
        start_date = end_date = None

        if activity.begin_on is not None:
            start_date = add_days(self.boarding_begins_on, activity.begin_on)
            start_date = self.update_if_holiday(start_date, holiday_list)

            if activity.duration is not None:
                end_date = add_days(
                    self.boarding_begins_on, activity.begin_on + activity.duration
                )
                end_date = self.update_if_holiday(end_date, holiday_list)

        return [start_date, end_date]

    def update_if_holiday(self, date, holiday_list):
        # Advance the date forward until it no longer falls on a holiday.
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
        # Delete all tasks linked to the project, then delete the project itself.
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
