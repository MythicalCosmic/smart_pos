from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from stock.models import (
    ProductionOrder, ProductionOrderIngredient, ProductionOrderOutput, ProductionOrderStep,
    Recipe, RecipeIngredient, RecipeStep, RecipeByProduct,
    StockItem, StockUnit, StockLocation, StockBatch, StockSettings
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError, InsufficientStockError,
    to_decimal, round_decimal, generate_number
)


class ProductionOrderService(BaseService):
    model = ProductionOrder
    
    @classmethod
    def serialize(cls, po: ProductionOrder,
                  include_ingredients: bool = True,
                  include_outputs: bool = True,
                  include_steps: bool = True) -> Dict[str, Any]:
        data = {
            "id": po.id,
            "uuid": str(po.uuid),
            "order_number": po.order_number,
            
            "recipe_id": po.recipe_id,
            "recipe": {
                "id": po.recipe.id,
                "name": po.recipe.name,
                "code": po.recipe.code,
            },
            
            "batch_multiplier": str(po.batch_multiplier),
            "expected_output_qty": str(po.expected_output_qty),
            "actual_output_qty": str(po.actual_output_qty) if po.actual_output_qty else None,
            "output_unit": po.output_unit.short_name,
            
            "status": po.status,
            "status_display": po.get_status_display(),
            "priority": po.priority,
            "priority_display": po.get_priority_display(),
            
            "source_location_id": po.source_location_id,
            "source_location": po.source_location.name,
            "output_location_id": po.output_location_id,
            "output_location": po.output_location.name,
            
            "planned_start": po.planned_start.isoformat() if po.planned_start else None,
            "planned_end": po.planned_end.isoformat() if po.planned_end else None,
            "actual_start": po.actual_start.isoformat() if po.actual_start else None,
            "actual_end": po.actual_end.isoformat() if po.actual_end else None,
            
            "assigned_to_id": po.assigned_to_id,
            "created_by_id": po.created_by_id,
            
            "notes": po.notes,
            "created_at": po.created_at.isoformat(),
            "updated_at": po.updated_at.isoformat(),
        }
        
        if include_ingredients:
            data["ingredients"] = [
                ProductionOrderIngredientService.serialize(ing)
                for ing in po.ingredients.select_related("stock_item", "unit")
            ]
        
        if include_outputs:
            data["outputs"] = [
                ProductionOrderOutputService.serialize(out)
                for out in po.outputs.select_related("stock_item", "unit")
            ]
        
        if include_steps:
            data["steps"] = [
                ProductionOrderStepService.serialize(step)
                for step in po.steps.select_related("recipe_step").order_by("recipe_step__step_number")
            ]
        
        return data
    
    @classmethod
    def serialize_brief(cls, po: ProductionOrder) -> Dict[str, Any]:
        return {
            "id": po.id,
            "order_number": po.order_number,
            "recipe_name": po.recipe.name,
            "expected_output_qty": str(po.expected_output_qty),
            "output_unit": po.output_unit.short_name,
            "status": po.status,
            "status_display": po.get_status_display(),
            "priority": po.priority,
            "planned_start": po.planned_start.isoformat() if po.planned_start else None,
        }
    
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             search: str = None,
             status: str = None,
             priority: str = None,
             recipe_id: int = None,
             assigned_to_id: int = None,
             location_id: int = None,
             date_from: datetime = None,
             date_to: datetime = None) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related(
            "recipe", "output_unit", "source_location", "output_location"
        )
        
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(recipe__name__icontains=search)
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        if priority:
            queryset = queryset.filter(priority=priority)
        
        if recipe_id:
            queryset = queryset.filter(recipe_id=recipe_id)
        
        if assigned_to_id:
            queryset = queryset.filter(assigned_to_id=assigned_to_id)
        
        if location_id:
            queryset = queryset.filter(
                Q(source_location_id=location_id) | Q(output_location_id=location_id)
            )
        
        if date_from:
            queryset = queryset.filter(planned_start__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(planned_start__lte=date_to)
        
        queryset = queryset.order_by("-priority", "planned_start", "-created_at")
        
        orders, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "orders": [cls.serialize_brief(po) for po in orders],
            "pagination": pagination,
            "statuses": [{"value": c[0], "label": c[1]} for c in ProductionOrder.Status.choices],
            "priorities": [{"value": c[0], "label": c[1]} for c in ProductionOrder.Priority.choices],
        })
    
    @classmethod
    def get_active(cls, location_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(
            status__in=["PLANNED", "IN_PROGRESS"]
        ).select_related("recipe", "output_unit")
        
        if location_id:
            queryset = queryset.filter(
                Q(source_location_id=location_id) | Q(output_location_id=location_id)
            )
        
        orders = queryset.order_by("-priority", "planned_start")
        
        return success_response({
            "orders": [cls.serialize_brief(po) for po in orders],
            "count": orders.count()
        })
    
    @classmethod
    def get_schedule(cls, 
                     date_from: datetime,
                     date_to: datetime,
                     location_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(
            planned_start__gte=date_from,
            planned_start__lte=date_to,
            status__in=["DRAFT", "PLANNED", "IN_PROGRESS"]
        ).select_related("recipe", "output_unit", "output_location")
        
        if location_id:
            queryset = queryset.filter(output_location_id=location_id)
        
        orders = queryset.order_by("planned_start")
        
        return success_response({
            "schedule": [cls.serialize_brief(po) for po in orders],
            "count": orders.count(),
            "date_range": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
            }
        })
    
    
    @classmethod
    def get(cls, po_id: int) -> Dict[str, Any]:
        po = cls.model.objects.select_related(
            "recipe", "output_unit", "source_location", "output_location"
        ).filter(id=po_id).first()
        
        if not po:
            raise NotFoundError("Production order", po_id)
        
        return success_response({
            "order": cls.serialize(po)
        })
    
    @classmethod
    @transaction.atomic
    def create(cls,
               recipe_id: int,
               created_by_id: int,
               batch_multiplier: Decimal = Decimal("1"),
               source_location_id: int = None,
               output_location_id: int = None,
               planned_start: datetime = None,
               planned_end: datetime = None,
               priority: str = "NORMAL",
               assigned_to_id: int = None,
               notes: str = "",
               auto_allocate: bool = False) -> Dict[str, Any]:
        
        try:
            recipe = Recipe.objects.select_related(
                "output_item", "output_unit", "production_location"
            ).get(id=recipe_id, is_active=True, is_active_version=True)
        except Recipe.DoesNotExist:
            raise NotFoundError("Recipe", recipe_id)
        
        batch_multiplier = to_decimal(batch_multiplier)
        
        if recipe.min_batch_size and batch_multiplier < recipe.min_batch_size:
            raise ValidationError(f"Minimum batch multiplier is {recipe.min_batch_size}", "batch_multiplier")
        if recipe.max_batch_size and batch_multiplier > recipe.max_batch_size:
            raise ValidationError(f"Maximum batch multiplier is {recipe.max_batch_size}", "batch_multiplier")
        
        settings = StockSettings.load()
        
        if not source_location_id:
            source_location_id = settings.default_location_id
        if not output_location_id:
            output_location_id = (
                recipe.production_location_id or 
                settings.default_production_location_id or
                source_location_id
            )
        
        try:
            source_location = StockLocation.objects.get(id=source_location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Source location", source_location_id)
        
        try:
            output_location = StockLocation.objects.get(id=output_location_id, is_active=True)
        except StockLocation.DoesNotExist:
            raise NotFoundError("Output location", output_location_id)
        
        expected_output = recipe.output_quantity * batch_multiplier
        if recipe.yield_percentage < 100:
            expected_output = expected_output * recipe.yield_percentage / 100
        
        if planned_start and not planned_end and recipe.estimated_time_minutes:
            planned_end = planned_start + timedelta(minutes=recipe.estimated_time_minutes)
        
        order_number = generate_number("PROD", cls.model, "order_number")
        
        po = cls.model.objects.create(
            order_number=order_number,
            recipe=recipe,
            batch_multiplier=batch_multiplier,
            expected_output_qty=round_decimal(expected_output, 4),
            output_unit=recipe.output_unit,
            status=ProductionOrder.Status.DRAFT,
            priority=priority,
            source_location=source_location,
            output_location=output_location,
            planned_start=planned_start,
            planned_end=planned_end,
            assigned_to_id=assigned_to_id,
            created_by_id=created_by_id,
            notes=notes,
        )
        
        for recipe_ing in recipe.ingredients.select_related("stock_item", "unit"):
            planned_qty = recipe_ing.quantity * batch_multiplier
            if recipe_ing.is_scalable : recipe_ing.quantity
            
            if recipe_ing.waste_percentage > 0:
                planned_qty = planned_qty * (1 + recipe_ing.waste_percentage / 100)
            
            ProductionOrderIngredient.objects.create(
                production_order=po,
                recipe_ingredient=recipe_ing,
                stock_item=recipe_ing.stock_item,
                planned_quantity=round_decimal(planned_qty, 4),
                unit=recipe_ing.unit,
                status=ProductionOrderIngredient.IngredientStatus.PENDING,
            )
        
        for recipe_step in recipe.steps.all():
            ProductionOrderStep.objects.create(
                production_order=po,
                recipe_step=recipe_step,
                status=ProductionOrderStep.StepStatus.PENDING,
            )
        
        if auto_allocate:
            cls._allocate_ingredients(po.id)
        
        return success_response({
            "id": po.id,
            "order_number": order_number,
            "order": cls.serialize(po)
        }, f"Production order {order_number} created")
    
    @classmethod
    @transaction.atomic
    def create_from_low_stock(cls, 
                              output_item_id: int,
                              created_by_id: int,
                              target_quantity: Decimal = None) -> Dict[str, Any]:
        
        from .production_service import RecipeService
        recipe = RecipeService.get_active_for_item(output_item_id)
        
        if not recipe:
            raise BusinessRuleError("No active recipe found for this item")
        
        if not target_quantity:
            from .level_service import StockLevelService
            item = StockItem.objects.get(id=output_item_id)
            current = StockLevelService.get_available(output_item_id)
            shortage = item.reorder_point - current
            target_quantity = max(shortage, recipe.output_quantity)
        
        batch_multiplier = to_decimal(target_quantity) / recipe.output_quantity
        
        if recipe.min_batch_size and batch_multiplier < recipe.min_batch_size:
            batch_multiplier = recipe.min_batch_size
        
        return cls.create(
            recipe_id=recipe.id,
            created_by_id=created_by_id,
            batch_multiplier=batch_multiplier,
            notes="Auto-generated from low stock"
        )
    
    @classmethod
    @transaction.atomic
    def plan(cls, po_id: int) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status != ProductionOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot plan order in {po.status} status")
        
        availability = cls.check_ingredient_availability(po_id)
        
        if not availability["data"]["all_available"]:
            raise BusinessRuleError("Not all ingredients are available")
        
        po.status = ProductionOrder.Status.PLANNED
        po.save(update_fields=["status", "updated_at"])
        
        cls._allocate_ingredients(po_id)
        
        return success_response({
            "order": cls.serialize(po)
        }, "Production order planned")
    
    @classmethod
    @transaction.atomic
    def start(cls, po_id: int, user_id: int = None) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status != ProductionOrder.Status.PLANNED:
            raise BusinessRuleError(f"Cannot start order in {po.status} status")
        
        po.status = ProductionOrder.Status.IN_PROGRESS
        po.actual_start = timezone.now()
        
        update_fields = ["status", "actual_start", "updated_at"]
        
        if user_id and not po.assigned_to_id:
            po.assigned_to_id = user_id
            update_fields.append("assigned_to")
        
        po.save(update_fields=update_fields)
        
        return success_response({
            "order": cls.serialize(po)
        }, "Production started")
    
    @classmethod
    @transaction.atomic
    def complete(cls, po_id: int, 
                 actual_output_qty: Decimal,
                 user_id: int,
                 quality_status: str = "PASSED",
                 notes: str = "") -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status != ProductionOrder.Status.IN_PROGRESS:
            raise BusinessRuleError(f"Cannot complete order in {po.status} status")
        
        actual_output_qty = to_decimal(actual_output_qty)
        
        cls._consume_ingredients(po_id, user_id)
        
        cls._create_output(po_id, actual_output_qty, user_id, quality_status)
        
        po.status = ProductionOrder.Status.COMPLETED
        po.actual_output_qty = actual_output_qty
        po.actual_end = timezone.now()
        
        if notes:
            po.notes = f"{po.notes}\n{notes}".strip()
        
        po.save(update_fields=["status", "actual_output_qty", "actual_end", "notes", "updated_at"])
        
        variance = actual_output_qty - po.expected_output_qty
        variance_pct = (variance / po.expected_output_qty * 100) if po.expected_output_qty else 0
        
        return success_response({
            "order": cls.serialize(po),
            "variance": {
                "quantity": str(variance),
                "percentage": str(round_decimal(variance_pct, 2)),
            }
        }, "Production completed")
    
    @classmethod
    @transaction.atomic
    def cancel(cls, po_id: int, reason: str = "") -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status in [ProductionOrder.Status.COMPLETED, ProductionOrder.Status.CANCELLED]:
            raise BusinessRuleError(f"Cannot cancel order in {po.status} status")
        
        if po.status in [ProductionOrder.Status.PLANNED, ProductionOrder.Status.IN_PROGRESS]:
            cls._release_ingredients(po_id)
        
        po.status = ProductionOrder.Status.CANCELLED
        if reason:
            po.notes = f"{po.notes}\nCancelled: {reason}".strip()
        
        po.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Production order cancelled")
    
    @classmethod
    @transaction.atomic
    def hold(cls, po_id: int, reason: str = "") -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status not in [ProductionOrder.Status.PLANNED, ProductionOrder.Status.IN_PROGRESS]:
            raise BusinessRuleError(f"Cannot hold order in {po.status} status")
        
        po.status = ProductionOrder.Status.ON_HOLD
        if reason:
            po.notes = f"{po.notes}\nOn hold: {reason}".strip()
        
        po.save(update_fields=["status", "notes", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Production order on hold")
    
    @classmethod
    @transaction.atomic
    def resume(cls, po_id: int) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        if po.status != ProductionOrder.Status.ON_HOLD:
            raise BusinessRuleError(f"Cannot resume order in {po.status} status")
        
        new_status = ProductionOrder.Status.IN_PROGRESS if po.actual_start else ProductionOrder.Status.PLANNED
        
        po.status = new_status
        po.save(update_fields=["status", "updated_at"])
        
        return success_response({
            "order": cls.serialize(po)
        }, "Production resumed")
    
    
    @classmethod
    def check_ingredient_availability(cls, po_id: int) -> Dict[str, Any]:
        po = cls.get_by_id(po_id)
        if not po:
            raise NotFoundError("Production order", po_id)
        
        from .level_service import StockLevelService
        
        availability = []
        all_available = True
        
        for ing in po.ingredients.select_related("stock_item", "unit"):
            available = StockLevelService.get_available(ing.stock_item_id, po.source_location_id)
            required = ing.planned_quantity
            
            is_available = available >= required
            if not is_available:
                all_available = False
            
            availability.append({
                "stock_item_id": ing.stock_item_id,
                "stock_item_name": ing.stock_item.name,
                "required": str(required),
                "available": str(available),
                "shortage": str(max(Decimal("0"), required - available)),
                "is_available": is_available,
            })
        
        return success_response({
            "all_available": all_available,
            "ingredients": availability
        })
    
    @classmethod
    @transaction.atomic
    def _allocate_ingredients(cls, po_id: int):
        po = cls.get_by_id(po_id)
        if not po:
            return
        
        from .level_service import StockLevelService
        
        for ing in po.ingredients.filter(status=ProductionOrderIngredient.IngredientStatus.PENDING):
            StockLevelService.reserve(
                stock_item_id=ing.stock_item_id,
                location_id=po.source_location_id,
                quantity=ing.planned_quantity,
                user_id=po.created_by_id,
                reference_type="ProductionOrder",
                reference_id=po_id,
                notes=f"Reserved for production: {po.order_number}"
            )
            
            ing.status = ProductionOrderIngredient.IngredientStatus.ALLOCATED
            ing.save(update_fields=["status"])
    
    @classmethod
    @transaction.atomic
    def _release_ingredients(cls, po_id: int):
        po = cls.get_by_id(po_id)
        if not po:
            return
        
        from .level_service import StockLevelService
        
        for ing in po.ingredients.filter(status=ProductionOrderIngredient.IngredientStatus.ALLOCATED):
            StockLevelService.release_reservation(
                stock_item_id=ing.stock_item_id,
                location_id=po.source_location_id,
                quantity=ing.planned_quantity,
                user_id=po.created_by_id,
                notes=f"Released from cancelled production: {po.order_number}"
            )
            
            ing.status = ProductionOrderIngredient.IngredientStatus.PENDING
            ing.save(update_fields=["status"])
    
    @classmethod
    @transaction.atomic
    def _consume_ingredients(cls, po_id: int, user_id: int):
        po = cls.get_by_id(po_id)
        if not po:
            return
        
        settings = StockSettings.load()
        
        for ing in po.ingredients.select_related("stock_item"):
            actual_qty = ing.actual_quantity or ing.planned_quantity
            
            if settings.track_batches or ing.stock_item.track_batches:
                from .batch_service import StockBatchService
                result = StockBatchService.auto_consume(
                    stock_item_id=ing.stock_item_id,
                    location_id=po.source_location_id,
                    quantity=actual_qty,
                    movement_type="PRODUCTION_OUT",
                    user_id=user_id,
                    reference_type="ProductionOrder",
                    reference_id=po_id,
                    notes=f"Production: {po.order_number}"
                )
                
                if result.get("data", {}).get("batches"):
                    first_batch = result["data"]["batches"][0]
                    ing.batch_used_id = first_batch["batch_id"]
            else:
                from .level_service import StockLevelService
                StockLevelService.adjust(
                    stock_item_id=ing.stock_item_id,
                    location_id=po.source_location_id,
                    quantity=-actual_qty,
                    movement_type="PRODUCTION_OUT",
                    user_id=user_id,
                    production_order_id=po_id,
                    notes=f"Production: {po.order_number}"
                )
            
            if ing.actual_quantity:
                ing.variance = ing.actual_quantity - ing.planned_quantity
            
            ing.status = ProductionOrderIngredient.IngredientStatus.CONSUMED
            ing.save(update_fields=["status", "batch_used", "variance"])
    
    @classmethod
    @transaction.atomic
    def _create_output(cls, po_id: int, quantity: Decimal, user_id: int, quality_status: str):
        po = cls.get_by_id(po_id)
        if not po:
            return
        
        settings = StockSettings.load()
        
        total_cost = sum(
            (ing.actual_quantity or ing.planned_quantity) * ing.stock_item.avg_cost_price
            for ing in po.ingredients.select_related("stock_item")
        )
        unit_cost = total_cost / quantity if quantity > 0 else Decimal("0")
        
        batch = None
        if settings.track_batches or po.recipe.output_item.track_batches:
            from .batch_service import StockBatchService
            batch_result = StockBatchService.create(
                stock_item_id=po.recipe.output_item_id,
                location_id=po.output_location_id,
                quantity=quantity,
                unit_cost=unit_cost,
                production_order_id=po_id,
                quality_status=quality_status,
            )
            batch = StockBatch.objects.get(id=batch_result["data"]["id"])
        
        from .level_service import StockLevelService
        StockLevelService.adjust(
            stock_item_id=po.recipe.output_item_id,
            location_id=po.output_location_id,
            quantity=quantity,
            movement_type="PRODUCTION_IN",
            user_id=user_id,
            batch_id=batch.id if batch else None,
            production_order_id=po_id,
            unit_cost=unit_cost,
            notes=f"Production output: {po.order_number}"
        )
        
        ProductionOrderOutput.objects.create(
            production_order=po,
            stock_item=po.recipe.output_item,
            quantity=quantity,
            unit=po.output_unit,
            is_primary_output=True,
            batch_created=batch,
            quality_status=quality_status,
        )
        
        for bp in po.recipe.by_products.select_related("stock_item", "unit"):
            bp_qty = bp.expected_quantity * po.batch_multiplier
            
            ProductionOrderOutput.objects.create(
                production_order=po,
                stock_item=bp.stock_item,
                quantity=bp_qty,
                unit=bp.unit,
                is_primary_output=False,
                is_byproduct=True,
                is_waste=bp.is_waste,
            )
            
            if not bp.is_waste:
                StockLevelService.adjust(
                    stock_item_id=bp.stock_item_id,
                    location_id=po.output_location_id,
                    quantity=bp_qty,
                    movement_type="PRODUCTION_IN",
                    user_id=user_id,
                    production_order_id=po_id,
                    notes=f"By-product from: {po.order_number}"
                )


class ProductionOrderIngredientService(BaseService):
    model = ProductionOrderIngredient
    
    @classmethod
    def serialize(cls, ing: ProductionOrderIngredient) -> Dict[str, Any]:
        return {
            "id": ing.id,
            "uuid": str(ing.uuid),
            "production_order_id": ing.production_order_id,
            "recipe_ingredient_id": ing.recipe_ingredient_id,
            "stock_item_id": ing.stock_item_id,
            "stock_item_name": ing.stock_item.name,
            "planned_quantity": str(ing.planned_quantity),
            "actual_quantity": str(ing.actual_quantity) if ing.actual_quantity else None,
            "unit": ing.unit.short_name,
            "batch_used_id": ing.batch_used_id,
            "variance": str(ing.variance) if ing.variance else None,
            "variance_reason": ing.variance_reason,
            "status": ing.status,
            "status_display": ing.get_status_display(),
        }
    
    @classmethod
    @transaction.atomic
    def record_actual(cls, 
                      ingredient_id: int,
                      actual_quantity: Decimal,
                      batch_id: int = None,
                      variance_reason: str = "") -> Dict[str, Any]:
        try:
            ing = cls.model.objects.select_related("production_order").get(id=ingredient_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Ingredient", ingredient_id)
        
        if ing.production_order.status != ProductionOrder.Status.IN_PROGRESS:
            raise BusinessRuleError("Can only record actuals for in-progress orders")
        
        ing.actual_quantity = to_decimal(actual_quantity)
        ing.variance = ing.actual_quantity - ing.planned_quantity
        ing.variance_reason = variance_reason
        
        if batch_id:
            ing.batch_used_id = batch_id
        
        ing.save(update_fields=["actual_quantity", "variance", "variance_reason", "batch_used"])
        
        return success_response({
            "ingredient": cls.serialize(ing)
        }, "Actual quantity recorded")


class ProductionOrderOutputService(BaseService):
    model = ProductionOrderOutput
    
    @classmethod
    def serialize(cls, out: ProductionOrderOutput) -> Dict[str, Any]:
        return {
            "id": out.id,
            "uuid": str(out.uuid),
            "production_order_id": out.production_order_id,
            "stock_item_id": out.stock_item_id,
            "stock_item_name": out.stock_item.name,
            "quantity": str(out.quantity),
            "unit": out.unit.short_name,
            "is_primary_output": out.is_primary_output,
            "is_byproduct": out.is_byproduct,
            "is_waste": out.is_waste,
            "batch_created_id": out.batch_created_id,
            "quality_status": out.quality_status,
            "quality_notes": out.quality_notes,
        }


class ProductionOrderStepService(BaseService):
    
    model = ProductionOrderStep
    
    @classmethod
    def serialize(cls, step: ProductionOrderStep) -> Dict[str, Any]:
        return {
            "id": step.id,
            "uuid": str(step.uuid),
            "production_order_id": step.production_order_id,
            "recipe_step_id": step.recipe_step_id,
            "step_number": step.recipe_step.step_number,
            "title": step.recipe_step.title,
            "description": step.recipe_step.description,
            "duration_minutes": step.recipe_step.duration_minutes,
            "temperature": step.recipe_step.temperature,
            "equipment_needed": step.recipe_step.equipment_needed,
            "is_checkpoint": step.recipe_step.is_checkpoint,
            "status": step.status,
            "status_display": step.get_status_display(),
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "completed_by_id": step.completed_by_id,
            "notes": step.notes,
            "checkpoint_passed": step.checkpoint_passed,
        }
    
    @classmethod
    @transaction.atomic
    def start(cls, step_id: int) -> Dict[str, Any]:
        try:
            step = cls.model.objects.select_related("production_order").get(id=step_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Step", step_id)
        
        if step.production_order.status != ProductionOrder.Status.IN_PROGRESS:
            raise BusinessRuleError("Production must be in progress")
        
        if step.status != ProductionOrderStep.StepStatus.PENDING:
            raise BusinessRuleError(f"Step is already {step.status}")
        
        step.status = ProductionOrderStep.StepStatus.IN_PROGRESS
        step.started_at = timezone.now()
        step.save(update_fields=["status", "started_at"])
        
        return success_response({
            "step": cls.serialize(step)
        }, "Step started")
    
    @classmethod
    @transaction.atomic
    def complete(cls, step_id: int, 
                 completed_by_id: int,
                 checkpoint_passed: bool = None,
                 notes: str = "") -> Dict[str, Any]:
        try:
            step = cls.model.objects.select_related("production_order", "recipe_step").get(id=step_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Step", step_id)
        
        if step.status not in [ProductionOrderStep.StepStatus.PENDING, ProductionOrderStep.StepStatus.IN_PROGRESS]:
            raise BusinessRuleError(f"Cannot complete step in {step.status} status")
        
        if step.recipe_step.is_checkpoint and checkpoint_passed is None:
            raise ValidationError("Checkpoint steps require checkpoint_passed value", "checkpoint_passed")
        
        step.status = ProductionOrderStep.StepStatus.COMPLETED
        step.completed_at = timezone.now()
        step.completed_by_id = completed_by_id
        step.checkpoint_passed = checkpoint_passed
        step.notes = notes
        
        if not step.started_at:
            step.started_at = step.completed_at
        
        step.save(update_fields=["status", "completed_at", "completed_by", "checkpoint_passed", "notes", "started_at"])
        
        return success_response({
            "step": cls.serialize(step)
        }, "Step completed")
    
    @classmethod
    @transaction.atomic
    def skip(cls, step_id: int, reason: str = "") -> Dict[str, Any]:
        try:
            step = cls.model.objects.select_related("recipe_step").get(id=step_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Step", step_id)
        
        if step.recipe_step.is_checkpoint:
            raise BusinessRuleError("Cannot skip checkpoint steps")
        
        step.status = ProductionOrderStep.StepStatus.SKIPPED
        step.notes = reason
        step.save(update_fields=["status", "notes"])
        
        return success_response({
            "step": cls.serialize(step)
        }, "Step skipped")