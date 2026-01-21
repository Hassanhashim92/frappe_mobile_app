### Frappe Mobile Application

Mobile app to manage erpnext activities

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app frappe_mobile_application
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/frappe_mobile_application
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### API Documentation (for Mobile Developers)

You can copy this section into MS Word or any other document editor and share it with your mobile developers.

---

## 1. Introduction

The `frappe_mobile_application` app provides a set of APIs for a mobile attendance application.

It is a separate Frappe app, but **HRMS is a prerequisite**, as it uses:

- Employee
- Employee Checkin
- Branch
- Department
- Project
- Company
- User
- File

All business logic (geofencing, photo requirements, etc.) is implemented in this app’s APIs.

You will call these APIs via HTTP using a base URL like:

`https://your-site-domain/api/method/frappe_mobile_application.api.<function_name>`

---

## 2. Authentication Model

There are two ways to authenticate:

- **Session-based**: Use username/password via `mobile_login` and keep the session cookie (`sid`).
- **Token-based (recommended)**: Use API key/secret as a token in the `Authorization` header.

### 2.1. Login API (`mobile_login`)

- **URL**: `/api/method/frappe_mobile_application.api.mobile_login`
- **Method**: `POST`
- **Auth**: Guest (no token required). Uses username/password.

**Purpose**

- Authenticate a user with ERPNext credentials.
- Optionally **generate** an API key + API secret and return them as a single `token` (`api_key:api_secret`).

**Request Parameters**

- `usr` (string, required): Username / email of ERPNext user.
- `pwd` (string, required): Password.
- `has_existing_token` (boolean or string, optional):
  - `false` / `"false"` / omitted:
    - Generate a new API secret (and API key if missing).
    - Return `token: "api_key:api_secret"`.
  - `true` / `"true"`:
    - Do **not** generate new keys.
    - Return `token: null` with a message to use existing token.

**Sample Request (JSON body)**

```json
{
  "usr": "user@example.com",
  "pwd": "MySecurePassword123",
  "has_existing_token": false
}
```

**Sample Success Response**

```json
{
  "login": {
    "message": "Logged In",
    "home_page": "/app",
    "full_name": "John Doe",
    "sid": "5f9f6c0ea3b4c3c"
  },
  "api_credentials": {
    "token": "85b63d87ba858a8:fc445087985ea1f",
    "generated": true,
    "message": "API credentials generated successfully."
  }
}
```

**Using the Token**

For subsequent API calls, send:

`Authorization: token 85b63d87ba858a8:fc445087985ea1f`

---

## 3. Employee Configuration API

### 3.1. `get_employee_configuration`

- **URL**: `/api/method/frappe_mobile_application.api.get_employee_configuration`
- **Method**: `GET` or `POST`
- **Auth**: Requires session or token.

**Purpose**

When the employee logs in, the mobile app calls this API to get:

- Basic employee information.
- Branch location and radius (for geofencing).
- Check-in / check-out rule settings (from Department or Project as per Company setting).

**Request Parameters**

- `employee_id` (string, optional):
  - If provided: use this Employee record.
  - If omitted: resolve Employee from the current logged-in user.

**Settings Resolution Logic**

1. Get the Employee.
2. Get Branch and location fields:
   - `Branch.custom_latitude`
   - `Branch.custom_longitude`
   - `Branch.custom_radius_in_meters`
3. Determine whether to read rules from Department or Project using:
   - `Company.custom_attendnace_validations_based_on_department` (boolean).
4. If **true** (use Department):
   - `Department.custom_required_to_upload_location_photo`
   - `Department.custom_required_to_upload_client_bio_metric_photo`
   - `Department.custom_required_location_check_on_check_out`
5. If **false** (use Project via Department.custom_project):
   - `Project.custom_required_to_upload_location_photo`
   - `Project.custom_required_to_upload_client_bio_metric_photo`
   - `Project.custom_required_location_check_on_check_out`
6. Any `None` values default to `false`.

**Sample Success Response**

```json
{
  "employee_id": "EMP-0001",
  "employee_name": "John Doe",
  "employee_code": "EMP-0001",
  "designation": "Software Engineer",
  "department": "DEPT-0001",
  "department_name": "IT Department",
  "company": "Raya Co Ltd",
  "branch": {
    "branch_id": "BR-001",
    "branch_name": "Head Office",
    "latitude": 24.7305898,
    "longitude": 46.8027571,
    "checkin_radius_meters": 100,
    "address": "Some address"
  },
  "settings": {
    "required_to_upload_location_photo": true,
    "required_to_upload_client_bio_metric_photo": false,
    "require_location_check_on_check_out": true,
    "settings_source": "department",
    "department_id": "DEPT-0001",
    "department_name": "IT Department",
    "project_id": "PROJ-0001",
    "project_name": "Project A"
  }
}
```

---

## 4. Check-in / Check-out Creation API

### 4.1. `create_checkin_checkout`

