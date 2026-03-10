from admins.services.base_service import Validator, ServiceResponse
from admins.helpers.auth_helpers import _parse_body


def _fail(errors: str) -> tuple:
    """(None, error_tuple) -- validation failed"""
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    """(clean_data, None) -- validation passed"""
    return data, None


def register_request(request) -> tuple:
    body = _parse_body(request)

    email = body.get("email", "")
    first_name = body.get("first_name", "")
    last_name = body.get("last_name", "")
    password = body.get("password", "")

    v = Validator()
    v.required(email, "Email").email(email)
    v.required(first_name, "First name").max_length(first_name, 30, "First name")
    v.required(last_name, "Last name").max_length(last_name, 30, "Last name")
    v.required(password, "Password").password_strength(password)

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "email": email.strip().lower(),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "password": password,
    })


def login_request(request) -> tuple:
    body = _parse_body(request)

    email = body.get("email", "")
    password = body.get("password", "")

    v = Validator()
    v.required(email, "Email")
    v.required(password, "Password").min_length(password, 8, "Password")

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "email": email.strip().lower(),
        "password": password,
        "device": body.get("device", ""),
    })


def change_password_request(request) -> tuple:
    body = _parse_body(request)

    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")

    v = Validator()
    v.required(current_password, "Current password")
    v.required(new_password, "New password").password_strength(new_password)

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "current_password": current_password,
        "new_password": new_password,
    })


def password_reset_request_request(request) -> tuple:
    body = _parse_body(request)
    email = body.get("email", "")

    v = Validator()
    v.required(email, "Email").email(email)

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({"email": email.strip().lower()})


def password_reset_confirm_request(request) -> tuple:
    body = _parse_body(request)

    token = body.get("token", "")
    new_password = body.get("new_password", "")

    v = Validator()
    v.required(token, "Token")
    v.required(new_password, "Password").password_strength(new_password)

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "token": token,
        "new_password": new_password,
    })


def revoke_session_request(request) -> tuple:
    body = _parse_body(request)
    session_key = body.get("session_key", "")

    v = Validator()
    v.required(session_key, "session_key")

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({"session_key": session_key})