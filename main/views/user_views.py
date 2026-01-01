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
    
    result = UserService.get_all_users(
        page=page,
        per_page=per_page,
        search=search,
        role=role,
        status=status,
        order_by=order_by
    )
    
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
def get_user(request, user_id):
    result = UserService.get_user_by_id(user_id)
    print(result)
    
    if result['success']:
        return APIResponse.success(data=result['user'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
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
    
    result = UserService.create_user(
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data['email'],
        password=data['password'],
        role=data.get('role', 'USER'),
        status=data.get('status', 'ACTIVE'),
    )
    
    if result['success']:
        return APIResponse.created(
            data={'user_id': result['user'].id},
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
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_user(request, user_id):
    result = UserService.delete_user(user_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.not_found(message=result['message'])


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
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@require_http_methods(["GET"])
def get_stats(request):
    result = UserService.get_user_stats()
    return APIResponse.success(data=result['stats'])