from django.db.models import Count
from main.models import User


class RoleService:
    
    ROLES = {
        'ADMIN': {
            'name': 'Admin',
            'description': 'Full system access',
            'permissions': ['all'],
            'level': 100,
        },
        'RESELLER': {
            'name': 'Reseller',
            'description': 'Can manage multiple branches',
            'permissions': ['view_reports', 'manage_branches', 'view_users'],
            'level': 80,
        },
        'CASHIER': {
            'name': 'Cashier',
            'description': 'Can create and manage orders',
            'permissions': ['create_order', 'view_orders', 'manage_orders', 'view_products'],
            'level': 50,
        },
        'USER': {
            'name': 'User',
            'description': 'Basic user access',
            'permissions': ['view_products', 'create_order'],
            'level': 10,
        },
    }
    
    @staticmethod
    def get_all_roles():
        roles = []
        for code, data in RoleService.ROLES.items():
            user_count = User.objects.filter(role=code, is_deleted=False).count()
            roles.append({
                'code': code,
                'name': data['name'],
                'description': data['description'],
                'permissions': data['permissions'],
                'level': data['level'],
                'user_count': user_count,
            })
        
        roles.sort(key=lambda x: x['level'], reverse=True)
        
        return {
            'success': True,
            'roles': roles,
            'count': len(roles)
        }
    
    @staticmethod
    def get_role(role_code):
        role_code = role_code.upper()
        
        if role_code not in RoleService.ROLES:
            return {'success': False, 'message': 'Role not found', 'error_code': 'NOT_FOUND'}
        
        data = RoleService.ROLES[role_code]
        user_count = User.objects.filter(role=role_code, is_deleted=False).count()
        
        return {
            'success': True,
            'role': {
                'code': role_code,
                'name': data['name'],
                'description': data['description'],
                'permissions': data['permissions'],
                'level': data['level'],
                'user_count': user_count,
            }
        }
    
    @staticmethod
    def get_role_permissions(role_code):
        role_code = role_code.upper()
        
        if role_code not in RoleService.ROLES:
            return {'success': False, 'message': 'Role not found', 'error_code': 'NOT_FOUND'}
        
        return {
            'success': True,
            'role': role_code,
            'permissions': RoleService.ROLES[role_code]['permissions']
        }
    
    @staticmethod
    def check_permission(role_code, permission):
        role_code = role_code.upper()
        
        if role_code not in RoleService.ROLES:
            return {'success': False, 'message': 'Role not found', 'error_code': 'NOT_FOUND'}
        
        permissions = RoleService.ROLES[role_code]['permissions']
        has_permission = 'all' in permissions or permission in permissions
        
        return {
            'success': True,
            'role': role_code,
            'permission': permission,
            'has_permission': has_permission
        }
    
    @staticmethod
    def get_role_stats():
        stats = User.objects.filter(is_deleted=False).values('role').annotate(count=Count('id'))
        
        role_counts = {role: 0 for role in RoleService.ROLES.keys()}
        for stat in stats:
            if stat['role'] in role_counts:
                role_counts[stat['role']] = stat['count']
        
        return {
            'success': True,
            'stats': role_counts,
            'total': sum(role_counts.values())
        }
    
    @staticmethod
    def is_valid_role(role_code):
        return role_code.upper() in RoleService.ROLES
    
    @staticmethod
    def get_role_level(role_code):
        role_code = role_code.upper()
        if role_code not in RoleService.ROLES:
            return 0
        return RoleService.ROLES[role_code]['level']
    
    @staticmethod
    def can_manage_role(manager_role, target_role):
        manager_level = RoleService.get_role_level(manager_role)
        target_level = RoleService.get_role_level(target_role)
        return manager_level > target_level
    
    @staticmethod
    def get_manageable_roles(role_code):
        current_level = RoleService.get_role_level(role_code)
        
        manageable = []
        for code, data in RoleService.ROLES.items():
            if data['level'] < current_level:
                manageable.append({
                    'code': code,
                    'name': data['name'],
                    'level': data['level'],
                })
        
        manageable.sort(key=lambda x: x['level'], reverse=True)
        
        return {
            'success': True,
            'current_role': role_code.upper(),
            'manageable_roles': manageable
        }