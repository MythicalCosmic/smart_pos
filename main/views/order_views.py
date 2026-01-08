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
    payment_status = request.GET.get('payment_status')
    statuses = request.GET.get('statuses')
    category_ids = request.GET.get('category_ids')
    
    user_id = request.GET.get('user_id')
    cashier_id = request.GET.get('cashier_id')
    order_by = request.GET.get('order_by', '-created_at')
    
    result = OrderService.get_all_orders(
        page=page,
        per_page=per_page,
        payment_status=payment_status,
        statuses=statuses,
        category_ids=category_ids,
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
    
    user = request.user
    user_id = user.id
    cashier_id = user.id if user.role == 'CASHIER' else None
    
    items = data.get('items', [])
    order_type = data.get('order_type', 'HALL')
    phone_number = data.get('phone_number')
    description = data.get('description')
    details = [item.get('detail') for item in items if 'detail' in item]


    
    if not items or len(items) == 0:
        return APIResponse.validation_error(
            errors={'items': 'At least one item is required'},
            message='Order must contain items'
        )
    
    if order_type not in ['HALL', 'DELIVERY', 'PICKUP']:
        return APIResponse.validation_error(
            errors={'order_type': 'Must be HALL, DELIVERY, or PICKUP'},
            message='Invalid order type'
        )
    
    if order_type == 'DELIVERY':
        if not phone_number:
            return APIResponse.validation_error(
                errors={'phone_number': 'Phone number is required for delivery orders'},
                message='Phone number required for delivery'
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
        order_type=order_type,
        phone_number=phone_number,
        description=description,
        detail=[details[idx] for idx in range(len(details))] if details else None,
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
    
    user = request.user
    cashier_id = user.id if user.role == 'CASHIER' else None
    
    result = OrderService.update_order_status(order_id, status, cashier_id)
    
    if result['success']:
        return APIResponse.success(
            data={'status': result.get('status')},
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def pay_order(request, order_id):
    user = request.user
    
    result = OrderService.mark_as_paid(order_id, user.id)
    
    if result['success']:
        return APIResponse.success(
            data={'is_paid': result.get('is_paid')},
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def mark_ready(request, order_id):
    result = OrderService.mark_order_ready(order_id)
    
    if result['success']:
        return APIResponse.success(
            data={
                'status': result.get('status'),
                'ready_at': result.get('ready_at'),
                'preparation_time_seconds': result.get('preparation_time_seconds'),
                'preparation_time_formatted': result.get('preparation_time_formatted')
            },
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def mark_item_ready(request, order_id, item_id):
    result = OrderService.mark_item_ready(order_id, item_id)
    
    if result['success']:
        return APIResponse.success(
            data={
                'item': result.get('item'),
                'order': result.get('order'),
                'items_status': result.get('items_status')
            },
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def unmark_item_ready(request, order_id, item_id):
    result = OrderService.unmark_item_ready(order_id, item_id)
    
    if result['success']:
        return APIResponse.success(
            data={
                'item_id': result.get('item_id'),
                'order_status': result.get('order_status')
            },
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["POST"])
@user_required
def cancel_order(request, order_id):
    result = OrderService.update_order_status(order_id, 'CANCELLED')
    
    if result['success']:
        return APIResponse.success(message='Order cancelled successfully')
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["GET"])
def client_display(request):
    result = OrderService.get_client_display_orders()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
def chef_display(request):
    result = OrderService.get_chef_display_orders()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_stats(request):
    result = OrderService.get_order_stats()
    return APIResponse.success(data=result['stats'])