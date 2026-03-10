from django.db import transaction
from django.utils import timezone

from main.models import User, Session, PasswordReset
from admins.services.base_service import ServiceResponse, CacheService
from admins.services.role_permission_service import RolePermissionService


SESSION_TTL = 72 * 3600
USER_CACHE_TTL = 600
PERMISSIONS_CACHE_TTL = 300
RATE_LIMIT_TTL = 900
MAX_LOGIN_ATTEMPTS = 5


class AuthService:

    @classmethod
    def login(cls, email: str, password: str,
              ip_address: str = "", user_agent: str = "", device: str = "") -> tuple:

        #rate limiting -- block brute force
        rate_key = f"login_attempts:{ip_address}"
        attempts = CacheService.get(rate_key) or 0
        if attempts >= MAX_LOGIN_ATTEMPTS:
            return ServiceResponse.error(
                "Too many login attempts. Try again in 15 minutes", status=429
            )

        #find user and verify password
        user = User.objects.filter(email=email, is_active=True).first()
        if not user or not user.check_password(password):
            CacheService.set(rate_key, attempts + 1, RATE_LIMIT_TTL)
            return ServiceResponse.error("Invalid credentials", status=401)

        #success -- clear rate limit
        CacheService.delete(rate_key)

        #update last login
        user.last_login_at = timezone.now()
        user.last_login_ip = ip_address
        user.save(update_fields=["last_login_at", "last_login_ip"])

        #create session
        session = Session.create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device=device,
        )

        cls._cache_user(user)
        cls._cache_permissions(user)

        return ServiceResponse.success(
            message="Logged in successfully",
            data={
                "session_key": session.key,
                "user": cls._serialize_user(user),
                "permissions": list(user.get_permissions()),
            },
        )

    @classmethod
    def logout(cls, session_key: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user_id = session.user_id
        session.invalidate()

        CacheService.delete(f"user:{user_id}")
        CacheService.delete(f"permissions:{user_id}")
        CacheService.delete(f"session:{session_key}")

        return ServiceResponse.success("Logged out successfully")

    @classmethod
    def logout_all(cls, session_key: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user
        Session.invalidate_all(user)

        CacheService.delete(f"user:{user.pk}")
        CacheService.delete(f"permissions:{user.pk}")

        return ServiceResponse.success("Logged out from all devices")

    @classmethod
    def me(cls, session_key: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user

        cached = CacheService.get(f"user:{user.pk}")
        if cached:
            return ServiceResponse.success("Profile retrieved", data=cached)

        user_data = cls._serialize_user(user)
        user_data["permissions"] = list(user.get_permissions())
        user_data["roles"] = list(user.get_roles())

        CacheService.set(f"user:{user.pk}", user_data, USER_CACHE_TTL)

        return ServiceResponse.success("Profile retrieved", data=user_data)

    @classmethod
    @transaction.atomic
    def change_password(cls, session_key: str, current_password: str, new_password: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user

        if not user.check_password(current_password):
            return ServiceResponse.error("Current password is incorrect")

        user.set_password(new_password)
        user.save(update_fields=["password"])

        #kill all other sessions
        Session.objects.filter(
            user=user, is_active=True
        ).exclude(key=session_key).update(is_active=False)

        return ServiceResponse.success("Password changed successfully")

    @classmethod
    def request_password_reset(cls, email: str) -> tuple:
        user = User.objects.filter(email=email, is_active=True).first()

        if user:
            reset = PasswordReset.create_token(user)
            #TODO: send email with reset.token

        #always success to prevent email enumeration
        return ServiceResponse.success(
            "If the email exists, a reset link has been sent"
        )

    @classmethod
    @transaction.atomic
    def reset_password(cls, token: str, new_password: str) -> tuple:
        reset = PasswordReset.validate_token(token)
        if not reset:
            return ServiceResponse.error("Invalid or expired reset token")

        user = reset.user

        user.set_password(new_password)
        user.save(update_fields=["password"])

        reset.consume()
        Session.invalidate_all(user)
        CacheService.delete(f"user:{user.pk}")

        return ServiceResponse.success("Password reset successfully. Please login again.")

    @classmethod
    def get_active_sessions(cls, session_key: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        sessions = Session.objects.filter(
            user=session.user, is_active=True, expires_at__gt=timezone.now()
        ).values("key", "ip_address", "device", "user_agent", "last_activity_at", "created_at")

        data = []
        for s in sessions:
            data.append({
                "key": s["key"][:12] + "...",
                "ip_address": s["ip_address"],
                "device": s["device"],
                "user_agent": s["user_agent"][:100] if s["user_agent"] else "",
                "last_activity": s["last_activity_at"].isoformat() if s["last_activity_at"] else None,
                "created_at": s["created_at"].isoformat() if s["created_at"] else None,
                "is_current": s["key"] == session_key,
            })

        return ServiceResponse.success("Active sessions", data=data)

    @classmethod
    def revoke_session(cls, session_key: str, target_key: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        target = Session.objects.filter(
            key=target_key, user=session.user, is_active=True
        ).first()

        if not target:
            return ServiceResponse.not_found("Session not found")

        target.invalidate()
        CacheService.delete(f"session:{target_key}")

        return ServiceResponse.success("Session revoked")

    @classmethod
    def _serialize_user(cls, user: User) -> dict:
        return {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "email_verified": user.email_verified_at is not None,
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    @classmethod
    def _cache_user(cls, user: User) -> None:
        CacheService.set(f"user:{user.pk}", cls._serialize_user(user), USER_CACHE_TTL)

    @classmethod
    def _cache_permissions(cls, user: User) -> None:
        RolePermissionService.cache_permissions(user)

    @classmethod
    def get_cached_permissions(cls, user_id: int) -> list:
        return RolePermissionService.get_cached_permissions(user_id)