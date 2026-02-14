"""
Stock Transfer Service - Manage inter-location stock transfers
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from stock.models import (
    StockTransfer, StockTransferItem, StockLocation, StockItem,
    StockUnit, StockBatch, StockLevel, StockSettings
)
from base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    to_decimal, generate_number
)


class StockTransferService(BaseService):
    """Manage stock transfers between locations"""
    
    model = StockTransfer
    
    # ==================== SERIALIZATION ====================
    
    @classmethod
    def serialize(cls, transfer: StockTransfer, include_items: bool = False) -> Dict[str, Any]:
        """Convert transfer to dictionary"""
        data = {
            "id": transfer.id,
            "uuid": str(transfer.uuid),
            "transfer_number": transfer.transfer_number,
            
            "from_location_id": transfer.from_location_id,
            "from_location": {
                "id": transfer.from_location.id,
                "name": transfer.from_location.name,
                "type": transfer.from_location.type,
            },
            
            "to_location_id": transfer.to_location_id,
            "to_location": {
                "id": transfer.to_location.id,
                "name": transfer.to_location.name,
                "type": transfer.to_location.type,
            },
            
            "status": transfer.status,
            "status_display": transfer.get_status_display(),
            "transfer_type": transfer.transfer_type,
            "transfer_type_display": transfer.get_transfer_type_display(),
            
            "requested_by_id": transfer.requested_by_id,
            "approved_by_id": transfer.approved_by_id,
            "shipped_by_id": transfer.shipped_by_id,
            "received_by_id": transfer.received_by_id,
            
            "requested_at": transfer.requested_at.isoformat() if transfer.requested_at else None,
            "approved_at": transfer.approved_at.isoformat() if transfer.approved_at else None,
            "shipped_at": transfer.shipped_at.isoformat() if transfer.shipped_at else None,
            "received_at": transfer.received_at.isoformat() if transfer.received_at else None,
            
            "notes": transfer.notes,
            "created_at": transfer.created_at.isoformat(),
            "updated_at": transfer.updated_at.isoformat(),
        }
        
        if include_items:
            data["items"] = [
                StockTransferItemService.serialize(item)
                for item in transfer.items.select_related("stock_item", "unit", "batch")
            ]
            data["item_count"] = transfer.items.count()
        
        return data
    
    @classmethod
    def serialize_brief(cls, transfer: StockTransfer) -> Dict[str, Any]:
        """Brief serialization"""
        return {
            "id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "from_location": transfer.from_location.name,
            "to_location": transfer.to_location.name,
            "status": transfer.status,
            "created_at": transfer.created_at.isoformat(),
        }
    
    # ==================== LIST & SEARCH ====================
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             from_location_id: int = None,
             to_location_id: int = None,
             status: str = None,
             transfer_type: str = None,
             date_from: date = None,
             date_to: date = None) -> Dict[str, Any]:
        """List transfers with filters"""
        queryset = cls.model.objects.select_related("from_location", "to_location")
        
        if from_location_id:
            queryset = queryset.filter(from_location_id=from_location_id)
        
        if to_location_id:
            queryset = queryset.filter(to_location_id=to_location_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if transfer_type:
            queryset = queryset.filter(transfer_type=transfer_type)
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        queryset = queryset.order_by("-created_at")
        
        transfers, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "transfers": [cls.serialize_brief(t) for t in transfers],
            "pagination": pagination,
            "statuses": [{"value": c[0], "label": c[1]} for c in StockTransfer.Status.choices],
            "types": [{"value": c[0], "label": c[1]} for c in StockTransfer.TransferType.choices],
        })
    
    @classmethod
    def get_pending(cls, location_id: int = None) -> Dict[str, Any]:
        """Get pending transfers (not completed/cancelled)"""
        queryset = cls.model.objects.filter(
            status__in=["DRAFT", "REQUESTED", "APPROVED", "IN_TRANSIT"]
        ).select_related("from_location", "to_location")
        
        if location_id:
            queryset = queryset.filter(
                Q(from_location_id=location_id) | Q(to_location_id=location_id)
            )
        
        return success_response({
            "transfers": [cls.serialize_brief(t) for t in queryset.order_by("-created_at")],
            "count": queryset.count()
        })
    
    @classmethod
    def get_incoming(cls, location_id: int) -> Dict[str, Any]:
        """Get incoming transfers for a location"""
        transfers = cls.model.objects.filter(
            to_location_id=location_id,
            status__in=["APPROVED", "IN_TRANSIT"]
        ).select_related("from_location").order_by("-created_at")
        
        return success_response({
            "transfers": [cls.serialize_brief(t) for t in transfers],
            "count": transfers.count()
        })
    
    @classmethod
    def get_outgoing(cls, location_id: int) -> Dict[str, Any]:
        """Get outgoing transfers from a location"""
        transfers = cls.model.objects.filter(
            from_location_id=location_id,
            status__in=["REQUESTED", "APPROVED", "IN_TRANSIT"]
        ).select_related("to_location").order_by("-created_at")
        
        return success_response({
            "transfers": [cls.serialize_brief(t) for t in transfers],
            "count": transfers.count()
        })
    
    # ==================== GET SINGLE ====================
    
    @classmethod
    def get(cls, transfer_id: int, include_items: bool = True) -> Dict[str, Any]:
        """Get single transfer"""
        transfer = cls.model.objects.select_related(
            "from_location", "to_location"
        ).filter(id=transfer_id).first()
        
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        return success_response({
            "transfer": cls.serialize(transfer, include_items=include_items)
        })
    
    # ==================== CREATE ====================
    
    @classmethod
    @transaction.atomic
    def create(cls,
               from_location_id: int,
               to_location_id: int,
               requested_by_id: int,
               transfer_type: str = "INTERNAL",
               notes: str = "",
               items: List[Dict] = None) -> Dict[str, Any]:
        """Create new transfer"""
        
        # Validate locations
        try:
            from_location = StockLocation.objects.get(id=from_location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("From location", from_location_id)
        
        try:
            to_location = StockLocation.objects.get(id=to_location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("To location", to_location_id)
        
        if from_location_id == to_location_id:
            raise ValidationError("Cannot transfer to same location", "to_location_id")
        
        # Validate transfer type
        valid_types = [c[0] for c in StockTransfer.TransferType.choices]
        if transfer_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "transfer_type")
        
        # Generate number
        transfer_number = generate_number("TRF", cls.model, "transfer_number")
        
        transfer = cls.model.objects.create(
            transfer_number=transfer_number,
            from_location=from_location,
            to_location=to_location,
            status=StockTransfer.Status.DRAFT,
            transfer_type=transfer_type,
            requested_by_id=requested_by_id,
            notes=notes,
        )
        
        # Add items if provided
        if items:
            for item_data in items:
                StockTransferItemService.add_item(
                    transfer_id=transfer.id,
                    stock_item_id=item_data["stock_item_id"],
                    requested_qty=item_data["quantity"],
                    unit_id=item_data.get("unit_id"),
                    batch_id=item_data.get("batch_id"),
                )
        
        return success_response({
            "id": transfer.id,
            "transfer_number": transfer_number,
            "transfer": cls.serialize(transfer, include_items=True)
        }, f"Transfer {transfer_number} created")
    
    # ==================== UPDATE ====================
    
    @classmethod
    @transaction.atomic
    def update(cls, transfer_id: int, **kwargs) -> Dict[str, Any]:
        """Update transfer"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status not in ["DRAFT", "REQUESTED"]:
            raise BusinessRuleError(f"Cannot update {transfer.status} transfer")
        
        update_fields = ["updated_at"]
        
        # Update locations
        if "from_location_id" in kwargs:
            try:
                location = StockLocation.objects.get(id=kwargs["from_location_id"], is_active=True)
                transfer.from_location = location
                update_fields.append("from_location")
            except StockLocation.DoesNotExist:
                raise NotFoundError("From location", kwargs["from_location_id"])
        
        if "to_location_id" in kwargs:
            try:
                location = StockLocation.objects.get(id=kwargs["to_location_id"], is_active=True)
                transfer.to_location = location
                update_fields.append("to_location")
            except StockLocation.DoesNotExist:
                raise NotFoundError("To location", kwargs["to_location_id"])
        
        if "notes" in kwargs:
            transfer.notes = kwargs["notes"]
            update_fields.append("notes")
        
        transfer.save(update_fields=update_fields)
        
        return success_response({
            "transfer": cls.serialize(transfer, include_items=True)
        }, "Transfer updated")
    
    # ==================== STATUS WORKFLOW ====================
    
    @classmethod
    @transaction.atomic
    def request(cls, transfer_id: int) -> Dict[str, Any]:
        """Submit transfer request"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status != "DRAFT":
            raise BusinessRuleError(f"Can only request DRAFT transfers")
        
        if not transfer.items.exists():
            raise BusinessRuleError("Cannot request empty transfer")
        
        transfer.status = StockTransfer.Status.REQUESTED
        transfer.requested_at = timezone.now()
        transfer.save(update_fields=["status", "requested_at", "updated_at"])
        
        return success_response({
            "transfer": cls.serialize(transfer)
        }, "Transfer requested")
    
    @classmethod
    @transaction.atomic
    def approve(cls, transfer_id: int, approved_by_id: int) -> Dict[str, Any]:
        """Approve transfer"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        settings = StockSettings.load()
        
        # Can approve from DRAFT (skip request) or REQUESTED
        if transfer.status not in ["DRAFT", "REQUESTED"]:
            raise BusinessRuleError(f"Cannot approve {transfer.status} transfer")
        
        # Check stock availability
        for item in transfer.items.all():
            available = StockLevel.objects.filter(
                stock_item_id=item.stock_item_id,
                location=transfer.from_location
            ).aggregate(qty=Sum("quantity"))["qty"] or Decimal("0")
            
            if item.requested_qty > available and not settings.allow_negative_stock:
                raise InsufficientStockError(
                    item.stock_item.name,
                    item.requested_qty,
                    available
                )
            
            # Set approved qty
            item.approved_qty = item.requested_qty
            item.save(update_fields=["approved_qty"])
        
        transfer.status = StockTransfer.Status.APPROVED
        transfer.approved_by_id = approved_by_id
        transfer.approved_at = timezone.now()
        if not transfer.requested_at:
            transfer.requested_at = timezone.now()
        transfer.save(update_fields=["status", "approved_by", "approved_at", "requested_at", "updated_at"])
        
        return success_response({
            "transfer": cls.serialize(transfer, include_items=True)
        }, "Transfer approved")
    
    @classmethod
    @transaction.atomic
    def ship(cls, transfer_id: int, shipped_by_id: int) -> Dict[str, Any]:
        """Ship transfer (deduct from source location)"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status != "APPROVED":
            raise BusinessRuleError(f"Can only ship APPROVED transfers")
        
        from .level_service import StockLevelService
        
        # Deduct from source location
        for item in transfer.items.select_related("stock_item", "unit"):
            qty = item.approved_qty or item.requested_qty
            
            StockLevelService.adjust(
                stock_item_id=item.stock_item_id,
                location_id=transfer.from_location_id,
                quantity=-qty,
                movement_type="TRANSFER_OUT",
                user_id=shipped_by_id,
                batch_id=item.batch_id,
                transfer_id=transfer.id,
                notes=f"Transfer to {transfer.to_location.name}"
            )
            
            item.shipped_qty = qty
            item.save(update_fields=["shipped_qty"])
        
        transfer.status = StockTransfer.Status.IN_TRANSIT
        transfer.shipped_by_id = shipped_by_id
        transfer.shipped_at = timezone.now()
        transfer.save(update_fields=["status", "shipped_by", "shipped_at", "updated_at"])
        
        return success_response({
            "transfer": cls.serialize(transfer, include_items=True)
        }, "Transfer shipped")
    
    @classmethod
    @transaction.atomic
    def receive(cls, transfer_id: int, received_by_id: int,
                received_quantities: Dict[int, Decimal] = None) -> Dict[str, Any]:
        """Receive transfer (add to destination location)"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status != "IN_TRANSIT":
            raise BusinessRuleError(f"Can only receive IN_TRANSIT transfers")
        
        from .level_service import StockLevelService
        
        # Add to destination location
        for item in transfer.items.select_related("stock_item", "unit"):
            # Allow partial receiving
            if received_quantities and item.id in received_quantities:
                qty = to_decimal(received_quantities[item.id])
            else:
                qty = item.shipped_qty or item.approved_qty or item.requested_qty
            
            StockLevelService.adjust(
                stock_item_id=item.stock_item_id,
                location_id=transfer.to_location_id,
                quantity=qty,
                movement_type="TRANSFER_IN",
                user_id=received_by_id,
                batch_id=item.batch_id,
                transfer_id=transfer.id,
                notes=f"Transfer from {transfer.from_location.name}"
            )
            
            item.received_qty = qty
            
            # Check for variance
            shipped = item.shipped_qty or item.approved_qty or item.requested_qty
            if qty != shipped:
                item.variance_reason = f"Shipped: {shipped}, Received: {qty}"
            
            item.save(update_fields=["received_qty", "variance_reason"])
        
        transfer.status = StockTransfer.Status.RECEIVED
        transfer.received_by_id = received_by_id
        transfer.received_at = timezone.now()
        transfer.save(update_fields=["status", "received_by", "received_at", "updated_at"])
        
        return success_response({
            "transfer": cls.serialize(transfer, include_items=True)
        }, "Transfer received")
    
    @classmethod
    @transaction.atomic
    def cancel(cls, transfer_id: int, reason: str = "") -> Dict[str, Any]:
        """Cancel transfer"""
        transfer = cls.get_by_id(transfer_id)
        if not transfer:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status in ["RECEIVED", "CANCELLED"]:
            raise BusinessRuleError(f"Cannot cancel {transfer.status} transfer")
        
        # If already shipped, need to reverse
        if transfer.status == "IN_TRANSIT":
            from .level_service import StockLevelService
            
            # Reverse the deduction
            for item in transfer.items.select_related("stock_item"):
                qty = item.shipped_qty or item.approved_qty or item.requested_qty
                
                StockLevelService.adjust(
                    stock_item_id=item.stock_item_id,
                    location_id=transfer.from_location_id,
                    quantity=qty,
                    movement_type="TRANSFER_IN",  # Reversing, so it's IN
                    user_id=transfer.shipped_by_id or transfer.requested_by_id,
                    transfer_id=transfer.id,
                    notes=f"Transfer cancelled: {reason}"
                )
        
        transfer.status = StockTransfer.Status.CANCELLED
        if reason:
            transfer.notes = f"{transfer.notes}\nCancelled: {reason}".strip()
        transfer.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "transfer": cls.serialize(transfer)
        }, "Transfer cancelled")
    
    # ==================== QUICK TRANSFER ====================
    
    @classmethod
    @transaction.atomic
    def quick_transfer(cls,
                       from_location_id: int,
                       to_location_id: int,
                       stock_item_id: int,
                       quantity: Decimal,
                       user_id: int,
                       unit_id: int = None,
                       batch_id: int = None,
                       notes: str = "") -> Dict[str, Any]:
        """Perform immediate transfer without approval workflow"""
        
        # Create transfer
        result = cls.create(
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            requested_by_id=user_id,
            notes=notes,
            items=[{
                "stock_item_id": stock_item_id,
                "quantity": quantity,
                "unit_id": unit_id,
                "batch_id": batch_id,
            }]
        )
        
        transfer_id = result["id"]
        
        # Approve and ship immediately
        cls.approve(transfer_id, user_id)
        cls.ship(transfer_id, user_id)
        cls.receive(transfer_id, user_id)
        
        return cls.get(transfer_id)


