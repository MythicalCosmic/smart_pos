from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..services.category_service import CategoryService
from main.helpers.response import APIResponse
from main.helpers.request import parse_json_body
from main.helpers.require_login import user_required
from rest_framework.decorators import api_view



@csrf_exempt
@api_view(["GET"])
@user_required
def list_categories(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    search = request.GET.get('search')
    status = request.GET.get('status')
    order_by = request.GET.get('order_by', 'sort_order')
    include_deleted = request.GET.get('include_deleted', False)
    
    result = CategoryService.get_all_categories(
        page=page,
        per_page=per_page,
        search=search,
        status=status,
        order_by=order_by,
        include_deleted=include_deleted
    )
    
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_category(request, category_id):
    result = CategoryService.get_category_by_id(category_id)
    
    if result['success']:
        return APIResponse.success(data=result['category'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def create_category(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    required = ['name', 'description', 'sort_order']
    missing = [field for field in required if not data.get(field)]
    
    if missing:
        return APIResponse.validation_error(
            errors={field: f'{field} is required' for field in missing},
            message=f'Missing required fields: {", ".join(missing)}'
        )
    
    result = CategoryService.create_category(
        name=data['name'],
        description=data['description'],
        sort_order=data['sort_order'],
        status=data.get('status', 'ACTIVE'),
        slug=data.get('slug')
    )
    
    if result['success']:
        return APIResponse.created(
            data={'category_id': result['category'].id},
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["PUT", "PATCH"])
@user_required
def update_category(request, category_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    result = CategoryService.update_category(category_id, **data)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["DELETE"])
@user_required
def delete_category(request, category_id):
    result = CategoryService.delete_category(category_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.not_found(message=result['message'])



@csrf_exempt
@api_view(["POST"])
@user_required
def restore_deleted_category(request, category_id):
    result = CategoryService.restore_category(category_id)
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.not_found(message=result['message'])

@csrf_exempt
@api_view(["PATCH"])
@user_required
def update_category_status(request, category_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    status = data.get('status')
    if not status:
        return APIResponse.validation_error(
            errors={'status': 'status is required'},
            message='Missing status field'
        )
    
    result = CategoryService.update_category_status(category_id, status)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])



@csrf_exempt
@api_view(["POST"])
@user_required
def reorder_categories(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    orders = data.get('orders')
    if not orders:
        return APIResponse.validation_error(
            errors={'orders': 'orders array is required'},
            message='Missing orders field'
        )
    
    result = CategoryService.reorder_categories(orders)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["GET"])
@user_required
def get_stats(request):
    result = CategoryService.get_category_stats()
    return APIResponse.success(data=result['stats'])