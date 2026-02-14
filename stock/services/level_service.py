from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    StockLevel, StockTransaction, StockItem, StockLocation,
    StockUnit, StockBatch, StockSettings
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    to_decimal, round_decimal, generate_number
)


class StockLevelService(BaseService):    
    model = StockLevel
    
    @classmethod
    def serialize(cls, level: StockLevel) -> Dict[str, Any]:
        return {
            "id": level.id,
            "uuid": str(level.uuid),
            "stock_item_id": level.stock_item_id,
            "stock_item": {
                "id": level.stock_item.id,
                "name": level.stock_item.name,
                "sku": level.stock_item.sku,
                "unit": level.stock_item.base_unit.short_name,
            },
            "location_id": level.location_id,
            "location": {
                "id": level.location.id,
                "name": level.location.name,
                "type": level.location.type,
            },
            "quantity": str(level.quantity),
            "reserved_quantity": str(level.reserved_quantity),
            "available_quantity": str(level.available_quantity),
            "pending_in_quantity": str(level.pending_in_quantity),
            "pending_out_quantity": str(level.pending_out_quantity),
            "last_counted_at": level.last_counted_at.isoformat() if level.last_counted_at else None,
            "last_restocked_at": level.last_restocked_at.isoformat() if level.last_restocked_at else None,
            "last_movement_at": level.last_movement_at.isoformat() if level.last_movement_at else None,
        }
    
    @classmethod
    def get_all(cls,
                location_id: int = None,
                category_id: int = None,
                item_type: str = None,
                low_stock_only: bool = False,
                page: int = 1,
                per_page: int = 50) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related(
            "stock_item", "stock_item__base_unit", "stock_item__category", "location"
        ).filter(stock_item__is_active=True)
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if category_id:
            queryset = queryset.filter(stock_item__category_id=category_id)
        
        if item_type:
            queryset = queryset.filter(stock_item__item_type=item_type)
        
        if low_stock_only:
            queryset = queryset.filter(
                quantity__lt=F("stock_item__reorder_point")
            )
        
        queryset = queryset.order_by("stock_item__name", "location__name")
        
        levels, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "levels": [cls.serialize(lvl) for lvl in levels],
            "pagination": pagination
        })
    
    @classmethod
    def get_for_item(cls, stock_item_id: int) -> Dict[str, Any]:
        levels = cls.model.objects.filter(
            stock_item_id=stock_item_id
        ).select_related("location").order_by("location__name")
        
        total = levels.aggregate(
            total_qty=Sum("quantity"),
            total_reserved=Sum("reserved_quantity")
        )
        
        return success_response({
            "levels": [cls.serialize(lvl) for lvl in levels],
            "total_quantity": str(total["total_qty"] or 0),
            "total_reserved": str(total["total_reserved"] or 0),
            "total_available": str((total["total_qty"] or 0) - (total["total_reserved"] or 0))
        })
    
    @classmethod
    def get_for_location(cls, location_id: int) -> Dict[str, Any]:
        levels = cls.model.objects.filter(
            location_id=location_id,
            stock_item__is_active=True
        ).select_related(
            "stock_item", "stock_item__base_unit"
        ).order_by("stock_item__name")
        
        return success_response({
            "levels": [cls.serialize(lvl) for lvl in levels],
            "count": levels.count()
        })
    
    @classmethod
    def get_level(cls, stock_item_id: int, location_id: int) -> StockLevel:
        level, created = cls.model.objects.get_or_create(
            stock_item_id=stock_item_id,
            location_id=location_id,
            defaults={
                "quantity": Decimal("0"),
                "reserved_quantity": Decimal("0"),
            }
        )
        return level
    
    @classmethod
    def get_available(cls, stock_item_id: int, location_id: int = None) -> Decimal:
        queryset = cls.model.objects.filter(stock_item_id=stock_item_id)
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        result = queryset.aggregate(
            total=Sum("quantity"),
            reserved=Sum("reserved_quantity")
        )
        
        total = result["total"] or Decimal("0")
        reserved = result["reserved"] or Decimal("0")
        
        return total - reserved
    
    @classmethod
    def get_low_stock_items(cls, location_id: int = None) -> Dict[str, Any]:
        if location_id:
            low_stock = cls.model.objects.filter(
                location_id=location_id,
                quantity__lt=F("stock_item__reorder_point"),
                stock_item__is_active=True
            ).select_related("stock_item", "location")
        else:
            low_stock = StockItem.objects.filter(
                is_active=True
            ).annotate(
                total_qty=Sum("stock_levels__quantity")
            ).filter(
                Q(total_qty__lt=F("reorder_point")) |
                Q(total_qty__isnull=True)
            )
        
        alerts = []
        if location_id:
            for level in low_stock:
                alerts.append({
                    "stock_item_id": level.stock_item_id,
                    "stock_item_name": level.stock_item.name,
                    "sku": level.stock_item.sku,
                    "location_id": level.location_id,
                    "location_name": level.location.name,
                    "current_quantity": str(level.quantity),
                    "reorder_point": str(level.stock_item.reorder_point),
                    "shortage": str(level.stock_item.reorder_point - level.quantity),
                })
        else:
            for item in low_stock:
                total_qty = item.total_qty or Decimal("0")
                alerts.append({
                    "stock_item_id": item.id,
                    "stock_item_name": item.name,
                    "sku": item.sku,
                    "current_quantity": str(total_qty),
                    "reorder_point": str(item.reorder_point),
                    "shortage": str(item.reorder_point - total_qty),
                })
        
        return success_response({
            "alerts": alerts,
            "count": len(alerts)
        })
    
    @classmethod
    @transaction.atomic
    def adjust(cls,
               stock_item_id: int,
               location_id: int,
               quantity: Decimal,
               movement_type: str,
               user_id: int,
               unit_id: int = None,
               batch_id: int = None,
               reference_type: str = None,
               reference_id: int = None,
               order_id: int = None,
               production_order_id: int = None,
               transfer_id: int = None,
               unit_cost: Decimal = None,
               notes: str = "") -> Dict[str, Any]:
        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({
                "skipped": True,
                "reason": "Stock system disabled"
            }, "Stock adjustment skipped (system disabled)")
        
        valid_types = [c[0] for c in StockTransaction.MovementType.choices]
        if movement_type not in valid_types:
            raise ValidationError(f"Invalid movement type. Valid: {valid_types}", "movement_type")
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        try:
            location = StockLocation.objects.get(id=location_id)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Location", location_id)
        
        if unit_id:
            try:
                unit = StockUnit.objects.get(id=unit_id)
            except StockUnit.DoesNotExist:
                raise NotFoundError("Unit", unit_id)
        else:
            unit = stock_item.base_unit
        
        quantity = to_decimal(quantity)
        
        if unit_id and unit_id != stock_item.base_unit_id:
            from .unit_service import StockItemUnitService
            base_quantity = StockItemUnitService.convert_for_item(
                stock_item_id, quantity, unit_id
            )
        else:
            base_quantity = quantity
        
        level = cls.get_level(stock_item_id, location_id)
        quantity_before = level.quantity
        
        is_outgoing = movement_type in [
            "SALE_OUT", "TRANSFER_OUT", "PRODUCTION_OUT",
            "ADJUSTMENT_MINUS", "WASTE", "SPOILAGE", "RETURN_TO_SUPPLIER"
        ]
        
        if is_outgoing:
            adjustment = -abs(base_quantity)
        else:
            adjustment = abs(base_quantity)
        
        new_quantity = level.quantity + adjustment
        if new_quantity < 0 and not settings.allow_negative_stock:
            raise InsufficientStockError(
                stock_item.name,
                abs(adjustment),
                level.quantity
            )
        
        level.quantity = new_quantity
        level.last_movement_at = timezone.now()
        
        if not is_outgoing:
            level.last_restocked_at = timezone.now()
        
        level.save(update_fields=["quantity", "last_movement_at", "last_restocked_at", "updated_at"])
        
        if unit_cost is None:
            unit_cost = stock_item.avg_cost_price
        
        trans_number = generate_number("TRX", StockTransaction, "transaction_number")
        
        trans = StockTransaction.objects.create(
            transaction_number=trans_number,
            stock_item=stock_item,
            location=location,
            batch_id=batch_id,
            movement_type=movement_type,
            quantity=abs(quantity),
            unit=unit,
            base_quantity=abs(base_quantity),
            quantity_before=quantity_before,
            quantity_after=new_quantity,
            unit_cost=to_decimal(unit_cost),
            total_cost=abs(base_quantity) * to_decimal(unit_cost),
            reference_type=reference_type or "",
            reference_id=reference_id,
            order_id=order_id,
            production_order_id=production_order_id,
            transfer_id=transfer_id,
            user_id=user_id,
            notes=notes,
        )
        
        return success_response({
            "transaction_id": trans.id,
            "transaction_number": trans.transaction_number,
            "quantity_before": str(quantity_before),
            "quantity_after": str(new_quantity),
            "adjustment": str(adjustment),
            "movement_type": movement_type,
        }, f"Stock adjusted: {adjustment:+} {stock_item.base_unit.short_name}")
    
    
    @classmethod
    @transaction.atomic
    def reserve(cls,
                stock_item_id: int,
                location_id: int,
                quantity: Decimal,
                user_id: int,
                reference_type: str = None,
                reference_id: int = None,
                notes: str = "") -> Dict[str, Any]:
        settings = StockSettings.load()
        if not settings.stock_enabled:
            return success_response({"skipped": True})
        
        quantity = abs(to_decimal(quantity))
        level = cls.get_level(stock_item_id, location_id)
        
        available = level.quantity - level.reserved_quantity
        if quantity > available:
            raise InsufficientStockError(
                StockItem.objects.get(id=stock_item_id).name,
                quantity, available
            )
        
        level.reserved_quantity += quantity
        level.save(update_fields=["reserved_quantity", "updated_at"])
        
        stock_item = StockItem.objects.get(id=stock_item_id)
        trans_number = generate_number("TRX", StockTransaction, "transaction_number")
        
        StockTransaction.objects.create(
            transaction_number=trans_number,
            stock_item_id=stock_item_id,
            location_id=location_id,
            movement_type="RESERVATION",
            quantity=quantity,
            unit=stock_item.base_unit,
            base_quantity=quantity,
            quantity_before=level.quantity,
            quantity_after=level.quantity, 
            user_id=user_id,
            reference_type=reference_type or "",
            reference_id=reference_id,
            notes=notes,
        )
        
        return success_response({
            "reserved": str(quantity),
            "total_reserved": str(level.reserved_quantity),
            "available": str(level.quantity - level.reserved_quantity)
        }, "Stock reserved")
    
    @classmethod
    @transaction.atomic
    def release_reservation(cls,
                           stock_item_id: int,
                           location_id: int,
                           quantity: Decimal,
                           user_id: int,
                           notes: str = "") -> Dict[str, Any]:
        settings = StockSettings.load()
        if not settings.stock_enabled:
            return success_response({"skipped": True})
        
        quantity = abs(to_decimal(quantity))
        level = cls.get_level(stock_item_id, location_id)
        
        release_qty = min(quantity, level.reserved_quantity)
        
        level.reserved_quantity -= release_qty
        level.save(update_fields=["reserved_quantity", "updated_at"])
        
        stock_item = StockItem.objects.get(id=stock_item_id)
        trans_number = generate_number("TRX", StockTransaction, "transaction_number")
        
        StockTransaction.objects.create(
            transaction_number=trans_number,
            stock_item_id=stock_item_id,
            location_id=location_id,
            movement_type="RESERVATION_RELEASE",
            quantity=release_qty,
            unit=stock_item.base_unit,
            base_quantity=release_qty,
            quantity_before=level.quantity,
            quantity_after=level.quantity,
            user_id=user_id,
            notes=notes,
        )
        
        return success_response({
            "released": str(release_qty),
            "remaining_reserved": str(level.reserved_quantity)
        }, "Reservation released")