class StockTransferItemService(BaseService):
    """Manage transfer line items"""
    
    model = StockTransferItem
    
    @classmethod
    def serialize(cls, item: StockTransferItem) -> Dict[str, Any]:
        """Serialize transfer item"""
        return {
            "id": item.id,
            "uuid": str(item.uuid),
            "stock_item_id": item.stock_item_id,
            "stock_item": {
                "id": item.stock_item.id,
                "name": item.stock_item.name,
                "sku": item.stock_item.sku,
            },
            "batch_id": item.batch_id,
            "batch_number": item.batch.batch_number if item.batch else None,
            "requested_qty": str(item.requested_qty),
            "approved_qty": str(item.approved_qty) if item.approved_qty else None,
            "shipped_qty": str(item.shipped_qty) if item.shipped_qty else None,
            "received_qty": str(item.received_qty) if item.received_qty else None,
            "unit_id": item.unit_id,
            "unit_short": item.unit.short_name,
            "variance_reason": item.variance_reason,
        }
    
    @classmethod
    @transaction.atomic
    def add_item(cls,
                 transfer_id: int,
                 stock_item_id: int,
                 requested_qty: Decimal,
                 unit_id: int = None,
                 batch_id: int = None) -> Dict[str, Any]:
        """Add item to transfer"""
        
        # Validate transfer
        try:
            transfer = StockTransfer.objects.get(id=transfer_id)
        except StockTransfer.DoesNotExist:
            raise NotFoundError("Transfer", transfer_id)
        
        if transfer.status not in ["DRAFT", "REQUESTED"]:
            raise BusinessRuleError("Cannot add items to approved/shipped transfer")
        
        # Validate stock item
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        # Validate unit
        if unit_id:
            try:
                unit = StockUnit.objects.get(id=unit_id)
            except StockUnit.DoesNotExist:
                raise NotFoundError("Unit", unit_id)
        else:
            unit = stock_item.base_unit
        
        # Validate batch
        batch = None
        if batch_id:
            try:
                batch = StockBatch.objects.get(
                    id=batch_id,
                    stock_item=stock_item,
                    location=transfer.from_location
                )
            except StockBatch.DoesNotExist:
                raise NotFoundError("Batch", batch_id)
        
        # Check if item already exists
        existing = cls.model.objects.filter(
            transfer=transfer,
            stock_item=stock_item,
            batch=batch
        ).first()
        
        if existing:
            # Update quantity
            existing.requested_qty += to_decimal(requested_qty)
            existing.save(update_fields=["requested_qty"])
            return success_response({
                "item": cls.serialize(existing)
            }, "Item quantity updated")
        
        item = cls.model.objects.create(
            transfer=transfer,
            stock_item=stock_item,
            batch=batch,
            requested_qty=to_decimal(requested_qty),
            unit=unit,
        )
        
        return success_response({
            "id": item.id,
            "item": cls.serialize(item)
        }, "Item added to transfer")
    
    @classmethod
    @transaction.atomic
    def update_item(cls, item_id: int, **kwargs) -> Dict[str, Any]:
        """Update transfer item"""
        try:
            item = cls.model.objects.select_related("transfer").get(id=item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Transfer item", item_id)
        
        if item.transfer.status not in ["DRAFT", "REQUESTED"]:
            raise BusinessRuleError("Cannot update items on approved/shipped transfer")
        
        if "requested_qty" in kwargs:
            item.requested_qty = to_decimal(kwargs["requested_qty"])
        
        item.save()
        
        return success_response({
            "item": cls.serialize(item)
        }, "Item updated")
    
    @classmethod
    @transaction.atomic
    def remove_item(cls, item_id: int) -> Dict[str, Any]:
        """Remove item from transfer"""
        try:
            item = cls.model.objects.select_related("transfer").get(id=item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Transfer item", item_id)
        
        if item.transfer.status not in ["DRAFT", "REQUESTED"]:
            raise BusinessRuleError("Cannot remove items from approved/shipped transfer")
        
        item.delete()
        
        return success_response(message="Item removed from transfer")