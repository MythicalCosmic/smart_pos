from pydoc import classname
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from django.db import transaction
from django.db.models import Q

from stock.models import StockUnit, StockItem, StockItemUnit
from stock.services.base_service import (
    BaseService, success_response, error_response, 
    ValidationError, NotFoundError, BusinessRuleError,
    to_decimal, round_decimal
)


class StockUnitService(BaseService):
    model = StockUnit
    
    def serialize(cls, unit: StockUnit, include_derived: bool = False) -> Dict[str, Any]:
        data = {
            "id": unit.id,
            "uuid": str(unit.uuid),
            "name": unit.name,
            "short_name": unit.short_name,
            "unit_type": unit.unit_type,
            "unit_type_display": unit.get_unit_type_display(),
            "is_base_unit": unit.is_base_unit,
            "base_unit_id": unit.base_unit_id,
            "conversion_factor": str(unit.conversion_factor),
            "decimal_places": unit.decimal_places,
            "is_active": unit.is_active,
        }
        
        if unit.base_unit:
            data["base_unit"] = {
                "id": unit.base_unit.id,
                "name": unit.base_unit.name,
                "short_name": unit.base_unit.short_name,
            }
        
        if include_derived:
            derived = unit.derived_units.filter(is_active=True)
            data["derived_units"] = [
                {
                    "id": d.id,
                    "name": d.name,
                    "short_name": d.short_name,
                    "conversion_factor": str(d.conversion_factor),
                }
                for d in derived
            ]
        
        return data
    
    @classmethod
    def list(cls, 
             include_inactive: bool = False,
             type_filter: str = None,
             base_only: bool = False) -> Dict[str, Any]:
        queryset = cls.model.objects.all()
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        if type_filter:
            queryset = queryset.filter(unit_type=type_filter)
        
        if base_only:
            queryset = queryset.filter(is_base_unit=True)
        
        queryset = queryset.order_by("unit_type", "name")

        units_by_type = {}
        all_units = []
        
        for unit in queryset:
            data = cls.serialize(cls, unit)
            all_units.append(data)
            
            if unit.unit_type not in units_by_type:
                units_by_type[unit.unit_type] = []
            units_by_type[unit.unit_type].append(data)
        
        return success_response({
            "units": all_units,
            "by_type": units_by_type,
            "count": len(all_units),
            "types": [
                {"value": c[0], "label": c[1]}
                for c in StockUnit.UnitType.choices
            ]
        })
    
    @classmethod
    def get_by_type(cls, unit_type: str) -> Dict[str, Any]:
        valid_types = [c[0] for c in StockUnit.UnitType.choices]
        if unit_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "unit_type")
        
        units = cls.model.objects.filter(
            unit_type=unit_type, 
            is_active=True
        ).order_by("-is_base_unit", "name")
        
        base_unit = units.filter(is_base_unit=True).first()
        
        return success_response({
            "units": [cls.serialize(u) for u in units],
            "base_unit": cls.serialize(base_unit) if base_unit else None,
            "count": units.count()
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20) -> Dict[str, Any]:
        units = cls.model.objects.filter(
            Q(name__icontains=query) | Q(short_name__icontains=query),
            is_active=True
        ).order_by("name")[:limit]
        
        return success_response({
            "units": [cls.serialize(u) for u in units],
            "count": units.count()
        })
    
    
    @classmethod
    def get(cls, unit_id: int, include_derived: bool = True) -> Dict[str, Any]:
        unit = cls.get_by_id(unit_id)
        if not unit:
            raise NotFoundError("Unit", unit_id)
        
        return success_response({
            "unit": cls.serialize(cls, unit, include_derived=include_derived)
        })
    
    @classmethod
    def get_base_unit(cls, unit_type: str) -> Optional[StockUnit]:
        return cls.model.objects.filter(
            unit_type=unit_type,
            is_base_unit=True,
            is_active=True
        ).first()
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               short_name: str,
               unit_type: str,
               is_base_unit: bool = False,
               base_unit_id: int = None,
               conversion_factor: Decimal = Decimal("1"),
               decimal_places: int = 2) -> Dict[str, Any]:
        
        valid_types = [c[0] for c in StockUnit.UnitType.choices]
        if unit_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "unit_type")
        
        if cls.model.objects.filter(short_name__iexact=short_name).exists():
            raise ValidationError(f"Unit with short name '{short_name}' already exists", "short_name")
        
        base_unit = None
        if is_base_unit:
            existing_base = cls.get_base_unit(unit_type)
            if existing_base:
                raise BusinessRuleError(f"Base unit already exists for {unit_type}: {existing_base.name}")
            conversion_factor = Decimal("1")
        elif base_unit_id:
            base_unit = cls.get_by_id(base_unit_id)
            if not base_unit:
                raise NotFoundError("Base unit", base_unit_id)
            if base_unit.unit_type != unit_type:
                raise ValidationError("Base unit must be of same type", "base_unit_id")
            if not base_unit.is_base_unit:
                raise ValidationError("Referenced unit is not a base unit", "base_unit_id")
        else:
            base_unit = cls.get_base_unit(unit_type)
            if not base_unit:
                raise BusinessRuleError(f"No base unit exists for {unit_type}. Create base unit first.")
        
        unit = cls.model.objects.create(
            name=name,
            short_name=short_name,
            unit_type=unit_type,
            is_base_unit=is_base_unit,
            base_unit=base_unit,
            conversion_factor=to_decimal(conversion_factor),
            decimal_places=decimal_places,
        )
        
        return success_response({
            "id": unit.id,
            "uuid": str(unit.uuid),
            "unit": unit.name,
        }, f"Unit '{name}' created")
    
    @classmethod
    @transaction.atomic
    def update(cls, unit_id: int, **kwargs) -> Dict[str, Any]:
        unit = cls.get_by_id(unit_id)
        if not unit:
            raise NotFoundError("Unit", unit_id)
        
        if "short_name" in kwargs and kwargs["short_name"] != unit.short_name:
            if cls.model.objects.filter(short_name__iexact=kwargs["short_name"]).exclude(id=unit_id).exists():
                raise ValidationError(f"Unit with short name '{kwargs['short_name']}' already exists", "short_name")
        
        if "unit_type" in kwargs and kwargs["unit_type"] != unit.unit_type:
            if unit.is_base_unit and unit.derived_units.exists():
                raise BusinessRuleError("Cannot change type of base unit with derived units")
        
        update_fields = []
        for field in ["name", "short_name", "conversion_factor", "decimal_places"]:
            if field in kwargs:
                setattr(unit, field, kwargs[field])
                update_fields.append(field)
        
        if update_fields:
            unit.save(update_fields=update_fields)
        
        return success_response({
            "unit": cls.serialize(unit)
        }, "Unit updated")
    
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, unit_id: int) -> Dict[str, Any]:
        unit = cls.get_by_id(unit_id)
        if not unit:
            raise NotFoundError("Unit", unit_id)
        
        if StockItem.objects.filter(base_unit=unit).exists():
            raise BusinessRuleError("Cannot deactivate unit used by stock items")
        
        if unit.is_base_unit and unit.derived_units.filter(is_active=True).exists():
            raise BusinessRuleError("Cannot deactivate base unit with active derived units")
        
        unit.is_active = False
        unit.save(update_fields=["is_active"])
        
        return success_response({
            "id": unit_id
        }, "Unit deactivated")
    
    @classmethod
    def convert(cls, 
                quantity: Decimal, 
                from_unit_id: int, 
                to_unit_id: int) -> Tuple[Decimal, Dict[str, Any]]:

        from_unit = cls.get_by_id(from_unit_id)
        to_unit = cls.get_by_id(to_unit_id)
        
        if not from_unit:
            raise NotFoundError("From unit", from_unit_id)
        if not to_unit:
            raise NotFoundError("To unit", to_unit_id)
        
        if from_unit.unit_type != to_unit.unit_type:
            raise BusinessRuleError(
                f"Cannot convert between different types: {from_unit.unit_type} → {to_unit.unit_type}"
            )
        
        quantity = to_decimal(quantity)
        
        if from_unit.is_base_unit:
            base_quantity = quantity
        else:
            base_quantity = quantity * from_unit.conversion_factor
        
        if to_unit.is_base_unit:
            result = base_quantity
        else:
            result = base_quantity / to_unit.conversion_factor
        
        result = round_decimal(result, to_unit.decimal_places)
        
        details = {
            "from_quantity": str(quantity),
            "from_unit": from_unit.short_name,
            "to_quantity": str(result),
            "to_unit": to_unit.short_name,
            "base_quantity": str(round_decimal(base_quantity, 4)),
        }
        
        return result, details
    
    @classmethod
    def to_base(cls, quantity: Decimal, unit_id: int) -> Tuple[Decimal, StockUnit]:
        unit = cls.get_by_id(unit_id)
        if not unit:
            raise NotFoundError("Unit", unit_id)
        
        quantity = to_decimal(quantity)
        
        if unit.is_base_unit:
            return quantity, unit
        
        base_quantity = quantity * unit.conversion_factor
        base_unit = unit.base_unit if unit.base_unit else unit
        
        return round_decimal(base_quantity, 4), base_unit
    
    @classmethod
    def from_base(cls, base_quantity: Decimal, to_unit_id: int) -> Decimal:
        unit = cls.get_by_id(to_unit_id)
        if not unit:
            raise NotFoundError("Unit", to_unit_id)
        
        base_quantity = to_decimal(base_quantity)
        
        if unit.is_base_unit:
            return base_quantity
        
        result = base_quantity / unit.conversion_factor
        return round_decimal(result, unit.decimal_places)


