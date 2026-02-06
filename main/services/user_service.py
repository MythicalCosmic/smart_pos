from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.utils.text import slugify
from main.models import User, Session, Order
import re


class UserService:
    
    VALID_ROLES = ['ADMIN', 'CASHIER', 'USER', 'RESELLER']
    VALID_STATUSES = ['ACTIVE', 'SUSPENDED']
    EMAIL_DOMAIN = 'smart.pos'
    
    @staticmethod
    def _get_base_queryset(include_deleted=False):
        if include_deleted:
            return User.objects.all()
        return User.objects.filter(is_deleted=False)
    
    @staticmethod
    def _generate_unique_email(first_name, last_name, exclude_id=None):
        first_slug = slugify(first_name, allow_unicode=False).replace('-', '')
        last_slug = slugify(last_name, allow_unicode=False).replace('-', '')
        
        if not first_slug:
            first_slug = 'user'
        if not last_slug:
            last_slug = 'pos'
        
        base_email = f"{first_slug}.{last_slug}@{UserService.EMAIL_DOMAIN}"
        email = base_email
        counter = 1
        
        while True:
            qs = User.objects.filter(email__iexact=email)
            if exclude_id:
                qs = qs.exclude(id=exclude_id)
            if not qs.exists():
                return email
            email = f"{first_slug}.{last_slug}{counter}@{UserService.EMAIL_DOMAIN}"
            counter += 1
    
    @staticmethod
    def _serialize_user(user, include_sensitive=False):
        data = {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': f"{user.first_name} {user.last_name}".strip(),
            'email': user.email,
            'username': user.email.split('@')[0] if user.email else None,
            'role': user.role,
            'status': user.status,
            'is_deleted': user.is_deleted,
            'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
            'last_login_api': user.last_login_api,
        }
        
        if include_sensitive:
            data['api_enabled'] = getattr(user, 'api_enabled', False)
        
        return data
    
    @staticmethod
    def get_all_users(page=1, per_page=20, search=None, role=None, status=None, 
                      order_by='-id', include_deleted=False):
        queryset = UserService._get_base_queryset(include_deleted)
        
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | 
                Q(first_name__icontains=search) | 
                Q(last_name__icontains=search)
            )
        
        if role:
            queryset = queryset.filter(role=role)
        
        if status:
            queryset = queryset.filter(status=status)
        
        queryset = queryset.order_by(order_by)
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        users = [UserService._serialize_user(user) for user in page_obj.object_list]
        
        return {
            'success': True,
            'users': users,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_users': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
    
    @staticmethod
    def get_user_by_id(user_id, include_deleted=False):
        try:
            queryset = UserService._get_base_queryset(include_deleted)
            user = queryset.get(id=user_id)
            
            return {
                'success': True,
                'user': UserService._serialize_user(user, include_sensitive=True)
            }
        except User.DoesNotExist:
            return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
    
    @staticmethod
    def get_user_by_email(email, include_deleted=False):
        try:
            queryset = UserService._get_base_queryset(include_deleted)
            user = queryset.get(email__iexact=email)
            
            return {
                'success': True,
                'user': UserService._serialize_user(user)
            }
        except User.DoesNotExist:
            return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
    
    @staticmethod
    def get_user_by_username(username, include_deleted=False):
        email = f"{username}@{UserService.EMAIL_DOMAIN}"
        return UserService.get_user_by_email(email, include_deleted)
    
    @staticmethod
    def create_user(first_name, last_name, password, role='USER', status='ACTIVE', email=None):
        try:
            if not first_name or not first_name.strip():
                return {'success': False, 'message': 'First name is required', 'error_code': 'VALIDATION_ERROR'}
            
            if not last_name or not last_name.strip():
                return {'success': False, 'message': 'Last name is required', 'error_code': 'VALIDATION_ERROR'}
            
            if not password or len(str(password)) < 4:
                return {'success': False, 'message': 'Password must be at least 4 characters', 'error_code': 'VALIDATION_ERROR'}
            
            if role not in UserService.VALID_ROLES:
                return {'success': False, 'message': f'Invalid role. Must be one of: {", ".join(UserService.VALID_ROLES)}', 'error_code': 'VALIDATION_ERROR'}
            
            if status not in UserService.VALID_STATUSES:
                return {'success': False, 'message': f'Invalid status. Must be one of: {", ".join(UserService.VALID_STATUSES)}', 'error_code': 'VALIDATION_ERROR'}
            
            first_name = first_name.strip()
            last_name = last_name.strip()
            
            if email:
                email = email.strip().lower()
                if User.objects.filter(email__iexact=email, is_deleted=False).exists():
                    return {'success': False, 'message': 'Email already exists', 'error_code': 'DUPLICATE_EMAIL'}
            else:
                email = UserService._generate_unique_email(first_name, last_name)
            
            user = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=make_password(str(password)),
                role=role,
                status=status,
            )
            
            return {
                'success': True, 
                'message': 'User created successfully',
                'user': UserService._serialize_user(user)
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to create user: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def update_user(user_id, **kwargs):
        try:
            try:
                user = User.objects.get(id=user_id, is_deleted=False)
            except User.DoesNotExist:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            regenerate_email = False
            new_first = kwargs.get('first_name', user.first_name)
            new_last = kwargs.get('last_name', user.last_name)
            
            if 'first_name' in kwargs or 'last_name' in kwargs:
                if new_first != user.first_name or new_last != user.last_name:
                    if user.email.endswith(f'@{UserService.EMAIL_DOMAIN}'):
                        regenerate_email = True
            
            if 'email' in kwargs and kwargs['email']:
                new_email = kwargs['email'].strip().lower()
                if new_email != user.email.lower():
                    if User.objects.filter(email__iexact=new_email, is_deleted=False).exclude(id=user_id).exists():
                        return {'success': False, 'message': 'Email already exists', 'error_code': 'DUPLICATE_EMAIL'}
                    kwargs['email'] = new_email
                    regenerate_email = False
            
            if 'password' in kwargs and kwargs['password']:
                if len(kwargs['password']) < 4:
                    return {'success': False, 'message': 'Password must be at least 4 characters', 'error_code': 'VALIDATION_ERROR'}
                kwargs['password'] = make_password(kwargs['password'])
            elif 'password' in kwargs:
                del kwargs['password']
            
            if 'role' in kwargs and kwargs['role'] not in UserService.VALID_ROLES:
                return {'success': False, 'message': f'Invalid role. Must be one of: {", ".join(UserService.VALID_ROLES)}', 'error_code': 'VALIDATION_ERROR'}
            
            if 'status' in kwargs and kwargs['status'] not in UserService.VALID_STATUSES:
                return {'success': False, 'message': f'Invalid status. Must be one of: {", ".join(UserService.VALID_STATUSES)}', 'error_code': 'VALIDATION_ERROR'}
            
            allowed_fields = ['first_name', 'last_name', 'email', 'password', 'role', 'status']
            for key, value in kwargs.items():
                if key in allowed_fields and hasattr(user, key):
                    if key in ['first_name', 'last_name'] and value:
                        value = value.strip()
                    setattr(user, key, value)
            
            if regenerate_email:
                user.email = UserService._generate_unique_email(
                    user.first_name, 
                    user.last_name, 
                    exclude_id=user_id
                )
            
            user.save()
            
            return {
                'success': True, 
                'message': 'User updated successfully',
                'user': UserService._serialize_user(user)
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to update user: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def delete_user(user_id, hard_delete=False):
        try:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            if user.is_deleted and not hard_delete:
                return {'success': False, 'message': 'User is already deleted', 'error_code': 'ALREADY_DELETED'}
            
            open_orders = Order.objects.filter(
                Q(user_id=user_id) | Q(cashier_id=user_id),
                status__in=['PREPARING'],
                is_paid=False
            ).count()
            
            if open_orders > 0:
                return {
                    'success': False,
                    'message': f'Cannot delete user. They have {open_orders} open order(s)',
                    'error_code': 'HAS_OPEN_ORDERS',
                    'open_orders_count': open_orders
                }
            
            Session.objects.filter(user_id=user).delete()
            
            if hard_delete:
                user.delete()
                return {'success': True, 'message': 'User permanently deleted'}
            else:
                user.is_deleted = True
                user.deleted_at = timezone.now()
                user.status = 'SUSPENDED'
                user.save(update_fields=['is_deleted', 'deleted_at', 'status'])
                return {'success': True, 'message': 'User deleted successfully'}
                
        except Exception as e:
            return {'success': False, 'message': f'Failed to delete user: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def restore_user(user_id):
        try:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            if not user.is_deleted:
                return {'success': False, 'message': 'User is not deleted', 'error_code': 'NOT_DELETED'}
            
            if User.objects.filter(email__iexact=user.email, is_deleted=False).exists():
                user.email = UserService._generate_unique_email(user.first_name, user.last_name)
            
            user.is_deleted = False
            user.deleted_at = None
            user.status = 'ACTIVE'
            user.save()
            
            return {
                'success': True,
                'message': 'User restored successfully',
                'user': UserService._serialize_user(user)
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to restore user: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def update_user_status(user_id, status):
        try:
            if status not in UserService.VALID_STATUSES:
                return {'success': False, 'message': f'Invalid status. Must be one of: {", ".join(UserService.VALID_STATUSES)}', 'error_code': 'VALIDATION_ERROR'}
            
            updated = User.objects.filter(id=user_id, is_deleted=False).update(status=status)
            
            if updated == 0:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            if status == 'SUSPENDED':
                Session.objects.filter(user_id_id=user_id).delete()
            
            return {'success': True, 'message': f'User status updated to {status}'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update status: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def update_user_role(user_id, role):
        try:
            if role not in UserService.VALID_ROLES:
                return {'success': False, 'message': f'Invalid role. Must be one of: {", ".join(UserService.VALID_ROLES)}', 'error_code': 'VALIDATION_ERROR'}
            
            updated = User.objects.filter(id=user_id, is_deleted=False).update(role=role)
            
            if updated == 0:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            return {'success': True, 'message': f'User role updated to {role}'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to update role: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def toggle_api_access(user_id):
        try:
            try:
                user = User.objects.get(id=user_id, is_deleted=False)
            except User.DoesNotExist:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            new_status = not getattr(user, 'api_enabled', False)
            User.objects.filter(id=user_id).update(api_enabled=new_status)
            
            return {
                'success': True, 
                'api_enabled': new_status, 
                'message': f'API access {"enabled" if new_status else "disabled"}'
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to toggle API access: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def change_password(user_id, current_password, new_password):
        try:
            try:
                user = User.objects.get(id=user_id, is_deleted=False)
            except User.DoesNotExist:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            if not check_password(current_password, user.password):
                return {'success': False, 'message': 'Current password is incorrect', 'error_code': 'INVALID_PASSWORD'}
            
            if len(new_password) < 4:
                return {'success': False, 'message': 'New password must be at least 4 characters', 'error_code': 'VALIDATION_ERROR'}
            
            user.password = make_password(new_password)
            user.save(update_fields=['password'])
            
            Session.objects.filter(user_id=user).delete()
            
            return {'success': True, 'message': 'Password changed successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to change password: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def reset_password(user_id, new_password):
        try:
            if len(new_password) < 4:
                return {'success': False, 'message': 'Password must be at least 4 characters', 'error_code': 'VALIDATION_ERROR'}
            
            updated = User.objects.filter(id=user_id, is_deleted=False).update(
                password=make_password(new_password)
            )
            
            if updated == 0:
                return {'success': False, 'message': 'User not found', 'error_code': 'NOT_FOUND'}
            
            Session.objects.filter(user_id_id=user_id).delete()
            
            return {'success': True, 'message': 'Password reset successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to reset password: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def get_user_stats():
        base_qs = User.objects.filter(is_deleted=False)
        
        total_users = base_qs.count()
        active_users = base_qs.filter(status='ACTIVE').count()
        suspended_users = base_qs.filter(status='SUSPENDED').count()
        admin_users = base_qs.filter(role='ADMIN').count()
        cashier_users = base_qs.filter(role='CASHIER').count()
        reseller_users = base_qs.filter(role='RESELLER').count()
        regular_users = base_qs.filter(role='USER').count()
        deleted_users = User.objects.filter(is_deleted=True).count()
        
        return {
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_users': active_users,
                'suspended_users': suspended_users,
                'deleted_users': deleted_users,
                'by_role': {
                    'admin': admin_users,
                    'cashier': cashier_users,
                    'reseller': reseller_users,
                    'user': regular_users,
                }
            }
        }
    
    @staticmethod
    def get_deleted_users(page=1, per_page=20):
        queryset = User.objects.filter(is_deleted=True).order_by('-deleted_at')
        
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        users = []
        for user in page_obj.object_list:
            users.append({
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': f"{user.first_name} {user.last_name}".strip(),
                'email': user.email,
                'username': user.email.split('@')[0] if user.email else None,
                'role': user.role,
                'deleted_at': user.deleted_at.isoformat() if user.deleted_at else None,
            })
        
        return {
            'success': True,
            'users': users,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_users': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }
    
    @staticmethod
    def get_users_by_role(role, active_only=True):
        if role not in UserService.VALID_ROLES:
            return {'success': False, 'message': f'Invalid role', 'error_code': 'VALIDATION_ERROR'}
        
        queryset = User.objects.filter(role=role, is_deleted=False)
        
        if active_only:
            queryset = queryset.filter(status='ACTIVE')
        
        users = [UserService._serialize_user(user) for user in queryset.order_by('first_name', 'last_name')]
        
        return {
            'success': True,
            'users': users,
            'count': len(users)
        }
    
    @staticmethod
    def get_cashiers(active_only=True):
        return UserService.get_users_by_role('CASHIER', active_only)
    
    @staticmethod
    def get_admins(active_only=True):
        return UserService.get_users_by_role('ADMIN', active_only)
    
    @staticmethod
    def bulk_update_status(user_ids, status):
        try:
            if not user_ids or not isinstance(user_ids, list):
                return {'success': False, 'message': 'Invalid user IDs', 'error_code': 'VALIDATION_ERROR'}
            
            if status not in UserService.VALID_STATUSES:
                return {'success': False, 'message': f'Invalid status', 'error_code': 'VALIDATION_ERROR'}
            
            updated = User.objects.filter(id__in=user_ids, is_deleted=False).update(status=status)
            
            if status == 'SUSPENDED':
                Session.objects.filter(user_id_id__in=user_ids).delete()
            
            return {
                'success': True,
                'message': f'{updated} user(s) updated to {status}',
                'updated_count': updated
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to update users: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def bulk_delete(user_ids):
        try:
            if not user_ids or not isinstance(user_ids, list):
                return {'success': False, 'message': 'Invalid user IDs', 'error_code': 'VALIDATION_ERROR'}
            
            users_with_orders = []
            for user_id in user_ids:
                open_orders = Order.objects.filter(
                    Q(user_id=user_id) | Q(cashier_id=user_id),
                    status__in=['PREPARING'],
                    is_paid=False
                ).exists()
                if open_orders:
                    try:
                        user = User.objects.get(id=user_id)
                        users_with_orders.append(f"{user.first_name} {user.last_name}")
                    except User.DoesNotExist:
                        pass
            
            if users_with_orders:
                return {
                    'success': False,
                    'message': f'Cannot delete users with open orders: {", ".join(users_with_orders)}',
                    'error_code': 'HAS_OPEN_ORDERS'
                }
            
            Session.objects.filter(user_id_id__in=user_ids).delete()
            
            updated = User.objects.filter(id__in=user_ids, is_deleted=False).update(
                is_deleted=True,
                deleted_at=timezone.now(),
                status='SUSPENDED'
            )
            
            return {
                'success': True,
                'message': f'{updated} user(s) deleted successfully',
                'deleted_count': updated
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to delete users: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def bulk_restore(user_ids):
        try:
            if not user_ids or not isinstance(user_ids, list):
                return {'success': False, 'message': 'Invalid user IDs', 'error_code': 'VALIDATION_ERROR'}
            
            restored = 0
            errors = []
            
            for user_id in user_ids:
                result = UserService.restore_user(user_id)
                if result['success']:
                    restored += 1
                else:
                    errors.append(f"User {user_id}: {result['message']}")
            
            return {
                'success': True,
                'message': f'{restored} user(s) restored successfully',
                'restored_count': restored,
                'errors': errors if errors else None
            }
        except Exception as e:
            return {'success': False, 'message': f'Failed to restore users: {str(e)}', 'error_code': 'SERVER_ERROR'}
    
    @staticmethod
    def search_users(query, limit=10, role=None, active_only=True):
        if not query or len(query) < 2:
            return {'success': True, 'users': []}
        
        queryset = User.objects.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query),
            is_deleted=False
        )
        
        if role:
            queryset = queryset.filter(role=role)
        
        if active_only:
            queryset = queryset.filter(status='ACTIVE')
        
        users = [
            {
                'id': u.id,
                'full_name': f"{u.first_name} {u.last_name}".strip(),
                'email': u.email,
                'username': u.email.split('@')[0] if u.email else None,
                'role': u.role,
            }
            for u in queryset[:limit]
        ]
        
        return {'success': True, 'users': users}
    
    @staticmethod
    def check_username_available(username):
        email = f"{username}@{UserService.EMAIL_DOMAIN}"
        exists = User.objects.filter(email__iexact=email, is_deleted=False).exists()
        return {
            'success': True,
            'username': username,
            'available': not exists
        }
    
    @staticmethod
    def preview_username(first_name, last_name):
        if not first_name or not last_name:
            return {'success': False, 'message': 'First and last name required', 'error_code': 'VALIDATION_ERROR'}
        
        email = UserService._generate_unique_email(first_name, last_name)
        username = email.split('@')[0]
        
        return {
            'success': True,
            'username': username,
            'email': email
        }