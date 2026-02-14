from typing import Dict, Any, Optional, List
from django.db import transaction
from django.db.models import Q, Count, Sum

from stock.models import StockLocation, StockLevel, StockSettings
from stock.services.base_service import (
    BaseService, success_response, error_response, paginate_queryset,
    ValidationError, NotFoundError, BusinessRuleError
)


class StockLocationService(BaseService):
    model = StockLocation
    
    @classmethod
    def serialize(cls, location: StockLocation, include_children: bool = False, 
                  include_stats: bool = False) -> Dict[str, Any]:
        data = {
            "id": location.id,
            "uuid": str(location.uuid),
            "name": location.name,
            "type": location.type,
            "type_display": location.get_type_display(),
            "parent_id": location.parent_location_id,
            "is_default": location.is_default,
            "is_production_area": location.is_production_area,
            "is_active": location.is_active,
            "sort_order": location.sort_order,
            "created_at": location.created_at.isoformat(),
        }
        
        if include_children:
            data["children"] = [
                cls.serialize(child, include_children=False)
                for child in location.children.filter(is_active=True).order_by("sort_order", "name")
            ]
        
        if include_stats:
            stats = StockLevel.objects.filter(location=location).aggregate(
                total_items=Count("id"),
                total_quantity=Sum("quantity"),
                reserved_quantity=Sum("reserved_quantity"),
            )
            data["stats"] = {
                "item_count": stats["total_items"] or 0,
                "total_quantity": str(stats["total_quantity"] or 0),
                "reserved_quantity": str(stats["reserved_quantity"] or 0),
            }
        
        return data
    
    
    @classmethod
    def list(cls, 
             include_inactive: bool = False,
             type_filter: str = None,
             parent_id: int = None,
             production_only: bool = False,
             include_children: bool = False,
             include_stats: bool = False) -> Dict[str, Any]:
        
        queryset = cls.model.objects.all()
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        if type_filter:
            queryset = queryset.filter(type=type_filter)
        
        if parent_id is not None:
            if parent_id == 0:
                queryset = queryset.filter(parent_location__isnull=True)
            else:
                queryset = queryset.filter(parent_location_id=parent_id)
        
        if production_only:
            queryset = queryset.filter(is_production_area=True)
        
        queryset = queryset.order_by("sort_order", "name")
        
        locations = [
            cls.serialize(loc, include_children=include_children, include_stats=include_stats)
            for loc in queryset
        ]
        
        return success_response({
            "locations": locations,
            "count": len(locations),
            "types": [
                {"value": c[0], "label": c[1]}
                for c in StockLocation.LocationType.choices
            ]
        })
    
    @classmethod
    def get_tree(cls, include_inactive: bool = False) -> Dict[str, Any]:
        queryset = cls.model.objects.filter(parent_location__isnull=True)
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        queryset = queryset.order_by("sort_order", "name")
        
        tree = [
            cls.serialize(loc, include_children=True)
            for loc in queryset
        ]
        
        return success_response({
            "tree": tree,
            "total_count": cls.model.objects.filter(is_active=True).count() if not include_inactive 
                          else cls.model.objects.count()
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20) -> Dict[str, Any]:
        locations = cls.model.objects.filter(
            Q(name__icontains=query) | Q(type__icontains=query),
            is_active=True
        ).order_by("name")[:limit]
        
        return success_response({
            "locations": [cls.serialize(loc) for loc in locations],
            "count": locations.count()
        })
    
    @classmethod
    def get(cls, location_id: int, include_children: bool = True, 
            include_stats: bool = True) -> Dict[str, Any]:
        location = cls.get_by_id(location_id)
        if not location:
            raise NotFoundError("Location", location_id)
        
        return success_response({
            "location": cls.serialize(location, include_children=include_children, 
                                      include_stats=include_stats)
        })
    
    @classmethod
    def get_default(cls) -> Optional[StockLocation]:
        try:
            return cls.model.objects.get(is_default=True, is_active=True)
        except cls.model.DoesNotExist:
            return cls.model.objects.filter(is_active=True).first()
    
    @classmethod
    def get_production_locations(cls) -> List[StockLocation]:
        return list(cls.model.objects.filter(is_production_area=True, is_active=True))
    
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               type: str,
               parent_id: int = None,
               is_default: bool = False,
               is_production_area: bool = False,
               sort_order: int = 0) -> Dict[str, Any]:
        
        valid_types = [c[0] for c in StockLocation.LocationType.choices]
        if type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "type")
        
        if cls.model.objects.filter(name__iexact=name).exists():
            raise ValidationError(f"Location with name '{name}' already exists", "name")
        
        parent = None
        if parent_id:
            parent = cls.get_by_id(parent_id)
            if not parent:
                raise NotFoundError("Parent location", parent_id)
            if not parent.is_active:
                raise BusinessRuleError("Cannot add child to inactive location")
        
        if is_default:
            cls.model.objects.filter(is_default=True).update(is_default=False)
        
        location = cls.model.objects.create(
            name=name,
            type=type,
            parent_location=parent,
            is_default=is_default,
            is_production_area=is_production_area,
            sort_order=sort_order,
        )
        
        return success_response({
            "id": location.id,
            "uuid": str(location.uuid),
            "location": cls.serialize(location)
        }, f"Location '{name}' created")
    
    
    @classmethod
    @transaction.atomic
    def update(cls, location_id: int, **kwargs) -> Dict[str, Any]:
        location = cls.get_by_id(location_id)
        if not location:
            raise NotFoundError("Location", location_id)
        
        if "type" in kwargs:
            valid_types = [c[0] for c in StockLocation.LocationType.choices]
            if kwargs["type"] not in valid_types:
                raise ValidationError(f"Invalid type. Valid: {valid_types}", "type")
        
        if "name" in kwargs and kwargs["name"] != location.name:
            if cls.model.objects.filter(name__iexact=kwargs["name"]).exclude(id=location_id).exists():
                raise ValidationError(f"Location with name '{kwargs['name']}' already exists", "name")
        
        if "parent_id" in kwargs:
            if kwargs["parent_id"]:
                parent = cls.get_by_id(kwargs["parent_id"])
                if not parent:
                    raise NotFoundError("Parent location", kwargs["parent_id"])
                if parent.id == location_id:
                    raise BusinessRuleError("Location cannot be its own parent")
                if cls._is_descendant(parent, location):
                    raise BusinessRuleError("Cannot create circular hierarchy")
                location.parent_location = parent
            else:
                location.parent_location = None
        
        if kwargs.get("is_default"):
            cls.model.objects.filter(is_default=True).exclude(id=location_id).update(is_default=False)
        
        update_fields = ["updated_at"]
        for field in ["name", "type", "is_default", "is_production_area", "sort_order"]:
            if field in kwargs:
                setattr(location, field, kwargs[field])
                update_fields.append(field)
        
        if "parent_id" in kwargs:
            update_fields.append("parent_location")
        
        location.save(update_fields=update_fields)
        
        return success_response({
            "location": cls.serialize(location)
        }, "Location updated")
    
    @classmethod
    def _is_descendant(cls, location: StockLocation, potential_ancestor: StockLocation) -> bool:
        current = location
        while current.parent_location:
            if current.parent_location_id == potential_ancestor.id:
                return True
            current = current.parent_location
        return False
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, location_id: int) -> Dict[str, Any]:
        location = cls.get_by_id(location_id)
        if not location:
            raise NotFoundError("Location", location_id)
        
        has_stock = StockLevel.objects.filter(
            location=location, 
            quantity__gt=0
        ).exists()
        
        if has_stock:
            raise BusinessRuleError("Cannot deactivate location with stock. Transfer stock first.")
        
        if location.is_default:
            raise BusinessRuleError("Cannot deactivate default location. Set another location as default first.")
        
        location.is_active = False
        location.save(update_fields=["is_active", "updated_at"])
        
        children_count = location.children.filter(is_active=True).update(is_active=False)
        
        return success_response({
            "id": location_id,
            "children_deactivated": children_count
        }, "Location deactivated")
    
    @classmethod
    @transaction.atomic
    def activate(cls, location_id: int) -> Dict[str, Any]:
        location = cls.get_by_id(location_id)
        if not location:
            raise NotFoundError("Location", location_id)
        
        if location.parent_location and not location.parent_location.is_active:
            raise BusinessRuleError("Cannot activate location with inactive parent")
        
        location.is_active = True
        location.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "location": cls.serialize(location)
        }, "Location activated")
    
    
    @classmethod
    @transaction.atomic
    def set_default(cls, location_id: int) -> Dict[str, Any]:
        location = cls.get_by_id(location_id)
        if not location:
            raise NotFoundError("Location", location_id)
        
        if not location.is_active:
            raise BusinessRuleError("Cannot set inactive location as default")
        
        cls.model.objects.filter(is_default=True).update(is_default=False)
        
        location.is_default = True
        location.save(update_fields=["is_default", "updated_at"])
        
        settings = StockSettings.load()
        settings.default_location = location
        settings.save(update_fields=["default_location", "updated_at"])
        
        return success_response({
            "location": cls.serialize(location)
        }, f"'{location.name}' set as default location")
    
    
    @classmethod
    @transaction.atomic
    def reorder(cls, location_ids: List[int]) -> Dict[str, Any]:
        for index, loc_id in enumerate(location_ids):
            cls.model.objects.filter(id=loc_id).update(sort_order=index)
        
        return success_response({
            "reordered": len(location_ids)
        }, "Locations reordered")