- **URL**: `/api/method/frappe_mobile_application.api.create_checkin_checkout`
- **Method**: `POST`
- **Auth**: Token or session.

**Purpose**

Create an `Employee Checkin` (IN/OUT) with all validations, geofencing, and photo rules for the mobile app.

**Important**: All validation errors are returned in the **minimal format**:

```json
{ "exception": "<human-readable message>" }
```

**Business Rules**

1. Employee:
   - Must exist and be active.
2. Log type:
   - `log_type` must be `"IN"` or `"OUT"`.
3. Location / geofencing:
   - For `IN`:
     - `latitude` and `longitude` required.
     - Must be within `radius` meters of branch (uses Branch latitude/longitude/radius).
   - For `OUT`:
     - If `require_location_check_on_check_out` is true → same as IN.
     - Else → location is optional.
4. Photos:
   - Controlled by settings from Department or Project:
     - `required_to_upload_location_photo`
     - `required_to_upload_client_bio_metric_photo`
   - If required:
     - Either file (multipart) or pre-uploaded file id must be provided.
5. Uniqueness per day:
   - Per employee:
     - Max 1 `"IN"` and 1 `"OUT"` per calendar date.
6. Timestamp:
   - ISO 8601.
   - Converted to naive UTC, microseconds removed.

**Request Parameters**

- `employee_id` (string, optional)
- `log_type` (string, required): `"IN"` or `"OUT"`.
- `latitude` (float)
- `longitude` (float)
- `device_id` (string, optional)
- `location_photo`:
  - Base64 string or multipart file.
- `client_biometric_photo`:
  - Base64 string or multipart file.
- `timestamp` (string, optional)
- `notes` (string, optional)
- `checkin_id` (string, optional)
- `location_photo_id` (string, optional, existing File name)
- `client_biometric_photo_id` (string, optional, existing File name)

**Sample Success Response**

```json
{
  "checkin_id": "EMP-CKIN-01-2026-000001",
  "employee_id": "EMP-0001",
  "employee_name": "John Doe",
  "log_type": "IN",
  "time": "2025-01-27T09:15:30",
  "latitude": 24.7305898,
  "longitude": 46.8027571,
  "shift": null,
  "shift_start": null,
  "shift_end": null,
  "attendance": null,
  "status": "success",
  "distance_from_branch_meters": 0.0,
  "location_photo_url": "/files/location_photo_EMP-0001_20250127_091530.jpg",
  "location_photo_id": "FILE-0001",
  "client_biometric_photo_url": "/files/biometric_photo_EMP-0001_20250127_091530.jpg",
  "client_biometric_photo_id": "FILE-0002"
}
```

**Sample Error Responses**

Minimal error format:

```json
{ "exception": "Location photo is required for check-in." }
```

More examples:

- Missing GPS:

```json
{ "exception": "Location is required for check-in. Please provide latitude and longitude." }
```

- Outside branch radius:

```json
{
  "exception": "You are 152.34 meters away from the branch location. Please move within 100 meters to check in."
}
```

- Duplicate check-in for same day:

```json
{
  "exception": "You have already completed your check-in for January 27, 2025. Only one check-in and one check-out are allowed per day."
}
```

- Unexpected issue:

```json
{
  "exception": "Something went wrong while creating your check-in. Please try again or contact support."
}
```

---

## 5. Check-in / Check-out History API

### 5.1. `get_employee_checkin_records`

- **URL**: `/api/method/frappe_mobile_application.api.get_employee_checkin_records`
- **Method**: `GET` or `POST`
- **Auth**: Token or session.

**Purpose**

Return a paginated list of check-in and check-out records for an employee, with optional filters and photo info.

**Request Parameters**

- `employee_id` (string, optional)
- `log_type` (string, optional): `"IN"` or `"OUT"`.
- `start_date` (string, optional): ISO 8601 or `YYYY-MM-DD`.
- `end_date` (string, optional): ISO 8601 or `YYYY-MM-DD`.
- `limit` (int, optional): default 100.
- `offset` (int, optional): default 0.

**Sample Success Response**

```json
{
  "records": [
    {
      "checkin_id": "EMP-CKIN-01-2026-000001",
      "employee_id": "EMP-0001",
      "employee_name": "John Doe",
      "log_type": "IN",
      "time": "2025-01-27T09:15:30",
      "latitude": 24.7305898,
      "longitude": 46.8027571,
      "device_id": "android-12345",
      "shift": null,
      "shift_start": null,
      "shift_end": null,
      "attendance": null,
      "skip_auto_attendance": 0,
      "location_photo_id": "FILE-0001",
      "location_photo_url": "/files/location_photo_EMP-0001_20250127_091530.jpg",
      "client_biometric_photo_id": "FILE-0002",
      "client_biometric_photo_url": "/files/biometric_photo_EMP-0001_20250127_091530.jpg"
    }
  ],
  "total_count": 10,
  "limit": 100,
  "offset": 0,
  "has_more": false
}
```

