from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..services.role_service import RoleService
from main.helpers.response import APIResponse


@csrf_exempt
@require_http_methods(["GET"])
def list_roles(request):
    result = RoleService.get_all_roles()
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_role(request, role_code):
    result = RoleService.get_role(role_code)
    
    if result['success']:
        return APIResponse.success(data=result['role'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def get_role_permissions(request, role_code):
    result = RoleService.get_role_permissions(role_code)
    
    if result['success']:
        return APIResponse.success(data=result)
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def check_permission(request, role_code, permission):
    result = RoleService.check_permission(role_code, permission)
    
    if result['success']:
        return APIResponse.success(data=result)
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def get_role_stats(request):
    result = RoleService.get_role_stats()
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_manageable_roles(request, role_code):
    result = RoleService.get_manageable_roles(role_code)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def validate_role(request):
    role_code = request.GET.get('role', '')
    is_valid = RoleService.is_valid_role(role_code)
    
    return APIResponse.success(data={
        'role': role_code,
        'is_valid': is_valid
    })