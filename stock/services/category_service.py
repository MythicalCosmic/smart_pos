"""
Stock Category Service - Manage stock categories with hierarchy
"""
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.db.models import Q, Count

from stock.models import StockCategory, StockItem
from stock.services.base_service import (
    BaseService, success_response, error_response,
    ValidationError, NotFoundError, BusinessRuleError
)


class StockCategoryService(BaseService):
    """Manage stock categories"""
    
    model = StockCategory
    
    # ==================== SERIALIZATION ====================
    
    @classmethod
    def serialize(cls, category: StockCategory, 
                  include_children: bool = False,
                  include_item_count: bool = False) -> Dict[str, Any]:
        """Convert category to dictionary"""
        data = {
            "id": category.id,
            "uuid": str(category.uuid),
            "name": category.name,
            "type": category.type,
            "type_display": category.get_type_display(),
            "parent_id": category.parent_id,
            "sort_order": category.sort_order,
            "is_active": category.is_active,
            "created_at": category.created_at.isoformat(),
        }
        
        if category.parent:
            data["parent"] = {
                "id": category.parent.id,
                "name": category.parent.name,
            }
        
        if include_children:
            data["children"] = [
                cls.serialize(child, include_children=False)
                for child in category.children.filter(is_active=True).order_by("sort_order", "name")
            ]
        
        if include_item_count:
            data["item_count"] = StockItem.objects.filter(
                category=category, 
                is_active=True
            ).count()
        
        return data
    
    # ==================== LIST & SEARCH ====================
    
    @classmethod
    def list(cls,
             include_inactive: bool = False,
             type_filter: str = None,
             parent_id: int = None,
             include_item_count: bool = False) -> Dict[str, Any]:
        """List categories with filters"""
        queryset = cls.model.objects.all()
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        if type_filter:
            queryset = queryset.filter(type=type_filter)
        
        if parent_id is not None:
            if parent_id == 0:
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent_id)
        
        queryset = queryset.order_by("sort_order", "name")
        
        categories = [
            cls.serialize(cat, include_item_count=include_item_count)
            for cat in queryset
        ]
        
        return success_response({
            "categories": categories,
            "count": len(categories),
            "types": [
                {"value": c[0], "label": c[1]}
                for c in StockCategory.CategoryType.choices
            ]
        })
    
    @classmethod
    def get_tree(cls, include_inactive: bool = False) -> Dict[str, Any]:
        """Get categories as hierarchical tree"""
        queryset = cls.model.objects.filter(parent__isnull=True)
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        queryset = queryset.order_by("sort_order", "name")
        
        tree = [
            cls.serialize(cat, include_children=True, include_item_count=True)
            for cat in queryset
        ]
        
        return success_response({
            "tree": tree,
            "total_count": cls.model.objects.filter(is_active=True).count() if not include_inactive 
                          else cls.model.objects.count()
        })
    
    @classmethod
    def search(cls, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search categories"""
        categories = cls.model.objects.filter(
            Q(name__icontains=query),
            is_active=True
        ).order_by("name")[:limit]
        
        return success_response({
            "categories": [cls.serialize(cat) for cat in categories],
            "count": categories.count()
        })
    
    @classmethod
    def get_by_type(cls, category_type: str) -> Dict[str, Any]:
        """Get categories by type"""
        valid_types = [c[0] for c in StockCategory.CategoryType.choices]
        if category_type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "type")
        
        categories = cls.model.objects.filter(
            type=category_type,
            is_active=True
        ).order_by("sort_order", "name")
        
        return success_response({
            "categories": [cls.serialize(cat, include_item_count=True) for cat in categories],
            "count": categories.count()
        })
    
    # ==================== GET SINGLE ====================
    
    @classmethod
    def get(cls, category_id: int, 
            include_children: bool = True,
            include_item_count: bool = True) -> Dict[str, Any]:
        """Get single category"""
        category = cls.get_by_id(category_id)
        if not category:
            raise NotFoundError("Category", category_id)
        
        return success_response({
            "category": cls.serialize(
                category, 
                include_children=include_children,
                include_item_count=include_item_count
            )
        })
    
    # ==================== CREATE ====================
    
    @classmethod
    @transaction.atomic
    def create(cls,
               name: str,
               type: str,
               parent_id: int = None,
               sort_order: int = 0) -> Dict[str, Any]:
        """Create new category"""
        
        # Validate type
        valid_types = [c[0] for c in StockCategory.CategoryType.choices]
        if type not in valid_types:
            raise ValidationError(f"Invalid type. Valid: {valid_types}", "type")
        
        # Check duplicate name within parent
        duplicate_query = cls.model.objects.filter(name__iexact=name)
        if parent_id:
            duplicate_query = duplicate_query.filter(parent_id=parent_id)
        else:
            duplicate_query = duplicate_query.filter(parent__isnull=True)
        
        if duplicate_query.exists():
            raise ValidationError(f"Category '{name}' already exists at this level", "name")
        
        # Validate parent
        parent = None
        if parent_id:
            parent = cls.get_by_id(parent_id)
            if not parent:
                raise NotFoundError("Parent category", parent_id)
            if not parent.is_active:
                raise BusinessRuleError("Cannot add child to inactive category")
        
        category = cls.model.objects.create(
            name=name,
            type=type,
            parent=parent,
            sort_order=sort_order,
        )
        
        return success_response({
            "id": category.id,
            "uuid": str(category.uuid),
            "category": cls.serialize(category)
        }, f"Category '{name}' created")
    
    # ==================== UPDATE ====================
    
    @classmethod
    @transaction.atomic
    def update(cls, category_id: int, **kwargs) -> Dict[str, Any]:
        """Update category"""
        category = cls.get_by_id(category_id)
        if not category:
            raise NotFoundError("Category", category_id)
        
        # Validate type
        if "type" in kwargs:
            valid_types = [c[0] for c in StockCategory.CategoryType.choices]
            if kwargs["type"] not in valid_types:
                raise ValidationError(f"Invalid type. Valid: {valid_types}", "type")
        
        # Check name uniqueness
        if "name" in kwargs and kwargs["name"] != category.name:
            parent_id = kwargs.get("parent_id", category.parent_id)
            duplicate_query = cls.model.objects.filter(name__iexact=kwargs["name"]).exclude(id=category_id)
            if parent_id:
                duplicate_query = duplicate_query.filter(parent_id=parent_id)
            else:
                duplicate_query = duplicate_query.filter(parent__isnull=True)
            
            if duplicate_query.exists():
                raise ValidationError(f"Category '{kwargs['name']}' already exists at this level", "name")
        
        # Validate parent change
        if "parent_id" in kwargs:
            if kwargs["parent_id"]:
                parent = cls.get_by_id(kwargs["parent_id"])
                if not parent:
                    raise NotFoundError("Parent category", kwargs["parent_id"])
                if parent.id == category_id:
                    raise BusinessRuleError("Category cannot be its own parent")
                # Check circular reference
                if cls._is_descendant(parent, category):
                    raise BusinessRuleError("Cannot create circular hierarchy")
                category.parent = parent
            else:
                category.parent = None
        
        # Update fields
        update_fields = ["updated_at"]
        for field in ["name", "type", "sort_order"]:
            if field in kwargs:
                setattr(category, field, kwargs[field])
                update_fields.append(field)
        
        if "parent_id" in kwargs:
            update_fields.append("parent")
        
        category.save(update_fields=update_fields)
        
        return success_response({
            "category": cls.serialize(category)
        }, "Category updated")
    
    @classmethod
    def _is_descendant(cls, category: StockCategory, potential_ancestor: StockCategory) -> bool:
        """Check if category is a descendant of potential_ancestor"""
        current = category
        while current.parent:
            if current.parent_id == potential_ancestor.id:
                return True
            current = current.parent
        return False
    
    # ==================== DELETE / DEACTIVATE ====================
    
    @classmethod
    @transaction.atomic
    def deactivate(cls, category_id: int, cascade: bool = False) -> Dict[str, Any]:
        """Deactivate category"""
        category = cls.get_by_id(category_id)
        if not category:
            raise NotFoundError("Category", category_id)
        
        # Check for active items
        if StockItem.objects.filter(category=category, is_active=True).exists():
            if not cascade:
                raise BusinessRuleError("Cannot deactivate category with active items. Use cascade=True or reassign items first.")
            # Cascade: Set items to no category
            StockItem.objects.filter(category=category).update(category=None)
        
        # Check for active children
        active_children = category.children.filter(is_active=True)
        if active_children.exists():
            if not cascade:
                raise BusinessRuleError("Cannot deactivate category with active children. Use cascade=True.")
            # Cascade deactivate children
            for child in active_children:
                cls.deactivate(child.id, cascade=True)
        
        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "id": category_id
        }, "Category deactivated")
    
    @classmethod
    @transaction.atomic
    def activate(cls, category_id: int) -> Dict[str, Any]:
        """Reactivate category"""
        category = cls.get_by_id(category_id)
        if not category:
            raise NotFoundError("Category", category_id)
        
        # If has parent, ensure parent is active
        if category.parent and not category.parent.is_active:
            raise BusinessRuleError("Cannot activate category with inactive parent")
        
        category.is_active = True
        category.save(update_fields=["is_active", "updated_at"])
        
        return success_response({
            "category": cls.serialize(category)
        }, "Category activated")
    
    # ==================== REORDER ====================
    
    @classmethod
    @transaction.atomic
    def reorder(cls, category_ids: List[int]) -> Dict[str, Any]:
        """Reorder categories"""
        for index, cat_id in enumerate(category_ids):
            cls.model.objects.filter(id=cat_id).update(sort_order=index)
        
        return success_response({
            "reordered": len(category_ids)
        }, "Categories reordered")
    
    # ==================== MOVE ====================
    
    @classmethod
    @transaction.atomic
    def move(cls, category_id: int, new_parent_id: int = None) -> Dict[str, Any]:
        """Move category to new parent"""
        return cls.update(category_id, parent_id=new_parent_id)