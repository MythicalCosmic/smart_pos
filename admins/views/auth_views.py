from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from admins.services.auth_service import AdminAuthService
from admins.services.base_service import ServiceResponse
from admins.helpers.auth_helpers import _get_client_ip, _get_token
from admins.requests.auth_requests import login_request, change_password_request


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_POST
def login(request):
    data, error = login_request(request)
    if error:
        return _json(error)

    result, status = AdminAuthService.login(
        email=data["email"],
        password=data["password"],
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )

    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def logout(request):
    token = _get_token(request)
    if not token:
        return _json(ServiceResponse.unauthorized())

    result, status = AdminAuthService.logout(token)
    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def logout_all(request):
    token = _get_token(request)
    if not token:
        return _json(ServiceResponse.unauthorized())

    result, status = AdminAuthService.logout_all(token)
    return JsonResponse(result, status=status)


@csrf_exempt
@require_GET
def me(request):
    token = _get_token(request)
    if not token:
        return _json(ServiceResponse.unauthorized())

    result, status = AdminAuthService.me(token)
    return JsonResponse(result, status=status)


@csrf_exempt
@require_POST
def change_password(request):
    token = _get_token(request)
    if not token:
        return _json(ServiceResponse.unauthorized())

    data, error = change_password_request(request)
    if error:
        return _json(error)

    result, status = AdminAuthService.change_password(
        token=token,
        current_password=data["current_password"],
        new_password=data["new_password"],
    )

    return JsonResponse(result, status=status)
