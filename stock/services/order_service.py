from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from stock.models import StockSettings, ProductStockLink, StockLevel
from base_service import (
    BaseService, success_response, error_response,
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    to_decimal
)
from .level_service import StockLevelService
from .product_link_service import ProductStockLinkService
from .settings_service import StockSettingsService


class OrderStockService:
    
    @classmethod
    def should_process_order(cls, order_status: str) -> bool:
        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return False
        
        if not settings.auto_deduct_on_sale:
            return False
        
        return order_status == settings.deduct_on_order_status
    
    @classmethod
    @transaction.atomic
    def deduct_for_order(cls,
                         order_id: int,
                         order_items: List[Dict],
                         location_id: int,
                         user_id: int,
                         order_status: str = None) -> Dict[str, Any]:

        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({
                "skipped": True,
                "reason": "Stock system disabled"
            })
        
        if order_status and order_status != settings.deduct_on_order_status:
            return success_response({
                "skipped": True,
                "reason": f"Deduction happens at {settings.deduct_on_order_status}, not {order_status}"
            })
        
        deductions = []
        errors = []
        
        for order_item in order_items:
            product_id = order_item["product_id"]
            quantity = to_decimal(order_item.get("quantity", 1))
            modifiers = order_item.get("modifiers", [])
            
            try:
                result = cls._deduct_for_product(
                    order_id=order_id,
                    product_id=product_id,
                    quantity=quantity,
                    modifiers=modifiers,
                    location_id=location_id,
                    user_id=user_id
                )
                deductions.extend(result.get("deductions", []))
            except InsufficientStockError as e:
                if settings.allow_negative_stock:
                    deductions.append({
                        "product_id": product_id,
                        "warning": str(e)
                    })
                else:
                    errors.append({
                        "product_id": product_id,
                        "error": str(e)
                    })
            except Exception as e:
                errors.append({
                    "product_id": product_id,
                    "error": str(e)
                })
        
        if errors and not settings.allow_negative_stock:
            raise BusinessRuleError(f"Stock deduction failed: {errors}")
        
        return success_response({
            "order_id": order_id,
            "deductions": deductions,
            "errors": errors,
            "total_deductions": len(deductions)
        }, f"Processed {len(deductions)} stock deduction(s)")
    
    @classmethod
    def _deduct_for_product(cls,
                            order_id: int,
                            product_id: int,
                            quantity: Decimal,
                            modifiers: List[Dict],
                            location_id: int,
                            user_id: int) -> Dict:
        deduction_items = ProductStockLinkService.get_deduction_items(product_id, quantity)
        
        if not deduction_items:
            return {"deductions": []}
        
        deductions = []
        
        for item in deduction_items:
            result = StockLevelService.adjust(
                stock_item_id=item["stock_item_id"],
                location_id=location_id,
                quantity=-item["quantity"],  
                movement_type="SALE_OUT",
                user_id=user_id,
                unit_id=item.get("unit_id"),
                order_id=order_id,
                notes=f"Order #{order_id} - Product #{product_id}"
            )
            
            deductions.append({
                "stock_item_id": item["stock_item_id"],
                "quantity": str(item["quantity"]),
                "transaction_id": result.get("transaction_id")
            })
        
        link = ProductStockLink.objects.filter(
            product_id=product_id,
            link_type="COMPONENT_BASED"
        ).first()
        
        if link and modifiers:
            for mod in modifiers:
                component_id = mod.get("component_id")
                action = mod.get("action")
                
                if not component_id:
                    continue
                
                from stock.models import ProductComponentStock
                comp = ProductComponentStock.objects.filter(id=component_id).first()
                
                if not comp:
                    continue
                
                if action == "REMOVE" and comp.is_removable:
                    pass
                elif action == "ADD" and comp.is_addable:
                    result = StockLevelService.adjust(
                        stock_item_id=comp.stock_item_id,
                        location_id=location_id,
                        quantity=-comp.quantity * quantity,
                        movement_type="SALE_OUT",
                        user_id=user_id,
                        unit_id=comp.unit_id,
                        order_id=order_id,
                        notes=f"Order #{order_id} - Added component"
                    )
                    
                    deductions.append({
                        "stock_item_id": comp.stock_item_id,
                        "quantity": str(comp.quantity * quantity),
                        "modifier": "ADD",
                        "transaction_id": result.get("transaction_id")
                    })
        
        return {"deductions": deductions}
    
    @classmethod
    @transaction.atomic
    def reverse_deduction(cls,
                          order_id: int,
                          user_id: int,
                          reason: str = "Order cancelled") -> Dict[str, Any]:

        from stock.models import StockTransaction
        
        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({
                "skipped": True,
                "reason": "Stock system disabled"
            })
        
        transactions = StockTransaction.objects.filter(
            order_id=order_id,
            movement_type="SALE_OUT"
        )
        
        if not transactions.exists():
            return success_response({
                "skipped": True,
                "reason": "No stock transactions found for order"
            })
        
        reversals = []
        
        for trans in transactions:
            result = StockLevelService.adjust(
                stock_item_id=trans.stock_item_id,
                location_id=trans.location_id,
                quantity=trans.base_quantity,  
                movement_type="RETURN_FROM_CUSTOMER",
                user_id=user_id,
                batch_id=trans.batch_id,
                order_id=order_id,
                notes=f"Reversal: {reason}"
            )
            
            reversals.append({
                "original_transaction_id": trans.id,
                "reversal_transaction_id": result.get("transaction_id"),
                "stock_item_id": trans.stock_item_id,
                "quantity": str(trans.base_quantity)
            })
        
        return success_response({
            "order_id": order_id,
            "reversals": reversals,
            "total_reversals": len(reversals)
        }, f"Reversed {len(reversals)} stock deduction(s)")
    
    @classmethod
    def check_availability(cls,
                           order_items: List[Dict],
                           location_id: int) -> Dict[str, Any]:
        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({
                "all_available": True,
                "stock_disabled": True
            })
        
        results = []
        all_available = True
        
        for order_item in order_items:
            product_id = order_item["product_id"]
            quantity = to_decimal(order_item.get("quantity", 1))
            
            deduction_items = ProductStockLinkService.get_deduction_items(product_id, quantity)
            
            if not deduction_items:
                results.append({
                    "product_id": product_id,
                    "available": True,
                    "not_linked": True
                })
                continue
            
            product_available = True
            shortages = []
            
            for item in deduction_items:
                available = StockLevelService.get_available(
                    stock_item_id=item["stock_item_id"],
                    location_id=location_id
                )
                
                required = item["quantity"]
                
                if required > available:
                    product_available = False
                    all_available = False
                    shortages.append({
                        "stock_item_id": item["stock_item_id"],
                        "required": str(required),
                        "available": str(available),
                        "shortage": str(required - available)
                    })
            
            results.append({
                "product_id": product_id,
                "available": product_available,
                "shortages": shortages if shortages else None
            })
        
        return success_response({
            "all_available": all_available,
            "allow_negative": settings.allow_negative_stock,
            "items": results
        })
    
    @classmethod
    @transaction.atomic
    def reserve_for_order(cls,
                          order_id: int,
                          order_items: List[Dict],
                          location_id: int,
                          user_id: int) -> Dict[str, Any]:

        settings = StockSettings.load()
        
        if not settings.stock_enabled or not settings.reserve_on_order_create:
            return success_response({
                "skipped": True,
                "reason": "Reservation not enabled"
            })
        
        reservations = []
        
        for order_item in order_items:
            product_id = order_item["product_id"]
            quantity = to_decimal(order_item.get("quantity", 1))
            
            deduction_items = ProductStockLinkService.get_deduction_items(product_id, quantity)
            
            for item in deduction_items:
                result = StockLevelService.reserve(
                    stock_item_id=item["stock_item_id"],
                    location_id=location_id,
                    quantity=item["quantity"],
                    user_id=user_id,
                    reference_type="Order",
                    reference_id=order_id
                )
                
                reservations.append({
                    "stock_item_id": item["stock_item_id"],
                    "quantity": str(item["quantity"])
                })
        
        return success_response({
            "order_id": order_id,
            "reservations": reservations
        }, f"Reserved {len(reservations)} item(s)")
    
    @classmethod
    @transaction.atomic
    def release_reservation(cls,
                            order_id: int,
                            user_id: int) -> Dict[str, Any]:

        from stock.models import StockTransaction
        
        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({"skipped": True})
        
        reservations = StockTransaction.objects.filter(
            reference_type="Order",
            reference_id=order_id,
            movement_type="RESERVATION"
        )
        
        releases = []
        
        for res in reservations:
            StockLevelService.release_reservation(
                stock_item_id=res.stock_item_id,
                location_id=res.location_id,
                quantity=res.base_quantity,
                user_id=user_id
            )
            
            releases.append({
                "stock_item_id": res.stock_item_id,
                "quantity": str(res.base_quantity)
            })
        
        return success_response({
            "order_id": order_id,
            "releases": releases
        }, f"Released {len(releases)} reservation(s)")


