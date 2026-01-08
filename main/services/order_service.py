from django.db.models import Q, Sum, Count, Max, F, DecimalField
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db import transaction
from decimal import Decimal
from main.models import Order, OrderItem, Product, User, Category
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import Coalesce
from .inkassa_service import InkassaService
from django.db import transaction


class OrderService:
    
    ALLOWED_STATUSES = ['PREPARING', 'READY', 'CANCELLED']


    @staticmethod
    def parse_array_param(param):
        if not param:
            return None
        param = param.strip().strip('[]')
        if not param:
            return None
        return [item.strip().strip('"\'') for item in param.split(',') if item.strip()]
    
    @staticmethod
    @transaction.atomic
    def _get_next_display_id():
        last = (
            Order.objects
            .select_for_update()
            .order_by('-id')
            .only('display_id')
            .first()
        )

        if not last or not last.display_id:
            return 1

        return (last.display_id % 100) + 1
    
    
    @staticmethod
    def get_all_orders(page=1, per_page=20, statuses=None, payment_status=None, 
                       category_ids=None, user_id=None, cashier_id=None, order_by='-created_at'):
        
        queryset = Order.objects.select_related('user', 'cashier').prefetch_related('items__product').all()

        if payment_status:
            payment_status = payment_status.strip().upper()
            if payment_status == 'PAID':
                queryset = queryset.filter(is_paid=True)
            elif payment_status == 'UNPAID':
                queryset = queryset.filter(is_paid=False)

        if statuses:
            statuses_list = OrderService.parse_array_param(statuses)
            if statuses_list:
                valid_statuses = [choice[0] for choice in Order.Status.choices]
                statuses_list = [s.upper() for s in statuses_list if s.upper() in valid_statuses]
                if statuses_list:
                    queryset = queryset.filter(status__in=statuses_list)

        if category_ids:
            category_ids_list = OrderService.parse_array_param(category_ids)
            if category_ids_list:
                try:
                    category_ids_int = [int(cid) for cid in category_ids_list]
                    queryset = queryset.filter(
                        items__product__category_id__in=category_ids_int
                    ).distinct()
                except ValueError:
                    pass  

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
                'order_type': order.order_type,
                'phone_number': order.phone_number,
                'description': order.description,
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
                'is_paid': order.is_paid,
                'total_amount': str(order.total_amount),
                'items_count': order.items.count(),
                'items': list(order.items.values(
                    'id',
                    'product__id',
                    'product__name',
                    'product__category__id',
                    'product__category__name',
                    'quantity',
                    'price',
                    'ready_at'
                )),
                'paid_at': order.paid_at.isoformat() if order.paid_at else None,
                'ready_at': order.ready_at,
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat()
            })
        
        result = {
            'orders': orders,
            'filters': {
                'statuses': OrderService.parse_array_param(statuses),
                'category_ids': OrderService.parse_array_param(category_ids),
                'payment_status': payment_status,
            },
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
                prep_time = None
                if item.ready_at:
                    prep_time = (item.ready_at - order.created_at).total_seconds()
                
                items.append({
                    'id': item.id,
                    'product': {
                        'id': item.product.id,
                        'name': item.product.name,
                        'category': item.product.category.name
                    },
                    'quantity': item.quantity,
                    'price': str(item.price),
                    'subtotal': str(item.price * item.quantity),
                    'ready_at': item.ready_at.isoformat() if item.ready_at else None,
                    'is_ready': item.ready_at is not None,
                    'preparation_time_seconds': prep_time,
                    'preparation_time_formatted': OrderService._format_duration(prep_time) if prep_time else None
                })
            
            order_prep_time = None
            if order.ready_at:
                order_prep_time = (order.ready_at - order.created_at).total_seconds()
            
            result = {
                'success': True,
                'order': {
                    'id': order.id,
                    'display_id': order.display_id,
                    'order_type': order.order_type,
                    'phone_number': order.phone_number,
                    'description': order.description,
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
                    'is_paid': order.is_paid,
                    'paid_at': order.paid_at.isoformat() if order.paid_at else None,
                    'total_amount': str(order.total_amount),
                    'items': items,
                    'items_ready_count': sum(1 for item in items if item['is_ready']),
                    'items_total_count': len(items),
                    'created_at': order.created_at.isoformat(),
                    'updated_at': order.updated_at.isoformat(),
                    'ready_at': order.ready_at.isoformat() if order.ready_at else None,
                    'preparation_time_seconds': order_prep_time,
                    'preparation_time_formatted': OrderService._format_duration(order_prep_time) if order_prep_time else None
                }
            }
            
            return result
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
    
    @staticmethod
    def _format_duration(seconds):
        if seconds is None:
            return None
        
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    @staticmethod
    @transaction.atomic
    def create_order(user_id, items, order_type='HALL', phone_number=None, description=None, cashier_id=None, detail=None):
        try:
            if not User.objects.filter(id=user_id).exists():
                return {'success': False, 'message': 'User not found'}
            
            if cashier_id and not User.objects.filter(id=cashier_id, role='CASHIER').exists():
                return {'success': False, 'message': 'Invalid cashier'}
            
            if not items or len(items) == 0:
                return {'success': False, 'message': 'Order must have at least one item'}
            
            if order_type not in ['HALL', 'DELIVERY', 'PICKUP']:
                return {'success': False, 'message': 'Invalid order type. Must be HALL, DELIVERY, or PICKUP'}

            display_id = OrderService._get_next_display_id()
            
            order = Order.objects.create(
                user_id=user_id,
                cashier_id=cashier_id,
                display_id=display_id,
                order_type=order_type,
                phone_number=phone_number,
                description=description,
                status='PREPARING',
                is_paid=False,
                total_amount=0
            )
            
            total_amount = Decimal('0.00')
            
            for item_data in items:
                product_id = item_data.get('product_id')
                detail = item_data.get('detail') if 'detail' in item_data else None
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
                    detail=detail,
                    quantity=quantity,
                    price=product.price,
                    ready_at=None 
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
            
            if order.status != 'PREPARING':
                return {'success': False, 'message': 'Cannot modify order that is not in PREPARING status'}
            
            product = Product.objects.get(id=product_id)
            
            existing_item = OrderItem.objects.filter(order=order, product=product, ready_at__isnull=True).first()
            
            if existing_item:
                existing_item.quantity += quantity
                existing_item.save()
            else:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price,
                    ready_at=None
                )

            if order.ready_at:
                order.ready_at = None
                order.status = 'PREPARING'
                order.save(update_fields=['ready_at', 'status'])
            
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
            
            if order.status != 'PREPARING':
                return {'success': False, 'message': 'Cannot modify order that is not in PREPARING status'}
            
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
            
            if order.status != 'PREPARING':
                return {'success': False, 'message': 'Cannot modify order that is not in PREPARING status'}
            
            item = OrderItem.objects.get(id=item_id, order=order)
            item.delete()
            
            if order.items.count() == 0:
                order.delete()
                return {'success': True, 'message': 'Order deleted (no items remaining)'}

            OrderService._check_and_update_order_ready_status(order)
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

            if status not in OrderService.ALLOWED_STATUSES:
                return {
                    'success': False,
                    'message': f'Invalid status. Allowed: {", ".join(OrderService.ALLOWED_STATUSES)}'
                }

            if order.status == 'CANCELLED':
                return {'success': False, 'message': 'Cannot update cancelled order'}

            order.status = status

            if status == 'READY':
                order.ready_at = timezone.now()
                order.items.filter(ready_at__isnull=True).update(ready_at=timezone.now())

            if cashier_id is not None:
                order.cashier_id = cashier_id

            update_fields = ['status']
            if status == 'READY':
                update_fields.append('ready_at')
            if cashier_id is not None:
                update_fields.append('cashier_id')

            order.save(update_fields=update_fields)

            return {
                'success': True,
                'message': f'Order status updated to {status}',
                'order_id': order.id,
                'status': status
            }

        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}

        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to update status: {str(e)}'
            }

    @staticmethod
    @transaction.atomic
    def mark_item_ready(order_id, item_id):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status == 'CANCELLED':
                return {'success': False, 'message': 'Cannot modify cancelled order'}
            
            if order.status == 'READY':
                return {'success': False, 'message': 'Order is already marked as ready'}
            
            item = OrderItem.objects.get(id=item_id, order=order)
            
            if item.ready_at is not None:
                return {'success': False, 'message': 'Item is already marked as ready'}
            
            now = timezone.now()
            item.ready_at = now
            item.save(update_fields=['ready_at'])
            
            item_prep_time = (item.ready_at - order.created_at).total_seconds()
            
            all_items_ready, order_ready = OrderService._check_and_update_order_ready_status(order)
            
            order_prep_time = None
            if order_ready and order.ready_at:
                order_prep_time = (order.ready_at - order.created_at).total_seconds()

            items_status = []
            for order_item in order.items.all():
                prep_time = None
                if order_item.ready_at:
                    prep_time = (order_item.ready_at - order.created_at).total_seconds()
                items_status.append({
                    'id': order_item.id,
                    'product_name': order_item.product.name,
                    'quantity': order_item.quantity,
                    'is_ready': order_item.ready_at is not None,
                    'ready_at': order_item.ready_at.isoformat() if order_item.ready_at else None,
                    'preparation_time_seconds': prep_time,
                    'preparation_time_formatted': OrderService._format_duration(prep_time) if prep_time else None
                })
            
            return {
                'success': True,
                'message': 'Item marked as ready',
                'item': {
                    'id': item.id,
                    'product_name': item.product.name,
                    'ready_at': item.ready_at.isoformat(),
                    'preparation_time_seconds': item_prep_time,
                    'preparation_time_formatted': OrderService._format_duration(item_prep_time)
                },
                'order': {
                    'id': order.id,
                    'display_id': order.display_id,
                    'status': order.status,
                    'all_items_ready': all_items_ready,
                    'ready_at': order.ready_at.isoformat() if order.ready_at else None,
                    'preparation_time_seconds': order_prep_time,
                    'preparation_time_formatted': OrderService._format_duration(order_prep_time) if order_prep_time else None
                },
                'items_status': items_status
            }
            
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except OrderItem.DoesNotExist:
            return {'success': False, 'message': 'Order item not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to mark item as ready: {str(e)}'}
    
    @staticmethod
    @transaction.atomic
    def unmark_item_ready(order_id, item_id):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status == 'CANCELLED':
                return {'success': False, 'message': 'Cannot modify cancelled order'}
            
            item = OrderItem.objects.get(id=item_id, order=order)
            
            if item.ready_at is None:
                return {'success': False, 'message': 'Item is not marked as ready'}
            
            item.ready_at = None
            item.save(update_fields=['ready_at'])
            if order.status == 'READY':
                order.status = 'PREPARING'
                order.ready_at = None
                order.save(update_fields=['status', 'ready_at'])
            
            return {
                'success': True,
                'message': 'Item unmarked as ready',
                'item_id': item.id,
                'order_status': order.status
            }
            
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except OrderItem.DoesNotExist:
            return {'success': False, 'message': 'Order item not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to unmark item: {str(e)}'}
    
    @staticmethod
    def _check_and_update_order_ready_status(order):
        total_items = order.items.count()
        ready_items = order.items.filter(ready_at__isnull=False).count()
        
        all_items_ready = total_items > 0 and total_items == ready_items
        
        if all_items_ready and order.status != 'READY':
            order.status = 'READY'
            order.ready_at = timezone.now()
            order.save(update_fields=['status', 'ready_at'])
            return True, True
        
        return all_items_ready, False

    @staticmethod
    @transaction.atomic
    def mark_as_paid(order_id, admin_id):
        try:
            order = Order.objects.get(id=order_id)

            if order.status == 'CANCELLED':
                return {'success': False, 'message': 'Cancelled order cannot be paid'}

            if order.is_paid:
                return {'success': False, 'message': 'Order already paid'}

            order.is_paid = True
            order.paid_at = timezone.now()
            order.cashier_id = admin_id
            order.save(update_fields=['is_paid', 'paid_at', 'cashier_id'])

            InkassaService.add_to_register(order.total_amount)

            return {
                'success': True,
                'message': 'Order marked as paid',
                'is_paid': True
            }

        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}

    @staticmethod
    def mark_order_ready(order_id):
        try:
            order = Order.objects.get(id=order_id)
            
            if order.status == 'CANCELLED':
                return {'success': False, 'message': 'Cannot mark cancelled order as ready'}
            
            if order.status == 'READY':
                return {'success': False, 'message': 'Order is already ready'}
            
            now = timezone.now()
            order.status = 'READY'
            order.ready_at = now
            order.save(update_fields=['status', 'ready_at'])

            order.items.filter(ready_at__isnull=True).update(ready_at=now)

            order_prep_time = (order.ready_at - order.created_at).total_seconds()
            
            return {
                'success': True, 
                'message': 'Order marked as ready', 
                'status': order.status,
                'ready_at': order.ready_at.isoformat(),
                'preparation_time_seconds': order_prep_time,
                'preparation_time_formatted': OrderService._format_duration(order_prep_time)
            }
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to mark order as ready: {str(e)}'}
    
    @staticmethod
    def get_client_display_orders():
        five_minutes_ago = timezone.now() - timedelta(minutes=5)

        processing = Order.objects.filter(
            status='PREPARING'
        ).select_related('user').prefetch_related('items').order_by('created_at')

        finished = Order.objects.filter(
            status='READY',
            ready_at__gte=five_minutes_ago
        ).select_related('user').order_by('-ready_at')
        
        processing_list = []
        for order in processing:
            total_items = order.items.count()
            ready_items = order.items.filter(ready_at__isnull=False).count()
            
            processing_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'status': order.status,
                'is_paid': order.is_paid,
                'items_ready': ready_items,
                'items_total': total_items,
                'progress_percent': round((ready_items / total_items * 100) if total_items > 0 else 0, 1),
                'created_at': order.created_at.isoformat()
            })
        
        finished_list = []
        for order in finished:
            order_prep_time = None
            if order.ready_at:
                order_prep_time = (order.ready_at - order.created_at).total_seconds()
            
            finished_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'is_paid': order.is_paid,
                'completed_at': order.ready_at.isoformat(),
                'preparation_time_seconds': order_prep_time,
                'preparation_time_formatted': OrderService._format_duration(order_prep_time) if order_prep_time else None
            })
        
        result = {
            'success': True,
            'processing': processing_list,
            'finished': finished_list
        }
        
        return result
    
    @staticmethod
    def get_chef_display_orders():
        orders = Order.objects.filter(
            status='PREPARING'
        ).select_related('user').prefetch_related('items__product').order_by('created_at')
        
        orders_list = []
        for order in orders:
            items = []
            ready_count = 0
            for item in order.items.all():
                is_ready = item.ready_at is not None
                if is_ready:
                    ready_count += 1
                
                prep_time = None
                if item.ready_at:
                    prep_time = (item.ready_at - order.created_at).total_seconds()
                
                items.append({
                    'id': item.id,
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'detail': item.detail,
                    'is_ready': is_ready,
                    'ready_at': item.ready_at.isoformat() if item.ready_at else None,
                    'preparation_time_seconds': prep_time,
                    'preparation_time_formatted': OrderService._format_duration(prep_time) if prep_time else None
                })
            
            total_items = len(items)
            orders_list.append({
                'id': order.id,
                'display_id': order.display_id,
                'user': f"{order.user.first_name} {order.user.last_name}",
                'total_amount': str(order.total_amount),
                'is_paid': order.is_paid,
                'items': items,
                'items_ready': ready_count,
                'items_total': total_items,
                'progress_percent': round((ready_count / total_items * 100) if total_items > 0 else 0, 1),
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
        preparing_orders = Order.objects.filter(status='PREPARING').count()
        ready_orders = Order.objects.filter(status='READY').count()
        cancelled_orders = Order.objects.filter(status='CANCELLED').count()
        paid_orders = Order.objects.filter(is_paid=True).count()
        unpaid_orders = Order.objects.filter(is_paid=False).count()
        
        total_revenue = Order.objects.filter(is_paid=True).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        completed_orders = Order.objects.filter(
            status='READY',
            ready_at__isnull=False
        )
        
        avg_prep_time = None
        if completed_orders.exists():
            total_prep_time = 0
            count = 0
            for order in completed_orders:
                prep_time = (order.ready_at - order.created_at).total_seconds()
                total_prep_time += prep_time
                count += 1
            if count > 0:
                avg_prep_time = total_prep_time / count
        
        result = {
            'success': True,
            'stats': {
                'total_orders': total,
                'preparing_orders': preparing_orders,
                'ready_orders': ready_orders,
                'cancelled_orders': cancelled_orders,
                'paid_orders': paid_orders,
                'unpaid_orders': unpaid_orders,
                'total_revenue': str(total_revenue),
                'average_preparation_time_seconds': avg_prep_time,
                'average_preparation_time_formatted': OrderService._format_duration(avg_prep_time) if avg_prep_time else None
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