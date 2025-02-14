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
                let lastLogin = "Never";

                if (r.message?.last_login) {
                    let loginDate = new Date(r.message.last_login);
                    let day = String(loginDate.getDate()).padStart(2, "0");
                    let month = String(loginDate.getMonth() + 1).padStart(2, "0"); // Months are 0-based
                    let year = loginDate.getFullYear();
                    let hours = String(loginDate.getHours()).padStart(2, "0");
                    let minutes = String(loginDate.getMinutes()).padStart(2, "0");

                    lastLogin = `${day}-${month}-${year} ${hours}:${minutes}`;
                }

                const helloText = `
                    <div class="hello-text" style="background-color: #ffffff; color: #000000; font-size: 12px; font-weight: bold; padding: 5px 8px; margin: 10px; border: 1px solid #152a36; border-radius: 10px; display: inline-block;">
                        Company: ${company}<br><i class="fa fa-clock-o" aria-hidden="true"></i> Last Active: ${lastLogin}
                    </div>
                `;
                $('.search-bar').before(helloText);
            }
        });
    }, 1000);
});
