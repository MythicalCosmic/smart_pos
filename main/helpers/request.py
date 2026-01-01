import json
from .response import APIResponse


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


def get_user_agent(request):
    return request.META.get('HTTP_USER_AGENT', 'Unknown')[:30]


def get_token_from_request(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    return auth_header[7:] if auth_header.startswith('Bearer ') else None


def parse_json_body(request):
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, APIResponse.error(message='Invalid JSON', status_code=400)
    except Exception as e:
        return None, APIResponse.server_error(message=str(e))