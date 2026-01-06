from django.db.models import Sum, Count, Avg, Q, F
from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime
from main.models import Order, Product, Category, User, Inkassa, CashRegister, OrderItem, Session
import json
import pytz


UZB_TZ = pytz.timezone('Asia/Tashkent')


def dashboard_callback(request, context):
    
    period = request.GET.get('period', 'week')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    time_from = request.GET.get('time_from', '00:00') or '00:00'
    time_to = request.GET.get('time_to', '23:59') or '23:59'
    
    now = timezone.now().astimezone(UZB_TZ)
    
    start_date = None
    end_date = None
    
    if date_from:
        try:
            hour_from, minute_from = 0, 0
            if time_from:
                time_parts = time_from.split(':')
                hour_from = int(time_parts[0])
                minute_from = int(time_parts[1]) if len(time_parts) > 1 else 0
            
            start_date = UZB_TZ.localize(
                datetime.strptime(date_from, '%Y-%m-%d').replace(
                    hour=hour_from, minute=minute_from, second=0, microsecond=0
                )
            )
        except (ValueError, IndexError):
            start_date = None
    
    if date_to:
        try:
            hour_to, minute_to = 23, 59
            if time_to:
                time_parts = time_to.split(':')
                hour_to = int(time_parts[0])
                minute_to = int(time_parts[1]) if len(time_parts) > 1 else 59
            
            end_date = UZB_TZ.localize(
                datetime.strptime(date_to, '%Y-%m-%d').replace(
                    hour=hour_to, minute=minute_to, second=59, microsecond=999999
                )
            )
        except (ValueError, IndexError):
            end_date = None
    
    if start_date or end_date:
        period = 'custom'
        
        if start_date and not end_date:
            end_date = now
        
        if end_date and not start_date:
            start_date = end_date - timedelta(days=7)
        
        total_seconds = (end_date - start_date).total_seconds()
        hours_diff = total_seconds / 3600
        days_diff = total_seconds / 86400
        
        if hours_diff <= 24:
            interval = 'hour'
        elif days_diff <= 31:
            interval = 'day'
        else:
            interval = 'month'
    elif period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
        interval = 'hour'
    elif period == 'week':
        start_date = now - timedelta(days=7)
        end_date = now
        interval = 'day'
    elif period == 'month':
        start_date = now - timedelta(days=30)
        end_date = now
        interval = 'day'
    elif period == 'year':
        start_date = now - timedelta(days=365)
        end_date = now
        interval = 'month'
    else:
        start_date = now - timedelta(days=7)
        end_date = now
        interval = 'day'
    
    date_filter = Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
    
    cash_register = CashRegister.objects.first()
    current_balance = cash_register.current_balance if cash_register else 0
    
    last_inkassa = Inkassa.objects.order_by('-created_at').first()
    period_start = last_inkassa.period_end if last_inkassa else Order.objects.order_by('created_at').first().created_at if Order.objects.exists() else now
    
    filtered_orders = Order.objects.filter(date_filter)
    
    total_orders = filtered_orders.count()
    
    preparing_orders = filtered_orders.filter(status='PREPARING').count()
    ready_orders = filtered_orders.filter(status='READY').count()
    canceled_orders = filtered_orders.filter(status='CANCELED').count()
    
    paid_orders = filtered_orders.filter(is_paid=True).count()
    unpaid_orders = filtered_orders.filter(is_paid=False).count()
    
    total_revenue = filtered_orders.filter(
        is_paid=True
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    avg_order_value = filtered_orders.filter(
        is_paid=True
    ).aggregate(avg=Avg('total_amount'))['avg'] or 0
    
    current_period_revenue = Order.objects.filter(
        is_paid=True,
        created_at__gte=period_start
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    active_session_threshold = now - timedelta(minutes=30)
    active_sessions = Session.objects.filter(
        last_activity__gte=active_session_threshold
    ).count()
    
    recent_logins = User.objects.filter(
        last_login_at__gte=start_date,
        last_login_at__lte=end_date
    ).order_by('-last_login_at')[:10]
    
    recent_logins_count = User.objects.filter(
        last_login_at__gte=start_date,
        last_login_at__lte=end_date
    ).count()
    
    current_user = None
    if hasattr(request, 'user') and request.user.is_authenticated:
        current_user = {
            'id': request.user.id,
            'name': f"{request.user.first_name} {request.user.last_name}",
            'email': request.user.email,
            'last_login': request.user.last_login_at.astimezone(UZB_TZ).strftime('%Y-%m-%d %H:%M') if hasattr(request.user, 'last_login_at') and request.user.last_login_at else None,
        }
    
    try:
        revenue_chart_data = get_revenue_chart_data(start_date, end_date, interval)
    except Exception as e:
        revenue_chart_data = {'labels': [], 'datasets': [{'label': 'Revenue', 'data': []}]}
    
    try:
        orders_chart_data = get_orders_chart_data(start_date, end_date, interval)
    except Exception as e:
        orders_chart_data = {'labels': [], 'datasets': [{'label': 'Orders', 'data': []}]}
    
    top_products = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__created_at__lte=end_date,
        order__is_paid=True
    ).values(
        'product__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-total_quantity')[:5]
    
    category_data = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__created_at__lte=end_date,
        order__is_paid=True
    ).values(
        'product__category__name'
    ).annotate(
        revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-revenue')
    
    cashier_performance = Order.objects.filter(
        date_filter,
        is_paid=True,
        cashier__isnull=False
    ).values(
        'cashier__first_name',
        'cashier__last_name'
    ).annotate(
        order_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-total_revenue')[:5]
    
    filters = [
        {'label': 'Today', 'link': '?period=day', 'active': period == 'day'},
        {'label': 'Week', 'link': '?period=week', 'active': period == 'week'},
        {'label': 'Month', 'link': '?period=month', 'active': period == 'month'},
        {'label': 'Year', 'link': '?period=year', 'active': period == 'year'},
    ]
    
    if period == 'custom':
        period_label = f"{start_date.strftime('%d.%m.%Y %H:%M')} — {end_date.strftime('%d.%m.%Y %H:%M')}"
    elif period == 'day':
        period_label = 'Today'
    elif period == 'week':
        period_label = 'Last 7 days'
    elif period == 'month':
        period_label = 'Last 30 days'
    elif period == 'year':
        period_label = 'Last 365 days'
    else:
        period_label = period
    
    date_from_value = start_date.strftime('%Y-%m-%d') if period == 'custom' and date_from else ''
    date_to_value = end_date.strftime('%Y-%m-%d') if period == 'custom' and date_to else ''
    time_from_value = time_from if period == 'custom' else '00:00'
    time_to_value = time_to if period == 'custom' else '23:59'
    
    context.update({
        'period': period,
        'period_label': period_label,
        'filters': filters,
        'current_user': current_user,
        'date_from': date_from_value,
        'date_to': date_to_value,
        'time_from': time_from_value,
        'time_to': time_to_value,
        'display_date_from': start_date.strftime('%d.%m.%Y') if start_date else '',
        'display_time_from': start_date.strftime('%H:%M') if start_date else '',
        'display_date_to': end_date.strftime('%d.%m.%Y') if end_date else '',
        'display_time_to': end_date.strftime('%H:%M') if end_date else '',
        'current_time': now.strftime('%d.%m.%Y %H:%M'),
        'kpis': [
            {
                'title': 'Total Revenue',
                'metric': f'{total_revenue:,.0f} UZS',
                'footer': period_label,
                'icon': 'payments',
            },
            {
                'title': 'Total Orders',
                'metric': str(total_orders),
                'footer': period_label,
                'icon': 'shopping_cart',
            },
            {
                'title': 'Avg Order Value',
                'metric': f'{avg_order_value:,.0f} UZS',
                'footer': period_label,
                'icon': 'trending_up',
            },
            {
                'title': 'Cash Register',
                'metric': f'{current_balance:,.0f} UZS',
                'footer': f'Since last inkassa: {current_period_revenue:,.0f} UZS',
                'icon': 'account_balance_wallet',
            },
        ],
        'order_status_cards': [
            {
                'title': 'Preparing',
                'count': preparing_orders,
                'color': 'orange',
            },
            {
                'title': 'Ready',
                'count': ready_orders,
                'color': 'yellow',
            },
            {
                'title': 'Canceled',
                'count': canceled_orders,
                'color': 'red',
            },
        ],
        'payment_status_cards': [
            {
                'title': 'Paid Orders',
                'count': paid_orders,
                'color': 'green',
            },
            {
                'title': 'Unpaid Orders',
                'count': unpaid_orders,
                'color': 'red',
            },
        ],
        'login_stats': {
            'active_sessions': active_sessions,
            'recent_logins_count': recent_logins_count,
        },
        'recent_logins': [
            {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'email': user.email,
                'last_login_at': user.last_login_at.astimezone(UZB_TZ).strftime('%d.%m.%Y %H:%M') if user.last_login_at else None,
                'last_login_api': user.last_login_api,
            }
            for user in recent_logins
        ],
        'revenue_chart_json': json.dumps(revenue_chart_data),
        'orders_chart_json': json.dumps(orders_chart_data),
        'top_products': top_products,
        'category_data': category_data,
        'cashier_performance': cashier_performance,
    })
    
    
    return context


def get_revenue_chart_data(start_date, end_date, interval):
    labels = []
    data = []
    
    if interval == 'hour':
        current = start_date.replace(minute=0, second=0, microsecond=0)
        while current <= end_date:
            hour_end = current + timedelta(hours=1)
            labels.append(current.strftime('%H:%M'))
            
            revenue = Order.objects.filter(
                is_paid=True,
                created_at__gte=current,
                created_at__lt=hour_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
            current = hour_end
    
    elif interval == 'day':
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            day_end = current + timedelta(days=1)
            labels.append(current.strftime('%d.%m'))
            
            revenue = Order.objects.filter(
                is_paid=True,
                created_at__gte=current,
                created_at__lt=day_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
            current = day_end
    
    elif interval == 'month':
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            if current.month == 12:
                month_end = current.replace(year=current.year + 1, month=1)
            else:
                month_end = current.replace(month=current.month + 1)
            labels.append(current.strftime('%b %Y'))
            
            revenue = Order.objects.filter(
                is_paid=True,
                created_at__gte=current,
                created_at__lt=month_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
            current = month_end
    
    return {
        'labels': labels,
        'datasets': [{
            'label': 'Revenue',
            'data': data,
            'borderColor': '#10b981',
            'backgroundColor': 'rgba(16, 185, 129, 0.1)',
            'tension': 0.4,
            'fill': True,
        }]
    }


def get_orders_chart_data(start_date, end_date, interval):
    labels = []
    data = []
    
    if interval == 'hour':
        current = start_date.replace(minute=0, second=0, microsecond=0)
        while current <= end_date:
            hour_end = current + timedelta(hours=1)
            labels.append(current.strftime('%H:%M'))
            
            count = Order.objects.filter(
                created_at__gte=current,
                created_at__lt=hour_end
            ).count()
            data.append(count)
            current = hour_end
    
    elif interval == 'day':
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            day_end = current + timedelta(days=1)
            labels.append(current.strftime('%d.%m'))
            
            count = Order.objects.filter(
                created_at__gte=current,
                created_at__lt=day_end
            ).count()
            data.append(count)
            current = day_end
    
    elif interval == 'month':
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            if current.month == 12:
                month_end = current.replace(year=current.year + 1, month=1)
            else:
                month_end = current.replace(month=current.month + 1)
            labels.append(current.strftime('%b %Y'))
            
            count = Order.objects.filter(
                created_at__gte=current,
                created_at__lt=month_end
            ).count()
            data.append(count)
            current = month_end
    
    return {
        'labels': labels,
        'datasets': [{
            'label': 'Orders',
            'data': data,
            'borderColor': '#3b82f6',
            'backgroundColor': 'rgba(59, 130, 246, 0.1)',
            'tension': 0.4,
            'fill': True,
        }]
    }