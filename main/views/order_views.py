from django.views.decorators.csrf import csrf_exempt
from ..services.order_service import OrderService
from main.helpers.response import APIResponse
from main.helpers.request import parse_json_body
from main.helpers.require_login import user_required
from rest_framework.decorators import api_view


@csrf_exempt
@api_view(["GET"])
@user_required
def list_orders(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    status = request.GET.get('status')
    user_id = request.GET.get('user_id')
    cashier_id = request.GET.get('cashier_id')
    order_by = request.GET.get('order_by', '-created_at')
    
    result = OrderService.get_all_orders(
        page=page,
        per_page=per_page,
        status=status,
        user_id=user_id,
        cashier_id=cashier_id,
        order_by=order_by
    )
    
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_order(request, order_id):
    result = OrderService.get_order_by_id(order_id)
    
    if result['success']:
        return APIResponse.success(data=result['order'])
    
    return APIResponse.not_found(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def create_order(request):
    data, error = parse_json_body(request)
    if error:
        return error
    
    # Get authenticated user from request
    user = request.user
    
    # Use authenticated user's ID as customer
    user_id = user.id
    
    # If user is a cashier, they are the cashier. Otherwise no cashier assigned yet
    cashier_id = user.id if user.role == 'CASHIER' else None
    
    items = data.get('items', [])
    
    if not items or len(items) == 0:
        return APIResponse.validation_error(
            errors={'items': 'At least one item is required'},
            message='Order must contain items'
        )
    
    for idx, item in enumerate(items):
        if 'product_id' not in item:
            return APIResponse.validation_error(
                errors={f'items[{idx}].product_id': 'product_id is required'},
                message=f'Item {idx} missing product_id'
            )
        if 'quantity' not in item or item['quantity'] <= 0:
            return APIResponse.validation_error(
                errors={f'items[{idx}].quantity': 'quantity must be greater than 0'},
                message=f'Invalid quantity for item {idx}'
            )
    
    result = OrderService.create_order(
        user_id=user_id,
        items=items,
        cashier_id=cashier_id
    )
    
    if result['success']:
        return APIResponse.created(
            data={
                'order_id': result['order'].id,
                'display_id': result['order'].display_id
            },
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def add_item(request, order_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    if not product_id:
        return APIResponse.validation_error(
            errors={'product_id': 'product_id is required'},
            message='Missing product_id field'
        )
    
    if quantity <= 0:
        return APIResponse.validation_error(
            errors={'quantity': 'quantity must be greater than 0'},
            message='Invalid quantity'
        )
    
    result = OrderService.add_item_to_order(order_id, product_id, quantity)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["PATCH"])
@user_required
def update_item(request, order_id, item_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    quantity = data.get('quantity')
    
    if not quantity or quantity <= 0:
        return APIResponse.validation_error(
            errors={'quantity': 'quantity must be greater than 0'},
            message='Invalid quantity'
        )
    
    result = OrderService.update_order_item(order_id, item_id, quantity)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["DELETE"])
@user_required
def remove_item(request, order_id, item_id):
    result = OrderService.remove_item_from_order(order_id, item_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["PATCH"])
@user_required
def update_status(request, order_id):
    data, error = parse_json_body(request)
    if error:
        return error
    
    status = data.get('status')
    
    if not status:
        return APIResponse.validation_error(
            errors={'status': 'status is required'},
            message='Missing status field'
        )
    
    # Get authenticated user's ID as cashier if they're a cashier
    user = request.user
    cashier_id = user.id if user.role == 'CASHIER' else None
    
    result = OrderService.update_order_status(order_id, status, cashier_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def pay_order(request, order_id):
    """Mark order as paid - automatically uses authenticated cashier"""
    user = request.user
    
    # Only cashiers can mark orders as paid
    if user.role != 'ADMIN':
        return APIResponse.error(
            message='Only cashiers can process payments',
            status_code=403
        )
    
    result = OrderService.update_order_status(order_id, 'PAID', user.id)
    
    if result['success']:
        return APIResponse.success(message='Order paid successfully')
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def mark_ready(request, order_id):
    """Chef marks order as ready/finished"""
    result = OrderService.mark_order_ready(order_id)
    
    if result['success']:
        return APIResponse.success(message=result['message'])
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def cancel_order(request, order_id):
    """Cancel order"""
    result = OrderService.update_order_status(order_id, 'CANCELED')
    
    if result['success']:
        return APIResponse.success(message='Order canceled successfully')
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["GET"])
def client_display(request):
    """
    Public endpoint for CLIENT display screen
    Shows:
    - Processing: OPEN or PAID orders (not ready yet)
    - Finished: READY orders from last 5 minutes
    """
    result = OrderService.get_client_display_orders()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
def chef_display(request):
    """
    Public endpoint for CHEF display screen
    Shows only PAID orders that need to be prepared
    """
    result = OrderService.get_chef_display_orders()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_stats(request):
    result = OrderService.get_order_stats()
    return APIResponse.success(data=result['stats'])