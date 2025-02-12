$(document).ready(function () {
    setTimeout(function () {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "User",
                name: frappe.session.user
            },
            callback: function (r) {
                if (r.message) {
                    let lastLogin = r.message.last_login || "Never";
                    let company = frappe.defaults.get_user_default("Company") || "No Company";

                    $('.search-bar').before(
                        '<div class="hello-text" style="background-color: #ffffff; color: #333; font-size: 14px; font-weight: bold; padding: 5px 10px; margin-bottom: 10px; border-left: 2px solid #ccb064; border-radius: 5px; display: inline-block;">' +
                        'Company: ' + company + '<br>Last Login: ' + lastLogin +
                        '</div>'
                    );
                }
            }
        });
    }, 1000);
});
