from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F, Q
from django.utils import timezone
from datetime import datetime
import uuid as uuid_lib


class StockService:
    @staticmethod
    def is_enabled():
        """Check if stock system is enabled"""
        from stock.models import StockSettings
        try:
            settings = StockSettings.load()
            return settings.stock_enabled
        except:
            return False
    
    @staticmethod
    def get_settings():
        """Get all stock settings"""
        from stock.models import StockSettings
        settings = StockSettings.load()
        return {
            'stock_enabled': settings.stock_enabled,
            'production_enabled': settings.production_enabled,
            'purchasing_enabled': settings.purchasing_enabled,
            'multi_location_enabled': settings.multi_location_enabled,
            'track_cost': settings.track_cost,
            'track_batches': settings.track_batches,
            'track_expiry': settings.track_expiry,
            'allow_negative_stock': settings.allow_negative_stock,
            'auto_deduct_on_sale': settings.auto_deduct_on_sale,
            'deduct_on_order_status': settings.deduct_on_order_status,
            'costing_method': settings.costing_method,
            'default_location_id': settings.default_location_id,
        }
    
    @staticmethod
    def update_settings(**kwargs):
        """Update stock settings"""
        from stock.models import StockSettings
        settings = StockSettings.load()
        
        allowed_fields = [
            'stock_enabled', 'production_enabled', 'purchasing_enabled',
            'multi_location_enabled', 'track_cost', 'track_batches',
            'track_expiry', 'allow_negative_stock', 'auto_deduct_on_sale',
            'deduct_on_order_status', 'costing_method', 'default_location_id',
            'low_stock_alert_enabled', 'expiry_alert_enabled', 'expiry_alert_days',
        ]
        
        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(settings, key, value)
        
        settings.save()
        return {'success': True, 'message': 'Settings updated', 'settings': StockService.get_settings()}
    
    @staticmethod
    def toggle_stock(enabled: bool):
        """Master switch to enable/disable stock system"""
        return StockService.update_settings(stock_enabled=enabled)
    
    # ==================== STOCK LEVELS ====================
    
    @staticmethod
    def get_stock_level(stock_item_id, location_id=None):
        """Get current stock level for an item"""
        from stock.models import StockLevel, StockSettings
        
        if location_id is None:
            settings = StockSettings.load()
            location_id = settings.default_location_id
        
        try:
            level = StockLevel.objects.get(stock_item_id=stock_item_id, location_id=location_id)
            return {
                'success': True,
                'quantity': float(level.quantity),
                'reserved': float(level.reserved_quantity),
                'available': float(level.available_quantity),
                'pending_in': float(level.pending_in_quantity),
                'pending_out': float(level.pending_out_quantity),
            }
        except StockLevel.DoesNotExist:
            return {
                'success': True,
                'quantity': 0,
                'reserved': 0,
                'available': 0,
                'pending_in': 0,
                'pending_out': 0,
            }
    
    @staticmethod
    def get_all_stock_levels(location_id=None, category_id=None, low_stock_only=False):
        """Get all stock levels with filters"""
        from stock.models import StockLevel, StockItem, StockSettings
        
        if location_id is None:
            settings = StockSettings.load()
            location_id = settings.default_location_id
        
        queryset = StockLevel.objects.select_related('stock_item', 'location').filter(location_id=location_id)
        
        if category_id:
            queryset = queryset.filter(stock_item__category_id=category_id)
        
        if low_stock_only:
            queryset = queryset.filter(quantity__lte=F('stock_item__reorder_point'))
        
        levels = []
        for level in queryset:
            item = level.stock_item
            levels.append({
                'id': level.id,
                'stock_item_id': item.id,
                'stock_item_name': item.name,
                'sku': item.sku,
                'category': item.category.name if item.category else None,
                'quantity': float(level.quantity),
                'reserved': float(level.reserved_quantity),
                'available': float(level.available_quantity),
                'unit': item.base_unit.short_name,
                'min_level': float(item.min_stock_level),
                'reorder_point': float(item.reorder_point),
                'is_low_stock': level.quantity <= item.reorder_point,
                'cost_price': float(item.avg_cost_price),
                'total_value': float(level.quantity * item.avg_cost_price),
            })
        
        return {'success': True, 'levels': levels, 'count': len(levels)}
    
    # ==================== STOCK TRANSACTIONS ====================
    
    @staticmethod
    @transaction.atomic
    def adjust_stock(stock_item_id, quantity, movement_type, location_id=None, 
                     user_id=None, notes='', batch_id=None, reference_type='', reference_id=None):
        """
        Core method to adjust stock levels
        Positive quantity = IN, Negative quantity = OUT
        """
        from stock.models import StockItem, StockLevel, StockTransaction, StockBatch, StockSettings
        
        if not StockService.is_enabled():
            return {'success': True, 'message': 'Stock system disabled', 'skipped': True}
        
        settings = StockSettings.load()
        if location_id is None:
            location_id = settings.default_location_id
        
        try:
            item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            return {'success': False, 'message': 'Stock item not found', 'error_code': 'NOT_FOUND'}
        
        level, created = StockLevel.objects.get_or_create(
            stock_item_id=stock_item_id,
            location_id=location_id,
            defaults={'quantity': 0, 'reserved_quantity': 0}
        )
        
        quantity_before = level.quantity
        new_quantity = quantity_before + Decimal(str(quantity))
        
        if new_quantity < 0 and not settings.allow_negative_stock:
            return {
                'success': False, 
                'message': f'Insufficient stock. Available: {quantity_before}, Requested: {abs(quantity)}',
                'error_code': 'INSUFFICIENT_STOCK'
            }
        
        level.quantity = new_quantity
        level.last_movement_at = timezone.now()
        level.save()
        
        txn_number = f"TXN-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid_lib.uuid4().hex[:6].upper()}"
        
        unit_cost = item.avg_cost_price if settings.track_cost else Decimal('0')
        
        transaction_obj = StockTransaction.objects.create(
            transaction_number=txn_number,
            stock_item=item,
            location_id=location_id,
            batch_id=batch_id,
            movement_type=movement_type,
            quantity=abs(Decimal(str(quantity))),
            unit=item.base_unit,
            base_quantity=abs(Decimal(str(quantity))),
            quantity_before=quantity_before,
            quantity_after=new_quantity,
            unit_cost=unit_cost,
            total_cost=abs(Decimal(str(quantity))) * unit_cost,
            reference_type=reference_type,
            reference_id=reference_id,
            user_id=user_id,
            notes=notes,
        )
        
        return {
            'success': True,
            'message': 'Stock adjusted',
            'transaction_id': transaction_obj.id,
            'transaction_number': txn_number,
            'quantity_before': float(quantity_before),
            'quantity_after': float(new_quantity),
        }
    
    @staticmethod
    @transaction.atomic
    def deduct_for_order(order_id):
        """Deduct stock for all items in an order based on recipes/links"""
        from stock.models import ProductStockLink, StockSettings
        from main.models import Order, OrderItem
        
        if not StockService.is_enabled():
            return {'success': True, 'message': 'Stock system disabled', 'skipped': True}
        
        settings = StockSettings.load()
        if not settings.auto_deduct_on_sale:
            return {'success': True, 'message': 'Auto deduct disabled', 'skipped': True}
        
        try:
            order = Order.objects.prefetch_related('items__product').get(id=order_id)
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Order not found', 'error_code': 'NOT_FOUND'}
        
        deductions = []
        errors = []
        
        for order_item in order.items.all():
            product = order_item.product
            
            try:
                link = ProductStockLink.objects.select_related('recipe', 'stock_item').get(
                    product=product, 
                    is_active=True
                )
            except ProductStockLink.DoesNotExist:
                continue
            
            if link.link_type == 'DIRECT_ITEM' and link.stock_item:
                qty_to_deduct = link.quantity_per_sale * order_item.quantity
                result = StockService.adjust_stock(
                    stock_item_id=link.stock_item_id,
                    quantity=-float(qty_to_deduct),
                    movement_type='SALE_OUT',
                    user_id=order.cashier_id,
                    reference_type='Order',
                    reference_id=order.id,
                    notes=f'Order #{order.display_id} - {product.name} x{order_item.quantity}'
                )
                
                if result['success']:
                    deductions.append({
                        'product': product.name,
                        'stock_item': link.stock_item.name,
                        'quantity': float(qty_to_deduct),
                    })
                else:
                    errors.append(f"{product.name}: {result['message']}")
            
            elif link.link_type == 'RECIPE' and link.recipe:
                recipe_result = StockService._deduct_recipe(
                    recipe_id=link.recipe_id,
                    multiplier=order_item.quantity * link.quantity_per_sale,
                    order_id=order.id,
                    user_id=order.cashier_id,
                )
                
                if recipe_result['success']:
                    deductions.extend(recipe_result['deductions'])
                else:
                    errors.append(f"{product.name}: {recipe_result['message']}")
            
            elif link.link_type == 'COMPONENT_BASED':
                for component in link.components.all():
                    qty_to_deduct = component.quantity * order_item.quantity
                    result = StockService.adjust_stock(
                        stock_item_id=component.stock_item_id,
                        quantity=-float(qty_to_deduct),
                        movement_type='SALE_OUT',
                        user_id=order.cashier_id,
                        reference_type='Order',
                        reference_id=order.id,
                        notes=f'Order #{order.display_id} - {product.name} ({component.component_name})'
                    )
                    
                    if result['success']:
                        deductions.append({
                            'product': product.name,
                            'component': component.component_name,
                            'stock_item': component.stock_item.name,
                            'quantity': float(qty_to_deduct),
                        })
                    else:
                        errors.append(f"{product.name} ({component.component_name}): {result['message']}")
        
        return {
            'success': len(errors) == 0,
            'message': 'Stock deducted' if not errors else 'Partial deduction',
            'deductions': deductions,
            'errors': errors,
        }
    
    @staticmethod
    @transaction.atomic
    def _deduct_recipe(recipe_id, multiplier, order_id=None, user_id=None, production_order_id=None):
        """Deduct all ingredients for a recipe"""
        from stock.models import Recipe, RecipeIngredient
        
        try:
            recipe = Recipe.objects.prefetch_related('ingredients__stock_item').get(
                id=recipe_id, 
                is_active=True,
                is_active_version=True
            )
        except Recipe.DoesNotExist:
            return {'success': False, 'message': 'Recipe not found', 'error_code': 'NOT_FOUND'}
        
        deductions = []
        
        for ingredient in recipe.ingredients.filter(is_optional=False):
            if not ingredient.is_scalable:
                qty = ingredient.quantity
            else:
                qty = ingredient.quantity * Decimal(str(multiplier))
            
            waste_factor = 1 + (ingredient.waste_percentage / 100)
            qty_with_waste = qty * waste_factor
            
            result = StockService.adjust_stock(
                stock_item_id=ingredient.stock_item_id,
                quantity=-float(qty_with_waste),
                movement_type='PRODUCTION_OUT' if production_order_id else 'SALE_OUT',
                user_id=user_id,
                reference_type='ProductionOrder' if production_order_id else 'Order',
                reference_id=production_order_id or order_id,
                notes=f'Recipe: {recipe.name} - {ingredient.stock_item.name}'
            )
            
            if result['success']:
                deductions.append({
                    'recipe': recipe.name,
                    'stock_item': ingredient.stock_item.name,
                    'quantity': float(qty_with_waste),
                })
            else:
                return result
        
        return {'success': True, 'deductions': deductions}
    
    @staticmethod
    @transaction.atomic
    def reverse_order_deduction(order_id):
        """Reverse stock deductions for a cancelled order"""
        from stock.models import StockTransaction
        
        if not StockService.is_enabled():
            return {'success': True, 'message': 'Stock system disabled', 'skipped': True}
        
        transactions = StockTransaction.objects.filter(
            reference_type='Order',
            reference_id=order_id,
            movement_type='SALE_OUT'
        )
        
        reversed_count = 0
        for txn in transactions:
            result = StockService.adjust_stock(
                stock_item_id=txn.stock_item_id,
                quantity=float(txn.base_quantity),
                movement_type='RETURN_FROM_CUSTOMER',
                location_id=txn.location_id,
                user_id=txn.user_id,
                reference_type='Order',
                reference_id=order_id,
                notes=f'Reversal of {txn.transaction_number}'
            )
            if result['success']:
                reversed_count += 1
        
        return {
            'success': True,
            'message': f'Reversed {reversed_count} transactions',
            'reversed_count': reversed_count,
        }
    
    # ==================== STOCK ITEMS ====================
    
    @staticmethod
    def get_stock_items(page=1, per_page=20, search=None, category_id=None, 
                        item_type=None, active_only=True):
        """Get all stock items with filters"""
        from stock.models import StockItem
        from django.core.paginator import Paginator
        
        queryset = StockItem.objects.select_related('category', 'base_unit')
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(barcode__icontains=search)
            )
        
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        
        queryset = queryset.order_by('name')
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        items = []
        for item in page_obj.object_list:
            items.append({
                'id': item.id,
                'uuid': str(item.uuid),
                'name': item.name,
                'sku': item.sku,
                'barcode': item.barcode,
                'category': {'id': item.category.id, 'name': item.category.name} if item.category else None,
                'base_unit': {'id': item.base_unit.id, 'name': item.base_unit.name, 'short': item.base_unit.short_name},
                'item_type': item.item_type,
                'min_stock': float(item.min_stock_level),
                'reorder_point': float(item.reorder_point),
                'cost_price': float(item.cost_price),
                'avg_cost': float(item.avg_cost_price),
                'is_purchasable': item.is_purchasable,
                'is_sellable': item.is_sellable,
                'is_producible': item.is_producible,
                'track_batches': item.track_batches,
                'track_expiry': item.track_expiry,
            })
        
        return {
            'success': True,
            'items': items,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_items': paginator.count,
                'per_page': per_page,
            }
        }
    
    @staticmethod
    def create_stock_item(name, base_unit_id, item_type='RAW', category_id=None, 
                          sku=None, barcode=None, **kwargs):
        """Create a new stock item"""
        from stock.models import StockItem, StockUnit, StockCategory
        
        try:
            unit = StockUnit.objects.get(id=base_unit_id)
        except StockUnit.DoesNotExist:
            return {'success': False, 'message': 'Unit not found', 'error_code': 'NOT_FOUND'}
        
        if category_id:
            try:
                category = StockCategory.objects.get(id=category_id)
            except StockCategory.DoesNotExist:
                return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
        
        if sku and StockItem.objects.filter(sku=sku).exists():
            return {'success': False, 'message': 'SKU already exists', 'error_code': 'DUPLICATE_SKU'}
        
        item = StockItem.objects.create(
            name=name,
            base_unit=unit,
            item_type=item_type,
            category_id=category_id,
            sku=sku,
            barcode=barcode,
            min_stock_level=kwargs.get('min_stock_level', 0),
            max_stock_level=kwargs.get('max_stock_level'),
            reorder_point=kwargs.get('reorder_point', 0),
            cost_price=kwargs.get('cost_price', 0),
            is_purchasable=kwargs.get('is_purchasable', True),
            is_sellable=kwargs.get('is_sellable', False),
            is_producible=kwargs.get('is_producible', False),
            track_batches=kwargs.get('track_batches', False),
            track_expiry=kwargs.get('track_expiry', False),
            default_expiry_days=kwargs.get('default_expiry_days'),
        )
        
        return {
            'success': True,
            'message': 'Stock item created',
            'item': {'id': item.id, 'name': item.name, 'uuid': str(item.uuid)}
        }
    
    # ==================== PRODUCT-STOCK LINKING ====================
    
    @staticmethod
    def link_product_to_stock(product_id, link_type, stock_item_id=None, recipe_id=None,
                              quantity_per_sale=1, deduct_on_status='PREPARING'):
        """Link a POS product to stock item or recipe"""
        from stock.models import ProductStockLink
        from main.models import Product
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return {'success': False, 'message': 'Product not found', 'error_code': 'NOT_FOUND'}
        
        ProductStockLink.objects.filter(product=product).delete()
        
        link = ProductStockLink.objects.create(
            product=product,
            link_type=link_type,
            stock_item_id=stock_item_id if link_type == 'DIRECT_ITEM' else None,
            recipe_id=recipe_id if link_type == 'RECIPE' else None,
            quantity_per_sale=quantity_per_sale,
            deduct_on_status=deduct_on_status,
            is_active=True,
        )
        
        return {
            'success': True,
            'message': 'Product linked to stock',
            'link_id': link.id,
        }
    
    @staticmethod
    def get_product_stock_link(product_id):
        """Get stock link for a product"""
        from stock.models import ProductStockLink
        
        try:
            link = ProductStockLink.objects.select_related(
                'stock_item', 'recipe'
            ).prefetch_related('components__stock_item').get(product_id=product_id)
            
            data = {
                'id': link.id,
                'link_type': link.link_type,
                'quantity_per_sale': float(link.quantity_per_sale),
                'deduct_on_status': link.deduct_on_status,
                'is_active': link.is_active,
            }
            
            if link.link_type == 'DIRECT_ITEM' and link.stock_item:
                data['stock_item'] = {
                    'id': link.stock_item.id,
                    'name': link.stock_item.name,
                }
            elif link.link_type == 'RECIPE' and link.recipe:
                data['recipe'] = {
                    'id': link.recipe.id,
                    'name': link.recipe.name,
                }
            elif link.link_type == 'COMPONENT_BASED':
                data['components'] = [
                    {
                        'name': c.component_name,
                        'stock_item': {'id': c.stock_item.id, 'name': c.stock_item.name},
                        'quantity': float(c.quantity),
                    }
                    for c in link.components.all()
                ]
            
            return {'success': True, 'link': data}
        except ProductStockLink.DoesNotExist:
            return {'success': True, 'link': None, 'message': 'No stock link'}
    
    # ==================== TRANSACTION HISTORY ====================
    
    @staticmethod
    def get_transactions(stock_item_id=None, location_id=None, movement_type=None,
                         date_from=None, date_to=None, page=1, per_page=50):
        """Get stock transaction history"""
        from stock.models import StockTransaction
        from django.core.paginator import Paginator
        
        queryset = StockTransaction.objects.select_related(
            'stock_item', 'location', 'user'
        ).order_by('-created_at')
        
        if stock_item_id:
            queryset = queryset.filter(stock_item_id=stock_item_id)
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        transactions = []
        for txn in page_obj.object_list:
            transactions.append({
                'id': txn.id,
                'transaction_number': txn.transaction_number,
                'stock_item': {'id': txn.stock_item.id, 'name': txn.stock_item.name},
                'location': txn.location.name,
                'movement_type': txn.movement_type,
                'movement_display': txn.get_movement_type_display(),
                'quantity': float(txn.quantity),
                'unit': txn.unit.short_name,
                'quantity_before': float(txn.quantity_before),
                'quantity_after': float(txn.quantity_after),
                'unit_cost': float(txn.unit_cost),
                'total_cost': float(txn.total_cost),
                'reference_type': txn.reference_type,
                'reference_id': txn.reference_id,
                'user': f"{txn.user.first_name} {txn.user.last_name}" if txn.user else None,
                'notes': txn.notes,
                'created_at': txn.created_at.isoformat(),
            })
        
        return {
            'success': True,
            'transactions': transactions,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_transactions': paginator.count,
            }
        }