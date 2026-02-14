from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone

from stock.models import (
    Supplier, SupplierStockItem, StockItem, StockUnit,
    PurchaseOrder
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal
)


class SupplierService(BaseService):
    model = Supplier
    
    @classmethod
    def serialize(cls, supplier: Supplier, 
                  include_items: bool = False,
                  include_stats: bool = False) -> Dict[str, Any]:
        data = {
            "id": supplier.id,
            "uuid": str(supplier.uuid),
            "code": supplier.code,
            "name": supplier.name,
            "legal_name": supplier.legal_name,
            
            "contact_person": supplier.contact_person,
            "email": supplier.email,
            "phone": supplier.phone,
            "mobile": supplier.mobile,
            
            "address": supplier.address,
            "city": supplier.city,
            "country": supplier.country,
            "tax_id": supplier.tax_id,
            
            "payment_terms_days": supplier.payment_terms_days,
            "credit_limit": str(supplier.credit_limit) if supplier.credit_limit else None,
            "current_balance": str(supplier.current_balance),
            "currency": supplier.currency,
            
            "lead_time_days": supplier.lead_time_days,
            "minimum_order_value": str(supplier.minimum_order_value) if supplier.minimum_order_value else None,
            
            "rating": supplier.rating,
            "is_active": supplier.is_active,
            "notes": supplier.notes,
            "created_at": supplier.created_at.isoformat(),
        }
        
        if include_items:
            data["items"] = [
                SupplierStockItemService.serialize(si)
                for si in supplier.stock_items.select_related("stock_item", "unit")
            ]
            data["item_count"] = supplier.stock_items.count()
        
        if include_stats:
            po_stats = PurchaseOrder.objects.filter(supplier=supplier).aggregate(
                total_orders=Count("id"),
                total_value=Sum("total"),
                avg_order_value=Avg("total")
            )
            data["stats"] = {
                "total_orders": po_stats["total_orders"] or 0,
                "total_value": str(po_stats["total_value"] or 0),
                "avg_order_value": str(po_stats["avg_order_value"] or 0),
            }
        
        return data
    
    @classmethod
    def serialize_brief(cls, supplier: Supplier) -> Dict[str, Any]:
        return {
            "id": supplier.id,
            "uuid": str(supplier.uuid),
            "code": supplier.code,
            "name": supplier.name,
            "city": supplier.city,
            "rating": supplier.rating,
            "is_active": supplier.is_active,
        }
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             search: str = None,
             active_only: bool = True,
             has_items_only: bool = False) -> Dict[str, Any]:
        queryset = cls.model.objects.all()
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(contact_person__icontains=search) |
                Q(email__icontains=search)
            )
        
        if has_items_only:
            queryset = queryset.annotate(
                item_count=Count("stock_items")
            ).filter(item_count__gt=0)
        
        queryset = queryset.order_by("name")
        
        suppliers, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "suppliers": [cls.serialize_brief(s) for s in suppliers],
            "pagination": pagination
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20) -> Dict[str, Any]:
        suppliers = cls.model.objects.filter(
            Q(name__icontains=query) | Q(code__icontains=query),
            is_active=True
        ).order_by("name")[:limit]
        
        return success_response({
            "suppliers": [cls.serialize_brief(s) for s in suppliers],
            "count": suppliers.count()
        })
    
    @classmethod
    def get_for_item(cls, stock_item_id: int) -> Dict[str, Any]:
        supplier_items = SupplierStockItem.objects.filter(
            stock_item_id=stock_item_id,
            supplier__is_active=True
        ).select_related("supplier", "unit").order_by("-is_preferred", "price")
        
        suppliers = []
        for si in supplier_items:
            suppliers.append({
                "supplier": cls.serialize_brief(si.supplier),
                "supplier_sku": si.supplier_sku,
                "supplier_name": si.supplier_name,
                "price": str(si.price),
                "currency": si.currency,
                "min_order_qty": str(si.min_order_qty),
                "pack_size": str(si.pack_size),
                "lead_time_days": si.lead_time_days,
                "is_preferred": si.is_preferred,
            })
        
        return success_response({
            "suppliers": suppliers,
            "count": len(suppliers)
        })
    
    @classmethod
    def get(cls, supplier_id: int, 
            include_items: bool = True,
            include_stats: bool = True) -> Dict[str, Any]:
        supplier = cls.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        return success_response({
            "supplier": cls.serialize(supplier, include_items=include_items, include_stats=include_stats)
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               code: str = None,
               legal_name: str = "",
               contact_person: str = "",
               email: str = "",
               phone: str = "",
               mobile: str = "",
               address: str = "",
               city: str = "",
               country: str = "",
               tax_id: str = "",
               payment_terms_days: int = 30,
               credit_limit: Decimal = None,
               currency: str = "UZS",
               lead_time_days: int = 1,
               minimum_order_value: Decimal = None,
               rating: int = None,
               notes: str = "") -> Dict[str, Any]:
        
        if not code:
            code = cls._generate_code(name)
        
        if cls.model.objects.filter(code=code).exists():
            raise ValidationError(f"Supplier code '{code}' already exists", "code")
        
        if rating is not None and (rating < 1 or rating > 5):
            raise ValidationError("Rating must be between 1 and 5", "rating")
        
        supplier = cls.model.objects.create(
            code=code,
            name=name,
            legal_name=legal_name,
            contact_person=contact_person,
            email=email,
            phone=phone,
            mobile=mobile,
            address=address,
            city=city,
            country=country,
            tax_id=tax_id,
            payment_terms_days=payment_terms_days,
            credit_limit=credit_limit,
            currency=currency,
            lead_time_days=lead_time_days,
            minimum_order_value=minimum_order_value,
            rating=rating,
            notes=notes,
        )
        
        return success_response({
            "id": supplier.id,
            "uuid": str(supplier.uuid),
            "code": supplier.code,
            "supplier": cls.serialize(supplier)
        }, f"Supplier '{name}' created")
    
    @classmethod
    def _generate_code(cls, name: str) -> str:
        prefix = "".join(c for c in name.upper() if c.isalnum())[:3]
        if len(prefix) < 3:
            prefix = prefix.ljust(3, "X")
        
        count = cls.model.objects.filter(code__startswith=prefix).count()
        return f"{prefix}{count + 1:03d}"
    
    @classmethod
    @transaction.atomic
    def update(cls, supplier_id: int, **kwargs) -> Dict[str, Any]:
        supplier = cls.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        if "code" in kwargs and kwargs["code"] != supplier.code:
            if cls.model.objects.filter(code=kwargs["code"]).exclude(id=supplier_id).exists():
                raise ValidationError(f"Supplier code '{kwargs['code']}' already exists", "code")
        
        if "rating" in kwargs and kwargs["rating"] is not None:
            if kwargs["rating"] < 1 or kwargs["rating"] > 5:
                raise ValidationError("Rating must be between 1 and 5", "rating")
        
        update_fields = ["updated_at"]
        allowed_fields = [
            "code", "name", "legal_name", "contact_person", "email",
            "phone", "mobile", "address", "city", "country", "tax_id",
            "payment_terms_days", "credit_limit", "currency",
            "lead_time_days", "minimum_order_value", "rating", "notes"
        ]
        
        for field in allowed_fields:
            if field in kwargs:
                setattr(supplier, field, kwargs[field])
                update_fields.append(field)
        
        supplier.save(update_fields=update_fields)
        
        return success_response({
            "supplier": cls.serialize(supplier)
        }, "Supplier updated")
    
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, supplier_id: int) -> Dict[str, Any]:
        supplier = cls.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        pending_pos = PurchaseOrder.objects.filter(
            supplier=supplier,
            status__in=["DRAFT", "SENT", "CONFIRMED", "PARTIAL"]
        ).count()
        
        if pending_pos > 0:
            raise BusinessRuleError(f"Cannot deactivate supplier with {pending_pos} pending purchase order(s)")
        
        supplier.is_active = False
        supplier.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "id": supplier_id
        }, "Supplier deactivated")
    
    @classmethod
    @transaction.atomic
    def activate(cls, supplier_id: int) -> Dict[str, Any]:
        supplier = cls.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        supplier.is_active = True
        supplier.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "supplier": cls.serialize(supplier)
        }, "Supplier activated")
    
    @classmethod
    @transaction.atomic
    def update_balance(cls, supplier_id: int, amount: Decimal, operation: str = "add") -> Dict[str, Any]:
        supplier = cls.get_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        amount = to_decimal(amount)
        
        if operation == "add":
            supplier.current_balance += amount
        elif operation == "subtract":
            supplier.current_balance -= amount
        elif operation == "set":
            supplier.current_balance = amount
        else:
            raise ValidationError(f"Invalid operation. Valid: add, subtract, set", "operation")
        
        supplier.save(update_fields=["current_balance", "updated_at"])
        
        return success_response({
            "current_balance": str(supplier.current_balance)
        }, "Balance updated")


