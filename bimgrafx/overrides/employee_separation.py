import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import add_days, unique
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday
from hrms.hr.doctype.employee_separation.employee_separation import EmployeeSeparation


class CustomEmployeeSeparation(EmployeeSeparation):

    def on_submit(self):
        """
        Fully overrides the entire on_submit chain
        (EmployeeSeparation → EmployeeBoardingController) so we never let
        the grandparent attempt to insert a Project without a project_code.

        Replicates all grandparent logic here with the project_code fix baked in.
        """
        # ── 1. Ensure a Project exists and has a project_code ─────────────
        if not self.project:
            project_name = _("Employee Separation") + " : " + self.employee
            project_code = "PRJ-{}".format(frappe.generate_hash(length=8))

            project = frappe.get_doc({
                "doctype": "Project",
                "project_name": project_name,
                "expected_start_date": self.resignation_letter_date,
                "department": self.department,
                "company": self.company,
                "project_code": project_code,
            }).insert(ignore_permissions=True, ignore_mandatory=True)

            # Write to DB and in-memory both
            self.project = project.name
            self.db_set("project", project.name)
            frappe.db.commit()           # flush so any re-read also sees it

        else:
            # A project was pre-linked — validate it has a project_code
            project = frappe.get_doc("Project", self.project)
            if not project.project_code:
                frappe.throw(_("The linked Project must have a Project Code."))

        # ── 2. Set boarding status (replicates EmployeeBoardingController) ─
        self.db_set("boarding_status", "Pending")
        self.reload()

        # ── 3. Create tasks and notify users ──────────────────────────────
        self.create_task_and_notify_user()

    def create_task_and_notify_user(self):
        holiday_list = self._get_holiday_list()

        for activity in self.activities:
            if activity.task:
                continue

            dates = self._get_task_dates(activity, holiday_list)

            task = frappe.get_doc({
                "doctype": "Task",
                "project": self.project,
                "subject": "{} : {}".format(activity.activity_name, self.employee_name),
                "description": activity.description,
                "department": self.department,
                "company": self.company,
                "task_weight": activity.task_weight,
                "exp_start_date": dates[0],
                "exp_end_date": dates[1],
            }).insert(ignore_permissions=True)

            activity.db_set("task", task.name)

            users = [activity.user] if activity.user else []

            if activity.role:
                user_list = frappe.db.sql_list(
                    """
                    SELECT DISTINCT(has_role.parent)
                    FROM `tabHas Role` has_role
                    LEFT JOIN `tabUser` user ON has_role.parent = user.name
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
                self._assign_task_to_users(task, users)

    def _get_holiday_list(self):
        """Get holiday list for Employee Separation from employee record."""
        return get_holiday_list_for_employee(self.employee)

    def _get_task_dates(self, activity, holiday_list):
        start_date = end_date = None

        if activity.begin_on is not None:
            start_date = add_days(self.boarding_begins_on, activity.begin_on)
            start_date = self._skip_holidays(start_date, holiday_list)

            if activity.duration is not None:
                end_date = add_days(
                    self.boarding_begins_on,
                    activity.begin_on + activity.duration
                )
                end_date = self._skip_holidays(end_date, holiday_list)

        return [start_date, end_date]

    def _skip_holidays(self, date, holiday_list):
        while is_holiday(holiday_list, date):
            date = add_days(date, 1)
        return date

    def _assign_task_to_users(self, task, users):
        for user in users:
            assign_to.add({
                "assign_to": [user],
                "doctype": task.doctype,
                "name": task.name,
                "description": task.description or task.subject,
                "notify": self.notify_users_by_email,
            })

    def on_cancel(self):
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
