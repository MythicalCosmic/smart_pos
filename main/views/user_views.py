from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..services.user_service import UserService
from main.helpers.response import APIResponse
from main.helpers.request import parse_json_body


@csrf_exempt
@require_http_methods(["GET"])
def list_users(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    search = request.GET.get('search')
    role = request.GET.get('role')
    status = request.GET.get('status')
    order_by = request.GET.get('order_by', '-id')
    include_deleted = request.GET.get('include_deleted', 'false').lower() == 'true'
    
    result = UserService.get_all_users(
        page=page,
        per_page=per_page,
        search=search,
        role=role,
        status=status,
        order_by=order_by,
        include_deleted=include_deleted
    )
    
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_user(request, user_id):
    include_deleted = request.GET.get('include_deleted', 'false').lower() == 'true'
    result = UserService.get_user_by_id(user_id, include_deleted=include_deleted)
    
    if result['success']:
        return APIResponse.success(data=result['user'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def get_user_by_username(request, username):
    result = UserService.get_user_by_username(username)
    
    if result['success']:
        return APIResponse.success(data=result['user'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    required = ['first_name', 'last_name', 'password']
    missing = [field for field in required if not data.get(field)]
    
    if missing:
        return APIResponse.validation_error(
            errors={field: f'{field} is required' for field in missing},
            message=f'Missing required fields: {", ".join(missing)}'
        )
    
    result = UserService.create_user(
        first_name=data['first_name'],
        last_name=data['last_name'],
        password=data['password'],
        role=data.get('role', 'USER'),
        status=data.get('status', 'ACTIVE'),
        email=data.get('email'),
    )
    
    if result['success']:
        return APIResponse.created(
            data=result['user'],
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def update_user(request, user_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    result = UserService.update_user(user_id, **data)
    
    if result['success']:
        return APIResponse.success(data=result['user'], message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_user(request, user_id):
    hard_delete = request.GET.get('hard', 'false').lower() == 'true'
    result = UserService.delete_user(user_id, hard_delete=hard_delete)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    if result.get('error_code') == 'HAS_OPEN_ORDERS':
        return APIResponse.error(
            message=result['message'],
            data={'open_orders_count': result.get('open_orders_count')}
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def restore_user(request, user_id):
    result = UserService.restore_user(user_id)
    
    if result['success']:
        return APIResponse.success(data=result.get('user'), message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["PATCH"])
def update_user_status(request, user_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    status = data.get('status')
    if not status:
        return APIResponse.validation_error(
            errors={'status': 'status is required'},
            message='Missing status field'
        )
    
    result = UserService.update_user_status(user_id, status)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["PATCH"])
def update_user_role(request, user_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    role = data.get('role')
    if not role:
        return APIResponse.validation_error(
            errors={'role': 'role is required'},
            message='Missing role field'
        )
    
    result = UserService.update_user_role(user_id, role)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def change_password(request, user_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return APIResponse.validation_error(
            errors={
                'current_password': 'current_password is required' if not current_password else None,
                'new_password': 'new_password is required' if not new_password else None,
            },
            message='Missing required fields'
        )
    
    result = UserService.change_password(user_id, current_password, new_password)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    if result.get('error_code') == 'INVALID_PASSWORD':
        return APIResponse.error(message=result['message'], status_code=401)
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def reset_password(request, user_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    new_password = data.get('new_password')
    if not new_password:
        return APIResponse.validation_error(
            errors={'new_password': 'new_password is required'},
            message='Missing new_password field'
        )
    
    result = UserService.reset_password(user_id, new_password)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    if result.get('error_code') == 'NOT_FOUND':
        return APIResponse.not_found(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def get_stats(request):
    result = UserService.get_user_stats()
    return APIResponse.success(data=result['stats'])


@csrf_exempt
@require_http_methods(["GET"])
def get_deleted_users(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    
    result = UserService.get_deleted_users(page=page, per_page=per_page)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_cashiers(request):
    active_only = request.GET.get('active_only', 'true').lower() == 'true'
    result = UserService.get_cashiers(active_only=active_only)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_admins(request):
    active_only = request.GET.get('active_only', 'true').lower() == 'true'
    result = UserService.get_admins(active_only=active_only)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_users_by_role(request, role):
    active_only = request.GET.get('active_only', 'true').lower() == 'true'
    result = UserService.get_users_by_role(role.upper(), active_only=active_only)
    
    if result['success']:
        return APIResponse.success(data=result)
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def search_users(request):
    query = request.GET.get('q', '')
    limit = int(request.GET.get('limit', 10))
    role = request.GET.get('role')
    active_only = request.GET.get('active_only', 'true').lower() == 'true'
    
    result = UserService.search_users(
        query=query,
        limit=limit,
        role=role.upper() if role else None,
        active_only=active_only
    )
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def check_username_available(request):
    username = request.GET.get('username', '')
    if not username:
        return APIResponse.validation_error(
            errors={'username': 'username is required'},
            message='Missing username parameter'
        )
    
    result = UserService.check_username_available(username)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def preview_username(request):
    first_name = request.GET.get('first_name', '')
    last_name = request.GET.get('last_name', '')
    
    if not first_name or not last_name:
        return APIResponse.validation_error(
            errors={
                'first_name': 'first_name is required' if not first_name else None,
                'last_name': 'last_name is required' if not last_name else None,
            },
            message='Missing required parameters'
        )
    
    result = UserService.preview_username(first_name, last_name)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["POST"])
def bulk_update_status(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    user_ids = data.get('user_ids', [])
    status = data.get('status')
    
    if not user_ids:
        return APIResponse.validation_error(
            errors={'user_ids': 'user_ids is required'},
            message='Missing user_ids'
        )
    
    if not status:
        return APIResponse.validation_error(
            errors={'status': 'status is required'},
            message='Missing status'
        )
    
    result = UserService.bulk_update_status(user_ids, status)
    
    if result['success']:
        return APIResponse.success(data={'updated_count': result['updated_count']}, message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    user_ids = data.get('user_ids', [])
    
    if not user_ids:
        return APIResponse.validation_error(
            errors={'user_ids': 'user_ids is required'},
            message='Missing user_ids'
        )
    
    result = UserService.bulk_delete(user_ids)
    
    if result['success']:
        return APIResponse.success(data={'deleted_count': result['deleted_count']}, message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def bulk_restore(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    user_ids = data.get('user_ids', [])
    
    if not user_ids:
        return APIResponse.validation_error(
            errors={'user_ids': 'user_ids is required'},
            message='Missing user_ids'
        )
    
    result = UserService.bulk_restore(user_ids)
    
    if result['success']:
        return APIResponse.success(
            data={'restored_count': result['restored_count'], 'errors': result.get('errors')},
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])