class SupplierStockItemService(BaseService):
    
    model = SupplierStockItem
    
    @classmethod
    def serialize(cls, si: SupplierStockItem) -> Dict[str, Any]:
        return {
            "id": si.id,
            "uuid": str(si.uuid),
            "supplier_id": si.supplier_id,
            "stock_item_id": si.stock_item_id,
            "stock_item_name": si.stock_item.name,
            "supplier_sku": si.supplier_sku,
            "supplier_name": si.supplier_name,
            "unit_id": si.unit_id,
            "unit_name": si.unit.name,
            "unit_short": si.unit.short_name,
            "price": str(si.price),
            "currency": si.currency,
            "min_order_qty": str(si.min_order_qty),
            "pack_size": str(si.pack_size),
            "lead_time_days": si.lead_time_days,
            "is_preferred": si.is_preferred,
            "last_price_update": si.last_price_update.isoformat() if si.last_price_update else None,
            "notes": si.notes,
        }
    
    @classmethod
    @transaction.atomic
    def add_item(cls,
                 supplier_id: int,
                 stock_item_id: int,
                 unit_id: int,
                 price: Decimal,
                 supplier_sku: str = "",
                 supplier_name: str = "",
                 currency: str = "UZS",
                 min_order_qty: Decimal = Decimal("1"),
                 pack_size: Decimal = Decimal("1"),
                 lead_time_days: int = None,
                 is_preferred: bool = False,
                 notes: str = "") -> Dict[str, Any]:
        
        try:
            supplier = Supplier.objects.get(id=supplier_id, is_active=True)
        except Supplier.DoesNotExist:
            raise NotFoundError("Supplier", supplier_id)
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        try:
            unit = StockUnit.objects.get(id=unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Unit", unit_id)
        
        if cls.model.objects.filter(supplier_id=supplier_id, stock_item_id=stock_item_id).exists():
            raise ValidationError("Item already exists for this supplier", "stock_item_id")
        
        if is_preferred:
            cls.model.objects.filter(
                stock_item_id=stock_item_id, 
                is_preferred=True
            ).update(is_preferred=False)
        
        si = cls.model.objects.create(
            supplier_id=supplier_id,
            stock_item_id=stock_item_id,
            supplier_sku=supplier_sku,
            supplier_name=supplier_name or stock_item.name,
            unit=unit,
            price=to_decimal(price),
            currency=currency,
            min_order_qty=to_decimal(min_order_qty),
            pack_size=to_decimal(pack_size),
            lead_time_days=lead_time_days or supplier.lead_time_days,
            is_preferred=is_preferred,
            notes=notes,
            last_price_update=timezone.now(),
        )
        
        return success_response({
            "id": si.id,
            "supplier_item": cls.serialize(si)
        }, "Item added to supplier")
    
    @classmethod
    @transaction.atomic
    def update_item(cls, supplier_item_id: int, **kwargs) -> Dict[str, Any]:
        try:
            si = cls.model.objects.select_related("stock_item", "unit").get(id=supplier_item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Supplier item", supplier_item_id)
        
        update_fields = ["updated_at"]
        allowed_fields = [
            "supplier_sku", "supplier_name", "price", "currency",
            "min_order_qty", "pack_size", "lead_time_days", "notes"
        ]
        
        for field in allowed_fields:
            if field in kwargs:
                value = kwargs[field]
                if field in ["price", "min_order_qty", "pack_size"]:
                    value = to_decimal(value)
                setattr(si, field, value)
                update_fields.append(field)
        
        if "price" in kwargs:
            si.last_price_update = timezone.now()
            update_fields.append("last_price_update")
        
        if "is_preferred" in kwargs and kwargs["is_preferred"]:
            cls.model.objects.filter(
                stock_item=si.stock_item,
                is_preferred=True
            ).exclude(id=si.id).update(is_preferred=False)
            si.is_preferred = True
            update_fields.append("is_preferred")
        
        si.save(update_fields=update_fields)
        
        return success_response({
            "supplier_item": cls.serialize(si)
        }, "Supplier item updated")
    
    @classmethod
    @transaction.atomic
    def remove_item(cls, supplier_item_id: int) -> Dict[str, Any]:
        try:
            si = cls.model.objects.get(id=supplier_item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Supplier item", supplier_item_id)
        
        si.delete()
        
        return success_response(message="Item removed from supplier")
    
    @classmethod
    def get_preferred_supplier(cls, stock_item_id: int) -> Optional[SupplierStockItem]:
        return cls.model.objects.filter(
            stock_item_id=stock_item_id,
            is_preferred=True,
            supplier__is_active=True
        ).select_related("supplier", "unit").first()
    
    @classmethod
    def get_cheapest_supplier(cls, stock_item_id: int) -> Optional[SupplierStockItem]:
        return cls.model.objects.filter(
            stock_item_id=stock_item_id,
            supplier__is_active=True
        ).select_related("supplier", "unit").order_by("price").first()