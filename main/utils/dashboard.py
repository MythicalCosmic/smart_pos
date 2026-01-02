from django.db.models import Sum, Count, Avg, Q, F
from django.db import models
from django.utils import timezone
from datetime import timedelta
from main.models import Order, Product, Category, User, Inkassa, CashRegister, OrderItem
import json


def dashboard_callback(request, context):
    """
    Custom dashboard callback for Unfold admin
    Provides data for charts and statistics
    """
    
    print("=" * 50)
    print("DASHBOARD CALLBACK CALLED!")
    print("=" * 50)
    
    # Get time filters from request
    period = request.GET.get('period', 'week')  # day, week, month, year
    
    # Calculate date ranges
    now = timezone.now()
    if period == 'day':
        start_date = now - timedelta(hours=24)
        interval = 'hour'
    elif period == 'week':
        start_date = now - timedelta(days=7)
        interval = 'day'
    elif period == 'month':
        start_date = now - timedelta(days=30)
        interval = 'day'
    elif period == 'year':
        start_date = now - timedelta(days=365)
        interval = 'month'
    else:
        start_date = now - timedelta(days=7)
        interval = 'day'
    
    # Get cash register
    cash_register = CashRegister.objects.first()
    current_balance = cash_register.current_balance if cash_register else 0
    
    # Get last inkassa
    last_inkassa = Inkassa.objects.order_by('-created_at').first()
    period_start = last_inkassa.period_end if last_inkassa else Order.objects.order_by('created_at').first().created_at if Order.objects.exists() else now
    
    # Orders statistics
    total_orders = Order.objects.filter(
        created_at__gte=start_date
    ).count()
    
    open_orders = Order.objects.filter(status='OPEN').count()
    paid_orders = Order.objects.filter(status='PAID').count()
    ready_orders = Order.objects.filter(status='READY').count()
    
    # Revenue statistics
    total_revenue = Order.objects.filter(
        status__in=['PAID', 'READY'],
        created_at__gte=start_date
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    avg_order_value = Order.objects.filter(
        status__in=['PAID', 'READY'],
        created_at__gte=start_date
    ).aggregate(avg=Avg('total_amount'))['avg'] or 0
    
    # Current period (since last inkassa) revenue
    current_period_revenue = Order.objects.filter(
        status__in=['PAID', 'READY'],
        created_at__gte=period_start
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Revenue chart data (Chart.js format)
    try:
        revenue_chart_data = get_revenue_chart_data(start_date, interval)
    except Exception as e:
        print(f"Error generating revenue chart: {e}")
        revenue_chart_data = {'labels': [], 'datasets': [{'label': 'Revenue', 'data': []}]}
    
    # Orders chart data
    try:
        orders_chart_data = get_orders_chart_data(start_date, interval)
    except Exception as e:
        print(f"Error generating orders chart: {e}")
        orders_chart_data = {'labels': [], 'datasets': [{'label': 'Orders', 'data': []}]}
    
    # Top products
    top_products = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__status__in=['PAID', 'READY']
    ).values(
        'product__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-total_quantity')[:5]
    
    # Category breakdown
    category_data = OrderItem.objects.filter(
        order__created_at__gte=start_date,
        order__status__in=['PAID', 'READY']
    ).values(
        'product__category__name'
    ).annotate(
        revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('-revenue')
    
    # Cashier performance
    cashier_performance = Order.objects.filter(
        status__in=['PAID', 'READY'],
        created_at__gte=start_date,
        cashier__isnull=False
    ).values(
        'cashier__first_name',
        'cashier__last_name'
    ).annotate(
        order_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-total_revenue')[:5]
    
    # Period filters for navigation
    filters = [
        {'label': 'Today', 'link': '?period=day'},
        {'label': 'Week', 'link': '?period=week'},
        {'label': 'Month', 'link': '?period=month'},
        {'label': 'Year', 'link': '?period=year'},
    ]
    
    context.update({
        'period': period,
        'filters': filters,
        'kpis': [
            {
                'title': 'Total Revenue',
                'metric': f'{total_revenue:,.0f} UZS',
                'footer': f'Last {period}',
                'icon': 'payments',
            },
            {
                'title': 'Total Orders',
                'metric': str(total_orders),
                'footer': f'Last {period}',
                'icon': 'shopping_cart',
            },
            {
                'title': 'Avg Order Value',
                'metric': f'{avg_order_value:,.0f} UZS',
                'footer': f'Last {period}',
                'icon': 'trending_up',
            },
            {
                'title': 'Cash Register',
                'metric': f'{current_balance:,.0f} UZS',
                'footer': f'Current period: {current_period_revenue:,.0f} UZS',
                'icon': 'account_balance_wallet',
            },
        ],
        'order_status_cards': [
            {
                'title': 'Open Orders',
                'count': open_orders,
                'color': 'blue',
            },
            {
                'title': 'Paid Orders',
                'count': paid_orders,
                'color': 'green',
            },
            {
                'title': 'Ready Orders',
                'count': ready_orders,
                'color': 'yellow',
            },
        ],
        'revenue_chart_json': json.dumps(revenue_chart_data),
        'orders_chart_json': json.dumps(orders_chart_data),
        'top_products': top_products,
        'category_data': category_data,
        'cashier_performance': cashier_performance,
    })
    
    
    return context


def get_revenue_chart_data(start_date, interval):
    """Generate revenue chart data for Chart.js"""
    labels = []
    data = []
    
    if interval == 'hour':
        # Last 24 hours
        for i in range(24):
            hour_start = start_date + timedelta(hours=i)
            hour_end = hour_start + timedelta(hours=1)
            labels.append(hour_start.strftime('%H:00'))
            
            revenue = Order.objects.filter(
                status__in=['PAID', 'READY'],
                created_at__gte=hour_start,
                created_at__lt=hour_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
    
    elif interval == 'day':
        # Last 7 or 30 days
        days = 7 if (timezone.now() - start_date).days <= 7 else 30
        for i in range(days):
            day_start = start_date + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            labels.append(day_start.strftime('%b %d'))
            
            revenue = Order.objects.filter(
                status__in=['PAID', 'READY'],
                created_at__gte=day_start,
                created_at__lt=day_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
    
    elif interval == 'month':
        # Last 12 months
        for i in range(12):
            month_start = start_date + timedelta(days=i*30)
            month_end = month_start + timedelta(days=30)
            labels.append(month_start.strftime('%b'))
            
            revenue = Order.objects.filter(
                status__in=['PAID', 'READY'],
                created_at__gte=month_start,
                created_at__lt=month_end
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            data.append(float(revenue))
    
    return {
        'labels': labels,
        'datasets': [{
            'label': 'Revenue',
            'data': data,
            'borderColor': '#10b981',
            'backgroundColor': 'rgba(16, 185, 129, 0.1)',
            'tension': 0.4,
        }]
    }


def get_orders_chart_data(start_date, interval):
    """Generate orders chart data for Chart.js"""
    labels = []
    data = []
    
    if interval == 'hour':
        for i in range(24):
            hour_start = start_date + timedelta(hours=i)
            hour_end = hour_start + timedelta(hours=1)
            labels.append(hour_start.strftime('%H:00'))
            
            count = Order.objects.filter(
                created_at__gte=hour_start,
                created_at__lt=hour_end
            ).count()
            data.append(count)
    
    elif interval == 'day':
        days = 7 if (timezone.now() - start_date).days <= 7 else 30
        for i in range(days):
            day_start = start_date + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            labels.append(day_start.strftime('%b %d'))
            
            count = Order.objects.filter(
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            data.append(count)
    
    elif interval == 'month':
        for i in range(12):
            month_start = start_date + timedelta(days=i*30)
            month_end = month_start + timedelta(days=30)
            labels.append(month_start.strftime('%b'))
            
            count = Order.objects.filter(
                created_at__gte=month_start,
                created_at__lt=month_end
            ).count()
            data.append(count)
    
    return {
        'labels': labels,
        'datasets': [{
            'label': 'Orders',
            'data': data,
            'borderColor': '#3b82f6',
            'backgroundColor': 'rgba(59, 130, 246, 0.1)',
            'tension': 0.4,
        }]
    }