class StockItemUnitService(BaseService):
    model = StockItemUnit
    
    @classmethod
    def serialize(cls, item_unit: StockItemUnit) -> Dict[str, Any]:
        return {
            "id": item_unit.id,
            "uuid": str(item_unit.uuid),
            "stock_item_id": item_unit.stock_item_id,
            "unit_id": item_unit.unit_id,
            "unit": {
                "id": item_unit.unit.id,
                "name": item_unit.unit.name,
                "short_name": item_unit.unit.short_name,
            },
            "is_default": item_unit.is_default,
            "conversion_to_base": str(item_unit.conversion_to_base),
            "barcode": item_unit.barcode,
        }
    
    @classmethod
    def get_for_item(cls, stock_item_id: int) -> Dict[str, Any]:
        item_units = cls.model.objects.filter(
            stock_item_id=stock_item_id
        ).select_related("unit").order_by("-is_default", "unit__name")
        
        return success_response({
            "units": [cls.serialize(iu) for iu in item_units],
            "count": item_units.count()
        })
    
    @classmethod
    @transaction.atomic
    def add_unit(cls,
                 stock_item_id: int,
                 unit_id: int,
                 conversion_to_base: Decimal,
                 is_default: bool = False,
                 barcode: str = None) -> Dict[str, Any]:
        from stock.models import StockItem
        
        try:
            stock_item = StockItem.objects.get(id=stock_item_id)
        except StockItem.DoesNotExist:
            raise NotFoundError("Stock item", stock_item_id)
        
        unit = StockUnitService.get_by_id(unit_id)
        if not unit:
            raise NotFoundError("Unit", unit_id)
        
        if cls.model.objects.filter(stock_item_id=stock_item_id, unit_id=unit_id).exists():
            raise ValidationError("This unit is already added to the item", "unit_id")
        
        if is_default:
            cls.model.objects.filter(stock_item_id=stock_item_id, is_default=True).update(is_default=False)
        
        item_unit = cls.model.objects.create(
            stock_item_id=stock_item_id,
            unit_id=unit_id,
            conversion_to_base=to_decimal(conversion_to_base),
            is_default=is_default,
            barcode=barcode or "",
        )
        
        return success_response({
            "id": item_unit.id,
            "item_unit": cls.serialize(item_unit)
        }, "Unit added to item")
    
    @classmethod
    @transaction.atomic
    def remove_unit(cls, item_unit_id: int) -> Dict[str, Any]:
        try:
            item_unit = cls.model.objects.get(id=item_unit_id)
        except cls.model.DoesNotExist:
            raise NotFoundError("Item unit", item_unit_id)
        
        item_unit.delete()
        
        return success_response(message="Unit removed from item")
    
    @classmethod
    def convert_for_item(cls, 
                         stock_item_id: int,
                         quantity: Decimal,
                         from_unit_id: int) -> Decimal:
        try:
            item_unit = cls.model.objects.get(
                stock_item_id=stock_item_id,
                unit_id=from_unit_id
            )
            return to_decimal(quantity) * item_unit.conversion_to_base
        except cls.model.DoesNotExist:
            result, _ = StockUnitService.convert(
                quantity, 
                from_unit_id, 
                StockItem.objects.get(id=stock_item_id).base_unit_id
            )
            return result