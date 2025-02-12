$(document).ready(function () {
    setTimeout(function () {
        const user = frappe.session.user;
        const company = frappe.defaults.get_user_default("Company") || "No Company";

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "User",
                name: user
            },
            callback: function (r) {
                const lastLogin = r.message?.last_login || "Never";

                const helloText = `
                    <div class="hello-text" style="background-color: #ffffff; color: #333; font-size: 14px; font-weight: bold; padding: 5px 10px; margin-bottom: 10px; border-left: 2px solid #ccb064; border-radius: 5px; display: inline-block;">
                        Company: ${company}<br>Last Login: ${lastLogin}
                    </div>
                `;
                $('.search-bar').before(helloText);
            }
        });
    }, 1000);
});
