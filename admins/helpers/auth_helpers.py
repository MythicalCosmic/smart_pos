import json
from django.http import JsonResponse


def _parse_body(request) -> dict:
    try:
        return json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _get_client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _get_session_key(request) -> str:
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Session "):
        return auth[8:].strip()
    return request.COOKIES.get("session_key", "")


def _session_cookie(response, session_key) -> JsonResponse:
    response.set_cookie(
        "session_key",
        session_key,
        max_age=72 * 3600,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response


def _clear_cookie(response) -> JsonResponse:
    response.delete_cookie("session_key")
    return response
