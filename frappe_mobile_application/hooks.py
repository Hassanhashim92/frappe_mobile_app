app_name = "frappe_mobile_application"
app_title = "Frappe Mobile Application"
app_publisher = "Sarmad"
app_description = "Mobile app to manage erpnext activities"
app_email = "sarmad@rayacoltd.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_mobile_application",
# 		"logo": "/assets/frappe_mobile_application/logo.png",
# 		"title": "Frappe Mobile Application",
# 		"route": "/frappe_mobile_application",
# 		"has_permission": "frappe_mobile_application.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_mobile_application/css/frappe_mobile_application.css"
# app_include_js = "/assets/frappe_mobile_application/js/frappe_mobile_application.js"

# include js, css files in header of web template
# web_include_css = "/assets/frappe_mobile_application/css/frappe_mobile_application.css"
# web_include_js = "/assets/frappe_mobile_application/js/frappe_mobile_application.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_mobile_application/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_mobile_application/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "frappe_mobile_application.utils.jinja_methods",
# 	"filters": "frappe_mobile_application.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "frappe_mobile_application.install.before_install"
# after_install = "frappe_mobile_application.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_mobile_application.uninstall.before_uninstall"
# after_uninstall = "frappe_mobile_application.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_mobile_application.utils.before_app_install"
# after_app_install = "frappe_mobile_application.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_mobile_application.utils.before_app_uninstall"
# after_app_uninstall = "frappe_mobile_application.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_mobile_application.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"frappe_mobile_application.tasks.all"
# 	],
# 	"daily": [
# 		"frappe_mobile_application.tasks.daily"
# 	],
# 	"hourly": [
# 		"frappe_mobile_application.tasks.hourly"
# 	],
# 	"weekly": [
# 		"frappe_mobile_application.tasks.weekly"
# 	],
# 	"monthly": [
# 		"frappe_mobile_application.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "frappe_mobile_application.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "frappe_mobile_application.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_mobile_application.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_mobile_application.utils.before_request"]
# after_request = ["frappe_mobile_application.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_mobile_application.utils.before_job"]
# after_job = ["frappe_mobile_application.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"frappe_mobile_application.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name", "in", [
					"Branch-custom_longitude",
					"Branch-custom_latitude",
					"Branch-custom_column_break_pwwle",
					"Employee Checkin-custom_location_photo",
					"Employee Checkin-custom_client_bio_metric_photo",
					"Company-custom_attendnace_validations_based_on_department",
					"Project-custom_required_location_check_on_check_out",
					"Project-custom_column_break_ievfh",
					"Project-custom_required_to_upload_client_bio_metric_photo",
					"Project-custom_required_to_upload_location_photo",
					"Project-custom__mobile_app_attendance_configurations",
					"Department-custom_required_location_check_on_check_out",
					"Department-custom_column_break_dayvd",
					"Department-custom_required_to_upload_client_bio_metric_photo",
					"Department-custom_required_to_upload_location_photo",
					"Department-custom__mobile_app_attendance_configurations",
					"Branch-custom_radius_in_meters",
					"Branch-custom_column_break_hvd5h",
					"Branch-custom_mobile_app_attendance_configurations",
				]
			]
		]
	}
]
