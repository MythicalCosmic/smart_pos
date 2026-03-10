from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.db import transaction
from main.services.auth_service import AuthService
from admins.services.base_service import ServiceResponse
from main.models import User, Session
from admins.helpers.auth_helpers import _clear_cookie, _get_client_ip, _get_session_key, _session_cookie
from admins.requests.auth_requests import (
    login_request,
    change_password_request,
    password_reset_request_request,
    password_reset_confirm_request,
    revoke_session_request,
)


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)

@csrf_exempt
@require_POST
def login(request):
    data, error = login_request(request)
    if error:
        return _json(error)

    result, status = AuthService.login(
        email=data["email"],
        password=data["password"],
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        device=data["device"],
    )

    response = JsonResponse(result, status=status)

    session_key = result.get("data", {}).get("session_key")
    if result.get("success") and session_key:
        _session_cookie(response, session_key)

    return response


@csrf_exempt
@require_POST
def logout(request):
    session_key = _get_session_key(request)
    if not session_key:
        return _json(ServiceResponse.unauthorized())

    result, status = AuthService.logout(session_key)
    response = JsonResponse(result, status=status)

    if result.get("success"):
        _clear_cookie(response)

    return response


@csrf_exempt
@require_POST
def logout_all(request):
    session_key = _get_session_key(request)
    if not session_key:
        return _json(ServiceResponse.unauthorized())

    result, status = AuthService.logout_all(session_key)
    response = JsonResponse(result, status=status)

    if result.get("success"):
        _clear_cookie(response)

    return response


@csrf_exempt
@require_GET
def me(request):
    session_key = _get_session_key(request)
    if not session_key:
        return _json(ServiceResponse.unauthorized())

    result, status = AuthService.me(session_key)
    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def change_password(request):
    session_key = _get_session_key(request)
    if not session_key:
        return _json(ServiceResponse.unauthorized())

    data, error = change_password_request(request)
    if error:
        return _json(error)

    result, status = AuthService.change_password(
        session_key=session_key,
        current_password=data["current_password"],
        new_password=data["new_password"],
    )

    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def password_reset_request(request):
    data, error = password_reset_request_request(request)
    if error:
        return _json(error)

    result, status = AuthService.request_password_reset(email=data["email"])
    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def password_reset_confirm(request):
    data, error = password_reset_confirm_request(request)
    if error:
        return _json(error)

    result, status = AuthService.reset_password(
        token=data["token"],
        new_password=data["new_password"],
    )

    return JsonResponse(result, status=status)


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def sessions(request):
    session_key = _get_session_key(request)
    if not session_key:
        return _json(ServiceResponse.unauthorized())

    if request.method == "GET":
        result, status = AuthService.get_active_sessions(session_key)
        return JsonResponse(result, status=status)

    if request.method == "DELETE":
        data, error = revoke_session_request(request)
        if error:
            return _json(error)

        result, status = AuthService.revoke_session(session_key, data["session_key"])
        return JsonResponse(result, status=status)