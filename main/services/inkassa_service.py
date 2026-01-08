from django.db.models import Sum, Count, Avg, Q, F
from django.db import transaction
from decimal import Decimal
from main.models import Order, OrderItem, Product, Category, User, CashRegister, Inkassa
from django.utils import timezone


class InkassaService:
    
    @staticmethod
    def get_or_create_cash_register():
        register, created = CashRegister.objects.get_or_create(
            id=1,
            defaults={'current_balance': Decimal('0.00')}
        )
        return register
    
    @staticmethod
    def get_current_balance():
        register = InkassaService.get_or_create_cash_register()
        return {
            'success': True,
            'balance': str(register.current_balance),
            'last_updated': register.last_updated.isoformat()
        }
    
    @staticmethod
    @transaction.atomic
    def add_to_register(amount):
        register = InkassaService.get_or_create_cash_register()
        register.current_balance += Decimal(str(amount))
        register.save()
        return register.current_balance
    
    @staticmethod
    def get_last_inkassa():
        last_inkassa = Inkassa.objects.order_by('-created_at').first()
        return last_inkassa
    
    @staticmethod
    def get_period_start():
        last_inkassa = InkassaService.get_last_inkassa()
        if last_inkassa:
            return last_inkassa.period_end
        first_order = Order.objects.order_by('created_at').first()
        return first_order.created_at if first_order else timezone.now()
    
    @staticmethod
    def get_current_period_stats():
        period_start = InkassaService.get_period_start()
        register = InkassaService.get_or_create_cash_register()
        orders = Order.objects.filter(
            status__in=['PAID', 'READY'],
            updated_at__gte=period_start
        )
        
        total_orders = orders.count()
        total_revenue = orders.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')

        avg_order_value = orders.aggregate(
            avg=Avg('total_amount')
        )['avg'] or Decimal('0.00')

        paid_orders = orders.filter(status='PAID').count()
        ready_orders = orders.filter(status='READY').count()

        cashier_stats = orders.values(
            'cashier__first_name', 
            'cashier__last_name',
            'cashier_id'
        ).annotate(
            order_count=Count('id'),
            total_revenue=Sum('total_amount')
        ).order_by('-order_count')

        top_products = OrderItem.objects.filter(
            order__in=orders
        ).values(
            'product__name',
            'product_id'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('price') * F('quantity'))
        ).order_by('-total_quantity')[:10]

        category_revenue = OrderItem.objects.filter(
            order__in=orders
        ).values(
            'product__category__name'
        ).annotate(
            total_revenue=Sum(F('price') * F('quantity')),
            items_sold=Sum('quantity')
        ).order_by('-total_revenue')
        
        return {
            'success': True,
            'period_start': period_start.isoformat(),
            'current_time': timezone.now().isoformat(),
            'cash_register': {
                'current_balance': str(register.current_balance),
                'last_updated': register.last_updated.isoformat()
            },
            'summary': {
                'total_orders': total_orders,
                'paid_orders': paid_orders,
                'ready_orders': ready_orders,
                'total_revenue': str(total_revenue),
                'average_order_value': str(avg_order_value)
            },
            'cashier_performance': [
                {
                    'cashier_id': stat['cashier_id'],
                    'cashier_name': f"{stat['cashier__first_name']} {stat['cashier__last_name']}" if stat['cashier__first_name'] else 'Unknown',
                    'order_count': stat['order_count'],
                    'total_revenue': str(stat['total_revenue'])
                }
                for stat in cashier_stats
            ],
            'top_products': [
                {
                    'product_id': item['product_id'],
                    'product_name': item['product__name'],
                    'quantity_sold': item['total_quantity'],
                    'revenue': str(item['total_revenue'])
                }
                for item in top_products
            ],
            'category_revenue': [
                {
                    'category': cat['product__category__name'],
                    'revenue': str(cat['total_revenue']),
                    'items_sold': cat['items_sold']
                }
                for cat in category_revenue
            ]
        }
    
    @staticmethod
    @transaction.atomic
    def perform_inkassa(cashier_id, amount_to_remove=None, notes=None):
        try:
            cashier = User.objects.get(id=cashier_id)
            
            if cashier.role not in ['CASHIER', 'ADMIN']:
                return {
                    'success': False,
                    'message': 'Only cashiers and admins can perform inkassa'
                }
            
            register = InkassaService.get_or_create_cash_register()
            period_start = InkassaService.get_period_start()

            stats = InkassaService.get_current_period_stats()
            
            balance_before = register.current_balance

            if amount_to_remove is None:
                amount_to_remove = balance_before
            else:
                amount_to_remove = Decimal(str(amount_to_remove))

            if amount_to_remove > balance_before:
                return {
                    'success': False,
                    'message': f'Cannot remove {amount_to_remove}. Only {balance_before} in register.'
                }
            
            if amount_to_remove < 0:
                return {
                    'success': False,
                    'message': 'Amount must be positive'
                }
            
            balance_after = balance_before - amount_to_remove

            inkassa = Inkassa.objects.create(
                cashier=cashier,
                amount=amount_to_remove,
                balance_before=balance_before,
                balance_after=balance_after,
                period_start=period_start,
                total_orders=stats['summary']['total_orders'],
                total_revenue=Decimal(stats['summary']['total_revenue']),
                notes=notes
            )

            register.current_balance = balance_after
            register.save()
            
            return {
                'success': True,
                'message': 'Inkassa performed successfully',
                'inkassa': {
                    'id': inkassa.id,
                    'cashier': f"{cashier.first_name} {cashier.last_name}",
                    'amount_removed': str(amount_to_remove),
                    'balance_before': str(balance_before),
                    'balance_after': str(balance_after),
                    'period_covered': {
                        'start': period_start.isoformat(),
                        'end': inkassa.period_end.isoformat()
                    },
                    'statistics': {
                        'total_orders': inkassa.total_orders,
                        'total_revenue': str(inkassa.total_revenue)
                    }
                }
            }
        except User.DoesNotExist:
            return {'success': False, 'message': 'Cashier not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to perform inkassa: {str(e)}'}
    
    @staticmethod
    def get_inkassa_history(page=1, per_page=20):
        from django.core.paginator import Paginator
        
        inkassas = Inkassa.objects.select_related('cashier').order_by('-created_at')
        
        paginator = Paginator(inkassas, per_page)
        page_obj = paginator.get_page(page)
        
        inkassa_list = []
        for inkassa in page_obj.object_list:
            inkassa_list.append({
                'id': inkassa.id,
                'cashier': {
                    'id': inkassa.cashier.id if inkassa.cashier else None,
                    'name': f"{inkassa.cashier.first_name} {inkassa.cashier.last_name}" if inkassa.cashier else 'Unknown'
                },
                'amount': str(inkassa.amount),
                'balance_before': str(inkassa.balance_before),
                'balance_after': str(inkassa.balance_after),
                'period': {
                    'start': inkassa.period_start.isoformat() if inkassa.period_start else None,
                    'end': inkassa.period_end.isoformat()
                },
                'statistics': {
                    'total_orders': inkassa.total_orders,
                    'total_revenue': str(inkassa.total_revenue)
                },
                'notes': inkassa.notes,
                'created_at': inkassa.created_at.isoformat()
            })
        
        return {
            'success': True,
            'inkassas': inkassa_list,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_inkassas': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
    
    @staticmethod
    def get_inkassa_by_id(inkassa_id):
        try:
            inkassa = Inkassa.objects.select_related('cashier').get(id=inkassa_id)
            
            return {
                'success': True,
                'inkassa': {
                    'id': inkassa.id,
                    'cashier': {
                        'id': inkassa.cashier.id if inkassa.cashier else None,
                        'name': f"{inkassa.cashier.first_name} {inkassa.cashier.last_name}" if inkassa.cashier else 'Unknown'
                    },
                    'amount': str(inkassa.amount),
                    'balance_before': str(inkassa.balance_before),
                    'balance_after': str(inkassa.balance_after),
                    'period': {
                        'start': inkassa.period_start.isoformat() if inkassa.period_start else None,
                        'end': inkassa.period_end.isoformat()
                    },
                    'statistics': {
                        'total_orders': inkassa.total_orders,
                        'total_revenue': str(inkassa.total_revenue)
                    },
                    'notes': inkassa.notes,
                    'created_at': inkassa.created_at.isoformat()
                }
            }
        except Inkassa.DoesNotExist:
            return {'success': False, 'message': 'Inkassa not found'}