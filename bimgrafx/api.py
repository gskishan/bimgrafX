import frappe
from frappe.utils import today, date_diff, nowdate


def get_hr_managers():
    """Fetch all enabled users having HR Manager role"""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager"},
        fields=["parent"]
    )

    user_ids = [u.parent for u in users]

    if not user_ids:
        return []

    # Get email IDs from User doctype
    emails = frappe.get_all(
        "User",
        filters={
            "name": ["in", user_ids],
            "enabled": 1
        },
        pluck="email"
    )

    return emails


def send_birthday_reminder():
    # Get today's birthdays
    report_data = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "date_of_birth"],
        filters={"date_of_birth": ["like", f"%{today()[5:]}"]},
    )

    if not report_data:
        return

    # Get HR Managers
    recipients = get_hr_managers()

    if not recipients:
        return

    # Build table rows
    rows = ""
    for emp in report_data:
        rows += f"""
        <tr>
            <td>{emp.employee_name}</td>
            <td>{emp.name}</td>
            <td>{emp.date_of_birth}</td>
        </tr>
        """

    # Email content
    message = f"""
    <p>Dear Team,</p>
    <p>Here are the employees who have birthdays today:</p>

    <table border="1" cellpadding="6" cellspacing="0">
        <tr>
            <th>Employee Name</th>
            <th>Employee ID</th>
            <th>Date of Birth</th>
        </tr>
        {rows}
    </table>

    <p>Regards,<br>HR & Admin Department</p>
    """

    # Send mail
    frappe.sendmail(
        recipients=recipients,
        subject=f"🎂 Birthday Reminder – {today()}",
        message=message,
    )


def send_work_anniversary_reminder():
    """Send work anniversary reminders to all HR Managers"""

    # Fetch employees where today matches month/day of date_of_joining
    report_data = frappe.db.sql(
        """
        SELECT 
            name,
            employee_name,
            date_of_joining,
            FLOOR(DATEDIFF(CURDATE(), date_of_joining) / 365) AS years
        FROM `tabEmployee`
        WHERE 
            DATE_FORMAT(date_of_joining, '%m-%d') = DATE_FORMAT(CURDATE(), '%m-%d')
            AND status = 'Active'
        """,
        as_dict=True,
    )

    if not report_data:
        return

    # Get HR Manager recipients
    recipients = get_hr_managers()
    if not recipients:
        return

    # Prepare table
    rows = ""
    for emp in report_data:
        rows += f"""
        <tr>
            <td>{emp.employee_name}</td>
            <td>{emp.name}</td>
            <td>{emp.date_of_joining}</td>
            <td>{emp.years} Years</td>
        </tr>
        """

    # Email Body
    message = f"""
    <p>Dear Team,</p>

    <p>The following employees are celebrating their work anniversary today:</p>

    <table border="1" cellpadding="6" cellspacing="0">
        <tr>
            <th>Employee Name</th>
            <th>Employee ID</th>
            <th>Date of Joining</th>
            <th>Years Completed</th>
        </tr>
        {rows}
    </table>

    <p>Regards,<br>HR & Admin Department</p>
    """

    # Send the email
    frappe.sendmail(
        recipients=recipients,
        subject=f"🎉 Work Anniversary Reminder – {today()}",
        message=message,
    )
