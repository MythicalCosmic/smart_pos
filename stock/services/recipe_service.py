from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Prefetch
from django.utils import timezone

from client import models
from stock import models
from stock.models import (
    Recipe, RecipeIngredient, RecipeIngredientSubstitute, RecipeByProduct, RecipeStep,
    StockItem, StockUnit, StockLocation
)
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal, round_decimal
)


class RecipeService(BaseService):
    model = Recipe
    
    @classmethod
    def serialize(cls, recipe: Recipe, 
                  include_ingredients: bool = True,
                  include_steps: bool = True,
                  include_byproducts: bool = True,
                  include_cost: bool = False) -> Dict[str, Any]:
        data = {
            "id": recipe.id,
            "uuid": str(recipe.uuid),
            "name": recipe.name,
            "code": recipe.code,
            
            "output_item_id": recipe.output_item_id,
            "output_item": {
                "id": recipe.output_item.id,
                "name": recipe.output_item.name,
                "sku": recipe.output_item.sku,
            },
            "output_quantity": str(recipe.output_quantity),
            "output_unit_id": recipe.output_unit_id,
            "output_unit": recipe.output_unit.short_name,
            
            "recipe_type": recipe.recipe_type,
            "recipe_type_display": recipe.get_recipe_type_display(),
            "version": recipe.version,
            "is_active_version": recipe.is_active_version,
            "parent_recipe_id": recipe.parent_recipe_id,
            
            "yield_percentage": str(recipe.yield_percentage),
            "estimated_time_minutes": recipe.estimated_time_minutes,
            "difficulty_level": recipe.difficulty_level,
            "production_location_id": recipe.production_location_id,
            "production_location_name": recipe.production_location.name if recipe.production_location else None,
            
            "is_scalable": recipe.is_scalable,
            "min_batch_size": str(recipe.min_batch_size),
            "max_batch_size": str(recipe.max_batch_size) if recipe.max_batch_size else None,
            
            "instructions": recipe.instructions,
            "notes": recipe.notes,
            
            "created_by_id": recipe.created_by_id,
            "approved_by_id": recipe.approved_by_id,
            "approved_at": recipe.approved_at.isoformat() if recipe.approved_at else None,
            
            "is_active": recipe.is_active,
            "created_at": recipe.created_at.isoformat(),
            "updated_at": recipe.updated_at.isoformat(),
        }
        
        if include_ingredients:
            data["ingredients"] = [
                RecipeIngredientService.serialize(ing, include_substitutes=True)
                for ing in recipe.ingredients.select_related("stock_item", "unit").order_by("sort_order")
            ]
            data["ingredient_count"] = len(data["ingredients"])
        
        if include_steps:
            data["steps"] = [
                RecipeStepService.serialize(step)
                for step in recipe.steps.order_by("step_number")
            ]
            data["step_count"] = len(data["steps"])
        
        if include_byproducts:
            data["by_products"] = [
                RecipeByProductService.serialize(bp)
                for bp in recipe.by_products.select_related("stock_item", "unit")
            ]
        
        if include_cost:
            data["estimated_cost"] = str(cls.calculate_cost(recipe.id))
        
        return data
    
    @classmethod
    def serialize_brief(cls, recipe: Recipe) -> Dict[str, Any]:
        return {
            "id": recipe.id,
            "uuid": str(recipe.uuid),
            "name": recipe.name,
            "code": recipe.code,
            "recipe_type": recipe.recipe_type,
            "output_item_name": recipe.output_item.name,
            "output_quantity": str(recipe.output_quantity),
            "output_unit": recipe.output_unit.short_name,
            "version": recipe.version,
            "is_active_version": recipe.is_active_version,
            "is_active": recipe.is_active,
        }
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 20,
             search: str = None,
             recipe_type: str = None,
             output_item_id: int = None,
             active_only: bool = True,
             active_version_only: bool = True,
             production_location_id: int = None) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related("output_item", "output_unit")
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if active_version_only:
            queryset = queryset.filter(is_active_version=True)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(output_item__name__icontains=search)
            )
        
        if recipe_type:
            queryset = queryset.filter(recipe_type=recipe_type)
        
        if output_item_id:
            queryset = queryset.filter(output_item_id=output_item_id)
        
        if production_location_id:
            queryset = queryset.filter(production_location_id=production_location_id)
        
        queryset = queryset.order_by("name", "-version")
        
        recipes, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "recipes": [cls.serialize_brief(r) for r in recipes],
            "pagination": pagination,
            "recipe_types": [
                {"value": c[0], "label": c[1]}
                for c in Recipe.RecipeType.choices
            ]
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20) -> Dict[str, Any]:
        recipes = cls.model.objects.filter(
            Q(name__icontains=query) | Q(code__icontains=query),
            is_active=True,
            is_active_version=True
        ).select_related("output_item", "output_unit").order_by("name")[:limit]
        
        return success_response({
            "recipes": [cls.serialize_brief(r) for r in recipes],
            "count": recipes.count()
        })
    
    @classmethod
    def get_for_item(cls, output_item_id: int) -> Dict[str, Any]:
        recipes = cls.model.objects.filter(
            output_item_id=output_item_id,
            is_active=True
        ).select_related("output_unit").order_by("-is_active_version", "-version")
        
        return success_response({
            "recipes": [cls.serialize_brief(r) for r in recipes],
            "count": recipes.count()
        })
    
    @classmethod
    def get_versions(cls, recipe_id: int) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        root = recipe
        while root.parent_recipe:
            root = root.parent_recipe
        
        versions = cls.model.objects.filter(
            Q(id=root.id) | Q(parent_recipe=root)
        ).order_by("-version")
        
        return success_response({
            "versions": [cls.serialize_brief(v) for v in versions],
            "current_version": recipe.version,
            "active_version": next((v.version for v in versions if v.is_active_version), None)
        })
    
    @classmethod
    def get(cls, recipe_id: int, 
            include_cost: bool = True) -> Dict[str, Any]:
        recipe = cls.model.objects.select_related(
            "output_item", "output_unit", "production_location"
        ).filter(id=recipe_id).first()
        
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        return success_response({
            "recipe": cls.serialize(recipe, include_cost=include_cost)
        })
    
    @classmethod
    def get_active_for_item(cls, output_item_id: int) -> Optional[Recipe]:
        return cls.model.objects.filter(
            output_item_id=output_item_id,
            is_active=True,
            is_active_version=True
        ).first()
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               output_item_id: int,
               output_quantity: Decimal,
               output_unit_id: int,
               recipe_type: str = "PRODUCTION",
               code: str = None,
               yield_percentage: Decimal = Decimal("100"),
               estimated_time_minutes: int = None,
               difficulty_level: int = 1,
               production_location_id: int = None,
               instructions: str = "",
               notes: str = "",
               is_scalable: bool = True,
               min_batch_size: Decimal = Decimal("1"),
               max_batch_size: Decimal = None,
               created_by_id: int = None,
               ingredients: List[Dict] = None,
               steps: List[Dict] = None,
               by_products: List[Dict] = None) -> Dict[str, Any]:
        
        valid_types = [c[0] for c in Recipe.RecipeType.choices]
        if recipe_type not in valid_types:
            raise ValidationError(f"Invalid recipe type. Valid: {valid_types}", "recipe_type")
        
        try:
            output_item = StockItem.objects.get(id=output_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Output item", output_item_id)
        
        try:
            output_unit = StockUnit.objects.get(id=output_unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Output unit", output_unit_id)
        
        production_location = None
        if production_location_id:
            try:
                production_location = StockLocation.objects.get(id=production_location_id, is_active=True)
            except StockLocation.DoesNotExist:
                raise NotFoundError("Production location", production_location_id)
        
        if not code:
            code = cls._generate_code(name)
        
        if cls.model.objects.filter(code=code).exists():
            raise ValidationError(f"Recipe code '{code}' already exists", "code")
        
        recipe = cls.model.objects.create(
            name=name,
            code=code,
            output_item=output_item,
            output_quantity=to_decimal(output_quantity),
            output_unit=output_unit,
            recipe_type=recipe_type,
            version=1,
            is_active_version=True,
            yield_percentage=to_decimal(yield_percentage),
            estimated_time_minutes=estimated_time_minutes,
            difficulty_level=difficulty_level,
            production_location=production_location,
            instructions=instructions,
            notes=notes,
            is_scalable=is_scalable,
            min_batch_size=to_decimal(min_batch_size),
            max_batch_size=to_decimal(max_batch_size) if max_batch_size else None,
            created_by_id=created_by_id,
        )
        
        if ingredients:
            for idx, ing_data in enumerate(ingredients):
                RecipeIngredientService.add(
                    recipe_id=recipe.id,
                    stock_item_id=ing_data["stock_item_id"],
                    quantity=ing_data["quantity"],
                    unit_id=ing_data["unit_id"],
                    is_optional=ing_data.get("is_optional", False),
                    waste_percentage=ing_data.get("waste_percentage", 0),
                    prep_instructions=ing_data.get("prep_instructions", ""),
                    sort_order=ing_data.get("sort_order", idx),
                )
        
        if steps:
            for step_data in steps:
                RecipeStepService.add(
                    recipe_id=recipe.id,
                    step_number=step_data["step_number"],
                    title=step_data["title"],
                    description=step_data.get("description", ""),
                    duration_minutes=step_data.get("duration_minutes"),
                    temperature=step_data.get("temperature", ""),
                    equipment_needed=step_data.get("equipment_needed", ""),
                    is_checkpoint=step_data.get("is_checkpoint", False),
                )
        if by_products:
            for bp_data in by_products:
                RecipeByProductService.add(
                    recipe_id=recipe.id,
                    stock_item_id=bp_data["stock_item_id"],
                    expected_quantity=bp_data["expected_quantity"],
                    unit_id=bp_data["unit_id"],
                    is_waste=bp_data.get("is_waste", False),
                    value_percentage=bp_data.get("value_percentage", 0),
                )
        
        return success_response({
            "id": recipe.id,
            "uuid": str(recipe.uuid),
            "code": recipe.code,
            "recipe": cls.serialize(recipe)
        }, f"Recipe '{name}' created")
    
    @classmethod
    def _generate_code(cls, name: str) -> str:
        prefix = "RCP"
        name_part = "".join(c for c in name.upper() if c.isalnum())[:4]
        
        count = cls.model.objects.filter(code__startswith=f"{prefix}-{name_part}").count()
        return f"{prefix}-{name_part}-{count + 1:03d}"
    
    
    @classmethod
    @transaction.atomic
    def update(cls, recipe_id: int, **kwargs) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        minor_fields = ["instructions", "notes", "difficulty_level", "estimated_time_minutes", 
                        "production_location_id", "is_scalable", "min_batch_size", "max_batch_size"]
        
        updating_major = any(k not in minor_fields for k in kwargs.keys() 
                            if k not in ["name", "code"])
        
        if updating_major and recipe.approved_at:
            return cls.create_new_version(recipe_id, **kwargs)
        
        update_fields = ["updated_at"]
        
        for field in minor_fields:
            if field in kwargs:
                if field == "production_location_id":
                    if kwargs[field]:
                        try:
                            location = StockLocation.objects.get(id=kwargs[field], is_active=True)
                            recipe.production_location = location
                        except StockLocation.DoesNotExist:
                            raise NotFoundError("Production location", kwargs[field])
                    else:
                        recipe.production_location = None
                    update_fields.append("production_location")
                else:
                    value = kwargs[field]
                    if field in ["min_batch_size", "max_batch_size"]:
                        value = to_decimal(value) if value else None
                    setattr(recipe, field, value)
                    update_fields.append(field)
        
        if "name" in kwargs:
            recipe.name = kwargs["name"]
            update_fields.append("name")
        
        recipe.save(update_fields=update_fields)
        
        return success_response({
            "recipe": cls.serialize(recipe)
        }, "Recipe updated")
    
    @classmethod
    @transaction.atomic
    def create_new_version(cls, recipe_id: int, **kwargs) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        root = recipe
        while root.parent_recipe:
            root = root.parent_recipe
        
        max_version = cls.model.objects.filter(
            Q(id=root.id) | Q(parent_recipe=root)
        ).count()
        
        new_recipe = cls.model.objects.create(
            name=kwargs.get("name", recipe.name),
            code=recipe.code,  
            output_item=recipe.output_item,
            output_quantity=to_decimal(kwargs.get("output_quantity", recipe.output_quantity)),
            output_unit=recipe.output_unit,
            recipe_type=recipe.recipe_type,
            version=max_version + 1,
            is_active_version=False,  
            parent_recipe=root,
            yield_percentage=to_decimal(kwargs.get("yield_percentage", recipe.yield_percentage)),
            estimated_time_minutes=kwargs.get("estimated_time_minutes", recipe.estimated_time_minutes),
            difficulty_level=kwargs.get("difficulty_level", recipe.difficulty_level),
            production_location=recipe.production_location,
            instructions=kwargs.get("instructions", recipe.instructions),
            notes=kwargs.get("notes", recipe.notes),
            is_scalable=kwargs.get("is_scalable", recipe.is_scalable),
            min_batch_size=to_decimal(kwargs.get("min_batch_size", recipe.min_batch_size)),
            max_batch_size=to_decimal(kwargs.get("max_batch_size", recipe.max_batch_size)) if recipe.max_batch_size else None,
            created_by_id=kwargs.get("created_by_id"),
        )
        
        for ing in recipe.ingredients.all():
            new_ing = RecipeIngredient.objects.create(
                recipe=new_recipe,
                stock_item=ing.stock_item,
                quantity=ing.quantity,
                unit=ing.unit,
                is_optional=ing.is_optional,
                is_scalable=ing.is_scalable,
                waste_percentage=ing.waste_percentage,
                prep_instructions=ing.prep_instructions,
                sort_order=ing.sort_order,
                substitute_group=ing.substitute_group,
            )
            for sub in ing.substitutes.all():
                RecipeIngredientSubstitute.objects.create(
                    recipe_ingredient=new_ing,
                    substitute_item=sub.substitute_item,
                    quantity=sub.quantity,
                    unit=sub.unit,
                    conversion_note=sub.conversion_note,
                    priority=sub.priority,
                )
        
        for step in recipe.steps.all():
            RecipeStep.objects.create(
                recipe=new_recipe,
                step_number=step.step_number,
                title=step.title,
                description=step.description,
                duration_minutes=step.duration_minutes,
                temperature=step.temperature,
                equipment_needed=step.equipment_needed,
                is_checkpoint=step.is_checkpoint,
                photo_url=step.photo_url,
            )
        
        for bp in recipe.by_products.all():
            RecipeByProduct.objects.create(
                recipe=new_recipe,
                stock_item=bp.stock_item,
                expected_quantity=bp.expected_quantity,
                unit=bp.unit,
                is_waste=bp.is_waste,
                value_percentage=bp.value_percentage,
            )
        
        return success_response({
            "id": new_recipe.id,
            "version": new_recipe.version,
            "recipe": cls.serialize(new_recipe)
        }, f"New version {new_recipe.version} created")
    
    
    @classmethod
    @transaction.atomic
    def approve(cls, recipe_id: int, approved_by_id: int) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        if recipe.approved_at:
            raise BusinessRuleError("Recipe is already approved")
        
        if recipe.parent_recipe:
            cls.model.objects.filter(
                Q(id=recipe.parent_recipe_id) | Q(parent_recipe=recipe.parent_recipe)
            ).update(is_active_version=False)
        
        recipe.approved_by_id = approved_by_id
        recipe.approved_at = timezone.now()
        recipe.is_active_version = True
        recipe.save(update_fields=["approved_by", "approved_at", "is_active_version", "updated_at"])
        
        return success_response({
            "recipe": cls.serialize(recipe)
        }, f"Recipe v{recipe.version} approved and activated")
    
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, recipe_id: int) -> Dict[str, Any]:
        """Deactivate recipe"""
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        recipe.is_active = False
        recipe.save(update_fields=["is_active", "updated_at"])
        
        return success_response({"id": recipe_id}, "Recipe deactivated")
    
    @classmethod
    @transaction.atomic
    def activate(cls, recipe_id: int) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        recipe.is_active = True
        recipe.save(update_fields=["is_active", "updated_at"])
        
        return success_response({"recipe": cls.serialize(recipe)}, "Recipe activated")
    
    
    @classmethod
    def calculate_cost(cls, recipe_id: int, batch_multiplier: Decimal = Decimal("1")) -> Decimal:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            return Decimal("0")
        
        total_cost = Decimal("0")
        
        for ing in recipe.ingredients.select_related("stock_item", "unit"):
            qty = ing.quantity * batch_multiplier
            
            if ing.waste_percentage > 0:
                qty = qty * (1 + ing.waste_percentage / 100)
            
            item_cost = ing.stock_item.avg_cost_price
            
            if ing.unit_id != ing.stock_item.base_unit_id:
                from .unit_service import StockUnitService
                qty, _ = StockUnitService.convert(qty, ing.unit_id, ing.stock_item.base_unit_id)
            
            total_cost += qty * item_cost
        
        return round_decimal(total_cost, 2)
    
    
    @classmethod
    def scale_recipe(cls, recipe_id: int, 
                     target_quantity: Decimal = None,
                     batch_multiplier: Decimal = None) -> Dict[str, Any]:
        recipe = cls.get_by_id(recipe_id)
        if not recipe:
            raise NotFoundError("Recipe", recipe_id)
        
        if not recipe.is_scalable:
            raise BusinessRuleError("This recipe cannot be scaled")
        
        if target_quantity:
            multiplier = to_decimal(target_quantity) / recipe.output_quantity
        elif batch_multiplier:
            multiplier = to_decimal(batch_multiplier)
        else:
            multiplier = Decimal("1")
        
        if recipe.min_batch_size and multiplier < recipe.min_batch_size:
            raise ValidationError(f"Minimum batch multiplier is {recipe.min_batch_size}", "multiplier")
        if recipe.max_batch_size and multiplier > recipe.max_batch_size:
            raise ValidationError(f"Maximum batch multiplier is {recipe.max_batch_size}", "multiplier")
        
        scaled_ingredients = []
        for ing in recipe.ingredients.select_related("stock_item", "unit").order_by("sort_order"):
            scaled_qty = ing.quantity * multiplier if ing.is_scalable else ing.quantity
            with_waste = scaled_qty * (1 + ing.waste_percentage / 100) if ing.waste_percentage else scaled_qty
            
            scaled_ingredients.append({
                "stock_item_id": ing.stock_item_id,
                "stock_item_name": ing.stock_item.name,
                "original_quantity": str(ing.quantity),
                "scaled_quantity": str(round_decimal(scaled_qty, 4)),
                "with_waste": str(round_decimal(with_waste, 4)),
                "unit": ing.unit.short_name,
                "is_optional": ing.is_optional,
            })
        
        scaled_output = recipe.output_quantity * multiplier
        
        scaled_byproducts = []
        for bp in recipe.by_products.select_related("stock_item", "unit"):
            scaled_byproducts.append({
                "stock_item_name": bp.stock_item.name,
                "expected_quantity": str(round_decimal(bp.expected_quantity * multiplier, 4)),
                "unit": bp.unit.short_name,
                "is_waste": bp.is_waste,
            })
        
        return success_response({
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "multiplier": str(multiplier),
            "original_output": str(recipe.output_quantity),
            "scaled_output": str(round_decimal(scaled_output, 4)),
            "output_unit": recipe.output_unit.short_name,
            "ingredients": scaled_ingredients,
            "by_products": scaled_byproducts,
            "estimated_cost": str(cls.calculate_cost(recipe.id, multiplier)),
        })


class RecipeIngredientService(BaseService):
    
    model = RecipeIngredient
    
    @classmethod
    def serialize(cls, ing: RecipeIngredient, include_substitutes: bool = True) -> Dict[str, Any]:
        data = {
            "id": ing.id,
            "uuid": str(ing.uuid),
            "recipe_id": ing.recipe_id,
            "stock_item_id": ing.stock_item_id,
            "stock_item": {
                "id": ing.stock_item.id,
                "name": ing.stock_item.name,
                "sku": ing.stock_item.sku,
            },
            "quantity": str(ing.quantity),
            "unit_id": ing.unit_id,
            "unit": ing.unit.short_name,
            "is_optional": ing.is_optional,
            "is_scalable": ing.is_scalable,
            "waste_percentage": str(ing.waste_percentage),
            "prep_instructions": ing.prep_instructions,
            "sort_order": ing.sort_order,
            "substitute_group": ing.substitute_group,
        }
        
        if include_substitutes:
            data["substitutes"] = [
                RecipeIngredientSubstituteService.serialize(sub)
                for sub in ing.substitutes.select_related("substitute_item", "unit").order_by("priority")
            ]
        
        return data
    
    @classmethod
    @transaction.atomic
    def add(cls,
            recipe_id: int,
            stock_item_id: int,
            quantity: Decimal,
            unit_id: int,
            is_optional: bool = False,
            is_scalable: bool = True,
            waste_percentage: Decimal = Decimal("0"),
            prep_instructions: str = "",
            sort_order: int = 0,
            substitute_group: str = "") -> Dict[str, Any]:
        
        try:
            recipe = Recipe.objects.get(id=recipe_id)
        except Recipe.DoesNotExist:
            raise NotFoundError("Recipe", recipe_id)
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        try:
            unit = StockUnit.objects.get(id=unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Unit", unit_id)
        
        if sort_order == 0:
            last = cls.model.objects.filter(recipe=recipe).order_by("-sort_order").first()
            sort_order = (last.sort_order + 1) if last else 1
        
        ing = cls.model.objects.create(
            recipe=recipe,
            stock_item=stock_item,
            quantity=to_decimal(quantity),
            unit=unit,
            is_optional=is_optional,
            is_scalable=is_scalable,
            waste_percentage=to_decimal(waste_percentage),
            prep_instructions=prep_instructions,
            sort_order=sort_order,
            substitute_group=substitute_group,
        )
        
        return success_response({
            "id": ing.id,
            "ingredient": cls.serialize(ing)
        }, "Ingredient added")
    
    @classmethod
    @transaction.atomic
    def update(cls, ingredient_id: int, **kwargs) -> Dict[str, Any]:
        try:
            ing = cls.model.objects.select_related("stock_item", "unit").get(id=ingredient_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Ingredient", ingredient_id)
        
        update_fields = ["updated_at"] if hasattr(ing, "updated_at") else []
        
        if "stock_item_id" in kwargs:
            try:
                ing.stock_item = StockItem.objects.get(id=kwargs["stock_item_id"])
                update_fields.append("stock_item")
            except StockItem.DoesNotExist:
                raise NotFoundError("Stock item", kwargs["stock_item_id"])
        
        if "unit_id" in kwargs:
            try:
                ing.unit = StockUnit.objects.get(id=kwargs["unit_id"], is_active=True)
                update_fields.append("unit")
            except StockUnit.DoesNotExist:
                raise NotFoundError("Unit", kwargs["unit_id"])
        
        for field in ["quantity", "is_optional", "is_scalable", "waste_percentage", 
                      "prep_instructions", "sort_order", "substitute_group"]:
            if field in kwargs:
                value = kwargs[field]
                if field in ["quantity", "waste_percentage"]:
                    value = to_decimal(value)
                setattr(ing, field, value)
                update_fields.append(field)
        
        ing.save()
        
        return success_response({
            "ingredient": cls.serialize(ing)
        }, "Ingredient updated")
    
    @classmethod
    @transaction.atomic
    def remove(cls, ingredient_id: int) -> Dict[str, Any]:
        try:
            ing = cls.model.objects.get(id=ingredient_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Ingredient", ingredient_id)
        
        ing.delete()
        return success_response(message="Ingredient removed")
    
    @classmethod
    @transaction.atomic
    def reorder(cls, recipe_id: int, ingredient_ids: List[int]) -> Dict[str, Any]:
        for idx, ing_id in enumerate(ingredient_ids):
            cls.model.objects.filter(id=ing_id, recipe_id=recipe_id).update(sort_order=idx)
        
        return success_response({"reordered": len(ingredient_ids)}, "Ingredients reordered")


class RecipeIngredientSubstituteService(BaseService):
    
    model = RecipeIngredientSubstitute
    
    @classmethod
    def serialize(cls, sub: RecipeIngredientSubstitute) -> Dict[str, Any]:
        return {
            "id": sub.id,
            "uuid": str(sub.uuid),
            "recipe_ingredient_id": sub.recipe_ingredient_id,
            "substitute_item_id": sub.substitute_item_id,
            "substitute_item_name": sub.substitute_item.name,
            "quantity": str(sub.quantity),
            "unit": sub.unit.short_name,
            "conversion_note": sub.conversion_note,
            "priority": sub.priority,
        }
    
    @classmethod
    @transaction.atomic
    def add(cls,
            recipe_ingredient_id: int,
            substitute_item_id: int,
            quantity: Decimal,
            unit_id: int,
            conversion_note: str = "",
            priority: int = 1) -> Dict[str, Any]:
        
        try:
            recipe_ing = RecipeIngredient.objects.get(id=recipe_ingredient_id)
        except RecipeIngredient.DoesNotExist:
            raise NotFoundError("Recipe ingredient", recipe_ingredient_id)
        
        try:
            substitute_item = StockItem.objects.get(id=substitute_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Substitute item", substitute_item_id)
        
        try:
            unit = StockUnit.objects.get(id=unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Unit", unit_id)
        
        sub = cls.model.objects.create(
            recipe_ingredient=recipe_ing,
            substitute_item=substitute_item,
            quantity=to_decimal(quantity),
            unit=unit,
            conversion_note=conversion_note,
            priority=priority,
        )
        
        return success_response({
            "id": sub.id,
            "substitute": cls.serialize(sub)
        }, "Substitute added")
    
    @classmethod
    @transaction.atomic
    def remove(cls, substitute_id: int) -> Dict[str, Any]:
        try:
            sub = cls.model.objects.get(id=substitute_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Substitute", substitute_id)
        
        sub.delete()
        return success_response(message="Substitute removed")


class RecipeByProductService(BaseService):
    
    model = RecipeByProduct
    
    @classmethod
    def serialize(cls, bp: RecipeByProduct) -> Dict[str, Any]:
        return {
            "id": bp.id,
            "uuid": str(bp.uuid),
            "recipe_id": bp.recipe_id,
            "stock_item_id": bp.stock_item_id,
            "stock_item_name": bp.stock_item.name,
            "expected_quantity": str(bp.expected_quantity),
            "unit": bp.unit.short_name,
            "is_waste": bp.is_waste,
            "value_percentage": str(bp.value_percentage),
        }
    
    @classmethod
    @transaction.atomic
    def add(cls,
            recipe_id: int,
            stock_item_id: int,
            expected_quantity: Decimal,
            unit_id: int,
            is_waste: bool = False,
            value_percentage: Decimal = Decimal("0")) -> Dict[str, Any]:
        
        try:
            recipe = Recipe.objects.get(id=recipe_id)
        except Recipe.DoesNotExist:
            raise NotFoundError("Recipe", recipe_id)
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        try:
            unit = StockUnit.objects.get(id=unit_id, is_active=True)
        except StockUnit.DoesNotExist:
            raise NotFoundError("Unit", unit_id)
        
        bp = cls.model.objects.create(
            recipe=recipe,
            stock_item=stock_item,
            expected_quantity=to_decimal(expected_quantity),
            unit=unit,
            is_waste=is_waste,
            value_percentage=to_decimal(value_percentage),
        )
        
        return success_response({
            "id": bp.id,
            "by_product": cls.serialize(bp)
        }, "By-product added")
    
    @classmethod
    @transaction.atomic
    def remove(cls, byproduct_id: int) -> Dict[str, Any]:
        try:
            bp = cls.model.objects.get(id=byproduct_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("By-product", byproduct_id)
        
        bp.delete()
        return success_response(message="By-product removed")


class RecipeStepService(BaseService):
    
    model = RecipeStep
    
    @classmethod
    def serialize(cls, step: RecipeStep) -> Dict[str, Any]:
        return {
            "id": step.id,
            "uuid": str(step.uuid),
            "recipe_id": step.recipe_id,
            "step_number": step.step_number,
            "title": step.title,
            "description": step.description,
            "duration_minutes": step.duration_minutes,
            "temperature": step.temperature,
            "equipment_needed": step.equipment_needed,
            "is_checkpoint": step.is_checkpoint,
            "photo_url": step.photo_url,
        }
    
    @classmethod
    @transaction.atomic
    def add(cls,
            recipe_id: int,
            step_number: int,
            title: str,
            description: str = "",
            duration_minutes: int = None,
            temperature: str = "",
            equipment_needed: str = "",
            is_checkpoint: bool = False,
            photo_url: str = "") -> Dict[str, Any]:
        
        try:
            recipe = Recipe.objects.get(id=recipe_id)
        except Recipe.DoesNotExist:
            raise NotFoundError("Recipe", recipe_id)
        
        if cls.model.objects.filter(recipe=recipe, step_number=step_number).exists():
            cls.model.objects.filter(
                recipe=recipe, 
                step_number__gte=step_number
            ).update(step_number=models.F("step_number") + 1)
        
        step = cls.model.objects.create(
            recipe=recipe,
            step_number=step_number,
            title=title,
            description=description,
            duration_minutes=duration_minutes,
            temperature=temperature,
            equipment_needed=equipment_needed,
            is_checkpoint=is_checkpoint,
            photo_url=photo_url,
        )
        
        return success_response({
            "id": step.id,
            "step": cls.serialize(step)
        }, "Step added")
    
    @classmethod
    @transaction.atomic
    def update(cls, step_id: int, **kwargs) -> Dict[str, Any]:
        try:
            step = cls.model.objects.get(id=step_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Step", step_id)
        
        for field in ["title", "description", "duration_minutes", "temperature",
                      "equipment_needed", "is_checkpoint", "photo_url"]:
            if field in kwargs:
                setattr(step, field, kwargs[field])
        
        step.save()
        
        return success_response({
            "step": cls.serialize(step)
        }, "Step updated")
    
    @classmethod
    @transaction.atomic
    def remove(cls, step_id: int) -> Dict[str, Any]:
        try:
            step = cls.model.objects.get(id=step_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Step", step_id)
        
        recipe_id = step.recipe_id
        step_number = step.step_number
        
        step.delete()
        
        cls.model.objects.filter(
            recipe_id=recipe_id,
            step_number__gt=step_number
        ).update(step_number=models.F("step_number") - 1)
        
        return success_response(message="Step removed")
    
    @classmethod
    @transaction.atomic
    def reorder(cls, recipe_id: int, step_ids: List[int]) -> Dict[str, Any]:
        for idx, step_id in enumerate(step_ids, 1):
            cls.model.objects.filter(id=step_id, recipe_id=recipe_id).update(step_number=idx)
        
        return success_response({"reordered": len(step_ids)}, "Steps reordered")