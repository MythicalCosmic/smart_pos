import json


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


def _get_token(request) -> str:
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""
