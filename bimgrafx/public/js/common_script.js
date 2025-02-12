$(document).ready(function() {
    setTimeout(function() {
        $('.search-bar').before(
            '<div class="hello-text" style="background-color: #f8f9fa; color: #333; font-size: 16px; font-weight: bold; padding: 10px 15px; margin-bottom: 10px; border-left: 4px solid #007bff; border-radius: 5px; display: inline-block;">' 
            + frappe.defaults.get_user_default("Company") + 
            '</div>'
        );
    }, 1000);
});
