"""
Stock Batch Service - Batch tracking with expiry management
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    StockBatch, StockItem, StockLocation, StockTransaction,
    StockSettings, Supplier, PurchaseOrder, ProductionOrder
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    to_decimal, round_decimal, generate_number
)


class StockBatchService(BaseService):
    """Manage stock batches"""
    
    model = StockBatch
    
    # ==================== SERIALIZATION ====================
    
    @classmethod
    def serialize(cls, batch: StockBatch, include_transactions: bool = False) -> Dict[str, Any]:
        """Convert batch to dictionary"""
        data = {
            "id": batch.id,
            "uuid": str(batch.uuid),
            "batch_number": batch.batch_number,
            
            "stock_item_id": batch.stock_item_id,
            "stock_item": {
                "id": batch.stock_item.id,
                "name": batch.stock_item.name,
                "sku": batch.stock_item.sku,
            },
            
            "location_id": batch.location_id,
            "location_name": batch.location.name,
            
            "initial_quantity": str(batch.initial_quantity),
            "current_quantity": str(batch.current_quantity),
            "reserved_quantity": str(batch.reserved_quantity),
            "available_quantity": str(batch.current_quantity - batch.reserved_quantity),
            
            "unit_cost": str(batch.unit_cost),
            "total_cost": str(batch.total_cost),
            
            "manufactured_date": batch.manufactured_date.isoformat() if batch.manufactured_date else None,
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
            "days_until_expiry": cls._days_until_expiry(batch),
            "is_expired": cls._is_expired(batch),
            
            "supplier_id": batch.supplier_id,
            "supplier_name": batch.supplier.name if batch.supplier else None,
            "purchase_order_id": batch.purchase_order_id,
            "production_order_id": batch.production_order_id,
            
            "status": batch.status,
            "status_display": batch.get_status_display(),
            "quality_status": batch.quality_status,
            "notes": batch.notes,
            
            "received_at": batch.received_at.isoformat() if batch.received_at else None,
            "created_at": batch.created_at.isoformat(),
        }
        
        if include_transactions:
            transactions = batch.transactions.select_related("unit").order_by("-created_at")[:20]
            data["recent_transactions"] = [
                {
                    "id": t.id,
                    "movement_type": t.movement_type,
                    "quantity": str(t.quantity),
                    "created_at": t.created_at.isoformat(),
                }
                for t in transactions
            ]
        
        return data
    
    @classmethod
    def _days_until_expiry(cls, batch: StockBatch) -> Optional[int]:
        """Calculate days until expiry"""
        if not batch.expiry_date:
            return None
        today = timezone.now().date()
        delta = batch.expiry_date - today
        return delta.days
    
    @classmethod
    def _is_expired(cls, batch: StockBatch) -> bool:
        """Check if batch is expired"""
        if not batch.expiry_date:
            return False
        return batch.expiry_date < timezone.now().date()
    
    # ==================== LIST & SEARCH ====================
    
    @classmethod
    def list(cls,
             stock_item_id: int = None,
             location_id: int = None,
             status: str = None,
             expiring_within_days: int = None,
             expired_only: bool = False,
             has_stock_only: bool = True,
             page: int = 1,
             per_page: int = 50) -> Dict[str, Any]:
        """List batches with filters"""
        queryset = cls.model.objects.select_related(
            "stock_item", "location", "supplier"
        )
        
        if stock_item_id:
            queryset = queryset.filter(stock_item_id=stock_item_id)
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if has_stock_only:
            queryset = queryset.filter(current_quantity__gt=0)
        
        if expired_only:
            queryset = queryset.filter(expiry_date__lt=timezone.now().date())
        elif expiring_within_days:
            expiry_threshold = timezone.now().date() + timedelta(days=expiring_within_days)
            queryset = queryset.filter(
                expiry_date__isnull=False,
                expiry_date__lte=expiry_threshold,
                expiry_date__gte=timezone.now().date()
            )
        
        # Order by expiry (FEFO) then by creation (FIFO)
        queryset = queryset.order_by("expiry_date", "created_at")
        
        batches, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "batches": [cls.serialize(b) for b in batches],
            "pagination": pagination,
            "statuses": [
                {"value": c[0], "label": c[1]}
                for c in StockBatch.BatchStatus.choices
            ]
        })
    
    @classmethod
    def get_available_batches(cls, 
                              stock_item_id: int, 
                              location_id: int,
                              costing_method: str = None) -> List[StockBatch]:
        """
        Get available batches for an item at location, ordered by costing method
        """
        settings = StockSettings.load()
        method = costing_method or settings.costing_method
        
        queryset = cls.model.objects.filter(
            stock_item_id=stock_item_id,
            location_id=location_id,
            status=StockBatch.BatchStatus.AVAILABLE,
            current_quantity__gt=F("reserved_quantity")
        )
        
        # Exclude expired batches
        queryset = queryset.exclude(
            expiry_date__lt=timezone.now().date()
        )
        
        # Order based on costing method
        if method == "FIFO":
            queryset = queryset.order_by("created_at")
        elif method == "LIFO":
            queryset = queryset.order_by("-created_at")
        elif method == "FEFO":
            queryset = queryset.order_by("expiry_date", "created_at")
        else:
            queryset = queryset.order_by("created_at")
        
        return list(queryset)
    
    @classmethod
    def get_expiring_batches(cls, days: int = None) -> Dict[str, Any]:
        """Get batches expiring soon"""
        settings = StockSettings.load()
        days = days or settings.expiry_alert_days
        
        expiry_threshold = timezone.now().date() + timedelta(days=days)
        today = timezone.now().date()
        
        batches = cls.model.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lte=expiry_threshold,
            expiry_date__gte=today,
            current_quantity__gt=0,
            status=StockBatch.BatchStatus.AVAILABLE
        ).select_related("stock_item", "location").order_by("expiry_date")
        
        return success_response({
            "batches": [cls.serialize(b) for b in batches],
            "count": batches.count(),
            "alert_days": days
        })
    
    @classmethod
    def get_expired_batches(cls) -> Dict[str, Any]:
        """Get all expired batches with stock"""
        batches = cls.model.objects.filter(
            expiry_date__lt=timezone.now().date(),
            current_quantity__gt=0
        ).select_related("stock_item", "location").order_by("expiry_date")
        
        # Total expired value
        total_value = batches.aggregate(
            total=Sum(F("current_quantity") * F("unit_cost"))
        )["total"] or Decimal("0")
        
        return success_response({
            "batches": [cls.serialize(b) for b in batches],
            "count": batches.count(),
            "total_value": str(total_value)
        })
    
    # ==================== GET SINGLE ====================
    
    @classmethod
    def get(cls, batch_id: int, include_transactions: bool = True) -> Dict[str, Any]:
        """Get single batch"""
        batch = cls.model.objects.select_related(
            "stock_item", "location", "supplier"
        ).filter(id=batch_id).first()
        
        if not batch:
            raise NotFoundError("Batch", batch_id)
        
        return success_response({
            "batch": cls.serialize(batch, include_transactions=include_transactions)
        })
    
    @classmethod
    def find_by_number(cls, batch_number: str, stock_item_id: int = None) -> Dict[str, Any]:
        """Find batch by number"""
        queryset = cls.model.objects.filter(batch_number=batch_number)
        
        if stock_item_id:
            queryset = queryset.filter(stock_item_id=stock_item_id)
        
        batch = queryset.select_related("stock_item", "location").first()
        
        if not batch:
            raise NotFoundError("Batch", batch_number)
        
        return success_response({
            "batch": cls.serialize(batch)
        })
    
    # ==================== CREATE ====================
    
    @classmethod
    @transaction.atomic
    def create(cls,
               stock_item_id: int,
               location_id: int,
               quantity: Decimal,
               unit_cost: Decimal = None,
               batch_number: str = None,
               manufactured_date: date = None,
               expiry_date: date = None,
               supplier_id: int = None,
               purchase_order_id: int = None,
               production_order_id: int = None,
               quality_status: str = "PASSED",
               notes: str = "") -> Dict[str, Any]:
        """Create new batch"""
        
        # Validate stock item
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        # Validate location
        try:
            location = StockLocation.objects.get(id=location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Location", location_id)
        
        quantity = to_decimal(quantity)
        if quantity <= 0:
            raise ValidationError("Quantity must be positive", "quantity")
        
        # Generate batch number if not provided
        if not batch_number:
            batch_number = cls._generate_batch_number(stock_item)
        
        # Check batch number uniqueness for this item
        if cls.model.objects.filter(
            batch_number=batch_number, 
            stock_item_id=stock_item_id
        ).exists():
            raise ValidationError(f"Batch number '{batch_number}' already exists for this item", "batch_number")
        
        # Default cost
        if unit_cost is None:
            unit_cost = stock_item.avg_cost_price
        
        # Auto-calculate expiry if item has default
        if not expiry_date and stock_item.track_expiry and stock_item.default_expiry_days:
            manufactured = manufactured_date or timezone.now().date()
            expiry_date = manufactured + timedelta(days=stock_item.default_expiry_days)
        
        # Validate supplier
        supplier = None
        if supplier_id:
            try:
                supplier = Supplier.objects.get(id=supplier_id)
            except Supplier.DoesNotExist:
                raise NotFoundError("Supplier", supplier_id)
        
        batch = cls.model.objects.create(
            batch_number=batch_number,
            stock_item=stock_item,
            location=location,
            initial_quantity=quantity,
            current_quantity=quantity,
            unit_cost=to_decimal(unit_cost),
            total_cost=quantity * to_decimal(unit_cost),
            manufactured_date=manufactured_date,
            expiry_date=expiry_date,
            supplier=supplier,
            purchase_order_id=purchase_order_id,
            production_order_id=production_order_id,
            quality_status=quality_status,
            notes=notes,
            status=StockBatch.BatchStatus.AVAILABLE,
            received_at=timezone.now(),
        )
        
        return success_response({
            "id": batch.id,
            "batch_number": batch.batch_number,
            "batch": cls.serialize(batch)
        }, f"Batch '{batch_number}' created")
    
    @classmethod
    def _generate_batch_number(cls, stock_item: StockItem) -> str:
        """Generate unique batch number"""
        today = timezone.now()
        prefix = f"B{today.strftime('%y%m%d')}"
        
        # Count today's batches for this item
        count = cls.model.objects.filter(
            stock_item=stock_item,
            batch_number__startswith=prefix
        ).count()
        
        return f"{prefix}-{stock_item.sku or stock_item.id}-{count + 1:03d}"
    
    # ==================== UPDATE ====================
    
    @classmethod
    @transaction.atomic
    def update(cls, batch_id: int, **kwargs) -> Dict[str, Any]:
        """Update batch"""
        batch = cls.get_by_id(batch_id)
        if not batch:
            raise NotFoundError("Batch", batch_id)
        
        update_fields = ["updated_at"]
        
        # Fields that can be updated
        for field in ["manufactured_date", "expiry_date", "quality_status", "notes"]:
            if field in kwargs:
                setattr(batch, field, kwargs[field])
                update_fields.append(field)
        
        batch.save(update_fields=update_fields)
        
        return success_response({
            "batch": cls.serialize(batch)
        }, "Batch updated")
    
    # ==================== STATUS MANAGEMENT ====================
    
    @classmethod
    @transaction.atomic
    def set_status(cls, batch_id: int, status: str, notes: str = "") -> Dict[str, Any]:
        """Change batch status"""
        batch = cls.get_by_id(batch_id)
        if not batch:
            raise NotFoundError("Batch", batch_id)
        
        valid_statuses = [c[0] for c in StockBatch.BatchStatus.choices]
        if status not in valid_statuses:
            raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "status")
        
        old_status = batch.status
        batch.status = status
        
        if notes:
            batch.notes = f"{batch.notes}\n{timezone.now().isoformat()}: {old_status} → {status}: {notes}".strip()
        
        batch.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "batch": cls.serialize(batch),
            "old_status": old_status,
            "new_status": status
        }, f"Batch status changed to {status}")
    
    @classmethod
    @transaction.atomic
    def quarantine(cls, batch_id: int, reason: str = "") -> Dict[str, Any]:
        """Put batch in quarantine"""
        return cls.set_status(batch_id, "QUARANTINE", reason)
    
    @classmethod
    @transaction.atomic
    def release_from_quarantine(cls, batch_id: int) -> Dict[str, Any]:
        """Release batch from quarantine"""
        return cls.set_status(batch_id, "AVAILABLE", "Released from quarantine")
    
    @classmethod
    @transaction.atomic
    def mark_expired(cls, batch_id: int) -> Dict[str, Any]:
        """Mark batch as expired"""
        return cls.set_status(batch_id, "EXPIRED", "Manually marked expired")
    
    # ==================== CONSUME FROM BATCH ====================
    
    @classmethod
    @transaction.atomic
    def consume(cls,
                batch_id: int,
                quantity: Decimal,
                movement_type: str,
                user_id: int,
                reference_type: str = None,
                reference_id: int = None,
                notes: str = "") -> Dict[str, Any]:
        """Consume quantity from batch"""
        batch = cls.get_by_id(batch_id)
        if not batch:
            raise NotFoundError("Batch", batch_id)
        
        quantity = abs(to_decimal(quantity))
        available = batch.current_quantity - batch.reserved_quantity
        
        if quantity > available:
            raise InsufficientStockError(
                f"Batch {batch.batch_number}",
                quantity, available
            )
        
        batch.current_quantity -= quantity
        
        # Update status if consumed
        if batch.current_quantity <= 0:
            batch.status = StockBatch.BatchStatus.CONSUMED
        
        batch.save(update_fields=["current_quantity", "status", "updated_at"])
        
        # Create transaction
        from .level_service import StockLevelService
        StockLevelService.adjust(
            stock_item_id=batch.stock_item_id,
            location_id=batch.location_id,
            quantity=-quantity,
            movement_type=movement_type,
            user_id=user_id,
            batch_id=batch.id,
            unit_cost=batch.unit_cost,
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes
        )
        
        return success_response({
            "consumed": str(quantity),
            "remaining": str(batch.current_quantity),
            "batch_status": batch.status
        }, f"Consumed {quantity} from batch")
    
    # ==================== AUTO-CONSUME (FIFO/LIFO/FEFO) ====================
    
    @classmethod
    @transaction.atomic
    def auto_consume(cls,
                     stock_item_id: int,
                     location_id: int,
                     quantity: Decimal,
                     movement_type: str,
                     user_id: int,
                     reference_type: str = None,
                     reference_id: int = None,
                     notes: str = "") -> Dict[str, Any]:
        """
        Automatically consume from batches based on costing method
        Returns list of batches consumed from
        """
        settings = StockSettings.load()
        
        if not settings.track_batches:
            # If batch tracking disabled, just adjust level
            from .level_service import StockLevelService
            return StockLevelService.adjust(
                stock_item_id=stock_item_id,
                location_id=location_id,
                quantity=-quantity,
                movement_type=movement_type,
                user_id=user_id,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes
            )
        
        quantity = abs(to_decimal(quantity))
        remaining = quantity
        consumed_batches = []
        
        # Get available batches in order
        batches = cls.get_available_batches(stock_item_id, location_id)
        
        for batch in batches:
            if remaining <= 0:
                break
            
            available = batch.current_quantity - batch.reserved_quantity
            consume_qty = min(remaining, available)
            
            if consume_qty > 0:
                cls.consume(
                    batch_id=batch.id,
                    quantity=consume_qty,
                    movement_type=movement_type,
                    user_id=user_id,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    notes=notes
                )
                
                consumed_batches.append({
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "quantity": str(consume_qty),
                    "unit_cost": str(batch.unit_cost)
                })
                
                remaining -= consume_qty
        
        if remaining > 0:
            raise InsufficientStockError(
                StockItem.objects.get(id=stock_item_id).name,
                quantity,
                quantity - remaining
            )
        
        return success_response({
            "total_consumed": str(quantity),
            "batches": consumed_batches
        }, f"Consumed from {len(consumed_batches)} batch(es)")