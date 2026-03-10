from admins.services.base_service import Validator, ServiceResponse
from admins.helpers.auth_helpers import _parse_body


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


def login_request(request) -> tuple:
    body = _parse_body(request)

    email = body.get("email", "")
    password = body.get("password", "")

    v = Validator()
    v.required(email, "Email")
    v.required(password, "Password")

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "email": email.strip().lower(),
        "password": password,
    })


def change_password_request(request) -> tuple:
    body = _parse_body(request)

    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")

    v = Validator()
    v.required(current_password, "Current password")
    v.required(new_password, "New password").min_length(new_password, 4, "New password")

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "current_password": current_password,
        "new_password": new_password,
    })
