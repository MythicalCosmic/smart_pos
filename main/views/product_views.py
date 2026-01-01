from django.views.decorators.csrf import csrf_exempt
from ..services.product_service import ProductService
from main.helpers.response import APIResponse
from main.helpers.request import parse_json_body
from main.helpers.require_login import user_required
from rest_framework.decorators import api_view


@csrf_exempt
@api_view(["GET"])
@user_required
def list_products(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    search = request.GET.get('search')
    category_id = request.GET.get('category_id')
    order_by = request.GET.get('order_by', '-created_at')
    
    result = ProductService.get_all_products(
        page=page,
        per_page=per_page,
        search=search,
        category_id=category_id,
        order_by=order_by
    )
    
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_products_by_category(request, category_id):
    result = ProductService.get_products_by_category(category_id)
    
    if result['success']:
        return APIResponse.success(data=result)
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@api_view(["GET"])
@user_required
def get_product(request, product_id):
    result = ProductService.get_product_by_id(product_id)
    
    if result['success']:
        return APIResponse.success(data=result['product'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def create_product(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    required = ['name', 'description', 'price', 'category_id']
    missing = [field for field in required if not data.get(field)]
    
    if missing:
        return APIResponse.validation_error(
            errors={field: f'{field} is required' for field in missing},
            message=f'Missing required fields: {", ".join(missing)}'
        )
    
    try:
        price = float(data['price'])
        if price <= 0:
            return APIResponse.validation_error(
                errors={'price': 'Price must be greater than 0'},
                message='Invalid price value'
            )
    except (ValueError, TypeError):
        return APIResponse.validation_error(
            errors={'price': 'Price must be a valid number'},
            message='Invalid price format'
        )
    
    result = ProductService.create_product(
        name=data['name'],
        description=data['description'],
        price=price,
        category_id=data['category_id']
    )
    
    if result['success']:
        return APIResponse.created(
            data={'product_id': result['product'].id},
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["PUT", "PATCH"])
@user_required
def update_product(request, product_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    if 'price' in data:
        try:
            price = float(data['price'])
            if price <= 0:
                return APIResponse.validation_error(
                    errors={'price': 'Price must be greater than 0'},
                    message='Invalid price value'
                )
            data['price'] = price
        except (ValueError, TypeError):
            return APIResponse.validation_error(
                errors={'price': 'Price must be a valid number'},
                message='Invalid price format'
            )
    
    result = ProductService.update_product(product_id, **data)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["DELETE"])
@user_required
def delete_product(request, product_id):
    result = ProductService.delete_product(product_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@api_view(["GET"])
@user_required
def get_stats(request):
    result = ProductService.get_product_stats()
    return APIResponse.success(data=result['stats'])