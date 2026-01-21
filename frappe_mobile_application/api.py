import frappe
from frappe import _
from frappe.exceptions import DoesNotExistError, ValidationError
from frappe.utils import get_datetime
from hrms.hr.utils import get_distance_between_coordinates, validate_active_employee
from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError
import base64
from frappe.utils.file_manager import save_file
from frappe.auth import LoginManager


@frappe.whitelist(allow_guest=True)
def mobile_login(usr=None, pwd=None, has_existing_token=False):
	"""
	Mobile app login endpoint with API credential generation.
	
	This endpoint:
	1. Authenticates user using standard ERPNext login
	2. Generates API credentials if needed (based on has_existing_token flag)
	3. Returns login response with API credentials
	
	Args:
		usr (str, required): ERPNext username
		pwd (str, required): ERPNext password
		has_existing_token (bool, optional): 
			- False: Generate new API credentials if user doesn't have them
			- True: Skip credential generation (assumes mobile already has credentials)
	
	Returns:
		dict: {
			"login": {standard login response},
			"api_credentials": {
				"token": str (format: "api_key:api_secret"),
				"generated": bool,
				"message": str
			}
		}
	
	Raises:
		ValidationError: If login fails or credentials cannot be generated
	"""
	# Validate required parameters
	if not usr:
		frappe.throw(_("Username is required."), ValidationError)
	
	if not pwd:
		frappe.throw(_("Password is required."), ValidationError)
	
	# Convert has_existing_token to boolean (handles string "true"/"false" from API)
	if isinstance(has_existing_token, str):
		has_existing_token = has_existing_token.lower() in ("true", "1", "yes")
	else:
		has_existing_token = bool(has_existing_token)
	
	# Perform standard ERPNext login
	try:
		login_manager = LoginManager()
		login_manager.authenticate(usr, pwd)
		
		if not login_manager.user:
			frappe.throw(_("Invalid login credentials. Please check your username and password."), ValidationError)
		
		# Login successful - create session
		login_manager.post_login()
		
	except frappe.exceptions.AuthenticationError as e:
		# Handle authentication errors (wrong password, user disabled, etc.)
		frappe.throw(_("Login failed: {0}").format(str(e)), ValidationError)
	except Exception as e:
		# Handle any other login errors
		frappe.throw(_("Login error: {0}").format(str(e)), ValidationError)
	
	# Get user document
	try:
		user_doc = frappe.get_doc("User", login_manager.user)
	except Exception as e:
		frappe.throw(_("Error retrieving user information: {0}").format(str(e)), ValidationError)
	
	# Initialize response
	login_response = {
		"message": "Logged In",
		"home_page": "/app",
		"full_name": user_doc.full_name or user_doc.name,
		"sid": frappe.session.sid if hasattr(frappe.session, 'sid') else None
	}
	
	# Handle API credentials based on has_existing_token flag
	api_credentials = {}
	
	if has_existing_token:
		# Mobile app has existing token - don't generate new one
		api_credentials = {
			"token": None,
			"generated": False,
			"message": "Using existing API credentials."
		}
	else:
		# Mobile app doesn't have token - generate new credentials
		# If user already has api_key, we'll regenerate secret (since secret is hashed and can't be retrieved)
		try:
			# Check if user has existing API key
			has_api_key = bool(user_doc.api_key)
			
			# Generate API key and secret using Frappe's method
			api_secret = frappe.generate_hash(length=15)
			if not user_doc.api_key:
				api_key = frappe.generate_hash(length=15)
				user_doc.api_key = api_key
			else:
				api_key = user_doc.api_key
			user_doc.api_secret = api_secret
			user_doc.save(ignore_permissions=True)
			frappe.db.commit()
			
			# Format token as api_key:api_secret
			token = f"{api_key}:{api_secret}"
			api_credentials = {
				"token": token,
				"generated": True,
				"message": "API credentials generated successfully." if not has_api_key else "New API credentials generated. Old credentials are now invalid."
			}
		except Exception as e:
			frappe.throw(_("Error generating API credentials: {0}").format(str(e)), ValidationError)
	
	# Build final response
	response = {
		"login": login_response,
		"api_credentials": api_credentials
	}
	
	return response


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
	employee_code = employee.name
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
		required_to_upload_location_photo = getattr(department_doc, "custom_required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(department_doc, "custom_required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(department_doc, "custom_required_location_check_on_check_out", None)
		
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
		require_location_check_on_check_out = getattr(project_doc, "custom_required_location_check_on_check_out", None)
		
		# Check if settings fields exist in the doctype
		if not hasattr(project_doc, "custom_required_to_upload_location_photo") and \
		   not hasattr(project_doc, "custom_required_to_upload_client_bio_metric_photo") and \
		   not hasattr(project_doc, "custom_required_location_check_on_check_out"):
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
		required_to_upload_location_photo = getattr(department_doc, "custom_required_to_upload_location_photo", None)
		required_to_upload_client_bio_metric_photo = getattr(department_doc, "custom_required_to_upload_client_bio_metric_photo", None)
		require_location_check_on_check_out = getattr(department_doc, "custom_required_location_check_on_check_out", None)
		
		if not (hasattr(department_doc, "custom_required_to_upload_location_photo") or \
		        hasattr(department_doc, "custom_required_to_upload_client_bio_metric_photo") or \
		        hasattr(department_doc, "custom_required_location_check_on_check_out")):
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
		require_location_check_on_check_out = getattr(project_doc, "custom_required_location_check_on_check_out", None)
		
		if not (hasattr(project_doc, "custom_required_to_upload_location_photo") or \
		        hasattr(project_doc, "custom_required_to_upload_client_bio_metric_photo") or \
		        hasattr(project_doc, "custom_required_location_check_on_check_out")):
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
		action = "check-in" if log_type == "IN" else "check-out"
		frappe.throw(
			_("Location coordinates are required for {0}. Please enable GPS and try again.").format(action),
			ValidationError
		)
	
	try:
		latitude = float(latitude)
		longitude = float(longitude)
	except (ValueError, TypeError) as e:
		frappe.throw(
			_("Invalid location coordinates. Please ensure GPS is enabled and try again. Error: {0}").format(str(e)),
			ValidationError
		)
	
	# Validate coordinate ranges
	if not (-90 <= latitude <= 90):
		frappe.throw(
			_("Invalid latitude value. Latitude must be between -90 and 90 degrees."),
			ValidationError
		)
	if not (-180 <= longitude <= 180):
		frappe.throw(
			_("Invalid longitude value. Longitude must be between -180 and 180 degrees."),
			ValidationError
		)
	
	try:
		distance = get_distance_between_coordinates(
			branch_latitude, branch_longitude, latitude, longitude
		)
	except Exception as e:
		frappe.throw(
			_("Error calculating distance from branch location. Please try again. Error: {0}").format(str(e)),
			ValidationError
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
	# frappe.log_error(
	# 	f"DEBUG: _handle_photo_upload called - photo_type: {photo_type}, "
	# 	f"photo_data type: {type(photo_data)}, has_data: {bool(photo_data)}, "
	# 	f"employee_id: {employee_id}, checkin_id: {checkin_id}",
	# 	"Checkin Photo Upload Debug"
	# )
	
	if not photo_data:
		frappe.log_error(
			title="Checkin Photo Debug",
			message="_handle_photo_upload - photo_data is empty/None",
		)
		return None
	
	# If it's a file_id (already uploaded), return the file doc
	if isinstance(photo_data, str) and not photo_data.startswith("data:"):
		# Check if it's a valid file ID
		if frappe.db.exists("File", photo_data):
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"_handle_photo_upload - treating as file_id: {photo_data}",
			)
			return frappe.get_doc("File", photo_data)
		# If not a file ID, treat as base64
		frappe.log_error(
			title="Checkin Photo Debug",
			message="_handle_photo_upload - treating string as base64",
		)
	
	# Handle base64 encoded image
	if isinstance(photo_data, str):
		if photo_data.startswith("data:"):
			# Remove data:image/jpeg;base64, prefix
			photo_data = photo_data.split(",", 1)[1]
		
		try:
			file_bytes = base64.b64decode(photo_data)
			if not file_bytes or len(file_bytes) == 0:
				frappe.throw(
					_("Invalid image data. The photo appears to be empty. Please capture the photo again."),
					ValidationError
				)
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"_handle_photo_upload - decoded base64, size: {len(file_bytes)}",
			)
		except Exception as e:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"_handle_photo_upload - base64 decode error: {str(e)}",
			)
			frappe.throw(
				_("Invalid image format. Please ensure the photo is properly encoded and try again."),
				ValidationError
			)
	else:
		file_bytes = photo_data
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"_handle_photo_upload - using bytes directly, size: {len(file_bytes) if file_bytes else 0}",
		)
	
	# Generate filename
	from frappe.utils import now_datetime
	timestamp = now_datetime().strftime("%Y%m%d_%H%M%S")
	filename = f"{photo_type}_photo_{employee_id}_{timestamp}.jpg"
	
	frappe.log_error(
		title="Checkin Photo Debug",
		message=f"Calling save_file - filename: {filename}, checkin: {checkin_id}, size: {len(file_bytes) if file_bytes else 0}",
	)
	
	# Save file and attach to checkin
	try:
		if not file_bytes or len(file_bytes) == 0:
			frappe.throw(
				_("Photo file is empty. Please capture the photo again and try uploading."),
				ValidationError
			)
		
		# Validate file size (max 5MB as per documentation)
		max_size = 5 * 1024 * 1024  # 5MB in bytes
		if len(file_bytes) > max_size:
			frappe.throw(
				_("Photo file size exceeds the maximum limit of 5MB. Please compress the image and try again."),
				ValidationError
			)
		
		file_doc = save_file(
			fname=filename,
			content=file_bytes,
			dt="Employee Checkin",
			dn=checkin_id,
			is_private=0
		)
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"save_file successful - file_id: {file_doc.name if file_doc else 'None'}",
		)
	except ValidationError:
		# Re-raise validation errors as-is
		raise
	except Exception as e:
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"save_file error: {str(e)}",
		)
		frappe.throw(
			_("Error uploading photo. Please try again. If the problem persists, contact support."),
			ValidationError
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
	# Support multipart/form-data file uploads (e.g. Postman / mobile form-data)
	# If files are sent as real files instead of base64 strings, they will be
	# available on frappe.request.files, not in the named parameters above.
	try:
		request_files = getattr(frappe, "request", None) and getattr(frappe.request, "files", None)
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"request_files available: {request_files is not None}, keys: {list(request_files.keys()) if request_files else 'None'}",
		)
	except Exception as e:
		request_files = None
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"Error getting request_files: {str(e)}",
		)
	
	# Helper function to read bytes from FileStorage object
	def _read_file_storage(file_storage):
		"""Read bytes from a FileStorage object, handling stream position."""
		if not file_storage:
			return None
		try:
			# Reset stream to beginning in case it was partially read
			if hasattr(file_storage, 'stream') and hasattr(file_storage.stream, 'seek'):
				file_storage.stream.seek(0)
			# Use read() method directly on FileStorage, or stream.read()
			if hasattr(file_storage, 'read'):
				return file_storage.read()
			elif hasattr(file_storage, 'stream') and hasattr(file_storage.stream, 'read'):
				return file_storage.stream.read()
			else:
				return None
		except Exception as e:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Error reading file_storage stream: {str(e)}",
			)
			return None

	# Log initial state of photo parameters
	frappe.log_error(
		title="Checkin Photo Debug",
		message=(
			f"Initial params - loc_photo type: {type(location_photo)}, has_value: {bool(location_photo)}, "
			f"bio_photo type: {type(client_biometric_photo)}, has_value: {bool(client_biometric_photo)}, "
			f"loc_id: {location_photo_id}, bio_id: {client_biometric_photo_id}"
		),
	)

	# For location photo: handle different input types
	# 1. If location_photo is already bytes or base64 string, use it
	# 2. If location_photo is a FileStorage object, read from it
	# 3. If location_photo is None/empty, try to get from request_files
	if location_photo:
		# Check if it's a FileStorage object (from form_dict)
		if hasattr(location_photo, 'read') or (hasattr(location_photo, 'stream') and hasattr(location_photo.stream, 'read')):
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"location_photo is FileStorage object, reading bytes...",
			)
			location_photo = _read_file_storage(location_photo)
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Read location_photo from FileStorage, size: {len(location_photo) if location_photo else 0}",
			)
		# If it's already bytes or string, keep it as is
		elif isinstance(location_photo, (bytes, str)):
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"location_photo is already bytes/string, size: {len(location_photo) if location_photo else 0}",
			)
	# If location_photo is None/empty, try to get from request_files
	elif request_files:
		file_storage = request_files.get("location_photo")
		if file_storage:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Found location_photo in request_files, filename: {getattr(file_storage, 'filename', 'unknown')}",
			)
			location_photo = _read_file_storage(file_storage)
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Read location_photo from request_files, size: {len(location_photo) if location_photo else 0}",
			)
		else:
			frappe.log_error(
				title="Checkin Photo Debug",
				message="location_photo not found in request_files",
			)

	# For biometric photo: same logic
	if client_biometric_photo:
		# Check if it's a FileStorage object (from form_dict)
		if hasattr(client_biometric_photo, 'read') or (hasattr(client_biometric_photo, 'stream') and hasattr(client_biometric_photo.stream, 'read')):
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"client_biometric_photo is FileStorage object, reading bytes...",
			)
			client_biometric_photo = _read_file_storage(client_biometric_photo)
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Read client_biometric_photo from FileStorage, size: {len(client_biometric_photo) if client_biometric_photo else 0}",
			)
		# If it's already bytes or string, keep it as is
		elif isinstance(client_biometric_photo, (bytes, str)):
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"client_biometric_photo is already bytes/string, size: {len(client_biometric_photo) if client_biometric_photo else 0}",
			)
	# If client_biometric_photo is None/empty, try to get from request_files
	elif request_files:
		file_storage = request_files.get("client_biometric_photo")
		if file_storage:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Found client_biometric_photo in request_files, filename: {getattr(file_storage, 'filename', 'unknown')}",
			)
			client_biometric_photo = _read_file_storage(file_storage)
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Read client_biometric_photo from request_files, size: {len(client_biometric_photo) if client_biometric_photo else 0}",
			)
		else:
			frappe.log_error(
				title="Checkin Photo Debug",
				message="client_biometric_photo not found in request_files",
			)

	# Get employee record with clear error messages
	if employee_id:
		if not frappe.db.exists("Employee", employee_id):
			frappe.throw(
				_("Employee not found. Please check the employee ID and try again."),
				DoesNotExistError
			)
		try:
			employee = frappe.get_doc("Employee", employee_id)
		except Exception as e:
			frappe.throw(
				_("Error retrieving employee record: {0}").format(str(e)),
				DoesNotExistError
			)
	else:
		employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not employee_name:
			frappe.throw(
				_("Employee not found for user {0}. Please ensure your user account is linked to an employee record.").format(frappe.session.user),
				DoesNotExistError
			)
		try:
			employee = frappe.get_doc("Employee", employee_name)
		except Exception as e:
			frappe.throw(
				_("Error retrieving employee record: {0}").format(str(e)),
				DoesNotExistError
			)
	
	# Validate employee is active
	# The validate_active_employee function will throw a clear error if employee is inactive
	validate_active_employee(employee.name)
	
	# Validate log_type
	if not log_type or log_type not in ["IN", "OUT"]:
		frappe.throw(
			_("Invalid log_type. Must be 'IN' for check-in or 'OUT' for check-out."),
			ValidationError
		)
	
	# Get employee settings and branch info
	settings = _get_employee_settings(employee)
	
	# Validate location
	# For check-in: always required
	# For check-out: only if require_location_check_on_check_out is True
	if log_type == "IN":
		# Check-in: location is always required
		if not latitude or not longitude:
			frappe.throw(
				_("Location is required for check-in. Please provide latitude and longitude."),
				ValidationError
			)
		distance = _validate_location(
			latitude, longitude,
			settings["branch_latitude"],
			settings["branch_longitude"],
			settings["branch_radius"],
			log_type
		)
	elif settings["require_location_check_on_check_out"]:
		# Check-out: location required only if setting is true
		if not latitude or not longitude:
			frappe.throw(
				_("Location is required for check-out. Please provide latitude and longitude."),
				ValidationError
			)
		distance = _validate_location(
			latitude, longitude,
			settings["branch_latitude"],
			settings["branch_longitude"],
			settings["branch_radius"],
			log_type
		)
	else:
		# Check-out: location not required
		distance = None
	
	# Validate required photos
	location_photo_file = None
	client_biometric_photo_file = None
	
	# Validate required photos with clear error messages
	# Handle location photo
	if settings["required_to_upload_location_photo"]:
		if not location_photo and not location_photo_id:
			action = "check-in" if log_type == "IN" else "check-out"
			frappe.throw(
				_("Location photo is required for {0}. Please capture and upload a location photo before proceeding.").format(action),
				ValidationError
			)
		# Validate that if location_photo_id is provided, the file exists
		if location_photo_id and not frappe.db.exists("File", location_photo_id):
			frappe.throw(
				_("Location photo file not found. Please upload the photo again."),
				ValidationError
			)
	
	# Handle client biometric photo
	if settings["required_to_upload_client_bio_metric_photo"]:
		if not client_biometric_photo and not client_biometric_photo_id:
			action = "check-in" if log_type == "IN" else "check-out"
			frappe.throw(
				_("Client biometric photo is required for {0}. Please capture and upload a client biometric photo before proceeding.").format(action),
				ValidationError
			)
		# Validate that if client_biometric_photo_id is provided, the file exists
		if client_biometric_photo_id and not frappe.db.exists("File", client_biometric_photo_id):
			frappe.throw(
				_("Client biometric photo file not found. Please upload the photo again."),
				ValidationError
			)
	
	# Parse timestamp with clear error message
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
		except Exception as e:
			frappe.throw(
				_("Invalid timestamp format. Please use ISO 8601 format (e.g., 2025-01-27T09:15:30Z). Error: {0}").format(str(e)),
				ValidationError
			)
	else:
		checkin_time = get_datetime()
		# Remove microseconds as Employee Checkin doctype does
		checkin_time = checkin_time.replace(microsecond=0)
	
	# Ensure only one check-in and one check-out per employee per date
	# We consider the "date" component of checkin_time (already made naive above).
	from datetime import timedelta
	start_of_day = checkin_time.replace(hour=0, minute=0, second=0, microsecond=0)
	end_of_day = start_of_day + timedelta(days=1)
	
	existing_count = frappe.db.count(
		"Employee Checkin",
		filters={
			"employee": employee.name,
			"log_type": log_type,
			"time": ["between", [start_of_day, end_of_day]],
		},
	)
	if existing_count > 0:
		action = "check-in" if log_type == "IN" else "check-out"
		frappe.throw(
			_(
				"You already have a {0} record for {1}. Only one check-in and one check-out are allowed per day."
			).format(action, start_of_day.date().isoformat()),
			ValidationError,
		)
	
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
	
	# Insert the checkin record with proper error handling
	try:
		checkin_doc.insert()
		# Explicitly commit so that the record is guaranteed to be written
		# This is mainly to avoid any edge cases where the transaction might be left uncommitted
		frappe.db.commit()
	except frappe.DuplicateEntryError:
		frappe.throw(
			_("A check-in record already exists for this timestamp. Please wait a moment and try again, or use a different timestamp."),
			ValidationError
		)
	except Exception as e:
		# Catch any other validation errors from Employee Checkin doctype
		error_msg = str(e)
		if "duplicate" in error_msg.lower():
			frappe.throw(
				_("A check-in record already exists for this timestamp. Please wait a moment and try again."),
				ValidationError
			)
		else:
			# Re-raise with clearer message if possible
			frappe.throw(
				_("Error creating check-in record: {0}").format(error_msg),
				ValidationError
			)
	
	# Upload and/or link photos
	# Location photo: if a photo (or file id) is provided, always store/link it,
	# even if the setting "required_to_upload_location_photo" is disabled.
	frappe.log_error(
		title="Checkin Photo Debug",
		message=f"Before upload - loc_photo: {bool(location_photo)}, loc_id: {location_photo_id}, checkin: {checkin_doc.name}",
	)
	if location_photo:
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"Uploading location_photo, type: {type(location_photo)}, size: {len(location_photo) if isinstance(location_photo, (bytes, str)) else 'N/A'}",
		)
		location_photo_file = _handle_photo_upload(
			location_photo, employee.name, checkin_doc.name, "location"
		)
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"location_photo upload result - created: {location_photo_file is not None}, file_id: {location_photo_file.name if location_photo_file else 'None'}",
		)
	elif location_photo_id:
		# Link existing file
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"Linking existing file: {location_photo_id}",
		)
		if frappe.db.exists("File", location_photo_id):
			file_doc = frappe.get_doc("File", location_photo_id)
			file_doc.attached_to_doctype = "Employee Checkin"
			file_doc.attached_to_name = checkin_doc.name
			file_doc.save(ignore_permissions=True)
			location_photo_file = file_doc
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Linked location_photo_id: {location_photo_id}",
			)
		else:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"File not found for location_photo_id: {location_photo_id}",
			)
	else:
		frappe.log_error(
			title="Checkin Photo Debug",
			message="No location_photo or location_photo_id provided",
		)
	
	# Client biometric photo: same behavior
	frappe.log_error(
		title="Checkin Photo Debug",
		message=f"Before upload - bio_photo: {bool(client_biometric_photo)}, bio_id: {client_biometric_photo_id}",
	)
	if client_biometric_photo:
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"Uploading client_biometric_photo, type: {type(client_biometric_photo)}, size: {len(client_biometric_photo) if isinstance(client_biometric_photo, (bytes, str)) else 'N/A'}",
		)
		client_biometric_photo_file = _handle_photo_upload(
			client_biometric_photo, employee.name, checkin_doc.name, "biometric"
		)
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"client_biometric_photo upload result - created: {client_biometric_photo_file is not None}, file_id: {client_biometric_photo_file.name if client_biometric_photo_file else 'None'}",
		)
	elif client_biometric_photo_id:
		# Link existing file
		frappe.log_error(
			title="Checkin Photo Debug",
			message=f"Linking existing file: {client_biometric_photo_id}",
		)
		if frappe.db.exists("File", client_biometric_photo_id):
			file_doc = frappe.get_doc("File", client_biometric_photo_id)
			file_doc.attached_to_doctype = "Employee Checkin"
			file_doc.attached_to_name = checkin_doc.name
			file_doc.save(ignore_permissions=True)
			client_biometric_photo_file = file_doc
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"Linked client_biometric_photo_id: {client_biometric_photo_id}",
			)
		else:
			frappe.log_error(
				title="Checkin Photo Debug",
				message=f"File not found for client_biometric_photo_id: {client_biometric_photo_id}",
			)
	else:
		frappe.log_error(
			title="Checkin Photo Debug",
			message="No client_biometric_photo or client_biometric_photo_id provided",
		)

	# If custom Attach fields exist on Employee Checkin, populate them with file URLs
	# so that they show up in the form's "Location Photo" and "Client Bio Metric Photo" fields.
	# These are expected to be Data/Attach fields named:
	# - custom_location_photo
	# - custom_client_bio_metric_photo
	updated_values = {}
	if location_photo_file and hasattr(checkin_doc, "custom_location_photo"):
		updated_values["custom_location_photo"] = location_photo_file.file_url
	if client_biometric_photo_file and hasattr(checkin_doc, "custom_client_bio_metric_photo"):
		updated_values["custom_client_bio_metric_photo"] = client_biometric_photo_file.file_url
	if updated_values:
		frappe.db.set_value("Employee Checkin", checkin_doc.name, updated_values, update_modified=False)
	
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

