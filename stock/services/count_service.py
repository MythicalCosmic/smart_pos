from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    StockCount, StockCountItem, VarianceReasonCode,
    StockLocation, StockCategory, StockItem, StockLevel,
    StockBatch, StockSettings
)
from base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal, round_decimal, generate_number
)


class VarianceReasonCodeService(BaseService):
    model = VarianceReasonCode
    
    @classmethod
    def serialize(cls, code: VarianceReasonCode) -> Dict[str, Any]:
        return {
            "id": code.id,
            "uuid": str(code.uuid),
            "code": code.code,
            "name": code.name,
            "description": code.description,
            "requires_approval": code.requires_approval,
            "is_active": code.is_active,
        }
    
    @classmethod
    def list(cls, active_only: bool = True) -> Dict[str, Any]:
        queryset = cls.model.objects.all()
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        queryset = queryset.order_by("code")
        
        return success_response({
            "codes": [cls.serialize(c) for c in queryset],
            "count": queryset.count()
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               code: str,
               name: str,
               description: str = "",
               requires_approval: bool = False) -> Dict[str, Any]:
        
        if cls.model.objects.filter(code=code).exists():
            raise ValidationError(f"Code '{code}' already exists", "code")
        
        reason_code = cls.model.objects.create(
            code=code.upper(),
            name=name,
            description=description,
            requires_approval=requires_approval,
        )
        
        return success_response({
            "id": reason_code.id,
            "code": cls.serialize(reason_code)
        }, f"Variance code '{code}' created")
    
    @classmethod
    @transaction.atomic
    def update(cls, code_id: int, **kwargs) -> Dict[str, Any]:
        try:
            reason_code = cls.model.objects.get(id=code_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Variance code", code_id)
        
        for field in ["name", "description", "requires_approval", "is_active"]:
            if field in kwargs:
                setattr(reason_code, field, kwargs[field])
        
        reason_code.save()
        
        return success_response({
            "code": cls.serialize(reason_code)
        }, "Variance code updated")
    
    @classmethod
    def get_default_codes(cls) -> List[Dict]:
        return [
            {"code": "DAMAGE", "name": "Damaged", "description": "Item damaged", "requires_approval": True},
            {"code": "THEFT", "name": "Theft", "description": "Suspected theft", "requires_approval": True},
            {"code": "EXPIRED", "name": "Expired", "description": "Item expired", "requires_approval": False},
            {"code": "COUNT_ERR", "name": "Count Error", "description": "Previous count error", "requires_approval": False},
            {"code": "UNRECORDED", "name": "Unrecorded Movement", "description": "Movement not recorded", "requires_approval": True},
            {"code": "WASTE", "name": "Waste", "description": "Normal waste", "requires_approval": False},
            {"code": "SAMPLE", "name": "Sample", "description": "Used as sample", "requires_approval": False},
            {"code": "OTHER", "name": "Other", "description": "Other reason", "requires_approval": True},
        ]
    
    @classmethod
    @transaction.atomic
    def seed_defaults(cls) -> Dict[str, Any]:
        created = 0
        for code_data in cls.get_default_codes():
            if not cls.model.objects.filter(code=code_data["code"]).exists():
                cls.model.objects.create(**code_data)
                created += 1
        
        return success_response({
            "created": created
        }, f"Created {created} variance code(s)")


class StockCountService(BaseService):
    model = StockCount
    
    @classmethod
    def serialize(cls, count: StockCount, include_items: bool = False) -> Dict[str, Any]:
        data = {
            "id": count.id,
            "uuid": str(count.uuid),
            "count_number": count.count_number,
            
            "location_id": count.location_id,
            "location": {
                "id": count.location.id,
                "name": count.location.name,
            },
            
            "count_type": count.count_type,
            "count_type_display": count.get_count_type_display(),
            
            "category_filter_id": count.category_filter_id,
            "category_filter_name": count.category_filter.name if count.category_filter else None,
            
            "status": count.status,
            "status_display": count.get_status_display(),
            
            "started_at": count.started_at.isoformat() if count.started_at else None,
            "completed_at": count.completed_at.isoformat() if count.completed_at else None,
            
            "counted_by_id": count.counted_by_id,
            "approved_by_id": count.approved_by_id,
            "auto_adjust": count.auto_adjust,
            
            "notes": count.notes,
            "created_at": count.created_at.isoformat(),
        }
        
        if include_items:
            items = count.items.select_related(
                "stock_item", "batch", "reason_code"
            ).order_by("stock_item__name")
            
            data["items"] = [StockCountItemService.serialize(item) for item in items]
            data["item_count"] = items.count()
            
            # Summary statistics
            counted = items.filter(counted_quantity__isnull=False)
            data["summary"] = {
                "total_items": items.count(),
                "counted_items": counted.count(),
                "pending_items": items.filter(counted_quantity__isnull=True).count(),
                "items_with_variance": counted.exclude(variance=0).count(),
                "total_variance_cost": str(
                    counted.aggregate(total=Sum("variance_cost"))["total"] or 0
                ),
            }
        
        return data
    
    @classmethod
    def serialize_brief(cls, count: StockCount) -> Dict[str, Any]:
        """Brief serialization"""
        return {
            "id": count.id,
            "count_number": count.count_number,
            "location_name": count.location.name,
            "count_type": count.count_type,
            "status": count.status,
            "created_at": count.created_at.isoformat(),
        }
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             location_id: int = None,
             status: str = None,
             count_type: str = None,
             date_from: date = None,
             date_to: date = None) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related("location", "category_filter")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if count_type:
            queryset = queryset.filter(count_type=count_type)
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        queryset = queryset.order_by("-created_at")
        
        counts, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "counts": [cls.serialize_brief(c) for c in counts],
            "pagination": pagination,
            "statuses": [{"value": c[0], "label": c[1]} for c in StockCount.Status.choices],
            "count_types": [{"value": c[0], "label": c[1]} for c in StockCount.CountType.choices],
        })
    
    @classmethod
    def get_active(cls, location_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(
            status__in=["DRAFT", "IN_PROGRESS"]
        ).select_related("location")
        
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        return success_response({
            "counts": [cls.serialize_brief(c) for c in queryset.order_by("-created_at")],
            "count": queryset.count()
        })
    
    @classmethod
    def get(cls, count_id: int, include_items: bool = True) -> Dict[str, Any]:
        count = cls.model.objects.select_related(
            "location", "category_filter"
        ).filter(id=count_id).first()
        
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        return success_response({
            "count": cls.serialize(count, include_items=include_items)
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               location_id: int,
               count_type: str,
               counted_by_id: int,
               category_id: int = None,
               auto_adjust: bool = False,
               notes: str = "",
               include_zero_stock: bool = True) -> Dict[str, Any]:
        try:
            location = StockLocation.objects.get(id=location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Location", location_id)
        
        # Validate count type
        valid_types = [c[0] for c in StockCount.CountType.choices]
        if count_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "count_type")
        
        category = None
        if category_id:
            try:
                category = StockCategory.objects.get(id=category_id, is_active=True)
            except StockCategory.DoesNotExist:
                raise NotFoundError("Category", category_id)
        
        existing = cls.model.objects.filter(
            location=location,
            status__in=["DRAFT", "IN_PROGRESS"]
        ).first()
        
        if existing:
            raise BusinessRuleError(
                f"Active count already exists at this location: {existing.count_number}"
            )
        
        count_number = generate_number("CNT", cls.model, "count_number")
        
        count = cls.model.objects.create(
            count_number=count_number,
            location=location,
            count_type=count_type,
            category_filter=category,
            status=StockCount.Status.DRAFT,
            counted_by_id=counted_by_id,
            auto_adjust=auto_adjust,
            notes=notes,
        )
        
        items_created = cls._populate_count_items(count, include_zero_stock)
        
        return success_response({
            "id": count.id,
            "count_number": count_number,
            "items_created": items_created,
            "count": cls.serialize(count, include_items=True)
        }, f"Stock count {count_number} created with {items_created} items")
    
    @classmethod
    def _populate_count_items(cls, count: StockCount, include_zero_stock: bool) -> int:
        queryset = StockLevel.objects.filter(
            location=count.location,
            stock_item__is_active=True
        ).select_related("stock_item")
        
        if count.category_filter:
            queryset = queryset.filter(stock_item__category=count.category_filter)
        
        if not include_zero_stock:
            queryset = queryset.filter(quantity__gt=0)
        
        settings = StockSettings.load()
        items_created = 0
        
        for level in queryset:
            if settings.track_batches and level.stock_item.track_batches:
                batches = StockBatch.objects.filter(
                    stock_item=level.stock_item,
                    location=count.location,
                    current_quantity__gt=0
                )
                
                for batch in batches:
                    StockCountItem.objects.create(
                        stock_count=count,
                        stock_item=level.stock_item,
                        batch=batch,
                        system_quantity=batch.current_quantity,
                    )
                    items_created += 1
            else:
                StockCountItem.objects.create(
                    stock_count=count,
                    stock_item=level.stock_item,
                    system_quantity=level.quantity,
                )
                items_created += 1
        
        return items_created
    
    @classmethod
    @transaction.atomic
    def start(cls, count_id: int) -> Dict[str, Any]:
        count = cls.get_by_id(count_id)
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        if count.status != "DRAFT":
            raise BusinessRuleError(f"Can only start DRAFT counts")
        
        count.status = StockCount.Status.IN_PROGRESS
        count.started_at = timezone.now()
        count.save(update_fields=["status", "started_at", "updated_at"])
        
        return success_response({
            "count": cls.serialize(count)
        }, "Counting started")
    
    @classmethod
    @transaction.atomic
    def record_count(cls,
                     count_id: int,
                     item_id: int,
                     counted_quantity: Decimal,
                     reason_code_id: int = None,
                     notes: str = "") -> Dict[str, Any]:
        count = cls.get_by_id(count_id)
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        if count.status not in ["DRAFT", "IN_PROGRESS"]:
            raise BusinessRuleError(f"Cannot record counts for {count.status} count")
        
        try:
            item = StockCountItem.objects.get(id=item_id, stock_count=count)
        except StockCountItem.DoesNotExist:
            raise NotFoundError("Count item", item_id)
        
        if count.status == "DRAFT":
            count.status = StockCount.Status.IN_PROGRESS
            count.started_at = timezone.now()
            count.save(update_fields=["status", "started_at", "updated_at"])
        
        counted_quantity = to_decimal(counted_quantity)
        
        variance = counted_quantity - item.system_quantity
        variance_percentage = Decimal("0")
        if item.system_quantity != 0:
            variance_percentage = (variance / item.system_quantity) * 100
        
        unit_cost = item.stock_item.avg_cost_price
        variance_cost = variance * unit_cost
        
        reason_code = None
        if reason_code_id:
            try:
                reason_code = VarianceReasonCode.objects.get(id=reason_code_id, is_active=True)
            except VarianceReasonCode.DoesNotExist:
                raise NotFoundError("Reason code", reason_code_id)
        
        item.counted_quantity = counted_quantity
        item.variance = variance
        item.variance_percentage = round_decimal(variance_percentage, 2)
        item.variance_cost = round_decimal(variance_cost, 4)
        item.reason_code = reason_code
        item.notes = notes
        item.save()
        
        return success_response({
            "item": StockCountItemService.serialize(item)
        }, "Count recorded")
    
    @classmethod
    @transaction.atomic
    def complete(cls, count_id: int) -> Dict[str, Any]:
        count = cls.get_by_id(count_id)
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        if count.status != "IN_PROGRESS":
            raise BusinessRuleError(f"Can only complete IN_PROGRESS counts")
        
        uncounted = count.items.filter(counted_quantity__isnull=True).count()
        if uncounted > 0:
            raise BusinessRuleError(f"{uncounted} item(s) not yet counted")
        
        settings = StockSettings.load()
        
        if settings.require_count_approval:
            count.status = StockCount.Status.PENDING_APPROVAL
        else:
            count.status = StockCount.Status.APPROVED
            count.approved_by = count.counted_by
        
        count.completed_at = timezone.now()
        count.save(update_fields=["status", "completed_at", "approved_by", "updated_at"])
        
        if count.auto_adjust and count.status == "APPROVED":
            cls._apply_adjustments(count)
        
        return success_response({
            "count": cls.serialize(count, include_items=True)
        }, "Counting completed")
    
    @classmethod
    @transaction.atomic
    def approve(cls, count_id: int, approved_by_id: int, apply_adjustments: bool = True) -> Dict[str, Any]:
        count = cls.get_by_id(count_id)
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        if count.status != "PENDING_APPROVAL":
            raise BusinessRuleError(f"Can only approve PENDING_APPROVAL counts")
        
        count.status = StockCount.Status.APPROVED
        count.approved_by_id = approved_by_id
        count.save(update_fields=["status", "approved_by", "updated_at"])
        
        if apply_adjustments:
            cls._apply_adjustments(count)
        
        return success_response({
            "count": cls.serialize(count, include_items=True)
        }, "Count approved and adjustments applied")
    
    @classmethod
    def _apply_adjustments(cls, count: StockCount):
        from .level_service import StockLevelService
        
        items_with_variance = count.items.exclude(variance=0).select_related(
            "stock_item", "batch"
        )
        
        for item in items_with_variance:
            if item.variance == 0:
                continue
            
            if item.variance > 0:
                movement_type = "COUNT_ADJUSTMENT" 
            else:
                movement_type = "COUNT_ADJUSTMENT" 
            
            result = StockLevelService.adjust(
                stock_item_id=item.stock_item_id,
                location_id=count.location_id,
                movement_type=movement_type,
                user_id=count.approved_by_id or count.counted_by_id,
                batch_id=item.batch_id,
                reference_type="StockCount",
                reference_id=count.id,
                notes=f"Count adjustment: {count.count_number}"
            )
            
            item.is_adjusted = True
            if "transaction_id" in result:
                from stock.models import StockTransaction
                item.adjustment_transaction_id = result["transaction_id"]
            item.save(update_fields=["is_adjusted", "adjustment_transaction"])
        
        StockLevel.objects.filter(
            location=count.location,
            stock_item__in=count.items.values("stock_item")
        ).update(last_counted_at=timezone.now())
    
    @classmethod
    @transaction.atomic
    def cancel(cls, count_id: int, reason: str = "") -> Dict[str, Any]:
        count = cls.get_by_id(count_id)
        if not count:
            raise NotFoundError("Stock count", count_id)
        
        if count.status == "APPROVED":
            raise BusinessRuleError("Cannot cancel approved count")
        
        if count.status == "CANCELLED":
            raise BusinessRuleError("Count already cancelled")
        
        count.status = StockCount.Status.CANCELLED
        if reason:
            count.notes = f"{count.notes}\nCancelled: {reason}".strip()
        count.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "count": cls.serialize(count)
        }, "Stock count cancelled")
    
    @classmethod
    @transaction.atomic
    def create_blind_count(cls,
                           location_id: int,
                           counted_by_id: int,
                           count_type: str = "SPOT",
                           notes: str = "") -> Dict[str, Any]:
        result = cls.create(
            location_id=location_id,
            count_type=count_type,
            counted_by_id=counted_by_id,
            notes=notes,
            include_zero_stock=False,
        )
        
        
        return result


