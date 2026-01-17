import frappe
from frappe import _
from frappe.exceptions import DoesNotExistError, ValidationError
from frappe.utils import get_datetime
from hrms.hr.utils import get_distance_between_coordinates, validate_active_employee
from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError
import base64
from frappe.utils.file_manager import save_file


@frappe.whitelist()
def get_employee_configuration(employee_id=None):
	"""
	Get employee configuration data including branch location and check-in/check-out settings.
	
	This API returns:
	- Employee Name, Employee ID, Email, Department, Branch
	- Location Information (Latitude, Longitude, Radius from Branch)
	- Rules (required_to_upload_location_photo, required_to_upload_client_bio_metric_photo, 
	  require_location_check_on_check_out) from Department or Project based on Company setting
	
	Args:
		employee_id (str, optional): Employee ID. If not provided, uses authenticated user's employee record.
	
	Returns:
		dict: Employee configuration data with location and rules
	
	Raises:
		DoesNotExistError: If employee not found
		ValidationError: If required data is missing
	"""
	# Get employee record
	if employee_id:
		employee = frappe.get_doc("Employee", employee_id)
	else:
		# Get employee from authenticated user
		employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not employee_name:
			frappe.throw(_("Employee not found for user {0}").format(frappe.session.user), DoesNotExistError)
		employee = frappe.get_doc("Employee", employee_name)
	
	# Get employee basic information
	employee_name = getattr(employee, "employee_name", None) or employee.name
	# Try employee_code first, then employee_number, then fallback to name
	employee_code = getattr(employee, "employee_code", None) or getattr(employee, "employee_number", None) or employee.name
	# Get email from various possible fields
	email = getattr(employee, "company_email", None)
	if not email:
		frappe.throw(_("Employee has no company email assigned. Please assign a company email to the employee."), ValidationError)
	department = getattr(employee, "department", None) or ""
	department_name = frappe.db.get_value("Department", department, "department_name") if department else ""
	branch = getattr(employee, "branch", None) or ""
	branch_name = frappe.db.get_value("Branch", branch, "branch") if branch else ""
	
	# Validate branch exists
	if not branch:
		frappe.throw(
			_("Employee has no branch assigned. Please assign a branch to the employee."),
			ValidationError
		)
	
	# Get Branch location information
	branch_doc = frappe.get_doc("Branch", branch)
	# Get custom fields safely (they may not exist if not configured)
	latitude = getattr(branch_doc, "custom_latitude", None)
	longitude = getattr(branch_doc, "custom_longitude", None)
	radius = getattr(branch_doc, "custom_radius_in_meters", None)
	
	# Validate branch has location data
	if latitude is None or longitude is None or radius is None:
		frappe.throw(
			_("Branch {0} does not have location information (latitude, longitude, or radius) configured.").format(branch_name),
			ValidationError
		)
	
	# Get Company setting
	company = getattr(employee, "company", None)
	if not company:
		frappe.throw(
			_("Employee has no company assigned."),
			ValidationError
		)
	
	company_doc = frappe.get_doc("Company", company)
	# Get Company setting safely (it may be a custom field)
	use_department_settings = getattr(company_doc, "custom_attendnace_validations_based_on_department", False)
	if use_department_settings is None:
		use_department_settings = False
	
	# Get settings based on Company setting
	settings_source = ""
	project = None
	project_name = None
	
	if use_department_settings:
		# Get settings from Department
		if not department:
			frappe.throw(
				_("Company setting requires Department settings, but Employee has no Department assigned."),
				ValidationError
			)
		
		department_doc = frappe.get_doc("Department", department)
		# Get settings fields safely (they may be custom fields)
		required_to_upload_location_photo = getattr(department_doc, "required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(department_doc, "required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(department_doc, "require_location_check_on_check_out", None)
		
		# Check if settings fields exist in the doctype
		if not hasattr(department_doc, "required_to_upload_location_photo") and \
		   not hasattr(department_doc, "required_to_upload_client_bio_metric_photo") and \
		   not hasattr(department_doc, "require_location_check_on_check_out"):
			frappe.throw(
				_("Company setting requires Department settings, but Department has no validation settings configured. Please configure settings in Department."),
				ValidationError
			)
		
		# Default to False if fields exist but are None
		required_to_upload_location_photo = required_to_upload_location_photo if required_to_upload_location_photo is not None else False
		required_to_upload_client_bio_metric_photo = required_to_upload_client_bio_metric_photo if required_to_upload_client_bio_metric_photo is not None else False
		require_location_check_on_check_out = require_location_check_on_check_out if require_location_check_on_check_out is not None else False
		
		settings_source = "department"
	else:
		# Get settings from Project (via Department -> custom_project)
		if not department:
			frappe.throw(
				_("Company setting requires Project settings, but Employee has no Department assigned."),
				ValidationError
			)
		
		department_doc = frappe.get_doc("Department", department)
		# Get custom_project field safely (it may be a custom field)
		project = getattr(department_doc, "custom_project", None)
		
		if not project:
			frappe.throw(
				_("Company setting requires Project settings, but Department has no linked Project. Please link a Project to Department via custom_project field."),
				ValidationError
			)
		
		project_doc = frappe.get_doc("Project", project)
		project_name = frappe.db.get_value("Project", project, "project_name") or project
		# Get settings fields safely (they may be custom fields)
		required_to_upload_location_photo = getattr(project_doc, "custom_required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(project_doc, "custom_required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(project_doc, "custom_require_location_check_on_check_out", None)
		
		# Check if settings fields exist in the doctype
		if not hasattr(project_doc, "custom_required_to_upload_location_photo") and \
		   not hasattr(project_doc, "custom_required_to_upload_client_bio_metric_photo") and \
		   not hasattr(project_doc, "custom_require_location_check_on_check_out"):
			frappe.throw(
				_("Company setting requires Project settings, but linked Project has no validation settings configured. Please configure settings in Project."),
				ValidationError
			)
		
		# Default to False if fields exist but are None
		required_to_upload_location_photo = required_to_upload_location_photo if required_to_upload_location_photo is not None else False
		required_to_upload_client_bio_metric_photo = required_to_upload_client_bio_metric_photo if required_to_upload_client_bio_metric_photo is not None else False
		require_location_check_on_check_out = require_location_check_on_check_out if require_location_check_on_check_out is not None else False
		
		settings_source = "project"
	
	# Build branch information block
	branch_info = {
		"branch_id": branch,
		"branch_name": branch_name or branch,
		"latitude": latitude,
		"longitude": longitude,
		"checkin_radius_meters": radius,
		"address": getattr(branch_doc, "address", None),
	}
	
	# Build settings block with booleans and metadata
	settings = {
		"required_to_upload_location_photo": bool(required_to_upload_location_photo),
		"required_to_upload_client_bio_metric_photo": bool(required_to_upload_client_bio_metric_photo),
		"require_location_check_on_check_out": bool(require_location_check_on_check_out),
		"settings_source": settings_source,
		"department_id": department or None,
		"department_name": department_name or None,
		"project_id": project,
		"project_name": project_name,
	}
	
	# Build response matching the exact format from the image
	response = {
		"employee_id": employee_code,
		"employee_name": employee_name,
		"employee_code": employee_code,
		"designation": getattr(employee, "designation", None) or "",
		"department": department or "",
		"department_name": department_name or "",
		"company": company,
		"branch": branch_info,
		"settings": settings,
	}
	
	return response


def _get_employee_settings(employee):
	"""
	Helper function to get employee settings (same logic as get_employee_configuration).
	Returns: dict with settings and branch info
	"""
	department = getattr(employee, "department", None) or ""
	company = getattr(employee, "company", None)
	
	if not company:
		frappe.throw(_("Employee has no company assigned."), ValidationError)
	
	company_doc = frappe.get_doc("Company", company)
	use_department_settings = getattr(company_doc, "custom_attendnace_validations_based_on_department", False)
	if use_department_settings is None:
		use_department_settings = False
	
	# Get settings based on Company setting
	if use_department_settings:
		if not department:
			frappe.throw(
				_("Company setting requires Department settings, but Employee has no Department assigned."),
				ValidationError
			)
		
		department_doc = frappe.get_doc("Department", department)
		required_to_upload_location_photo = getattr(department_doc, "required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(department_doc, "required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(department_doc, "require_location_check_on_check_out", None)
		
		if not (hasattr(department_doc, "required_to_upload_location_photo") or \
		        hasattr(department_doc, "required_to_upload_client_bio_metric_photo") or \
		        hasattr(department_doc, "require_location_check_on_check_out")):
			frappe.throw(
				_("Company setting requires Department settings, but Department has no validation settings configured."),
				ValidationError
			)
		
		required_to_upload_location_photo = required_to_upload_location_photo if required_to_upload_location_photo is not None else False
		required_to_upload_client_bio_metric_photo = required_to_upload_client_bio_metric_photo if required_to_upload_client_bio_metric_photo is not None else False
		require_location_check_on_check_out = require_location_check_on_check_out if require_location_check_on_check_out is not None else False
	else:
		if not department:
			frappe.throw(
				_("Company setting requires Project settings, but Employee has no Department assigned."),
				ValidationError
			)
		
		department_doc = frappe.get_doc("Department", department)
		project = getattr(department_doc, "custom_project", None)
		
		if not project:
			frappe.throw(
				_("Company setting requires Project settings, but Department has no linked Project."),
				ValidationError
			)
		
		project_doc = frappe.get_doc("Project", project)
		required_to_upload_location_photo = getattr(project_doc, "custom_required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(project_doc, "custom_required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(project_doc, "custom_require_location_check_on_check_out", None)
		
		if not (hasattr(project_doc, "custom_required_to_upload_location_photo") or \
		        hasattr(project_doc, "custom_required_to_upload_client_bio_metric_photo") or \
		        hasattr(project_doc, "custom_require_location_check_on_check_out")):
			frappe.throw(
				_("Company setting requires Project settings, but linked Project has no validation settings configured."),
				ValidationError
			)
		
		required_to_upload_location_photo = required_to_upload_location_photo if required_to_upload_location_photo is not None else False
		required_to_upload_client_bio_metric_photo = required_to_upload_client_bio_metric_photo if required_to_upload_client_bio_metric_photo is not None else False
		require_location_check_on_check_out = require_location_check_on_check_out if require_location_check_on_check_out is not None else False
	
	# Get branch info
	branch = getattr(employee, "branch", None) or ""
	if not branch:
		frappe.throw(_("Employee has no branch assigned."), ValidationError)
	
	branch_doc = frappe.get_doc("Branch", branch)
	latitude = getattr(branch_doc, "custom_latitude", None)
	longitude = getattr(branch_doc, "custom_longitude", None)
	radius = getattr(branch_doc, "custom_radius_in_meters", None)
	
	if latitude is None or longitude is None or radius is None:
		branch_name = frappe.db.get_value("Branch", branch, "branch") or branch
		frappe.throw(
			_("Branch {0} does not have location information configured.").format(branch_name),
			ValidationError
		)
	
	return {
		"required_to_upload_location_photo": bool(required_to_upload_location_photo),
		"required_to_upload_client_bio_metric_photo": bool(required_to_upload_client_bio_metric_photo),
		"require_location_check_on_check_out": bool(require_location_check_on_check_out),
		"branch_latitude": float(latitude),
		"branch_longitude": float(longitude),
		"branch_radius": int(radius),
		"branch": branch,
	}


def _validate_location(latitude, longitude, branch_latitude, branch_longitude, branch_radius, log_type="IN"):
	"""
	Validate if employee location is within branch radius.
	Raises ValidationError if outside radius.
	"""
	if not latitude or not longitude:
		frappe.throw(_("Latitude and longitude are required for check-in/check-out."), ValidationError)
	
	try:
		latitude = float(latitude)
		longitude = float(longitude)
	except (ValueError, TypeError):
		frappe.throw(_("Invalid latitude or longitude values."), ValidationError)
	
	distance = get_distance_between_coordinates(
		branch_latitude, branch_longitude, latitude, longitude
	)
	
	if distance > branch_radius:
		action = "check in" if log_type == "IN" else "check out"
		frappe.throw(
			_("You are {0:.2f} meters away from the branch location. Please move within {1} meters to {2}.").format(
				distance, branch_radius, action
			),
			exc=CheckinRadiusExceededError,
		)
	
	return distance


def _handle_photo_upload(photo_data, employee_id, checkin_id, photo_type="location"):
	"""
	Handle photo upload from base64 or file_id.
	Returns file_doc or None.
	"""
	if not photo_data:
		return None
	
	# If it's a file_id (already uploaded), return the file doc
	if isinstance(photo_data, str) and not photo_data.startswith("data:"):
		# Check if it's a valid file ID
		if frappe.db.exists("File", photo_data):
			return frappe.get_doc("File", photo_data)
		# If not a file ID, treat as base64
	
	# Handle base64 encoded image
	if isinstance(photo_data, str):
		if photo_data.startswith("data:"):
			# Remove data:image/jpeg;base64, prefix
			photo_data = photo_data.split(",", 1)[1]
		
		try:
			file_bytes = base64.b64decode(photo_data)
		except Exception:
			frappe.throw(_("Invalid base64 image data."), ValidationError)
	else:
		file_bytes = photo_data
	
	# Generate filename
	from frappe.utils import now_datetime
	timestamp = now_datetime().strftime("%Y%m%d_%H%M%S")
	filename = f"{photo_type}_photo_{employee_id}_{timestamp}.jpg"
	
	# Save file and attach to checkin
	file_doc = save_file(
		fname=filename,
		content=file_bytes,
		dt="Employee Checkin",
		dn=checkin_id,
		is_private=0
	)
	
	return file_doc


@frappe.whitelist()
def create_checkin_checkout(
	employee_id=None,
	log_type="IN",
	latitude=None,
	longitude=None,
	device_id=None,
	location_photo=None,
	client_biometric_photo=None,
	timestamp=None,
	notes=None,
	checkin_id=None,
	location_photo_id=None,
	client_biometric_photo_id=None
):
	"""
	Create employee check-in or check-out record with all validations.
	
	This endpoint:
	1. Validates employee is active
	2. Validates location (geofencing) - always for check-in, conditional for checkout
	3. Validates required photos based on settings (Department or Project)
	4. Creates Employee Checkin record
	5. Links photos to checkin record
	6. Applies all existing Employee Checkin validations
	
	Args:
		employee_id (str, optional): Employee ID. If not provided, uses authenticated user's employee.
		log_type (str): "IN" for check-in, "OUT" for check-out
		latitude (float): GPS latitude
		longitude (float): GPS longitude
		device_id (str, optional): Device identifier
		location_photo (str, optional): Base64 encoded image or file_id for location photo
		client_biometric_photo (str, optional): Base64 encoded image or file_id for biometric photo
		timestamp (str, optional): ISO 8601 timestamp (defaults to current time)
		notes (str, optional): Optional notes
		checkin_id (str, optional): For checkout, link to original checkin_id
		location_photo_id (str, optional): Pre-uploaded file ID for location photo
		client_biometric_photo_id (str, optional): Pre-uploaded file ID for biometric photo
	
	Returns:
		dict: Checkin record details
	"""
	# Get employee record
	if employee_id:
		employee = frappe.get_doc("Employee", employee_id)
	else:
		employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not employee_name:
			frappe.throw(_("Employee not found for user {0}").format(frappe.session.user), DoesNotExistError)
		employee = frappe.get_doc("Employee", employee_name)
	
	# Validate employee is active
	validate_active_employee(employee.name)
	
	# Validate log_type
	if log_type not in ["IN", "OUT"]:
		frappe.throw(_("log_type must be 'IN' or 'OUT'."), ValidationError)
	
	# Get employee settings and branch info
	settings = _get_employee_settings(employee)
	
	# Validate location
	# For check-in: always required
	# For check-out: only if require_location_check_on_check_out is True
	if log_type == "IN" or settings["require_location_check_on_check_out"]:
		distance = _validate_location(
			latitude, longitude,
			settings["branch_latitude"],
			settings["branch_longitude"],
			settings["branch_radius"],
			log_type
		)
	else:
		distance = None
	
	# Validate required photos
	location_photo_file = None
	client_biometric_photo_file = None
	
	# Handle location photo
	if settings["required_to_upload_location_photo"]:
		if not location_photo and not location_photo_id:
			frappe.throw(
				_("Location photo is required. Please upload location photo before {0}.").format(
					"check-in" if log_type == "IN" else "check-out"
				),
				ValidationError
			)
		# We'll upload after creating checkin record
	
	# Handle client biometric photo
	if settings["required_to_upload_client_bio_metric_photo"]:
		if not client_biometric_photo and not client_biometric_photo_id:
			frappe.throw(
				_("Client biometric photo is required. Please upload client biometric photo before {0}.").format(
					"check-in" if log_type == "IN" else "check-out"
				),
				ValidationError
			)
		# We'll upload after creating checkin record
	
	# Parse timestamp
	if timestamp:
		try:
			checkin_time = get_datetime(timestamp)
			# Convert timezone-aware datetime to naive datetime for MySQL compatibility
			# MySQL DATETIME doesn't support timezone offsets
			if checkin_time.tzinfo is not None:
				# Convert to UTC and make naive (MySQL stores as naive datetime)
				from datetime import timezone
				checkin_time = checkin_time.astimezone(timezone.utc).replace(tzinfo=None)
			# Remove microseconds as Employee Checkin doctype does
			checkin_time = checkin_time.replace(microsecond=0)
		except Exception:
			frappe.throw(_("Invalid timestamp format. Use ISO 8601 format."), ValidationError)
	else:
		checkin_time = get_datetime()
		# Remove microseconds as Employee Checkin doctype does
		checkin_time = checkin_time.replace(microsecond=0)
	
	# Create Employee Checkin record
	checkin_doc = frappe.new_doc("Employee Checkin")
	checkin_doc.employee = employee.name
	checkin_doc.employee_name = getattr(employee, "employee_name", None) or employee.name
	checkin_doc.log_type = log_type
	checkin_doc.time = checkin_time
	checkin_doc.latitude = float(latitude) if latitude else None
	checkin_doc.longitude = float(longitude) if longitude else None
	checkin_doc.device_id = device_id
	# Set notes only if the field exists (it may be a custom field)
	if notes and hasattr(checkin_doc, "notes"):
		checkin_doc.notes = notes
	
	# Set geolocation (this will populate geolocation field from lat/long)
	checkin_doc.set_geolocation()
	
	# Fetch shift information
	checkin_doc.fetch_shift()
	
	# Validate duplicate log (this is done in Employee Checkin validate method)
	# We'll let the doc validation handle it
	
	# Insert the checkin record
	try:
		checkin_doc.insert()
		# Explicitly commit so that the record is guaranteed to be written
		# This is mainly to avoid any edge cases where the transaction might be left uncommitted
		frappe.db.commit()
	except frappe.DuplicateEntryError:
		frappe.throw(
			_("Duplicate check-in found for this timestamp. Please try again."),
			ValidationError
		)
	
	# Upload and link photos
	if settings["required_to_upload_location_photo"]:
		if location_photo:
			location_photo_file = _handle_photo_upload(
				location_photo, employee.name, checkin_doc.name, "location"
			)
		elif location_photo_id:
			# Link existing file
			if frappe.db.exists("File", location_photo_id):
				file_doc = frappe.get_doc("File", location_photo_id)
				file_doc.attached_to_doctype = "Employee Checkin"
				file_doc.attached_to_name = checkin_doc.name
				file_doc.save(ignore_permissions=True)
				location_photo_file = file_doc
	
	if settings["required_to_upload_client_bio_metric_photo"]:
		if client_biometric_photo:
			client_biometric_photo_file = _handle_photo_upload(
				client_biometric_photo, employee.name, checkin_doc.name, "biometric"
			)
		elif client_biometric_photo_id:
			# Link existing file
			if frappe.db.exists("File", client_biometric_photo_id):
				file_doc = frappe.get_doc("File", client_biometric_photo_id)
				file_doc.attached_to_doctype = "Employee Checkin"
				file_doc.attached_to_name = checkin_doc.name
				file_doc.save(ignore_permissions=True)
				client_biometric_photo_file = file_doc
	
	# Build response
	response = {
		"checkin_id": checkin_doc.name,
		"employee_id": getattr(employee, "employee_code", None) or getattr(employee, "employee_number", None) or employee.name,
		"employee_name": getattr(employee, "employee_name", None) or employee.name,
		"log_type": log_type,
		"time": checkin_doc.time.isoformat() if hasattr(checkin_doc.time, "isoformat") else str(checkin_doc.time),
		"latitude": checkin_doc.latitude,
		"longitude": checkin_doc.longitude,
		"shift": checkin_doc.shift,
		"shift_start": checkin_doc.shift_start.isoformat() if checkin_doc.shift_start and hasattr(checkin_doc.shift_start, "isoformat") else (str(checkin_doc.shift_start) if checkin_doc.shift_start else None),
		"shift_end": checkin_doc.shift_end.isoformat() if checkin_doc.shift_end and hasattr(checkin_doc.shift_end, "isoformat") else (str(checkin_doc.shift_end) if checkin_doc.shift_end else None),
		"attendance": checkin_doc.attendance,
		"status": "success",
	}
	
	if distance is not None:
		response["distance_from_branch_meters"] = round(distance, 2)
	
	if location_photo_file:
		response["location_photo_url"] = location_photo_file.file_url
		response["location_photo_id"] = location_photo_file.name
	
	if client_biometric_photo_file:
		response["client_biometric_photo_url"] = client_biometric_photo_file.file_url
		response["client_biometric_photo_id"] = client_biometric_photo_file.name
	
	return response


@frappe.whitelist()
def get_employee_checkin_records(
	employee_id=None,
	log_type=None,
	start_date=None,
	end_date=None,
	limit=None,
	offset=0
):
	"""
	Get all check-in and check-out records for the logged-in employee.
	
	This endpoint retrieves all Employee Checkin records for the authenticated employee,
	with optional filtering by log_type, date range, and pagination.
	
	Args:
		employee_id (str, optional): Employee ID. If not provided, uses authenticated user's employee.
		log_type (str, optional): Filter by log type ("IN" or "OUT"). If not provided, returns all.
		start_date (str, optional): Start date filter (ISO 8601 format or YYYY-MM-DD). If not provided, no start limit.
		end_date (str, optional): End date filter (ISO 8601 format or YYYY-MM-DD). If not provided, no end limit.
		limit (int, optional): Maximum number of records to return. Defaults to 100 if not specified.
		offset (int, optional): Number of records to skip for pagination. Defaults to 0.
	
	Returns:
		dict: {
			"records": [list of checkin records],
			"total_count": total number of records matching filters,
			"limit": limit applied,
			"offset": offset applied,
			"has_more": boolean indicating if more records are available
		}
	
	Raises:
		DoesNotExistError: If employee not found
		ValidationError: If invalid parameters provided
	"""
	# Get employee record
	if employee_id:
		employee = frappe.get_doc("Employee", employee_id)
	else:
		# Get employee from authenticated user
		employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not employee_name:
			frappe.throw(_("Employee not found for user {0}").format(frappe.session.user), DoesNotExistError)
		employee = frappe.get_doc("Employee", employee_name)
	
	# Build filters
	filters = {"employee": employee.name}
	
	# Add log_type filter if provided
	if log_type:
		if log_type not in ["IN", "OUT"]:
			frappe.throw(_("log_type must be 'IN' or 'OUT'."), ValidationError)
		filters["log_type"] = log_type
	
	# Add date filters if provided
	from datetime import timezone, timedelta
	
	if start_date and end_date:
		# Both dates provided - use between filter
		try:
			start_datetime = get_datetime(start_date)
			if start_datetime.tzinfo is not None:
				start_datetime = start_datetime.astimezone(timezone.utc).replace(tzinfo=None)
			
			end_datetime = get_datetime(end_date)
			if end_datetime.tzinfo is not None:
				end_datetime = end_datetime.astimezone(timezone.utc).replace(tzinfo=None)
			# Add one day to include the entire end date
			end_datetime = end_datetime + timedelta(days=1)
			
			filters["time"] = ["between", [start_datetime, end_datetime]]
		except Exception:
			frappe.throw(_("Invalid date format. Use ISO 8601 format or YYYY-MM-DD."), ValidationError)
	elif start_date:
		# Only start date provided
		try:
			start_datetime = get_datetime(start_date)
			if start_datetime.tzinfo is not None:
				start_datetime = start_datetime.astimezone(timezone.utc).replace(tzinfo=None)
			filters["time"] = [">=", start_datetime]
		except Exception:
			frappe.throw(_("Invalid start_date format. Use ISO 8601 format or YYYY-MM-DD."), ValidationError)
	elif end_date:
		# Only end date provided
		try:
			end_datetime = get_datetime(end_date)
			if end_datetime.tzinfo is not None:
				end_datetime = end_datetime.astimezone(timezone.utc).replace(tzinfo=None)
			# Add one day to include the entire end date
			end_datetime = end_datetime + timedelta(days=1)
			filters["time"] = ["<", end_datetime]
		except Exception:
			frappe.throw(_("Invalid end_date format. Use ISO 8601 format or YYYY-MM-DD."), ValidationError)
	
	# Set default limit
	if limit is None:
		limit = 100
	else:
		try:
			limit = int(limit)
			if limit < 1:
				limit = 100
		except (ValueError, TypeError):
			limit = 100
	
	# Validate offset
	try:
		offset = int(offset)
		if offset < 0:
			offset = 0
	except (ValueError, TypeError):
		offset = 0
	
	# Get total count
	total_count = frappe.db.count("Employee Checkin", filters=filters)
	
	# Get records with pagination, ordered by time descending (most recent first)
	checkin_records = frappe.get_all(
		"Employee Checkin",
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"log_type",
			"time",
			"latitude",
			"longitude",
			"device_id",
			"shift",
			"shift_start",
			"shift_end",
			"attendance",
			"skip_auto_attendance",
			"geolocation"
		],
		order_by="time desc",
		limit=limit,
		start=offset
	)
	
	# Get custom fields for location photo and biometric photo
	records_with_photos = []
	for record in checkin_records:
		# Get location photo (get the most recent one if multiple exist)
		location_photos = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Employee Checkin",
				"attached_to_name": record.name,
				"file_name": ["like", "%location_photo%"]
			},
			fields=["name", "file_url"],
			order_by="creation desc",
			limit=1
		)
		location_photo = location_photos[0] if location_photos else None
		
		# Get biometric photo (get the most recent one if multiple exist)
		biometric_photos = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Employee Checkin",
				"attached_to_name": record.name,
				"file_name": ["like", "%biometric%"]
			},
			fields=["name", "file_url"],
			order_by="creation desc",
			limit=1
		)
		biometric_photo = biometric_photos[0] if biometric_photos else None
		
		# Also check custom fields if they exist
		checkin_doc = frappe.get_doc("Employee Checkin", record.name)
		location_photo_id = getattr(checkin_doc, "custom_location_photo", None)
		biometric_photo_id = getattr(checkin_doc, "custom_client_bio_metric_photo", None)
		
		# Build record response
		record_data = {
			"checkin_id": record.name,
			"employee_id": getattr(employee, "employee_code", None) or getattr(employee, "employee_number", None) or employee.name,
			"employee_name": record.employee_name or employee.name,
			"log_type": record.log_type,
			"time": record.time.isoformat() if hasattr(record.time, "isoformat") else str(record.time),
			"latitude": record.latitude,
			"longitude": record.longitude,
			"device_id": record.device_id,
			"shift": record.shift,
			"shift_start": record.shift_start.isoformat() if record.shift_start and hasattr(record.shift_start, "isoformat") else (str(record.shift_start) if record.shift_start else None),
			"shift_end": record.shift_end.isoformat() if record.shift_end and hasattr(record.shift_end, "isoformat") else (str(record.shift_end) if record.shift_end else None),
			"attendance": record.attendance,
			"skip_auto_attendance": record.skip_auto_attendance,
		}
		
		# Add photo information
		if location_photo:
			record_data["location_photo_id"] = location_photo.name
			record_data["location_photo_url"] = location_photo.file_url
		elif location_photo_id:
			# Try to get file info from custom field
			if frappe.db.exists("File", location_photo_id):
				file_doc = frappe.get_doc("File", location_photo_id)
				record_data["location_photo_id"] = file_doc.name
				record_data["location_photo_url"] = file_doc.file_url
		
		if biometric_photo:
			record_data["client_biometric_photo_id"] = biometric_photo.name
			record_data["client_biometric_photo_url"] = biometric_photo.file_url
		elif biometric_photo_id:
			# Try to get file info from custom field
			if frappe.db.exists("File", biometric_photo_id):
				file_doc = frappe.get_doc("File", biometric_photo_id)
				record_data["client_biometric_photo_id"] = file_doc.name
				record_data["client_biometric_photo_url"] = file_doc.file_url
		
		records_with_photos.append(record_data)
	
	# Build response
	response = {
		"records": records_with_photos,
		"total_count": total_count,
		"limit": limit,
		"offset": offset,
		"has_more": (offset + limit) < total_count
	}
	
	return response

