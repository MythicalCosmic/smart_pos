from django.db.models import Q, Sum, Count, Max, F, DecimalField
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db import transaction
from decimal import Decimal
from main.models import Order, OrderItem, Product, User
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import Coalesce


class OrderService:
    
    @staticmethod
    def _get_next_display_id():
        """Get next display ID (cycles from 1-100)"""
        last_order = Order.objects.aggregate(max_id=Max('display_id'))
        max_id = last_order['max_id']
        
        if max_id is None or max_id >= 99:
            return 1
        return max_id + 1
    
    @staticmethod
    def get_all_orders(page=1, per_page=20, status=None, user_id=None, cashier_id=None, order_by='-created_at'):
        
        queryset = Order.objects.select_related('user', 'cashier').prefetch_related('items__product').all()
        
        if status:
            queryset = queryset.filter(status=status)
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        if cashier_id:
            queryset = queryset.filter(cashier_id=cashier_id)
        
        queryset = queryset.order_by(order_by)
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        orders = []
        for order in page_obj.object_list:
            orders.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': {
                    'id': order.user.id,
                    'name': f"{order.user.first_name} {order.user.last_name}",
                    'email': order.user.email
                },
                'cashier': {
                    'id': order.cashier.id,
                    'name': f"{order.cashier.first_name} {order.cashier.last_name}"
                } if order.cashier else None,
                'status': order.status,
                'total_amount': str(order.total_amount),
                'items_count': order.items.count(),
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat()
            })
        
        result = {
            'orders': orders,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_orders': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
        return result
    
    @staticmethod
    def get_order_by_id(order_id):
        try:
            order = Order.objects.select_related('user', 'cashier').prefetch_related('items__product__category').get(id=order_id)
            
            items = []
            for item in order.items.all():
                items.append({
                    'id': item.id,
                    'product': {
                        'id': item.product.id,
                        'name': item.product.name,
                        'category': item.product.category.name
                    },
                    'quantity': item.quantity,
                    'price': str(item.price),
                    'subtotal': str(item.price * item.quantity)
                })
            
            result = {
                'success': True,
                'order': {
                    'id': order.id,
                    'display_id': order.display_id,
                    'user': {
                        'id': order.user.id,
                        'name': f"{order.user.first_name} {order.user.last_name}",
                        'email': order.user.email
                    },
                    'cashier': {
                        'id': order.cashier.id,
                        'name': f"{order.cashier.first_name} {order.cashier.last_name}"
                    } if order.cashier else None,
                    'status': order.status,
                    'total_amount': str(order.total_amount),
                    'items': items,
                    'created_at': order.created_at.isoformat(),
                    'updated_at': order.updated_at.isoformat(),
                    'ready_at': order.ready_at.isoformat() if order.ready_at else None
                }
            }
            
            return result
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
    
    @staticmethod
    @transaction.atomic
    def create_order(user_id, items, cashier_id=None):
        try:
            if not User.objects.filter(id=user_id).exists():
                return {'success': False, 'message': 'User not found'}
            
            if cashier_id and not User.objects.filter(id=cashier_id, role='CASHIER').exists():
                return {'success': False, 'message': 'Invalid cashier'}
            
            if not items or len(items) == 0:
                return {'success': False, 'message': 'Order must have at least one item'}
            
            # Get next display ID
            display_id = OrderService._get_next_display_id()
            
            order = Order.objects.create(
                user_id=user_id,
                cashier_id=cashier_id,
                display_id=display_id,
                status='OPEN',
                total_amount=0
            )
            
            total_amount = Decimal('0.00')
            
            for item_data in items:
                product_id = item_data.get('product_id')
                quantity = item_data.get('quantity', 1)
                
                if quantity <= 0:
                    raise ValueError('Quantity must be greater than 0')
                
                try:
                    product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    raise ValueError(f'Product with id {product_id} not found')
                
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price
                )
                
                total_amount += product.price * quantity
            
            order.total_amount = total_amount
            order.save()
            
            return {
                'success': True,
                'order': order,
                'message': 'Order created successfully'
            }
        except ValueError as e:
            return {'success': False, 'message': str(e)}
        except Exception as e:
            return {'success': False, 'message': f'Failed to create order: {str(e)}'}
    
    @staticmethod
    @transaction.atomic
    def add_item_to_order(order_id, product_id, quantity):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status not in ['OPEN', 'PAID']:
                return {'success': False, 'message': 'Cannot modify a closed or ready order'}
            
            product = Product.objects.get(id=product_id)
            
            existing_item = OrderItem.objects.filter(order=order, product=product).first()
            
            if existing_item:
                existing_item.quantity += quantity
                existing_item.save()
            else:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price
                )
            
            OrderService._recalculate_order_total(order)
            
            return {'success': True, 'message': 'Item added to order successfully'}
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except Product.DoesNotExist:
            return {'success': False, 'message': 'Product not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to add item: {str(e)}'}
    
    @staticmethod
    @transaction.atomic
    def update_order_item(order_id, item_id, quantity):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status not in ['OPEN', 'PAID']:
                return {'success': False, 'message': 'Cannot modify a closed or ready order'}
            
            item = OrderItem.objects.get(id=item_id, order=order)
            
            if quantity <= 0:
                return {'success': False, 'message': 'Quantity must be greater than 0'}
            
            item.quantity = quantity
            item.save()
            
            OrderService._recalculate_order_total(order)
            
            return {'success': True, 'message': 'Order item updated successfully'}
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except OrderItem.DoesNotExist:
            return {'success': False, 'message': 'Order item not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update item: {str(e)}'}
    
    @staticmethod
    @transaction.atomic
    def remove_item_from_order(order_id, item_id):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status not in ['OPEN', 'PAID']:
                return {'success': False, 'message': 'Cannot modify a closed or ready order'}
            
            item = OrderItem.objects.get(id=item_id, order=order)
            item.delete()
            
            if order.items.count() == 0:
                order.delete()
                return {'success': True, 'message': 'Order deleted (no items remaining)'}
            
            OrderService._recalculate_order_total(order)
            
            return {'success': True, 'message': 'Item removed from order successfully'}
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except OrderItem.DoesNotExist:
            return {'success': False, 'message': 'Order item not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to remove item: {str(e)}'}
    
    @staticmethod
    def update_order_status(order_id, status, cashier_id=None):
        try:
            order = Order.objects.get(id=order_id)
            
            if status not in ['OPEN', 'PAID', 'READY', 'CANCELED']:
                return {'success': False, 'message': 'Invalid status'}
            
            if status == 'PAID' and cashier_id:
                if not User.objects.filter(id=cashier_id).exists():
                    return {'success': False, 'message': 'Invalid cashier'}
                order.cashier_id = cashier_id
            
            # When order is marked as READY, set ready_at timestamp
            if status == 'READY' and order.status != 'READY':
                order.ready_at = timezone.now()
            
            order.status = status
            order.save()
            
            return {'success': True, 'message': f'Order status updated to {status}'}
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update status: {str(e)}'}
    
    @staticmethod
    def mark_order_ready(order_id):
        """Chef marks order as ready/finished"""
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status == 'READY':
                return {'success': False, 'message': 'Order is already marked as ready'}
            
            if order.status == 'CANCELED':
                return {'success': False, 'message': 'Cannot mark canceled order as ready'}
            
            order.status = 'READY'
            order.ready_at = timezone.now()
            order.save()
            
            return {'success': True, 'message': 'Order marked as ready'}
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to mark order as ready: {str(e)}'}
    
    @staticmethod
    def get_client_display_orders():
        """
        Get orders for CLIENT display screen
        - Processing: Orders that are OPEN or PAID (not ready yet)
        - Finished: Orders that are READY and within last 5 minutes
        """
        
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        
        # Processing: OPEN or PAID orders
        processing = Order.objects.filter(
            status__in=['OPEN', 'PAID']
        ).select_related('user').order_by('created_at')
        
        # Finished: READY orders from last 5 minutes
        finished = Order.objects.filter(
            status='READY',
            ready_at__gte=five_minutes_ago
        ).select_related('user').order_by('-ready_at')
        
        processing_list = []
        for order in processing:
            processing_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'status': order.status,
                'created_at': order.created_at.isoformat()
            })
        
        finished_list = []
        for order in finished:
            finished_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'completed_at': order.ready_at.isoformat()
            })
        
        result = {
            'success': True,
            'processing': processing_list,
            'finished': finished_list
        }
        
        return result
    
    @staticmethod
    def get_chef_display_orders():
        """
        Get orders for CHEF display screen
        - Shows all PAID orders that need to be prepared
        - Does NOT show OPEN, READY, or CANCELED orders
        """
        
        # Only show PAID orders - these need to be prepared
        orders = Order.objects.select_related('user').prefetch_related('items__product').order_by('created_at')
        
        orders_list = []
        for order in orders:
            items = []
            for item in order.items.all():
                items.append({
                    'product_name': item.product.name,
                    'quantity': item.quantity
                })
            
            orders_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'items': items,
                'created_at': order.created_at.isoformat()
            })
        
        result = {
            'success': True,
            'orders': orders_list
        }
        
        return result
    
    @staticmethod
    def get_order_stats():
        
        total = Order.objects.count()
        open_orders = Order.objects.filter(status='OPEN').count()
        paid_orders = Order.objects.filter(status='PAID').count()
        ready_orders = Order.objects.filter(status='READY').count()
        canceled_orders = Order.objects.filter(status='CANCELED').count()
        
        total_revenue = Order.objects.filter(status__in=['PAID', 'READY']).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        result = {
            'success': True,
            'stats': {
                'total_orders': total,
                'open_orders': open_orders,
                'paid_orders': paid_orders,
                'ready_orders': ready_orders,
                'canceled_orders': canceled_orders,
                'total_revenue': str(total_revenue)
            }
        }
        return result
    
    @staticmethod
    def _recalculate_order_total(order):
        total = order.items.aggregate(
            total=Coalesce(
                Sum(
                    F('price') * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                Decimal('0.00')
            )
        )['total']

        order.total_amount = total
        order.save(update_fields=['total_amount'])