class OrderStatusHandler:

    
    @classmethod
    def on_status_change(cls,
                         order_id: int,
                         old_status: str,
                         new_status: str,
                         order_items: List[Dict],
                         location_id: int,
                         user_id: int) -> Dict[str, Any]:

        settings = StockSettings.load()
        
        if not settings.stock_enabled:
            return success_response({"skipped": True, "reason": "Stock disabled"})
        
        result = {"actions": []}
        
        if settings.reserve_on_order_create and old_status is None:
            res = OrderStockService.reserve_for_order(
                order_id, order_items, location_id, user_id
            )
            result["actions"].append({"action": "reserve", "result": res})
        
        if new_status == settings.deduct_on_order_status:
            if settings.reserve_on_order_create:
                OrderStockService.release_reservation(order_id, user_id)
            
            res = OrderStockService.deduct_for_order(
                order_id, order_items, location_id, user_id, new_status
            )
            result["actions"].append({"action": "deduct", "result": res})
        
        if new_status == "CANCELLED":
            if settings.reserve_on_order_create:
                OrderStockService.release_reservation(order_id, user_id)
            
            res = OrderStockService.reverse_deduction(
                order_id, user_id, "Order cancelled"
            )
            result["actions"].append({"action": "reverse", "result": res})
        
        return success_response(result)