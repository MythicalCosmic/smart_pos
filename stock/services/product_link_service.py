from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from stock.models import (
    ProductStockLink, ProductComponentStock,
    StockItem, StockUnit, Recipe, StockSettings
)
from base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal
)


class ProductStockLinkService(BaseService):
    
    model = ProductStockLink
    
    
    @classmethod
    def serialize(cls, link: ProductStockLink, include_components: bool = False) -> Dict[str, Any]:
        data = {
            "id": link.id,
            "uuid": str(link.uuid),
            "product_id": link.product_id,
            
            "link_type": link.link_type,
            "link_type_display": link.get_link_type_display(),
            
            "recipe_id": link.recipe_id,
            "recipe_name": link.recipe.name if link.recipe else None,
            
            "stock_item_id": link.stock_item_id,
            "stock_item_name": link.stock_item.name if link.stock_item else None,
            
            "quantity_per_sale": str(link.quantity_per_sale),
            "unit_id": link.unit_id,
            "unit_short": link.unit.short_name if link.unit else None,
            
            "deduct_on_status": link.deduct_on_status,
            "deduct_on_status_display": link.get_deduct_on_status_display(),
            
            "is_active": link.is_active,
            "created_at": link.created_at.isoformat(),
            "updated_at": link.updated_at.isoformat(),
        }
        
        if include_components and link.link_type == "COMPONENT_BASED":
            data["components"] = [
                ProductComponentService.serialize(comp)
                for comp in link.components.select_related("stock_item", "unit")
            ]
        
        return data
    
    
    @classmethod
    def list(cls,
             page: int = 1,
             per_page: int = 50,
             link_type: str = None,
             active_only: bool = True,
             unlinked_only: bool = False) -> Dict[str, Any]:
        queryset = cls.model.objects.select_related(
            "recipe", "stock_item", "unit"
        )
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if link_type:
            queryset = queryset.filter(link_type=link_type)
        
        queryset = queryset.order_by("product_id")
        
        links, pagination = paginate_queryset(queryset, page, per_page)
        
        return success_response({
            "links": [cls.serialize(link) for link in links],
            "pagination": pagination,
            "link_types": [{"value": c[0], "label": c[1]} for c in ProductStockLink.LinkType.choices],
            "deduct_statuses": [{"value": c[0], "label": c[1]} for c in ProductStockLink.DeductOn.choices],
        })
    
    
    @classmethod
    def get(cls, link_id: int, include_components: bool = True) -> Dict[str, Any]:
        link = cls.model.objects.select_related(
            "recipe", "stock_item", "unit"
        ).filter(id=link_id).first()
        
        if not link:
            raise NotFoundError("Product link", link_id)
        
        return success_response({
            "link": cls.serialize(link, include_components=include_components)
        })
    
    @classmethod
    def get_by_product(cls, product_id: int) -> Dict[str, Any]:
        link = cls.model.objects.select_related(
            "recipe", "stock_item", "unit"
        ).filter(product_id=product_id).first()
        
        if not link:
            return success_response({
                "link": None,
                "is_linked": False
            })
        
        return success_response({
            "link": cls.serialize(link, include_components=True),
            "is_linked": True
        })
    
    
    @classmethod
    @transaction.atomic
    def link_to_recipe(cls,
                       product_id: int,
                       recipe_id: int,
                       deduct_on_status: str = "PREPARING") -> Dict[str, Any]:
        
        if cls.model.objects.filter(product_id=product_id).exists():
            raise BusinessRuleError("Product already has a stock link. Remove existing link first.")
        
        try:
            recipe = Recipe.objects.get(id=recipe_id, is_active=True)
        except Recipe.DoesNotExist:
            raise NotFoundError("Recipe", recipe_id)
        
        valid_statuses = [c[0] for c in ProductStockLink.DeductOn.choices]
        if deduct_on_status not in valid_statuses:
            raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "deduct_on_status")
        
        link = cls.model.objects.create(
            product_id=product_id,
            link_type=ProductStockLink.LinkType.RECIPE,
            recipe=recipe,
            quantity_per_sale=Decimal("1"),
            unit=recipe.output_unit,
            deduct_on_status=deduct_on_status,
        )
        
        return success_response({
            "id": link.id,
            "link": cls.serialize(link)
        }, f"Product linked to recipe '{recipe.name}'")
    
    @classmethod
    @transaction.atomic
    def link_to_item(cls,
                     product_id: int,
                     stock_item_id: int,
                     quantity_per_sale: Decimal = Decimal("1"),
                     unit_id: int = None,
                     deduct_on_status: str = "PREPARING") -> Dict[str, Any]:
        
        if cls.model.objects.filter(product_id=product_id).exists():
            raise BusinessRuleError("Product already has a stock link. Remove existing link first.")
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id, is_active=True)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        if unit_id:
            try:
                unit = StockUnit.objects.get(id=unit_id, is_active=True)
            except StockUnit.DoesNotExist:
                raise NotFoundError("Unit", unit_id)
        else:
            unit = stock_item.base_unit
        
        valid_statuses = [c[0] for c in ProductStockLink.DeductOn.choices]
        if deduct_on_status not in valid_statuses:
            raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "deduct_on_status")
        
        link = cls.model.objects.create(
            product_id=product_id,
            link_type=ProductStockLink.LinkType.DIRECT_ITEM,
            stock_item=stock_item,
            quantity_per_sale=to_decimal(quantity_per_sale),
            unit=unit,
            deduct_on_status=deduct_on_status,
        )
        
        return success_response({
            "id": link.id,
            "link": cls.serialize(link)
        }, f"Product linked to stock item '{stock_item.name}'")
    
    @classmethod
    @transaction.atomic
    def link_with_components(cls,
                             product_id: int,
                             components: List[Dict],
                             deduct_on_status: str = "PREPARING") -> Dict[str, Any]:
        
        if cls.model.objects.filter(product_id=product_id).exists():
            raise BusinessRuleError("Product already has a stock link. Remove existing link first.")
        
        if not components:
            raise ValidationError("At least one component required", "components")
        
        valid_statuses = [c[0] for c in ProductStockLink.DeductOn.choices]
        if deduct_on_status not in valid_statuses:
            raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "deduct_on_status")
        
        link = cls.model.objects.create(
            product_id=product_id,
            link_type=ProductStockLink.LinkType.COMPONENT_BASED,
            quantity_per_sale=Decimal("1"),
            deduct_on_status=deduct_on_status,
        )
        
        for comp_data in components:
            ProductComponentService.add_component(
                link_id=link.id,
                stock_item_id=comp_data["stock_item_id"],
                quantity=comp_data["quantity"],
                component_name=comp_data.get("name", ""),
                unit_id=comp_data.get("unit_id"),
                is_default=comp_data.get("is_default", True),
                is_addable=comp_data.get("is_addable", True),
                is_removable=comp_data.get("is_removable", True),
                price_modifier=comp_data.get("price_modifier", 0),
            )
        
        return success_response({
            "id": link.id,
            "link": cls.serialize(link, include_components=True)
        }, "Product linked with components")
    
    @classmethod
    @transaction.atomic
    def update(cls, link_id: int, **kwargs) -> Dict[str, Any]:
        link = cls.get_by_id(link_id)
        if not link:
            raise NotFoundError("Product link", link_id)
        
        update_fields = ["updated_at"]
        
        if "quantity_per_sale" in kwargs:
            link.quantity_per_sale = to_decimal(kwargs["quantity_per_sale"])
            update_fields.append("quantity_per_sale")
        
        if "deduct_on_status" in kwargs:
            valid_statuses = [c[0] for c in ProductStockLink.DeductOn.choices]
            if kwargs["deduct_on_status"] not in valid_statuses:
                raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "deduct_on_status")
            link.deduct_on_status = kwargs["deduct_on_status"]
            update_fields.append("deduct_on_status")
        
        if "is_active" in kwargs:
            link.is_active = kwargs["is_active"]
            update_fields.append("is_active")
        
        link.save(update_fields=update_fields)
        
        return success_response({
            "link": cls.serialize(link, include_components=True)
        }, "Link updated")
    
    @classmethod
    @transaction.atomic
    def unlink(cls, product_id: int) -> Dict[str, Any]:
        link = cls.model.objects.filter(product_id=product_id).first()
        
        if not link:
            raise NotFoundError("Product link for product", product_id)
        
        link.delete()
        
        return success_response(message="Product unlinked from stock")
    
    
    @classmethod
    def get_deduction_items(cls, product_id: int, quantity: int = 1) -> List[Dict]:

        link = cls.model.objects.select_related(
            "recipe", "stock_item", "unit"
        ).filter(product_id=product_id, is_active=True).first()
        
        if not link:
            return []
        
        deductions = []
        sale_qty = to_decimal(quantity)
        
        if link.link_type == "DIRECT_ITEM":
            if link.stock_item:
                deductions.append({
                    "stock_item_id": link.stock_item_id,
                    "quantity": link.quantity_per_sale * sale_qty,
                    "unit_id": link.unit_id,
                })
        
        elif link.link_type == "RECIPE":
            if link.recipe:
                for ingredient in link.recipe.ingredients.select_related("stock_item", "unit"):
                    deductions.append({
                        "stock_item_id": ingredient.stock_item_id,
                        "quantity": ingredient.quantity * sale_qty * link.quantity_per_sale,
                        "unit_id": ingredient.unit_id,
                    })
        
        elif link.link_type == "COMPONENT_BASED":
            for comp in link.components.filter(is_default=True).select_related("stock_item", "unit"):
                deductions.append({
                    "stock_item_id": comp.stock_item_id,
                    "quantity": comp.quantity * sale_qty,
                    "unit_id": comp.unit_id,
                })
        
        return deductions
    
    @classmethod
    def should_deduct(cls, product_id: int, order_status: str) -> bool:
        settings = StockSettings.load()
        
        if not settings.stock_enabled or not settings.auto_deduct_on_sale:
            return False
        
        link = cls.model.objects.filter(product_id=product_id, is_active=True).first()
        
        if not link:
            return False
        
        return link.deduct_on_status == order_status


