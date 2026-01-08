from django.views.decorators.csrf import csrf_exempt
from ..services.inkassa_service import InkassaService
from main.helpers.response import APIResponse
from main.helpers.request import parse_json_body
from main.helpers.require_login import user_required
from rest_framework.decorators import api_view


@csrf_exempt
@api_view(["GET"])
@user_required
def get_cash_balance(request):
    result = InkassaService.get_current_balance()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_current_stats(request):
    result = InkassaService.get_current_period_stats()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["POST"])
@user_required
def perform_inkassa(request):
    data, error = parse_json_body(request)
    if error:
        data = {}
    
    user = request.user
    
    if user.role not in ['CASHIER', 'ADMIN']:
        return APIResponse.error(
            message='Only cashiers and admins can perform inkassa',
            status_code=403
        )
    
    amount = data.get('amount') 
    notes = data.get('notes')
    inkass_type = data.get('inkass_type')  
    
    if not inkass_type:
        return APIResponse.error(
            message='inkass_type is required (CASH, UZCARD, HUMO, PAYME, or ALL)',
            status_code=400
        )
    
    valid_types = ['CASH', 'UZCARD', 'HUMO', 'PAYME', 'ALL']
    if inkass_type.upper() not in valid_types:
        return APIResponse.error(
            message=f'Invalid inkass_type. Must be one of: {", ".join(valid_types)}',
            status_code=400
        )
    
    result = InkassaService.perform_inkassa(
        cashier_id=user.id,
        amount_to_remove=amount,
        inkass_type=inkass_type.upper(),
        notes=notes
    )
    
    if result['success']:
        return APIResponse.success(
            data=result['inkassa'],
            message=result['message']
        )
    
    return APIResponse.error(message=result['message'])


@csrf_exempt
@api_view(["GET"])
@user_required
def get_inkassa_history(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    
    result = InkassaService.get_inkassa_history(page=page, per_page=per_page)
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_inkassa(request, inkassa_id):
    result = InkassaService.get_inkassa_by_id(inkassa_id)
    
    if result['success']:
        return APIResponse.success(data=result['inkassa'])
    
    return APIResponse.not_found(message=result['message'])