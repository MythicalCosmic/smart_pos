import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction

from main.models import User, Session
from admins.services.base_service import ServiceResponse, CacheService


USER_CACHE_TTL = 600
RATE_LIMIT_TTL = 900
MAX_LOGIN_ATTEMPTS = 5


class AdminAuthService:
    JWT_SECRET = getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRY_DAYS = 365

    @classmethod
    def login(cls, email: str, password: str,
              ip_address: str = "", user_agent: str = "") -> tuple:

        # rate limiting
        rate_key = f"admin_login_attempts:{ip_address}"
        attempts = CacheService.get(rate_key) or 0
        if attempts >= MAX_LOGIN_ATTEMPTS:
            return ServiceResponse.error(
                "Too many login attempts. Try again in 15 minutes", status=429
            )

        # find user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            CacheService.set(rate_key, attempts + 1, RATE_LIMIT_TTL)
            return ServiceResponse.error("Invalid credentials", status=401)

        # check status
        if user.status == User.UserStatus.SUSPENDED:
            return ServiceResponse.error("Account suspended", status=403)

        # check password
        if not check_password(password, user.password):
            CacheService.set(rate_key, attempts + 1, RATE_LIMIT_TTL)
            return ServiceResponse.error("Invalid credentials", status=401)

        # admin only
        if user.role != User.RoleChoices.ADMIN:
            return ServiceResponse.error(
                "Access denied. Admin role required", status=403
            )

        # success -- clear rate limit
        CacheService.delete(rate_key)

        # generate token
        token = cls._generate_token(user)

        # clear old sessions and create new one
        Session.objects.filter(user_id=user).delete()
        Session.objects.create(
            user_id=user,
            ip_address=ip_address[:20] if ip_address else "",
            user_agent=user_agent[:30] if user_agent else "Unknown",
            payload=token[:20],
        )

        # update last login
        User.objects.filter(id=user.id).update(
            last_login_at=datetime.now().date(),
            last_login_api=ip_address[:20] if ip_address else None,
        )

        return ServiceResponse.success(
            message="Logged in successfully",
            data={
                "token": token,
                "user": cls._serialize_user(user),
            },
        )

    @classmethod
    def logout(cls, token: str) -> tuple:
        user = cls._verify_token(token)
        if not user:
            return ServiceResponse.unauthorized("Invalid or expired token")

        Session.objects.filter(user_id=user, payload=token[:20]).delete()
        CacheService.delete(f"admin_user:{user.pk}")

        return ServiceResponse.success("Logged out successfully")

    @classmethod
    def logout_all(cls, token: str) -> tuple:
        user = cls._verify_token(token)
        if not user:
            return ServiceResponse.unauthorized("Invalid or expired token")

        Session.objects.filter(user_id=user).delete()
        CacheService.delete(f"admin_user:{user.pk}")

        return ServiceResponse.success("Logged out from all devices")

    @classmethod
    def me(cls, token: str) -> tuple:
        user = cls._verify_token(token)
        if not user:
            return ServiceResponse.unauthorized("Invalid or expired token")

        cached = CacheService.get(f"admin_user:{user.pk}")
        if cached:
            return ServiceResponse.success("Profile retrieved", data=cached)

        user_data = cls._serialize_user(user)
        CacheService.set(f"admin_user:{user.pk}", user_data, USER_CACHE_TTL)

        return ServiceResponse.success("Profile retrieved", data=user_data)

    @classmethod
    @transaction.atomic
    def change_password(cls, token: str, current_password: str,
                        new_password: str) -> tuple:
        user = cls._verify_token(token)
        if not user:
            return ServiceResponse.unauthorized("Invalid or expired token")

        if not check_password(current_password, user.password):
            return ServiceResponse.error("Current password is incorrect")

        user.password = make_password(new_password)
        user.save(update_fields=["password"])

        # kill all sessions
        Session.objects.filter(user_id=user).delete()
        CacheService.delete(f"admin_user:{user.pk}")

        # create fresh session so user stays logged in
        new_token = cls._generate_token(user)
        Session.objects.create(
            user_id=user,
            ip_address="",
            user_agent="",
            payload=new_token[:20],
        )

        return ServiceResponse.success(
            "Password changed successfully",
            data={"token": new_token},
        )

    @classmethod
    def get_user_from_token(cls, token):
        return cls._verify_token(token)

    @classmethod
    def _generate_token(cls, user):
        payload = {
            'user_id': user.id,
            'email': user.email,
            'role': user.role,
            'exp': datetime.now(timezone.utc) + timedelta(days=cls.JWT_EXPIRY_DAYS),
            'iat': datetime.now(timezone.utc),
            'type': 'admin',
        }
        return jwt.encode(payload, cls.JWT_SECRET, algorithm=cls.JWT_ALGORITHM)

    @classmethod
    def _verify_token(cls, token):
        try:
            payload = jwt.decode(
                token, cls.JWT_SECRET, algorithms=[cls.JWT_ALGORITHM]
            )

            if payload.get('type') != 'admin':
                return None

            user = User.objects.get(id=payload['user_id'])

            if user.role != User.RoleChoices.ADMIN:
                return None

            if user.status != User.UserStatus.ACTIVE:
                return None

            if not Session.objects.filter(
                user_id=user, payload=token[:20]
            ).exists():
                return None

            return user

        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError,
                User.DoesNotExist):
            return None

    @classmethod
    def _serialize_user(cls, user) -> dict:
        return {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "status": user.status,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
        }