class ProductComponentService(BaseService):
    
    model = ProductComponentStock
    
    @classmethod
    def serialize(cls, comp: ProductComponentStock) -> Dict[str, Any]:
        return {
            "id": comp.id,
            "uuid": str(comp.uuid),
            "component_name": comp.component_name,
            "stock_item_id": comp.stock_item_id,
            "stock_item_name": comp.stock_item.name,
            "quantity": str(comp.quantity),
            "unit_id": comp.unit_id,
            "unit_short": comp.unit.short_name,
            "is_default": comp.is_default,
            "is_addable": comp.is_addable,
            "is_removable": comp.is_removable,
            "price_modifier": str(comp.price_modifier),
        }
    
    @classmethod
    @transaction.atomic
    def add_component(cls,
                      link_id: int,
                      stock_item_id: int,
                      quantity: Decimal,
                      component_name: str = "",
                      unit_id: int = None,
                      is_default: bool = True,
                      is_addable: bool = True,
                      is_removable: bool = True,
                      price_modifier: Decimal = Decimal("0")) -> Dict[str, Any]:
        
        try:
            link = ProductStockLink.objects.get(id=link_id)
        except ProductStockLink.DoesNotExist:
            raise NotFoundError("Product link", link_id)
        
        if link.link_type != "COMPONENT_BASED":
            raise BusinessRuleError("Can only add components to COMPONENT_BASED links")
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id, is_active=True)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        if unit_id:
            try:
                unit = StockUnit.objects.get(id=unit_id, is_active=True)
            except StockUnit.DoesNotExist:
                raise NotFoundError("Unit", unit_id)
        else:
            unit = stock_item.base_unit
        
        comp = cls.model.objects.create(
            product_stock_link=link,
            component_name=component_name or stock_item.name,
            stock_item=stock_item,
            quantity=to_decimal(quantity),
            unit=unit,
            is_default=is_default,
            is_addable=is_addable,
            is_removable=is_removable,
            price_modifier=to_decimal(price_modifier),
        )
        
        return success_response({
            "id": comp.id,
            "component": cls.serialize(comp)
        }, "Component added")
    
    @classmethod
    @transaction.atomic
    def update_component(cls, component_id: int, **kwargs) -> Dict[str, Any]:
        try:
            comp = cls.model.objects.get(id=component_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Component", component_id)
        
        for field in ["component_name", "quantity", "is_default", "is_addable", "is_removable", "price_modifier"]:
            if field in kwargs:
                value = kwargs[field]
                if field in ["quantity", "price_modifier"]:
                    value = to_decimal(value)
                setattr(comp, field, value)
        
        comp.save()
        
        return success_response({
            "component": cls.serialize(comp)
        }, "Component updated")
    
    @classmethod
    @transaction.atomic
    def remove_component(cls, component_id: int) -> Dict[str, Any]:
        try:
            comp = cls.model.objects.get(id=component_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Component", component_id)
        
        comp.delete()
        
        return success_response(message="Component removed")
    
    @classmethod
    def get_for_link(cls, link_id: int) -> Dict[str, Any]:
        components = cls.model.objects.filter(
            product_stock_link_id=link_id
        ).select_related("stock_item", "unit")
        
        return success_response({
            "components": [cls.serialize(c) for c in components],
            "count": components.count()
        })