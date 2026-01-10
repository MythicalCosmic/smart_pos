from django.db.models import Sum, Count, Avg, Q, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncHour, TruncDay, TruncMonth, ExtractHour
from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime
from main.models import Order, Product, Category, User, Inkassa, CashRegister, OrderItem, Session
import json
import pytz
from decimal import Decimal


UZB_TZ = pytz.timezone('Asia/Tashkent')


def dashboard_callback(request, context):
    period = request.GET.get('period', 'today')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    time_from = request.GET.get('time_from', '00:00') or '00:00'
    time_to = request.GET.get('time_to', '23:59') or '23:59'
    cashier_id = request.GET.get('cashier', '')
    
    now = timezone.now().astimezone(UZB_TZ)
    
    start_date, end_date, interval = calculate_date_range(
        period, date_from, date_to, time_from, time_to, now
    )
    
    if date_from or date_to:
        period = 'custom'
    
    date_filter = Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
    
    period_length = end_date - start_date
    prev_start = start_date - period_length
    prev_end = start_date
    prev_filter = Q(created_at__gte=prev_start) & Q(created_at__lt=prev_end)

    cash_register = CashRegister.objects.first()
    current_balance = cash_register.current_balance if cash_register else Decimal('0')
    
    last_inkassa = Inkassa.objects.order_by('-created_at').first()
    period_start_inkassa = last_inkassa.period_end if last_inkassa else (
        Order.objects.order_by('created_at').first().created_at 
        if Order.objects.exists() else now
    )
    
    filtered_orders = Order.objects.filter(date_filter)
    prev_orders = Order.objects.filter(prev_filter)
    
    total_orders = filtered_orders.count()
    prev_total_orders = prev_orders.count()

    status_counts = {
        'open': filtered_orders.filter(status='OPEN').count(),
        'preparing': filtered_orders.filter(status='PREPARING').count(),
        'ready': filtered_orders.filter(status='READY').count(),
        'completed': filtered_orders.filter(status='COMPLETED').count(),
        'canceled': filtered_orders.filter(status='CANCELED').count(),
    }

    paid_orders = filtered_orders.filter(is_paid=True).count()
    unpaid_orders = filtered_orders.filter(is_paid=False).count()
    
    total_revenue = filtered_orders.filter(
        is_paid=True
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    
    prev_revenue = prev_orders.filter(
        is_paid=True
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    revenue_growth = calculate_growth(total_revenue, prev_revenue)
    orders_growth = calculate_growth(total_orders, prev_total_orders)
    
    avg_order_value = filtered_orders.filter(
        is_paid=True
    ).aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0')
    
    prev_avg_order = prev_orders.filter(
        is_paid=True
    ).aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0')
    avg_order_growth = calculate_growth(avg_order_value, prev_avg_order)
    
    current_period_revenue = Order.objects.filter(
        is_paid=True,
        created_at__gte=period_start_inkassa
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    order_type_data = filtered_orders.values('order_type').annotate(
        count=Count('id'),
        revenue=Sum('total_amount', filter=Q(is_paid=True))
    ).order_by('-count')
    
    order_type_stats = {
        'HALL': {'count': 0, 'revenue': Decimal('0'), 'label': 'Dine-in', 'color': '#6366f1'},
        'DELIVERY': {'count': 0, 'revenue': Decimal('0'), 'label': 'Delivery', 'color': '#f59e0b'},
        'PICKUP': {'count': 0, 'revenue': Decimal('0'), 'label': 'Pickup', 'color': '#10b981'},
    }
    
    for item in order_type_data:
        if item['order_type'] in order_type_stats:
            order_type_stats[item['order_type']]['count'] = item['count']
            order_type_stats[item['order_type']]['revenue'] = item['revenue'] or Decimal('0')
    
    order_type_chart = {
        'labels': [order_type_stats[k]['label'] for k in order_type_stats],
        'data': [order_type_stats[k]['count'] for k in order_type_stats],
        'colors': [order_type_stats[k]['color'] for k in order_type_stats],
        'revenue': [float(order_type_stats[k]['revenue']) for k in order_type_stats],
    }

    product_sales = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__created_at__lte=end_date,
        order__is_paid=True
    ).values(
        'product__name',
        'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-total_quantity')

    total_items_sold = sum(item['total_quantity'] for item in product_sales)
    total_product_revenue = sum(float(item['total_revenue'] or 0) for item in product_sales)

    top_products_list = list(product_sales[:10])
    others_quantity = sum(item['total_quantity'] for item in product_sales[10:])
    others_revenue = sum(float(item['total_revenue'] or 0) for item in product_sales[10:])
    
    product_chart_colors = [
        '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6',
        '#ec4899', '#14b8a6', '#f97316', '#06b6d4', '#84cc16', '#6b7280'
    ]
    
    product_pie_data = {
        'labels': [p['product__name'] for p in top_products_list],
        'data': [p['total_quantity'] for p in top_products_list],
        'percentages': [
            round((p['total_quantity'] / total_items_sold * 100), 1) if total_items_sold > 0 else 0 
            for p in top_products_list
        ],
        'revenue': [float(p['total_revenue'] or 0) for p in top_products_list],
        'colors': product_chart_colors[:len(top_products_list)],
    }
    
    if others_quantity > 0:
        product_pie_data['labels'].append('Others')
        product_pie_data['data'].append(others_quantity)
        product_pie_data['percentages'].append(
            round((others_quantity / total_items_sold * 100), 1) if total_items_sold > 0 else 0
        )
        product_pie_data['revenue'].append(others_revenue)
        product_pie_data['colors'].append('#6b7280')
    
    category_sales = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__created_at__lte=end_date,
        order__is_paid=True
    ).values(
        'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-total_revenue')
    
    category_chart_colors = [
        '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#6366f1',
        '#ec4899', '#14b8a6', '#f97316', '#06b6d4', '#84cc16'
    ]
    
    category_pie_data = {
        'labels': [c['product__category__name'] or 'Uncategorized' for c in category_sales],
        'data': [float(c['total_revenue'] or 0) for c in category_sales],
        'quantities': [c['total_quantity'] for c in category_sales],
        'percentages': [
            round((float(c['total_revenue'] or 0) / total_product_revenue * 100), 1) 
            if total_product_revenue > 0 else 0 
            for c in category_sales
        ],
        'colors': category_chart_colors[:len(list(category_sales))],
    }
    
    all_cashiers = User.objects.filter(role__in=['CASHIER', 'ADMIN'])

    cashier_filter = date_filter
    if cashier_id:
        cashier_filter &= Q(cashier_id=cashier_id)
    
    cashier_performance = Order.objects.filter(
        cashier_filter,
        is_paid=True,
        cashier__isnull=False
    ).values(
        'cashier__id',
        'cashier__first_name',
        'cashier__last_name',
        'cashier__email'
    ).annotate(
        order_count=Count('id'),
        total_revenue=Sum('total_amount'),
        avg_order_value=Avg('total_amount'),
        hall_orders=Count('id', filter=Q(order_type='HALL')),
        delivery_orders=Count('id', filter=Q(order_type='DELIVERY')),
        pickup_orders=Count('id', filter=Q(order_type='PICKUP')),
    ).order_by('-total_revenue')
    
    best_cashier = cashier_performance.first() if cashier_performance else None

    cashier_shifts = Inkassa.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    ).select_related('cashier').order_by('-created_at')[:10]

    orders_with_ready_time = filtered_orders.filter(
        ready_at__isnull=False,
        status__in=['READY', 'COMPLETED']
    ).annotate(
        prep_time=ExpressionWrapper(
            F('ready_at') - F('created_at'),
            output_field=DurationField()
        )
    )
    
    avg_prep_time_seconds = 0
    if orders_with_ready_time.exists():
        total_prep_time = sum(
            (o.prep_time.total_seconds() for o in orders_with_ready_time if o.prep_time),
            0
        )
        avg_prep_time_seconds = total_prep_time / orders_with_ready_time.count() if orders_with_ready_time.count() > 0 else 0
    
    avg_prep_minutes = int(avg_prep_time_seconds // 60)
    avg_prep_seconds = int(avg_prep_time_seconds % 60)
    
    hourly_orders = filtered_orders.annotate(
        hour=ExtractHour('created_at')
    ).values('hour').annotate(
        count=Count('id'),
        revenue=Sum('total_amount', filter=Q(is_paid=True))
    ).order_by('hour')
    
    hourly_data = {str(i): {'count': 0, 'revenue': 0} for i in range(24)}
    peak_hour = {'hour': 0, 'count': 0}
    
    for h in hourly_orders:
        hourly_data[str(h['hour'])] = {
            'count': h['count'],
            'revenue': float(h['revenue'] or 0)
        }
        if h['count'] > peak_hour['count']:
            peak_hour = {'hour': h['hour'], 'count': h['count']}
    
    hourly_chart = {
        'labels': [f"{i:02d}:00" for i in range(24)],
        'data': [hourly_data[str(i)]['count'] for i in range(24)],
        'revenue': [hourly_data[str(i)]['revenue'] for i in range(24)],
    }
    
    revenue_chart_data = get_revenue_chart_data(start_date, end_date, interval)
    orders_chart_data = get_orders_chart_data(start_date, end_date, interval)
    
    weekly_growth_data = []
    for i in range(4):
        week_end = now - timedelta(weeks=i)
        week_start = week_end - timedelta(weeks=1)
        week_revenue = Order.objects.filter(
            is_paid=True,
            created_at__gte=week_start,
            created_at__lt=week_end
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        week_orders = Order.objects.filter(
            created_at__gte=week_start,
            created_at__lt=week_end
        ).count()
        weekly_growth_data.append({
            'week': f"Week {4-i}",
            'week_label': week_start.strftime('%d.%m') + ' - ' + week_end.strftime('%d.%m'),
            'revenue': float(week_revenue),
            'orders': week_orders,
        })
    weekly_growth_data.reverse()
    
    growth_chart = {
        'labels': [w['week_label'] for w in weekly_growth_data],
        'revenue': [w['revenue'] for w in weekly_growth_data],
        'orders': [w['orders'] for w in weekly_growth_data],
    }
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
    
    top_products = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__created_at__lte=end_date,
        order__is_paid=True
    ).values(
        'product__name',
        'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-total_quantity')[:10]
    
    filters = [
        {'label': 'Today', 'link': '?period=today', 'active': period == 'today', 'icon': 'today'},
        {'label': 'Yesterday', 'link': '?period=yesterday', 'active': period == 'yesterday', 'icon': 'event'},
        {'label': 'Week', 'link': '?period=week', 'active': period == 'week', 'icon': 'date_range'},
        {'label': 'Month', 'link': '?period=month', 'active': period == 'month', 'icon': 'calendar_month'},
        {'label': 'Year', 'link': '?period=year', 'active': period == 'year', 'icon': 'calendar_today'},
    ]
    
    period_label = get_period_label(period, start_date, end_date)

    context.update({
        'period': period,
        'period_label': period_label,
        'filters': filters,
        'current_time': now.strftime('%d.%m.%Y %H:%M'),
        'timezone_label': 'Asia/Tashkent (UTC+5)',
        
        'date_from': date_from,
        'date_to': date_to,
        'time_from': time_from,
        'time_to': time_to,
        'display_date_from': start_date.strftime('%d.%m.%Y'),
        'display_time_from': start_date.strftime('%H:%M'),
        'display_date_to': end_date.strftime('%d.%m.%Y'),
        'display_time_to': end_date.strftime('%H:%M'),
        
        'kpis': [
            {
                'title': 'Total Revenue',
                'metric': f'{total_revenue:,.0f}',
                'unit': 'UZS',
                'footer': period_label,
                'icon': 'payments',
                'color': 'emerald',
                'growth': revenue_growth,
            },
            {
                'title': 'Total Orders',
                'metric': str(total_orders),
                'unit': '',
                'footer': period_label,
                'icon': 'shopping_cart',
                'color': 'blue',
                'growth': orders_growth,
            },
            {
                'title': 'Avg Order Value',
                'metric': f'{avg_order_value:,.0f}',
                'unit': 'UZS',
                'footer': period_label,
                'icon': 'trending_up',
                'color': 'violet',
                'growth': avg_order_growth,
            },
            {
                'title': 'Cash Register',
                'metric': f'{current_balance:,.0f}',
                'unit': 'UZS',
                'footer': f'Since inkassa: {current_period_revenue:,.0f} UZS',
                'icon': 'account_balance_wallet',
                'color': 'amber',
                'growth': None,
            },
        ],
        
        'order_status_cards': [
            {'title': 'Open', 'count': status_counts['open'], 'color': 'blue', 'icon': 'pending'},
            {'title': 'Preparing', 'count': status_counts['preparing'], 'color': 'orange', 'icon': 'restaurant'},
            {'title': 'Ready', 'count': status_counts['ready'], 'color': 'amber', 'icon': 'done'},
            {'title': 'Completed', 'count': status_counts['completed'], 'color': 'green', 'icon': 'check_circle'},
            {'title': 'Canceled', 'count': status_counts['canceled'], 'color': 'red', 'icon': 'cancel'},
        ],
        
        'payment_status': {
            'paid': paid_orders,
            'unpaid': unpaid_orders,
            'paid_percentage': round(paid_orders / total_orders * 100, 1) if total_orders > 0 else 0,
        },
        
        'order_type_stats': order_type_stats,
        'order_type_chart_json': json.dumps(order_type_chart),
        
        'product_pie_json': json.dumps(product_pie_data),
        'total_items_sold': total_items_sold,
        'total_product_revenue': total_product_revenue,
 
        'category_pie_json': json.dumps(category_pie_data),
    
        'cashier_performance': list(cashier_performance[:10]),
        'best_cashier': best_cashier,
        'all_cashiers': all_cashiers,
        'selected_cashier': cashier_id,
        'cashier_shifts': cashier_shifts,
        
        'avg_prep_time': f'{avg_prep_minutes}:{avg_prep_seconds:02d}',
        'avg_prep_minutes': avg_prep_minutes,

        'peak_hour': peak_hour,
        'hourly_chart_json': json.dumps(hourly_chart),
    
        'growth_chart_json': json.dumps(growth_chart),
        'revenue_chart_json': json.dumps(revenue_chart_data),
        'orders_chart_json': json.dumps(orders_chart_data),
        
        'top_products': top_products,
        
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
    })
    
    return context


def calculate_date_range(period, date_from, date_to, time_from, time_to, now):
    
    start_date = None
    end_date = None
    interval = 'day'
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
        if start_date and not end_date:
            end_date = now
        if end_date and not start_date:
            start_date = end_date - timedelta(days=7)
        
        total_hours = (end_date - start_date).total_seconds() / 3600
        if total_hours <= 24:
            interval = 'hour'
        elif total_hours <= 24 * 31:
            interval = 'day'
        else:
            interval = 'month'
    else:
        if period == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            interval = 'hour'
        elif period == 'yesterday':
            yesterday = now - timedelta(days=1)
            start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
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
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            interval = 'hour'
    
    return start_date, end_date, interval


def calculate_growth(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((float(current) - float(previous)) / float(previous)) * 100, 1)


def get_period_label(period, start_date, end_date):
    if period == 'custom':
        return f"{start_date.strftime('%d.%m.%Y %H:%M')} — {end_date.strftime('%d.%m.%Y %H:%M')}"
    elif period == 'today':
        return 'Today'
    elif period == 'yesterday':
        return 'Yesterday'
    elif period == 'week':
        return 'Last 7 days'
    elif period == 'month':
        return 'Last 30 days'
    elif period == 'year':
        return 'Last 365 days'
    return period


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
            'backgroundColor': 'rgba(16, 185, 129, 0.15)',
            'tension': 0.4,
            'fill': True,
            'pointRadius': 4,
            'pointHoverRadius': 6,
            'pointBackgroundColor': '#10b981',
            'pointBorderColor': '#fff',
            'pointBorderWidth': 2,
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
            'borderColor': '#6366f1',
            'backgroundColor': 'rgba(99, 102, 241, 0.15)',
            'tension': 0.4,
            'fill': True,
            'pointRadius': 4,
            'pointHoverRadius': 6,
            'pointBackgroundColor': '#6366f1',
            'pointBorderColor': '#fff',
            'pointBorderWidth': 2,
        }]
    }