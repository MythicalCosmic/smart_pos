import json
from functools import wraps
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..services.auth_service import AuthService
from ..helpers.response import APIResponse
from ..helpers.request import get_client_ip, get_user_agent, get_token_from_request, parse_json_body


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    required = ['first_name', 'last_name', 'email', 'password']
    missing = [field for field in required if not data.get(field)]
    
    if missing:
        return APIResponse.validation_error(
            errors={field: f'{field} is required' for field in missing},
            message=f'Missing required fields: {", ".join(missing)}'
        )
    
    result = AuthService.register(
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data['email'],
        password=data['password'],
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request)
    )
    
    if result['success']:
        user = result['user']
        return APIResponse.created(
            data={
                'token': result['token'],
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                    'status': user.status
                }
            },
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'], status_code=400)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    missing = []
    if not data.get('email'):
        missing.append('email')
    if not data.get('password'):
        missing.append('password')
    
    if missing:
        return APIResponse.validation_error(
            errors={field: f'{field} is required' for field in missing},
            message=f'Missing required fields: {", ".join(missing)}'
        )
    
    result = AuthService.login(
        email=data['email'],
        password=data['password'],
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request)
    )
    
    if result['success']:
        user = result['user']
        return APIResponse.success(
            data={
                'token': result['token'],
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                    'status': user.status
                }
            },
            message=result['message']
        )
    
    return APIResponse.unauthorized(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def logout(request):
    token = get_token_from_request(request)
    if not token:
        return APIResponse.unauthorized(message='Token not provided')
    
    result = AuthService.logout(token)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.unauthorized(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def refresh_token(request):
    token = get_token_from_request(request)
    if not token:
        return APIResponse.unauthorized(message='Token not provided')
    
    result = AuthService.refresh_token(
        old_token=token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request)
    )
    
    if result['success']:
        return APIResponse.success(
            data={'token': result['token']},
            message=result['message']
        )
    
    return APIResponse.unauthorized(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def me(request):
    token = get_token_from_request(request)
    if not token:
        return APIResponse.unauthorized(message='Token not provided')
    
    user = AuthService.get_user_from_token(token)
    if not user:
        return APIResponse.unauthorized(message='Invalid or expired token')
    
    return APIResponse.success(
        data={
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'status': user.status,
            'last_login_at': str(user.last_login_at) if user.last_login_at else None
        },
        message='User data retrieved'
    )