class StockTransactionService(BaseService):
    model = StockTransaction
    
    @classmethod
    def serialize(cls, trans: StockTransaction) -> Dict[str, Any]:
        return {
            "id": trans.id,
            "uuid": str(trans.uuid),
            "transaction_number": trans.transaction_number,
            "stock_item_id": trans.stock_item_id,
            "stock_item_name": trans.stock_item.name,
            "location_id": trans.location_id,
            "location_name": trans.location.name,
            "batch_id": trans.batch_id,
            "movement_type": trans.movement_type,
            "movement_type_display": trans.get_movement_type_display(),
            "quantity": str(trans.quantity),
            "unit": trans.unit.short_name,
            "base_quantity": str(trans.base_quantity),
            "quantity_before": str(trans.quantity_before),
            "quantity_after": str(trans.quantity_after),
            "unit_cost": str(trans.unit_cost),
            "total_cost": str(trans.total_cost),
            "reference_type": trans.reference_type,
            "reference_id": trans.reference_id,
            "order_id": trans.order_id,
            "production_order_id": trans.production_order_id,
            "transfer_id": trans.transfer_id,
            "user_id": trans.user_id,
            "notes": trans.notes,
            "created_at": trans.created_at.isoformat(),
        }
    
    @classmethod
    def list(cls,
             stock_item_id: int = None,
             location_id: int = None,
             movement_type: str = None,
             date_from: date = None,
             date_to: date = None,
             order_id: int = None,
             production_order_id: int = None,
             transfer_id: int = None,
             page: int = 1,
             per_page: int = 50) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related(
            "stock_item", "location", "unit"
        )
        
        if stock_item_id:
            queryset = queryset.filter(stock_item_id=stock_item_id)
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        
        if production_order_id:
            queryset = queryset.filter(production_order_id=production_order_id)
        
        if transfer_id:
            queryset = queryset.filter(transfer_id=transfer_id)
        
        queryset = queryset.order_by("-created_at")
        
        transactions, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "transactions": [cls.serialize(t) for t in transactions],
            "pagination": pagination,
            "movement_types": [
                {"value": c[0], "label": c[1]}
                for c in StockTransaction.MovementType.choices
            ]
        })
    
    @classmethod
    def get_by_reference(cls, reference_type: str, reference_id: int) -> Dict[str, Any]:
        transactions = cls.model.objects.filter(
            reference_type=reference_type,
            reference_id=reference_id
        ).select_related("stock_item", "location", "unit").order_by("-created_at")
        
        return success_response({
            "transactions": [cls.serialize(t) for t in transactions],
            "count": transactions.count()
        })
    
    @classmethod
    def get_item_history(cls, stock_item_id: int, days: int = 30) -> Dict[str, Any]:
        since = timezone.now() - timedelta(days=days)
        
        transactions = cls.model.objects.filter(
            stock_item_id=stock_item_id,
            created_at__gte=since
        ).select_related("location", "unit").order_by("-created_at")
        
        summary = transactions.values("movement_type").annotate(
            count=Sum("id"),
            total_qty=Sum("base_quantity")
        )
        
        return success_response({
            "transactions": [cls.serialize(t) for t in transactions[:100]],
            "summary": list(summary),
            "total_transactions": transactions.count(),
            "period_days": days
        })