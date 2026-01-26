import jwt
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from ..models import User, Session, Order


class AuthService:
    JWT_SECRET = getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRY_DAYS = 365
    
    SHIFT_ROLES = [User.RoleChoices.CASHIER]
    
    @classmethod
    @transaction.atomic
    def register(cls, first_name, last_name, email, password, ip_address, user_agent='Chrome'):
        try:
            validate_email(email)
            
            if User.objects.filter(email=email).exists():
                return {'success': False, 'user': None, 'token': None, 'message': 'Email already registered'}
            
            if len(password) < 4:
                return {'success': False, 'user': None, 'token': None, 'message': 'Password must be at least 4 characters'}
            
            user = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=make_password(password),  
                role=User.RoleChoices.ADMIN,  
                status=User.UserStatus.ACTIVE
            )
            
            token = cls._generate_token(user)
            
            if ip_address:
                Session.objects.create(
                    user_id=user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    payload=token[:20] 
                )
                
                User.objects.filter(id=user.id).update(
                    last_login_at=datetime.now().date(),
                    last_login_api=ip_address
                )
            
            return {'success': True, 'user': user, 'token': token, 'message': 'User registered successfully'}
            
        except ValidationError as e:
            return {'success': False, 'user': None, 'token': None, 'message': f'Invalid email: {str(e)}'}
        except Exception as e:
            return {'success': False, 'user': None, 'token': None, 'message': f'Registration failed: {str(e)}'}
    
    @classmethod
    @transaction.atomic
    def login(cls, email, password, ip_address, user_agent='Chrome'):
        try:
            user = User.objects.select_related().only(
                'id', 'email', 'password', 'status', 'role', 'first_name', 'last_name'
            ).get(email=email)
            
            if user.status == User.UserStatus.SUSPENDED:
                return {'success': False, 'token': None, 'user': None, 'message': 'Account suspended'}
        
            if not check_password(password, user.password):
                return {'success': False, 'token': None, 'user': None, 'message': 'Invalid credentials'}
            
            Session.objects.filter(user_id=user).delete()
            
            token = cls._generate_token(user)
            
            Session.objects.create(
                user_id=user,
                ip_address=ip_address,
                user_agent=user_agent,
                payload=token[:20]
            )
            
            User.objects.filter(id=user.id).update(
                last_login_at=datetime.now().date(),
                last_login_api=ip_address
            )
            
            if user.role in cls.SHIFT_ROLES:
                cls._notify_shift_start(user)
            
            return {'success': True, 'token': token, 'user': user, 'message': 'Login successful'}
            
        except User.DoesNotExist:
            return {'success': False, 'token': None, 'user': None, 'message': 'Invalid credentials'}
        except Exception as e:
            return {'success': False, 'token': None, 'user': None, 'message': f'Login failed: {str(e)}'}
    
    @classmethod
    def logout(cls, token, force=False):
        try:
            user = cls._verify_token(token)
            if not user:
                return {'success': False, 'message': 'Invalid token'}
            
            if not force:
                open_orders = Order.objects.filter(
                    cashier_id=user.id,
                    status__in=['PREPARING'],
                    is_paid=False
                )
                
                if open_orders.exists():
                    order_ids = list(open_orders.values_list('display_id', flat=True)[:5])
                    return {
                        'success': False,
                        'message': f'Cannot logout. You have {open_orders.count()} unpaid open order(s): #{", #".join(map(str, order_ids))}',
                        'error_code': 'OPEN_ORDERS',
                        'open_orders_count': open_orders.count(),
                        'open_order_ids': list(open_orders.values_list('id', flat=True))
                    }
            
            if user.role in cls.SHIFT_ROLES:
                cls._notify_shift_end(user)
            
            Session.objects.filter(user_id=user).delete()
            return {'success': True, 'message': 'Logged out successfully'}
            
        except Exception as e:
            return {'success': False, 'message': f'Logout failed: {str(e)}'}
    
    @classmethod
    @transaction.atomic
    def refresh_token(cls, old_token, ip_address, user_agent='Chrome'):
        try:
            user = cls._verify_token(old_token)
            if not user:
                return {'success': False, 'token': None, 'message': 'Invalid token'}
            
            if user.status != User.UserStatus.ACTIVE:
                return {'success': False, 'token': None, 'message': 'Account not active'}
            
            Session.objects.filter(user_id=user).delete()
            
            new_token = cls._generate_token(user)
            
            Session.objects.create(
                user_id=user,
                ip_address=ip_address,
                user_agent=user_agent,
                payload=new_token[:20]
            )
            
            return {'success': True, 'token': new_token, 'message': 'Token refreshed'}
            
        except Exception as e:
            return {'success': False, 'token': None, 'message': f'Refresh failed: {str(e)}'}
    
    @classmethod
    def get_user_from_token(cls, token):
        return cls._verify_token(token)
    
    @classmethod
    def _generate_token(cls, user):
        payload = {
            'user_id': user.id,
            'email': user.email,
            'role': user.role,
            'exp': datetime.utcnow() + timedelta(days=cls.JWT_EXPIRY_DAYS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, cls.JWT_SECRET, algorithm=cls.JWT_ALGORITHM)
    
    @classmethod
    def _verify_token(cls, token):
        try:
            payload = jwt.decode(token, cls.JWT_SECRET, algorithms=[cls.JWT_ALGORITHM])
            
            user = User.objects.only('id', 'email', 'role', 'status', 'first_name', 'last_name').get(id=payload['user_id'])
            
            if not Session.objects.filter(user_id=user, payload=token[:20]).exists():
                return None
            
            return user
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist):
            return None
        except Exception:
            return None
    
    @classmethod
    def is_admin(cls, user):
        return user.role in [User.RoleChoices.ADMIN, User.RoleChoices.RESELLER]

    @classmethod
    def _notify_shift_start(cls, user):
        from threading import Thread
        
        def send():
            try:
                from main.services.shift_notification_service import get_shift_notification_service  
                service = get_shift_notification_service()
                user_name = f"{user.first_name} {user.last_name}".strip() or user.email
                service.on_cashier_login(user.id, user_name)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Shift notification error: {e}")
        
        Thread(target=send, daemon=True).start()

    @classmethod
    def _notify_shift_end(cls, user):
        from threading import Thread
        
        def send():
            try:
                from main.services.shift_notification_service import get_shift_notification_service
                service = get_shift_notification_service()
                service.on_cashier_logout(user.id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Shift notification error: {e}")
        
        Thread(target=send, daemon=True).start()