from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from main.models import Order


def client_display(request):
    """
    Render the client display page with split screen:
    - Left side: Processing orders (OPEN or PAID)
    - Right side: Finished orders (READY, last 5 minutes)
    """
    return render(request, 'client/display.html')


def get_orders_data(request):
    """
    AJAX endpoint to fetch current order data.
    Returns JSON for real-time updates without page refresh.
    """
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    
    # Processing: OPEN or PAID orders (not ready yet)
    processing_orders = Order.objects.filter(
        status__in=['OPEN', 'PAID']
    ).select_related('user').order_by('created_at')
    
    # Finished: READY orders from last 5 minutes
    finished_orders = Order.objects.filter(
        status='READY',
        ready_at__gte=five_minutes_ago
    ).select_related('user').order_by('-ready_at')
    
    processing_list = [
        {
            'id': order.id,
            'display_id': order.display_id,
            'user': f"{order.user.first_name} {order.user.last_name}",
            'total_amount': str(order.total_amount),
            'status': order.status,
            'order_type': order.order_type,
            'created_at': order.created_at.isoformat()
        }
        for order in processing_orders
    ]
    
    finished_list = [
        {
            'id': order.id,
            'display_id': order.display_id,
            'user': f"{order.user.first_name} {order.user.last_name}",
            'total_amount': str(order.total_amount),
            'order_type': order.order_type,
            'completed_at': order.ready_at.isoformat() if order.ready_at else None
        }
        for order in finished_orders
    ]
    
    return JsonResponse({
        'processing': processing_list,
        'finished': finished_list
    })