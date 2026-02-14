from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    PurchaseOrder, PurchaseOrderItem, PurchaseReceiving, PurchaseReceivingItem,
    Supplier, SupplierStockItem, StockItem, StockUnit, StockLocation,
    StockBatch, StockSettings
)
from base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal, round_decimal, generate_number
)


class PurchaseOrderService(BaseService):
    
    model = PurchaseOrder
    
    @classmethod
    def serialize(cls, po: PurchaseOrder, 
                  include_items: bool = True,
                  include_receivings: bool = False) -> Dict[str, Any]:
        data = {
            "id": po.id,
            "uuid": str(po.uuid),
            "order_number": po.order_number,
            
            "supplier_id": po.supplier_id,
            "supplier": {
                "id": po.supplier.id,
                "name": po.supplier.name,
                "code": po.supplier.code,
            },
            
            "delivery_location_id": po.delivery_location_id,
            "delivery_location": po.delivery_location.name,
            
            "status": po.status,
            "status_display": po.get_status_display(),
            "payment_status": po.payment_status,
            "payment_status_display": po.get_payment_status_display(),
            
            "order_date": po.order_date.isoformat(),
            "expected_date": po.expected_date.isoformat() if po.expected_date else None,
            "received_date": po.received_date.isoformat() if po.received_date else None,
            "payment_due_date": po.payment_due_date.isoformat() if po.payment_due_date else None,
            
            "subtotal": str(po.subtotal),
            "tax_amount": str(po.tax_amount),
            "shipping_cost": str(po.shipping_cost),
            "discount": str(po.discount),
            "total": str(po.total),
            "currency": po.currency,
            
            "created_by_id": po.created_by_id,
            "approved_by_id": po.approved_by_id,
            
            "notes": po.notes,
            "created_at": po.created_at.isoformat(),
            "updated_at": po.updated_at.isoformat(),
        }
        
        if include_items:
            data["items"] = [
                PurchaseOrderItemService.serialize(item)
                for item in po.items.select_related("stock_item", "unit")
            ]
            data["item_count"] = len(data["items"])
        
        if include_receivings:
            data["receivings"] = [
                PurchaseReceivingService.serialize_brief(rcv)
                for rcv in po.receivings.all()
            ]
        
        return data
    
    @classmethod
    def serialize_brief(cls, po: PurchaseOrder) -> Dict[str, Any]:
        return {
            "id": po.id,
            "order_number": po.order_number,
            "supplier_name": po.supplier.name,
            "status": po.status,
            "status_display": po.get_status_display(),
            "order_date": po.order_date.isoformat(),
            "total": str(po.total),
            "currency": po.currency,
        }
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             search: str = None,
             supplier_id: int = None,
             status: str = None,
             payment_status: str = None,
             date_from: date = None,
             date_to: date = None,
             location_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related("supplier", "delivery_location")
        
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(supplier__name__icontains=search)
            )
        
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        if date_from:
            queryset = queryset.filter(order_date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(order_date__lte=date_to)
        
        if location_id:
            queryset = queryset.filter(delivery_location_id=location_id)
        
        queryset = queryset.order_by("-order_date", "-created_at")
        
        orders, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "orders": [cls.serialize_brief(po) for po in orders],
            "pagination": pagination,
            "statuses": [{"value": c[0], "label": c[1]} for c in PurchaseOrder.Status.choices],
            "payment_statuses": [{"value": c[0], "label": c[1]} for c in PurchaseOrder.PaymentStatus.choices],
        })
    
    @classmethod
    def get_pending(cls, supplier_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(
            status__in=["DRAFT", "SENT", "CONFIRMED", "PARTIAL"]
        ).select_related("supplier", "delivery_location")
        
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        orders = queryset.order_by("expected_date", "order_date")
        
        return success_response({
            "orders": [cls.serialize_brief(po) for po in orders],
            "count": orders.count()
        })
    
    
    @classmethod
    def get(cls, po_id: int, 
            include_receivings: bool = True) -> Dict[str, Any]:
        po = cls.model.objects.select_related(
            "supplier", "delivery_location"
        ).filter(id=po_id).first()
        
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        return success_response({
            "order": cls.serialize(po, include_receivings=include_receivings)
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               supplier_id: int,
               delivery_location_id: int,
               order_date: date,
               created_by_id: int,
               expected_date: date = None,
               currency: str = "UZS",
               shipping_cost: Decimal = Decimal("0"),
               discount: Decimal = Decimal("0"),
               notes: str = "",
               items: List[Dict] = None) -> Dict[str, Any]:
        
        try:
            supplier = Supplier.objects.get(id=supplier_id, is_active=True)
        except Supplier.DoesNotExist:
            raise NotFoundError("Supplier", supplier_id)
        
        try:
            location = StockLocation.objects.get(id=delivery_location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Delivery location", delivery_location_id)
        
        order_number = generate_number("PO", cls.model, "order_number")
        
        payment_due_date = None
        if supplier.payment_terms_days:
            payment_due_date = order_date + timedelta(days=supplier.payment_terms_days)
        
        if not expected_date and supplier.lead_time_days:
            expected_date = order_date + timedelta(days=supplier.lead_time_days)
        
        po = cls.model.objects.create(
            order_number=order_number,
            supplier=supplier,
            delivery_location=location,
            status=PurchaseOrder.Status.DRAFT,
            order_date=order_date,
            expected_date=expected_date,
            currency=currency,
            shipping_cost=to_decimal(shipping_cost),
            discount=to_decimal(discount),
            payment_due_date=payment_due_date,
            created_by_id=created_by_id,
            notes=notes,
        )
        
        if items:
            for item_data in items:
                PurchaseOrderItemService.add(
                    purchase_order_id=po.id,
                    stock_item_id=item_data["stock_item_id"],
                    quantity=item_data["quantity"],
                    unit_id=item_data["unit_id"],
                    unit_price=item_data["unit_price"],
                    discount_percent=item_data.get("discount_percent", 0),
                    tax_percent=item_data.get("tax_percent", 0),
                    notes=item_data.get("notes", ""),
                )
        
        cls._recalculate_totals(po.id)
        po.refresh_from_db()
        
        return success_response({
            "id": po.id,
            "order_number": po.order_number,
            "order": cls.serialize(po)
        }, f"Purchase order {order_number} created")
    
    @classmethod
    @transaction.atomic
    def create_from_low_stock(cls,
                              supplier_id: int,
                              delivery_location_id: int,
                              created_by_id: int,
                              reorder_quantity_multiplier: Decimal = Decimal("1")) -> Dict[str, Any]:
        
        supplier_items = SupplierStockItem.objects.filter(
            supplier_id=supplier_id,
            supplier__is_active=True
        ).select_related("stock_item", "unit")
        
        items_to_order = []
        
        for si in supplier_items:
            from .level_service import StockLevelService
            available = StockLevelService.get_available(si.stock_item_id)
            
            if available < si.stock_item.reorder_point:
                shortage = si.stock_item.reorder_point - available
                order_qty = max(shortage * reorder_quantity_multiplier, si.min_order_qty)
                
                if si.pack_size > 1:
                    packs_needed = (order_qty / si.pack_size).quantize(Decimal("1"), rounding="ROUND_UP")
                    order_qty = packs_needed * si.pack_size
                
                items_to_order.append({
                    "stock_item_id": si.stock_item_id,
                    "quantity": order_qty,
                    "unit_id": si.unit_id,
                    "unit_price": si.price,
                })
        
        if not items_to_order:
            return success_response({
                "created": False,
                "reason": "No items below reorder point for this supplier"
            })
        
        return cls.create(
            supplier_id=supplier_id,
            delivery_location_id=delivery_location_id,
            order_date=timezone.now().date(),
            created_by_id=created_by_id,
            items=items_to_order,
            notes="Auto-generated from low stock"
        )
    
    @classmethod
    @transaction.atomic
    def update(cls, po_id: int, **kwargs) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        if po.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Can only update orders in DRAFT status")
        
        update_fields = ["updated_at"]
        
        if "supplier_id" in kwargs:
            try:
                po.supplier = Supplier.objects.get(id=kwargs["supplier_id"], is_active=True)
                update_fields.append("supplier")
            except Supplier.DoesNotExist:
                raise NotFoundError("Supplier", kwargs["supplier_id"])
        
        if "delivery_location_id" in kwargs:
            try:
                po.delivery_location = StockLocation.objects.get(
                    id=kwargs["delivery_location_id"], is_active=True
                )
                update_fields.append("delivery_location")
            except StockLocation.DoesNotExist:
                raise NotFoundError("Delivery location", kwargs["delivery_location_id"])
        
        for field in ["order_date", "expected_date", "currency", "shipping_cost", 
                      "discount", "payment_due_date", "notes"]:
            if field in kwargs:
                value = kwargs[field]
                if field in ["shipping_cost", "discount"]:
                    value = to_decimal(value)
                setattr(po, field, value)
                update_fields.append(field)
        
        po.save(update_fields=update_fields)
        
        if "shipping_cost" in kwargs or "discount" in kwargs:
            cls._recalculate_totals(po_id)
            po.refresh_from_db()
        
        return success_response({
            "order": cls.serialize(po)
        }, "Purchase order updated")
    
    @classmethod
    def _recalculate_totals(cls, po_id: int):
        po = cls.get_by_id(po_id)
        if not po:
            return
        
        items = po.items.all()
        
        subtotal = sum(item.total_price for item in items)
        tax_amount = sum(
            item.total_price * item.tax_percent / 100 
            for item in items
        )
        
        po.subtotal = subtotal
        po.tax_amount = tax_amount
        po.total = subtotal + tax_amount + po.shipping_cost - po.discount
        po.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])
    
    @classmethod
    @transaction.atomic
    def send(cls, po_id: int) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        if po.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot send order in {po.status} status")
        
        if not po.items.exists():
            raise BusinessRuleError("Cannot send order with no items")
        
        po.status = PurchaseOrder.Status.SENT
        po.save(update_fields=["status", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Purchase order sent to supplier")
    
    @classmethod
    @transaction.atomic
    def confirm(cls, po_id: int, approved_by_id: int = None) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        if po.status != PurchaseOrder.Status.SENT:
            raise BusinessRuleError(f"Cannot confirm order in {po.status} status")
        
        settings = StockSettings.load()
        if settings.require_po_approval and not approved_by_id:
            raise BusinessRuleError("PO approval is required")
        
        po.status = PurchaseOrder.Status.CONFIRMED
        if approved_by_id:
            po.approved_by_id = approved_by_id
        po.save(update_fields=["status", "approved_by", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Purchase order confirmed")
    
    @classmethod
    @transaction.atomic
    def cancel(cls, po_id: int, reason: str = "") -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        if po.status in [PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED]:
            raise BusinessRuleError(f"Cannot cancel order in {po.status} status")
        
        if po.receivings.filter(status=PurchaseReceiving.Status.COMPLETED).exists():
            raise BusinessRuleError("Cannot cancel order with completed receivings")
        
        po.status = PurchaseOrder.Status.CANCELLED
        if reason:
            po.notes = f"{po.notes}\nCancelled: {reason}".strip()
        po.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Purchase order cancelled")
    
    @classmethod
    @transaction.atomic
    def record_payment(cls, po_id: int, 
                       amount: Decimal,
                       payment_date: date = None,
                       notes: str = "") -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Purchase order", po_id)
        
        amount = to_decimal(amount)
        
        from .supplier_service import SupplierService
        SupplierService.update_balance(po.supplier_id, amount, "subtract")
        
        if amount >= po.total:
            po.payment_status = PurchaseOrder.PaymentStatus.PAID
        else:
            po.payment_status = PurchaseOrder.PaymentStatus.PARTIAL
        
        if notes:
            po.notes = f"{po.notes}\nPayment recorded: {amount} on {payment_date or timezone.now().date()}".strip()
        
        po.save(update_fields=["payment_status", "notes", "updated_at"])
        
        return success_response({
            "payment_status": po.payment_status,
            "payment_status_display": po.get_payment_status_display()
        }, "Payment recorded")
    
    
    @classmethod
    def get_stats(cls, date_from: date = None, date_to: date = None) -> Dict[str, Any]:
        queryset = cls.model.objects.all()
        
        if date_from:
            queryset = queryset.filter(order_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(order_date__lte=date_to)
        
        by_status = {}
        for status in PurchaseOrder.Status.choices:
            by_status[status[0]] = queryset.filter(status=status[0]).count()
        
        total_value = queryset.exclude(
            status=PurchaseOrder.Status.CANCELLED
        ).aggregate(total=Sum("total"))["total"] or Decimal("0")
        
        pending_value = queryset.filter(
            status__in=["DRAFT", "SENT", "CONFIRMED", "PARTIAL"]
        ).aggregate(total=Sum("total"))["total"] or Decimal("0")
        
        return success_response({
            "total_orders": queryset.count(),
            "by_status": by_status,
            "total_value": str(total_value),
            "pending_value": str(pending_value),
        })


class PurchaseOrderItemService(BaseService):
    
    model = PurchaseOrderItem
    
    @classmethod
    def serialize(cls, item: PurchaseOrderItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "uuid": str(item.uuid),
            "purchase_order_id": item.purchase_order_id,
            "stock_item_id": item.stock_item_id,
            "stock_item": {
                "id": item.stock_item.id,
                "name": item.stock_item.name,
                "sku": item.stock_item.sku,
            },
            "quantity_ordered": str(item.quantity_ordered),
            "quantity_received": str(item.quantity_received),
            "quantity_pending": str(item.quantity_ordered - item.quantity_received),
            "unit": item.unit.short_name,
            "unit_price": str(item.unit_price),
            "discount_percent": str(item.discount_percent),
            "tax_percent": str(item.tax_percent),
            "total_price": str(item.total_price),
            "notes": item.notes,
        }
    
    @classmethod
    @transaction.atomic
    def add(cls,
            purchase_order_id: int,
            stock_item_id: int,
            quantity: Decimal,
            unit_id: int,
            unit_price: Decimal,
            discount_percent: Decimal = Decimal("0"),
            tax_percent: Decimal = Decimal("0"),
            supplier_stock_item_id: int = None,
            notes: str = "") -> Dict[str, Any]:
        
        try:
            po = PurchaseOrder.objects.get(id=purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            raise NotFoundError("Purchase order", purchase_order_id)
        
        if po.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Can only add items to DRAFT orders")
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        try:
            unit = StockUnit.objects.get(id=unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Unit", unit_id)
        
        quantity = to_decimal(quantity)
        unit_price = to_decimal(unit_price)
        discount_percent = to_decimal(discount_percent)
        tax_percent = to_decimal(tax_percent)
        
        subtotal = quantity * unit_price
        discount_amount = subtotal * discount_percent / 100
        total_price = subtotal - discount_amount
        
        item = cls.model.objects.create(
            purchase_order=po,
            stock_item=stock_item,
            supplier_stock_item_id=supplier_stock_item_id,
            quantity_ordered=quantity,
            unit=unit,
            unit_price=unit_price,
            discount_percent=discount_percent,
            tax_percent=tax_percent,
            total_price=total_price,
            notes=notes,
        )
        
        PurchaseOrderService._recalculate_totals(purchase_order_id)
        
        return success_response({
            "id": item.id,
            "item": cls.serialize(item)
        }, "Item added to order")
    
    @classmethod
    @transaction.atomic
    def update(cls, item_id: int, **kwargs) -> Dict[str, Any]:
        try:
            item = cls.model.objects.select_related("purchase_order").get(id=item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Order item", item_id)
        
        if item.purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Can only update items in DRAFT orders")
        
        for field in ["quantity_ordered", "unit_price", "discount_percent", "tax_percent", "notes"]:
            if field in kwargs:
                value = kwargs[field]
                if field in ["quantity_ordered", "unit_price", "discount_percent", "tax_percent"]:
                    value = to_decimal(value)
                setattr(item, field, value)
        
        subtotal = item.quantity_ordered * item.unit_price
        discount_amount = subtotal * item.discount_percent / 100
        item.total_price = subtotal - discount_amount
        
        item.save()
        
        PurchaseOrderService._recalculate_totals(item.purchase_order_id)
        
        return success_response({
            "item": cls.serialize(item)
        }, "Item updated")
    
    @classmethod
    @transaction.atomic
    def remove(cls, item_id: int) -> Dict[str, Any]:
        try:
            item = cls.model.objects.select_related("purchase_order").get(id=item_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Order item", item_id)
        
        if item.purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Can only remove items from DRAFT orders")
        
        po_id = item.purchase_order_id
        item.delete()
        
        PurchaseOrderService._recalculate_totals(po_id)
        
        return success_response(message="Item removed")


class PurchaseReceivingService(BaseService):
    
    model = PurchaseReceiving
    
    @classmethod
    def serialize(cls, rcv: PurchaseReceiving, 
                  include_items: bool = True) -> Dict[str, Any]:
        data = {
            "id": rcv.id,
            "uuid": str(rcv.uuid),
            "receiving_number": rcv.receiving_number,
            "purchase_order_id": rcv.purchase_order_id,
            "purchase_order_number": rcv.purchase_order.order_number,
            "location_id": rcv.location_id,
            "location_name": rcv.location.name,
            "received_date": rcv.received_date.isoformat(),
            "received_by_id": rcv.received_by_id,
            "status": rcv.status,
            "status_display": rcv.get_status_display(),
            "notes": rcv.notes,
            "created_at": rcv.created_at.isoformat(),
        }
        
        if include_items:
            data["items"] = [
                PurchaseReceivingItemService.serialize(item)
                for item in rcv.items.select_related("stock_item", "unit")
            ]
        
        return data
    
    @classmethod
    def serialize_brief(cls, rcv: PurchaseReceiving) -> Dict[str, Any]:
        return {
            "id": rcv.id,
            "receiving_number": rcv.receiving_number,
            "received_date": rcv.received_date.isoformat(),
            "status": rcv.status,
        }
    
    @classmethod
    @transaction.atomic
    def create(cls,
               purchase_order_id: int,
               received_by_id: int,
               location_id: int = None,
               received_date: date = None,
               notes: str = "") -> Dict[str, Any]:
        
        try:
            po = PurchaseOrder.objects.get(id=purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            raise NotFoundError("Purchase order", purchase_order_id)
        
        if po.status not in [PurchaseOrder.Status.CONFIRMED, PurchaseOrder.Status.PARTIAL]:
            raise BusinessRuleError(f"Cannot receive order in {po.status} status")
        
        location_id = location_id or po.delivery_location_id
        
        try:
            location = StockLocation.objects.get(id=location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Location", location_id)
        
        receiving_number = generate_number("RCV", cls.model, "receiving_number")
        
        rcv = cls.model.objects.create(
            receiving_number=receiving_number,
            purchase_order=po,
            location=location,
            received_date=received_date or timezone.now().date(),
            received_by_id=received_by_id,
            status=PurchaseReceiving.Status.DRAFT,
            notes=notes,
        )
        
        return success_response({
            "id": rcv.id,
            "receiving_number": receiving_number,
            "receiving": cls.serialize(rcv)
        }, f"Receiving {receiving_number} created")
    
    @classmethod
    @transaction.atomic
    def complete(cls, receiving_id: int) -> Dict[str, Any]:
        try:
            rcv = cls.model.objects.select_related("purchase_order").get(id=receiving_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Receiving", receiving_id)
        
        if rcv.status != PurchaseReceiving.Status.DRAFT:
            raise BusinessRuleError("Receiving already completed")
        
        if not rcv.items.exists():
            raise BusinessRuleError("No items in receiving")
        
        settings = StockSettings.load()
        po = rcv.purchase_order
        
        for item in rcv.items.select_related("stock_item", "unit", "po_item"):
            batch = None
            if settings.track_batches or item.stock_item.track_batches:
                from .batch_service import StockBatchService
                batch_result = StockBatchService.create(
                    stock_item_id=item.stock_item_id,
                    location_id=rcv.location_id,
                    quantity=item.quantity_received,
                    unit_cost=item.unit_cost,
                    batch_number=item.batch_number or None,
                    expiry_date=item.expiry_date,
                    supplier_id=po.supplier_id,
                    purchase_order_id=po.id,
                    quality_status=item.quality_status,
                )
                batch = StockBatch.objects.get(id=batch_result["data"]["id"])
                item.batch_created = batch
                item.save(update_fields=["batch_created"])
            
            from .level_service import StockLevelService
            StockLevelService.adjust(
                stock_item_id=item.stock_item_id,
                location_id=rcv.location_id,
                quantity=item.quantity_received,
                movement_type="PURCHASE_IN",
                user_id=rcv.received_by_id,
                unit_id=item.unit_id,
                batch_id=batch.id if batch else None,
                reference_type="PurchaseReceiving",
                reference_id=rcv.id,
                unit_cost=item.unit_cost,
                notes=f"PO: {po.order_number}",
            )
            
            item.po_item.quantity_received += item.quantity_received
            item.po_item.save(update_fields=["quantity_received"])
            
            from .item_service import StockItemService
            StockItemService.update_cost(item.stock_item_id, item.unit_cost, "AVG")
        
        rcv.status = PurchaseReceiving.Status.COMPLETED
        rcv.save(update_fields=["status", "updated_at"])
        
        cls._update_po_status(po)
        
        return success_response({
            "receiving": cls.serialize(rcv)
        }, "Receiving completed")
    
    @classmethod
    def _update_po_status(cls, po: PurchaseOrder):
        items = po.items.all()
        
        fully_received = all(
            item.quantity_received >= item.quantity_ordered 
            for item in items
        )
        partially_received = any(
            item.quantity_received > 0 
            for item in items
        )
        
        if fully_received:
            po.status = PurchaseOrder.Status.RECEIVED
            po.received_date = timezone.now().date()
        elif partially_received:
            po.status = PurchaseOrder.Status.PARTIAL
        
        po.save(update_fields=["status", "received_date", "updated_at"])


class PurchaseReceivingItemService(BaseService):
    
    model = PurchaseReceivingItem
    
    @classmethod
    def serialize(cls, item: PurchaseReceivingItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "uuid": str(item.uuid),
            "receiving_id": item.receiving_id,
            "po_item_id": item.po_item_id,
            "stock_item_id": item.stock_item_id,
            "stock_item_name": item.stock_item.name,
            "quantity_received": str(item.quantity_received),
            "unit": item.unit.short_name,
            "batch_number": item.batch_number,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "unit_cost": str(item.unit_cost),
            "quality_status": item.quality_status,
            "notes": item.notes,
            "batch_created_id": item.batch_created_id,
        }
    
    @classmethod
    @transaction.atomic
    def add(cls,
            receiving_id: int,
            po_item_id: int,
            quantity_received: Decimal,
            batch_number: str = "",
            expiry_date: date = None,
            unit_cost: Decimal = None,
            quality_status: str = "PASSED",
            notes: str = "") -> Dict[str, Any]:
        try:
            rcv = PurchaseReceiving.objects.get(id=receiving_id)
        except PurchaseReceiving.DoesNotExist:
            raise NotFoundError("Receiving", receiving_id)
        
        if rcv.status != PurchaseReceiving.Status.DRAFT:
            raise BusinessRuleError("Cannot add items to completed receiving")
        
        try:
            po_item = PurchaseOrderItem.objects.select_related("stock_item", "unit").get(
                id=po_item_id,
                purchase_order=rcv.purchase_order
            )
        except PurchaseOrderItem.DoesNotExist:
            raise NotFoundError("PO item", po_item_id)
        
        quantity_received = to_decimal(quantity_received)
        
        already_received = po_item.quantity_received
        pending = po_item.quantity_ordered - already_received
        
        if quantity_received > pending:
            raise ValidationError(
                f"Cannot receive more than pending quantity ({pending})",
                "quantity_received"
            )
        
        item = cls.model.objects.create(
            receiving=rcv,
            po_item=po_item,
            stock_item=po_item.stock_item,
            quantity_received=quantity_received,
            unit=po_item.unit,
            batch_number=batch_number,
            expiry_date=expiry_date,
            unit_cost=unit_cost or po_item.unit_price,
            quality_status=quality_status,
            notes=notes,
        )
        
        return success_response({
            "id": item.id,
            "item": cls.serialize(item)
        }, "Item added to receiving")
    
    @classmethod
    @transaction.atomic
    def add_all_pending(cls, receiving_id: int) -> Dict[str, Any]:
        try:
            rcv = PurchaseReceiving.objects.select_related("purchase_order").get(id=receiving_id)
        except PurchaseReceiving.DoesNotExist:
            raise NotFoundError("Receiving", receiving_id)
        
        if rcv.status != PurchaseReceiving.Status.DRAFT:
            raise BusinessRuleError("Cannot add items to completed receiving")
        
        added = 0
        for po_item in rcv.purchase_order.items.all():
            pending = po_item.quantity_ordered - po_item.quantity_received
            if pending > 0:
                cls.add(
                    receiving_id=receiving_id,
                    po_item_id=po_item.id,
                    quantity_received=pending,
                    unit_cost=po_item.unit_price,
                )
                added += 1
        
        return success_response({
            "items_added": added
        }, f"{added} items added to receiving")
