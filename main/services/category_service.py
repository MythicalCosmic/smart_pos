from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils.text import slugify
from django.utils import timezone
from main.models import Category


class CategoryService:
    
    @staticmethod
    def _get_base_queryset(include_deleted=False):
        if include_deleted:
            return Category.objects.all()
        return Category.objects.filter(is_deleted=False)
    
    @staticmethod
    def _generate_unique_slug(name, exclude_id=None):
        base_slug = slugify(name, allow_unicode=True)
        if not base_slug:
            base_slug = 'category'
        
        slug = base_slug
        counter = 1
        
        while True:
            qs = Category.objects.filter(slug=slug, is_deleted=False)
            if exclude_id:
                qs = qs.exclude(id=exclude_id)
            if not qs.exists():
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1
    
    @staticmethod
    def get_all_categories(page=1, per_page=20, search=None, status=None, 
                           order_by='sort_order', include_deleted=False):
        queryset = CategoryService._get_base_queryset(include_deleted)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search) |
                Q(slug__icontains=search)
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        queryset = queryset.order_by(order_by)
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        categories = []
        for cat in page_obj.object_list:
            categories.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'description': cat.description,
                'colors': cat.colors,
                'status': cat.status,
                'sort_order': cat.sort_order,
                'is_deleted': cat.is_deleted,
                'created_at': cat.created_at.isoformat() if cat.created_at else None,
                'updated_at': cat.updated_at.isoformat() if cat.updated_at else None,
            })
        
        return {
            'success': True,
            'categories': categories,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_categories': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
    
    @staticmethod
    def get_active_categories():
        categories = Category.objects.filter(
            status='ACTIVE', 
            is_deleted=False
        ).order_by('sort_order').values(
            'id', 'name', 'slug', 'description', 'colors', 'sort_order'
        )
        
        return {'success': True, 'categories': list(categories)}
    
    @staticmethod
    def get_category_by_id(category_id, include_deleted=False):
        try:
            queryset = CategoryService._get_base_queryset(include_deleted)
            category = queryset.get(id=category_id)
            
            return {
                'success': True,
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'slug': category.slug,
                    'description': category.description,
                    'colors': category.colors,
                    'status': category.status,
                    'sort_order': category.sort_order,
                    'is_deleted': category.is_deleted,
                    'created_at': category.created_at.isoformat() if category.created_at else None,
                    'updated_at': category.updated_at.isoformat() if category.updated_at else None,
                }
            }
        except Category.DoesNotExist:
            return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
    
    @staticmethod
    def get_category_by_slug(slug):
        try:
            category = Category.objects.get(slug=slug, status='ACTIVE', is_deleted=False)
            
            return {
                'success': True,
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'slug': category.slug,
                    'description': category.description,
                    'colors': category.colors,
                    'sort_order': category.sort_order,
                }
            }
        except Category.DoesNotExist:
            return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
    
    @staticmethod
    def create_category(name, description=None, sort_order=0, status='ACTIVE', 
                        colors=None, slug=None):
        try:
            if not name or not name.strip():
                return {'success': False, 'message': 'Category name is required', 'error_code': 'VALIDATION_ERROR'}
            
            name = name.strip()
            
            if Category.objects.filter(name__iexact=name, is_deleted=False).exists():
                return {'success': False, 'message': 'Category with this name already exists', 'error_code': 'DUPLICATE_NAME'}
            
            if not slug:
                slug = CategoryService._generate_unique_slug(name)
            else:
                if Category.objects.filter(slug=slug, is_deleted=False).exists():
                    return {'success': False, 'message': 'Category with this slug already exists', 'error_code': 'DUPLICATE_SLUG'}
            
            category = Category.objects.create(
                name=name,
                slug=slug,
                description=description or '',
                sort_order=sort_order,
                status=status,
                colors=colors or [],
            )
            
            return {
                'success': True, 
                'message': 'Category created successfully',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'slug': category.slug,
                    'description': category.description,
                    'colors': category.colors,
                    'status': category.status,
                    'sort_order': category.sort_order,
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to create category: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def update_category(category_id, **kwargs):
        try:
            try:
                category = Category.objects.get(id=category_id, is_deleted=False)
            except Category.DoesNotExist:
                return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
            
            if 'name' in kwargs and kwargs['name']:
                new_name = kwargs['name'].strip()
                if new_name.lower() != category.name.lower():
                    if Category.objects.filter(name__iexact=new_name, is_deleted=False).exclude(id=category_id).exists():
                        return {'success': False, 'message': 'Category with this name already exists', 'error_code': 'DUPLICATE_NAME'}
                    kwargs['name'] = new_name
                    if 'slug' not in kwargs:
                        kwargs['slug'] = CategoryService._generate_unique_slug(new_name, exclude_id=category_id)
            
            if 'slug' in kwargs and kwargs['slug']:
                new_slug = kwargs['slug']
                if new_slug != category.slug:
                    if Category.objects.filter(slug=new_slug, is_deleted=False).exclude(id=category_id).exists():
                        return {'success': False, 'message': 'Category with this slug already exists', 'error_code': 'DUPLICATE_SLUG'}
            
            allowed_fields = ['name', 'slug', 'description', 'status', 'sort_order', 'colors']
            for key, value in kwargs.items():
                if key in allowed_fields and hasattr(category, key):
                    setattr(category, key, value)
            
            category.save()
            
            return {
                'success': True, 
                'message': 'Category updated successfully',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'slug': category.slug,
                    'description': category.description,
                    'colors': category.colors,
                    'status': category.status,
                    'sort_order': category.sort_order,
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to update category: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def delete_category(category_id, hard_delete=False):
        try:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
            
            if category.is_deleted and not hard_delete:
                return {'success': False, 'message': 'Category is already deleted', 'error_code': 'ALREADY_DELETED'}
            
            product_count = category.products.filter(is_deleted=False).count() if hasattr(category, 'products') else 0
            if product_count > 0:
                return {
                    'success': False, 
                    'message': f'Cannot delete category. It has {product_count} active product(s). Move or delete them first.',
                    'error_code': 'HAS_PRODUCTS',
                    'product_count': product_count
                }
            
            if hard_delete:
                category.delete()
                return {'success': True, 'message': 'Category permanently deleted'}
            else:
                category.is_deleted = True
                category.deleted_at = timezone.now()
                category.save(update_fields=['is_deleted', 'deleted_at'])
                return {'success': True, 'message': 'Category deleted successfully'}
                
        except Exception as e:
            return {'success': False, 'message': f'Failed to delete category: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def restore_category(category_id):
        try:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
            
            if not category.is_deleted:
                return {'success': False, 'message': 'Category is not deleted', 'error_code': 'NOT_DELETED'}
            
            if Category.objects.filter(slug=category.slug, is_deleted=False).exists():
                category.slug = CategoryService._generate_unique_slug(category.name)
            
            if Category.objects.filter(name__iexact=category.name, is_deleted=False).exists():
                category.name = f"{category.name} (restored)"
                category.slug = CategoryService._generate_unique_slug(category.name)
            
            category.is_deleted = False
            category.deleted_at = None
            category.save()
            
            return {
                'success': True, 
                'message': 'Category restored successfully',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'slug': category.slug,
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to restore category: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def update_category_status(category_id, status):
        try:
            if status not in ['ACTIVE', 'INACTIVE']:
                return {'success': False, 'message': 'Invalid status. Must be ACTIVE or INACTIVE', 'error_code': 'VALIDATION_ERROR'}
            
            updated = Category.objects.filter(id=category_id, is_deleted=False).update(status=status)
            
            if updated == 0:
                return {'success': False, 'message': 'Category not found', 'error_code': 'NOT_FOUND'}
            
            return {'success': True, 'message': f'Category status updated to {status}'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update status: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def reorder_categories(category_orders):
        try:
            if not category_orders or not isinstance(category_orders, list):
                return {'success': False, 'message': 'Invalid category orders data', 'error_code': 'VALIDATION_ERROR'}
            
            for item in category_orders:
                if 'id' not in item or 'sort_order' not in item:
                    return {'success': False, 'message': 'Each item must have id and sort_order', 'error_code': 'VALIDATION_ERROR'}
                
                Category.objects.filter(id=item['id'], is_deleted=False).update(sort_order=item['sort_order'])
            
            return {'success': True, 'message': 'Categories reordered successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to reorder: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def get_category_stats():
        total = Category.objects.filter(is_deleted=False).count()
        active = Category.objects.filter(status='ACTIVE', is_deleted=False).count()
        inactive = Category.objects.filter(status='INACTIVE', is_deleted=False).count()
        deleted = Category.objects.filter(is_deleted=True).count()
        
        return {
            'success': True,
            'stats': {
                'total_categories': total,
                'active_categories': active,
                'inactive_categories': inactive,
                'deleted_categories': deleted,
            }
        }
    
    @staticmethod
    def get_deleted_categories(page=1, per_page=20):
        queryset = Category.objects.filter(is_deleted=True).order_by('-deleted_at')
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        categories = []
        for cat in page_obj.object_list:
            categories.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'deleted_at': cat.deleted_at.isoformat() if cat.deleted_at else None,
            })
        
        return {
            'success': True,
            'categories': categories,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_categories': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
    
    @staticmethod
    def bulk_delete(category_ids):
        try:
            if not category_ids or not isinstance(category_ids, list):
                return {'success': False, 'message': 'Invalid category IDs', 'error_code': 'VALIDATION_ERROR'}
            
            categories_with_products = []
            for cat_id in category_ids:
                try:
                    cat = Category.objects.get(id=cat_id, is_deleted=False)
                    if hasattr(cat, 'products') and cat.products.filter(is_deleted=False).exists():
                        categories_with_products.append(cat.name)
                except Category.DoesNotExist:
                    pass
            
            if categories_with_products:
                return {
                    'success': False,
                    'message': f'Cannot delete categories with products: {", ".join(categories_with_products)}',
                    'error_code': 'HAS_PRODUCTS'
                }
            
            updated = Category.objects.filter(
                id__in=category_ids, 
                is_deleted=False
            ).update(
                is_deleted=True, 
                deleted_at=timezone.now()
            )
            
            return {
                'success': True, 
                'message': f'{updated} category(ies) deleted successfully',
                'deleted_count': updated
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to delete categories: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def bulk_restore(category_ids):
        try:
            if not category_ids or not isinstance(category_ids, list):
                return {'success': False, 'message': 'Invalid category IDs', 'error_code': 'VALIDATION_ERROR'}
            
            restored = 0
            for cat_id in category_ids:
                result = CategoryService.restore_category(cat_id)
                if result['success']:
                    restored += 1
            
            return {
                'success': True, 
                'message': f'{restored} category(ies) restored successfully',
                'restored_count': restored
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to restore categories: {str(e)}', 'error_code': 'SERVER_ERROR'}