class StockCountItemService(BaseService):
    
    model = StockCountItem
    
    @classmethod
    def serialize(cls, item: StockCountItem, hide_system_qty: bool = False) -> Dict[str, Any]:
        data = {
            "id": item.id,
            "uuid": str(item.uuid),
            "stock_item_id": item.stock_item_id,
            "stock_item": {
                "id": item.stock_item.id,
                "name": item.stock_item.name,
                "sku": item.stock_item.sku,
                "unit": item.stock_item.base_unit.short_name,
            },
            "batch_id": item.batch_id,
            "batch_number": item.batch.batch_number if item.batch else None,
            "counted_quantity": str(item.counted_quantity) if item.counted_quantity is not None else None,
            "is_counted": item.counted_quantity is not None,
            "notes": item.notes,
            "is_adjusted": item.is_adjusted,
        }
        
        if hide_system_qty and item.counted_quantity is None:
            data["system_quantity"] = "***"
            data["variance"] = None
            data["variance_percentage"] = None
            data["variance_cost"] = None
        else:
            data["system_quantity"] = str(item.system_quantity)
            data["variance"] = str(item.variance) if item.variance is not None else None
            data["variance_percentage"] = str(item.variance_percentage) if item.variance_percentage is not None else None
            data["variance_cost"] = str(item.variance_cost) if item.variance_cost is not None else None
        
        # Reason code
        if item.reason_code:
            data["reason_code"] = {
                "id": item.reason_code.id,
                "code": item.reason_code.code,
                "name": item.reason_code.name,
            }
        else:
            data["reason_code"] = None
        
        return data
    
    @classmethod
    def get_uncounted(cls, count_id: int) -> Dict[str, Any]:
        items = cls.model.objects.filter(
            stock_count_id=count_id,
            counted_quantity__isnull=True
        ).select_related("stock_item", "batch")
        
        return success_response({
            "items": [cls.serialize(item) for item in items],
            "count": items.count()
        })
    
    @classmethod
    def get_with_variance(cls, count_id: int) -> Dict[str, Any]:
        items = cls.model.objects.filter(
            stock_count_id=count_id,
            counted_quantity__isnull=False
        ).exclude(variance=0).select_related("stock_item", "batch", "reason_code")
        
        return success_response({
            "items": [cls.serialize(item) for item in items],
            "count": items.count()
        })