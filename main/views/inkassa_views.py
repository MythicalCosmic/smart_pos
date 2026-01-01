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
    """Get current cash register balance"""
    result = InkassaService.get_current_balance()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_current_stats(request):
    """Get statistics for current period (since last inkassa)"""
    result = InkassaService.get_current_period_stats()
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["POST"])
@user_required
def perform_inkassa(request):
    """
    Perform inkassa (cash withdrawal)
    Body can include:
    - amount: specific amount to withdraw (optional, defaults to all cash)
    - notes: any notes about this inkassa (optional)
    """
    data, error = parse_json_body(request)
    if error:
        data = {}
    
    user = request.user
    
    # Only cashiers and admins can perform inkassa
    if user.role not in ['CASHIER', 'ADMIN']:
        return APIResponse.error(
            message='Only cashiers and admins can perform inkassa',
            status_code=403
        )
    
    amount = data.get('amount')  # None means take all
    notes = data.get('notes')
    
    result = InkassaService.perform_inkassa(
        cashier_id=user.id,
        amount_to_remove=amount,
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
    """Get history of all inkassas"""
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    
    result = InkassaService.get_inkassa_history(page=page, per_page=per_page)
    return APIResponse.success(data=result)


@csrf_exempt
@api_view(["GET"])
@user_required
def get_inkassa(request, inkassa_id):
    """Get details of a specific inkassa"""
    result = InkassaService.get_inkassa_by_id(inkassa_id)
    
    if result['success']:
        return APIResponse.success(data=result['inkassa'])
    
    return APIResponse.not_found(message=result['message'])