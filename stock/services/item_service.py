from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    StockItem, StockCategory, StockUnit, StockItemUnit,
    StockLevel, StockBatch, StockTransaction, StockLocation,
    SupplierStockItem
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal, round_decimal
)


class StockItemService(BaseService):
    model = StockItem
    
    @classmethod
    def serialize(cls, item: StockItem, 
                  include_levels: bool = False,
                  include_units: bool = False,
                  include_suppliers: bool = False,
                  location_id: int = None) -> Dict[str, Any]:
        data = {
            "id": item.id,
            "uuid": str(item.uuid),
            "name": item.name,
            "sku": item.sku,
            "barcode": item.barcode,
            "item_type": item.item_type,
            "item_type_display": item.get_item_type_display(),
            
            "category_id": item.category_id,
            "category": {
                "id": item.category.id,
                "name": item.category.name,
            } if item.category else None,
            
            "base_unit_id": item.base_unit_id,
            "base_unit": {
                "id": item.base_unit.id,
                "name": item.base_unit.name,
                "short_name": item.base_unit.short_name,
            },
            
            "min_stock_level": str(item.min_stock_level),
            "max_stock_level": str(item.max_stock_level) if item.max_stock_level else None,
            "reorder_point": str(item.reorder_point),
            
            "cost_price": str(item.cost_price),
            "avg_cost_price": str(item.avg_cost_price),
            "last_cost_price": str(item.last_cost_price),
            
            "is_purchasable": item.is_purchasable,
            "is_sellable": item.is_sellable,
            "is_producible": item.is_producible,
            "track_batches": item.track_batches,
            "track_expiry": item.track_expiry,
            "default_expiry_days": item.default_expiry_days,
            "storage_conditions": item.storage_conditions,
            
            "is_active": item.is_active,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        
        if include_levels:
            levels_query = StockLevel.objects.filter(stock_item=item)
            if location_id:
                levels_query = levels_query.filter(location_id=location_id)
            
            data["stock_levels"] = [
                {
                    "location_id": lvl.location_id,
                    "location_name": lvl.location.name,
                    "quantity": str(lvl.quantity),
                    "reserved": str(lvl.reserved_quantity),
                    "available": str(lvl.available_quantity),
                    "pending_in": str(lvl.pending_in_quantity),
                    "pending_out": str(lvl.pending_out_quantity),
                }
                for lvl in levels_query.select_related("location")
            ]
            
            totals = levels_query.aggregate(
                total=Sum("quantity"),
                reserved=Sum("reserved_quantity")
            )
            data["total_stock"] = str(totals["total"] or 0)
            data["total_reserved"] = str(totals["reserved"] or 0)
        
        if include_units:
            data["alternative_units"] = [
                {
                    "id": au.id,
                    "unit_id": au.unit_id,
                    "unit_name": au.unit.name,
                    "short_name": au.unit.short_name,
                    "conversion_to_base": str(au.conversion_to_base),
                    "is_default": au.is_default,
                    "barcode": au.barcode,
                }
                for au in item.alternative_units.select_related("unit")
            ]
        
        if include_suppliers:
            data["suppliers"] = [
                {
                    "supplier_id": si.supplier_id,
                    "supplier_name": si.supplier.name,
                    "supplier_sku": si.supplier_sku,
                    "price": str(si.price),
                    "currency": si.currency,
                    "min_order_qty": str(si.min_order_qty),
                    "is_preferred": si.is_preferred,
                    "lead_time_days": si.lead_time_days,
                }
                for si in item.suppliers.select_related("supplier")
            ]
        
        return data
    
    @classmethod
    def serialize_brief(cls, item: StockItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "uuid": str(item.uuid),
            "name": item.name,
            "sku": item.sku,
            "item_type": item.item_type,
            "category_id": item.category_id,
            "base_unit_short": item.base_unit.short_name,
            "is_active": item.is_active,
        }
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             search: str = None,
             category_id: int = None,
             item_type: str = None,
             active_only: bool = True,
             purchasable_only: bool = False,
             sellable_only: bool = False,
             producible_only: bool = False,
             low_stock: bool = False,
             location_id: int = None,
             include_levels: bool = False) -> Dict[str, Any]:
        
        queryset = cls.model.objects.select_related("category", "base_unit")
        
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
            valid_types = [c[0] for c in StockItem.ItemType.choices]
            if item_type not in valid_types:
                raise ValidationError(f"Invalid type. Valid: {valid_types}", "item_type")
            queryset = queryset.filter(item_type=item_type)
        
        if purchasable_only:
            queryset = queryset.filter(is_purchasable=True)
        
        if sellable_only:
            queryset = queryset.filter(is_sellable=True)
        
        if producible_only:
            queryset = queryset.filter(is_producible=True)
        
        if low_stock:
            queryset = queryset.annotate(
                total_qty=Sum("stock_levels__quantity")
            ).filter(
                Q(total_qty__lt=F("reorder_point")) |
                Q(total_qty__isnull=True)
            )
        
        queryset = queryset.order_by("name")
        
        items, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "items": [
                cls.serialize(item, include_levels=include_levels, location_id=location_id)
                for item in items
            ],
            "pagination": pagination,
            "filters": {
                "types": [{"value": c[0], "label": c[1]} for c in StockItem.ItemType.choices]
            }
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20, 
               item_type: str = None,
               purchasable_only: bool = False) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(barcode__exact=query),
            is_active=True
        ).select_related("base_unit")
        
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        
        if purchasable_only:
            queryset = queryset.filter(is_purchasable=True)
        
        items = queryset.order_by("name")[:limit]
        
        return success_response({
            "items": [cls.serialize_brief(item) for item in items],
            "count": items.count()
        })
    
    @classmethod
    def find_by_barcode(cls, barcode: str) -> Dict[str, Any]:
        item = cls.model.objects.filter(barcode=barcode, is_active=True).first()
        
        if item:
            return success_response({
                "item": cls.serialize(item, include_levels=True),
                "unit_id": item.base_unit_id,
                "conversion": "1",
            })
        
        item_unit = StockItemUnit.objects.filter(
            barcode=barcode,
            stock_item__is_active=True
        ).select_related("stock_item", "unit").first()
        
        if item_unit:
            return success_response({
                "item": cls.serialize(item_unit.stock_item, include_levels=True),
                "unit_id": item_unit.unit_id,
                "conversion": str(item_unit.conversion_to_base),
            })
        
        raise NotFoundError("Item with barcode", barcode)
    
    @classmethod
    def get(cls, item_id: int, 
            include_levels: bool = True,
            include_units: bool = True,
            include_suppliers: bool = True) -> Dict[str, Any]:
        item = cls.model.objects.select_related("category", "base_unit").filter(id=item_id).first()
        if not item:
            raise NotFoundError("Stock item", item_id)
        
        return success_response({
            "item": cls.serialize(
                item,
                include_levels=include_levels,
                include_units=include_units,
                include_suppliers=include_suppliers
            )
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               base_unit_id: int,
               item_type: str = "RAW",
               category_id: int = None,
               sku: str = None,
               barcode: str = None,
               min_stock_level: Decimal = Decimal("0"),
               max_stock_level: Decimal = None,
               reorder_point: Decimal = Decimal("0"),
               cost_price: Decimal = Decimal("0"),
               is_purchasable: bool = True,
               is_sellable: bool = False,
               is_producible: bool = False,
               track_batches: bool = False,
               track_expiry: bool = False,
               default_expiry_days: int = None,
               storage_conditions: str = "",
               initial_stock: Decimal = None,
               initial_location_id: int = None) -> Dict[str, Any]:
        
        valid_types = [c[0] for c in StockItem.ItemType.choices]
        if item_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "item_type")
        
        try:
            base_unit = StockUnit.objects.get(id=base_unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Base unit", base_unit_id)
        
        category = None
        if category_id:
            try:
                category = StockCategory.objects.get(id=category_id, is_active=True)
            except StockCategory.DoesNotExist:
                raise NotFoundError("Category", category_id)
        
        if sku:
            if cls.model.objects.filter(sku=sku).exists():
                raise ValidationError(f"SKU '{sku}' already exists", "sku")
        
        if barcode:
            if cls.model.objects.filter(barcode=barcode).exists():
                raise ValidationError(f"Barcode '{barcode}' already exists", "barcode")
        
        if not sku:
            sku = cls._generate_sku(name, item_type)
        
        item = cls.model.objects.create(
            name=name,
            base_unit=base_unit,
            item_type=item_type,
            category=category,
            sku=sku,
            barcode=barcode,
            min_stock_level=to_decimal(min_stock_level),
            max_stock_level=to_decimal(max_stock_level) if max_stock_level else None,
            reorder_point=to_decimal(reorder_point),
            cost_price=to_decimal(cost_price),
            avg_cost_price=to_decimal(cost_price),
            last_cost_price=to_decimal(cost_price),
            is_purchasable=is_purchasable,
            is_sellable=is_sellable,
            is_producible=is_producible,
            track_batches=track_batches,
            track_expiry=track_expiry,
            default_expiry_days=default_expiry_days,
            storage_conditions=storage_conditions,
        )
        
        if initial_stock and to_decimal(initial_stock) > 0:
            from stock.services.level_service import StockLevelService
            location_id = initial_location_id
            if not location_id:
                from .settings_service import StockSettingsService
                location_id = StockSettingsService.get_default_location_id()
            
            if location_id:
                StockLevelService.adjust(
                    stock_item_id=item.id,
                    location_id=location_id,
                    quantity=to_decimal(initial_stock),
                    movement_type="OPENING_BALANCE",
                    user_id=1,  # System user
                    notes="Initial stock on item creation"
                )
        
        return success_response({
            "id": item.id,
            "uuid": str(item.uuid),
            "sku": item.sku,
            "item": cls.serialize(item)
        }, f"Stock item '{name}' created")
    
    @classmethod
    def _generate_sku(cls, name: str, item_type: str) -> str:
        prefix = item_type[:3].upper()
        name_part = "".join(c for c in name.upper() if c.isalnum())[:3]
        
        existing = cls.model.objects.filter(
            sku__startswith=f"{prefix}-{name_part}"
        ).count()
        
        return f"{prefix}-{name_part}-{existing + 1:04d}"
    
    
    @classmethod
    @transaction.atomic
    def update(cls, item_id: int, **kwargs) -> Dict[str, Any]:
        item = cls.get_by_id(item_id)
        if not item:
            raise NotFoundError("Stock item", item_id)
        
        if "item_type" in kwargs:
            valid_types = [c[0] for c in StockItem.ItemType.choices]
            if kwargs["item_type"] not in valid_types:
                raise ValidationError(f"Invalid type. Valid: {valid_types}", "item_type")
        
        if "category_id" in kwargs:
            if kwargs["category_id"]:
                try:
                    category = StockCategory.objects.get(id=kwargs["category_id"], is_active=True)
                    item.category = category
                except StockCategory.DoesNotExist:
                    raise NotFoundError("Category", kwargs["category_id"])
            else:
                item.category = None
        
        if "base_unit_id" in kwargs:
            try:
                base_unit = StockUnit.objects.get(id=kwargs["base_unit_id"], is_active=True)
                if StockTransaction.objects.filter(stock_item=item).exists():
                    raise BusinessRuleError("Cannot change base unit for item with transactions")
                item.base_unit = base_unit
            except StockUnit.DoesNotExist:
                raise NotFoundError("Base unit", kwargs["base_unit_id"])
        
        if "sku" in kwargs and kwargs["sku"] != item.sku:
            if cls.model.objects.filter(sku=kwargs["sku"]).exclude(id=item_id).exists():
                raise ValidationError(f"SKU '{kwargs['sku']}' already exists", "sku")
        
        if "barcode" in kwargs and kwargs["barcode"] != item.barcode:
            if kwargs["barcode"] and cls.model.objects.filter(barcode=kwargs["barcode"]).exclude(id=item_id).exists():
                raise ValidationError(f"Barcode '{kwargs['barcode']}' already exists", "barcode")
        
        update_fields = ["updated_at"]
        direct_fields = [
            "name", "sku", "barcode", "item_type",
            "min_stock_level", "max_stock_level", "reorder_point",
            "cost_price", "is_purchasable", "is_sellable", "is_producible",
            "track_batches", "track_expiry", "default_expiry_days", "storage_conditions"
        ]
        
        for field in direct_fields:
            if field in kwargs:
                value = kwargs[field]
                if field in ["min_stock_level", "max_stock_level", "reorder_point", "cost_price"]:
                    value = to_decimal(value) if value is not None else None
                setattr(item, field, value)
                update_fields.append(field)
        
        if "category_id" in kwargs:
            update_fields.append("category")
        if "base_unit_id" in kwargs:
            update_fields.append("base_unit")
        
        item.save(update_fields=update_fields)
        
        return success_response({
            "item": cls.serialize(item, include_levels=True)
        }, "Stock item updated")
    
    @classmethod
    @transaction.atomic
    def update_cost(cls, item_id: int, new_cost: Decimal, 
                    update_type: str = "LAST") -> Dict[str, Any]:
        item = cls.get_by_id(item_id)
        if not item:
            raise NotFoundError("Stock item", item_id)
        
        new_cost = to_decimal(new_cost)
        update_fields = ["updated_at", "last_cost_price"]
        item.last_cost_price = new_cost
        
        if update_type == "ALL":
            item.cost_price = new_cost
            item.avg_cost_price = new_cost
            update_fields.extend(["cost_price", "avg_cost_price"])
        elif update_type == "AVG":
            total_qty = StockLevel.objects.filter(stock_item=item).aggregate(
                total=Sum("quantity")
            )["total"] or Decimal("0")
            
            if total_qty > 0:
                old_value = total_qty * item.avg_cost_price
                new_avg = (old_value + new_cost) / (total_qty + 1)
                item.avg_cost_price = round_decimal(new_avg, 4)
            else:
                item.avg_cost_price = new_cost
            update_fields.append("avg_cost_price")
        
        item.save(update_fields=update_fields)
        
        return success_response({
            "cost_price": str(item.cost_price),
            "avg_cost_price": str(item.avg_cost_price),
            "last_cost_price": str(item.last_cost_price),
        }, "Cost updated")
    
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, item_id: int, force: bool = False) -> Dict[str, Any]:
        item = cls.get_by_id(item_id)
        if not item:
            raise NotFoundError("Stock item", item_id)
        
        if not force:
            total_stock = StockLevel.objects.filter(stock_item=item).aggregate(
                total=Sum("quantity")
            )["total"] or 0
            
            if total_stock > 0:
                raise BusinessRuleError(
                    f"Cannot deactivate item with {total_stock} in stock. "
                    "Adjust stock to zero first or use force=True."
                )
        
        item.is_active = False
        item.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "id": item_id
        }, "Stock item deactivated")
    
    @classmethod
    @transaction.atomic
    def activate(cls, item_id: int) -> Dict[str, Any]:
        item = cls.get_by_id(item_id)
        if not item:
            raise NotFoundError("Stock item", item_id)
        
        item.is_active = True
        item.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "item": cls.serialize(item)
        }, "Stock item activated")
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        total = cls.model.objects.filter(is_active=True).count()
        by_type = {}
        
        for type_choice in StockItem.ItemType.choices:
            by_type[type_choice[0]] = cls.model.objects.filter(
                is_active=True,
                item_type=type_choice[0]
            ).count()
        
        low_stock = cls.model.objects.filter(
            is_active=True
        ).annotate(
            total_qty=Sum("stock_levels__quantity")
        ).filter(
            Q(total_qty__lt=F("reorder_point")) |
            Q(total_qty__isnull=True)
        ).count()
        
        no_category = cls.model.objects.filter(
            is_active=True,
            category__isnull=True
        ).count()
        
        return success_response({
            "total_items": total,
            "by_type": by_type,
            "low_stock_count": low_stock,
            "no_category_count": no_category,
        })