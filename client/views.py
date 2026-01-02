from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from main.models import Order


def client_display(request):
    return render(request, 'client/display.html')


def get_orders_data(request):
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    
    processing_orders = Order.objects.filter(
        status='PREPARING'
    ).select_related('user').order_by('created_at')
    
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
            'is_paid': order.is_paid,
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
            'is_paid': order.is_paid,
            'order_type': order.order_type,
            'completed_at': order.ready_at.isoformat() if order.ready_at else None
        }
        for order in finished_orders
    ]
    
    return JsonResponse({
        'processing': processing_list,
        'finished': finished_list
    })


def chef_display(request):
    return render(request, 'client/chef_display.html')


def get_chef_orders_data(request):
    orders = Order.objects.filter(
        status='PREPARING'
    ).select_related('user').prefetch_related('items__product').order_by('created_at')
    orders_list = [
        {
            'id': order.id,
            'display_id': order.display_id,
            'user': f"{order.user.first_name} {order.user.last_name}",
            'total_amount': str(order.total_amount),
            'is_paid': order.is_paid,
            'order_type': order.order_type,
            'status': order.status,
            'items': [
                {
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'detail': item.detail
                }
                for item in order.items.all()
            ],
            'created_at': order.created_at.isoformat()
        }
        for order in orders
    ]
    
    return JsonResponse({'orders': orders_list})


def chef_mark_ready(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        order = Order.objects.get(id=order_id)
        
        if order.status == 'CANCELLED':
            return JsonResponse({'success': False, 'message': 'Cannot mark cancelled order as ready'})
        
        if order.status == 'READY':
            return JsonResponse({'success': False, 'message': 'Order is already ready'})
        
        order.status = 'READY'
        order.ready_at = timezone.now()
        order.save(update_fields=['status', 'ready_at'])
        
        return JsonResponse({'success': True, 'message': 'Order marked as ready', 'status': order.status})
    
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'}, status=404)