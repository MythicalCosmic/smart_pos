from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.cache import cache
from main.models import Product, Category


class ProductService:
    
    @staticmethod
    def get_all_products(page=1, per_page=20, search=None, category_id=None, order_by='-created_at'):
        
        queryset = Product.objects.select_related('category').all()
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        queryset = queryset.order_by(order_by)
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        products = []
        for product in page_obj.object_list:
            products.append({
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'price': str(product.price),
                'color': product.colors,
                'category': {
                    'id': product.category.id,
                    'name': product.category.name,
                    'slug': product.category.slug,
                    'color': product.category.colors,
                },
                'created_at': product.created_at.isoformat(),
                'updated_at': product.updated_at.isoformat()
            })
        
        result = {
            'products': products,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_products': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
        
        return result
    
    @staticmethod
    def get_products_by_category(category_id):

        try:
            category = Category.objects.get(id=category_id, status='ACTIVE')
            products = Product.objects.filter(category=category).values(
                'id', 'name', 'description', 'price'
            )
            
            result = {
                'success': True,
                'category': {
                    'id': category.id,
                    'name': category.name
                },
                'products': list(products)
            }
            
            return result
        except Category.DoesNotExist:
            return {'success': False, 'message': 'Category not found'}
    
    @staticmethod
    def get_product_by_id(product_id):
        
        try:
            product = Product.objects.select_related('category').get(id=product_id)
            result = {
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'description': product.description,
                    'price': str(product.price),
                    'category': {
                        'id': product.category.id,
                        'name': product.category.name,
                        'slug': product.category.slug
                    },
                    'created_at': product.created_at.isoformat(),
                    'updated_at': product.updated_at.isoformat()
                }
            }
            return result
        except Product.DoesNotExist:
            return {'success': False, 'message': 'Product not found'}
    
    @staticmethod
    def create_product(name, description, price, category_id):
        try:
            if not Category.objects.filter(id=category_id).exists():
                return {'success': False, 'message': 'Category not found'}
            
            if Product.objects.filter(name=name, category_id=category_id).exists():
                return {'success': False, 'message': 'Product with this name already exists in this category'}
            
            product = Product.objects.create(
                name=name,
                description=description,
                price=price,
                category_id=category_id
            )
            
            return {
                'success': True,
                'product': product,
                'message': 'Product created successfully'
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to create product: {str(e)}'}
    
    @staticmethod
    def update_product(product_id, **kwargs):
        try:
            product = Product.objects.get(id=product_id)
            
            if 'category_id' in kwargs:
                if not Category.objects.filter(id=kwargs['category_id']).exists():
                    return {'success': False, 'message': 'Category not found'}
            
            if 'name' in kwargs and kwargs['name'] != product.name:
                category_id = kwargs.get('category_id', product.category_id)
                if Product.objects.filter(name=kwargs['name'], category_id=category_id).exclude(id=product_id).exists():
                    return {'success': False, 'message': 'Product with this name already exists in this category'}
            
            for key, value in kwargs.items():
                if hasattr(product, key):
                    setattr(product, key, value)
            
            product.save()
            
            ProductService._clear_cache()
            
            return {
                'success': True,
                'product': product,
                'message': 'Product updated successfully'
            }
        except Product.DoesNotExist:
            return {'success': False, 'message': 'Product not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update product: {str(e)}'}
    
    @staticmethod
    def delete_product(product_id):
        try:
            product = Product.objects.get(id=product_id)
            product.delete()
            
            ProductService._clear_cache()
            
            return {'success': True, 'message': 'Product deleted successfully'}
        except Product.DoesNotExist:
            return {'success': False, 'message': 'Product not found'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to delete product: {str(e)}'}
    
    @staticmethod
    def get_product_stats():
        total = Product.objects.count()
        by_category = Product.objects.values('category__name').annotate(count=Count('id'))
        
        result = {
            'success': True,
            'stats': {
                'total_products': total,
                'by_category': list(by_category)
            }
        }
        
        return result
    
    @staticmethod
    def _clear_cache():
        try:
            cache.delete_pattern('products:*')
            cache.delete_pattern('product:*')
        except AttributeError:
            cache.clear()