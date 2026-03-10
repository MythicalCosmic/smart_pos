from django.utils import timezone

from main.models import User, Role, Permission, RolePermission, UserRole, Session
from admins.services.base_service import ServiceResponse, CacheService


PERMISSIONS_CACHE_TTL = 300


class RolePermissionService:

    @classmethod
    def get_cached_permissions(cls, user_id: int) -> list:
        cached = CacheService.get(f"permissions:{user_id}")
        if cached is not None:
            return cached

        try:
            user = User.objects.get(pk=user_id)
            perms = list(user.get_permissions())
            CacheService.set(f"permissions:{user_id}", perms, PERMISSIONS_CACHE_TTL)
            return perms
        except User.DoesNotExist:
            return []

    @classmethod
    def cache_permissions(cls, user: User) -> None:
        perms = list(user.get_permissions())
        CacheService.set(f"permissions:{user.pk}", perms, PERMISSIONS_CACHE_TTL)

    @classmethod
    def invalidate_permissions(cls, user_id: int) -> None:
        CacheService.delete(f"permissions:{user_id}")

    @classmethod
    def invalidate_user_cache(cls, user_id: int) -> None:
        CacheService.delete(f"user:{user_id}")
        CacheService.delete(f"permissions:{user_id}")

    @classmethod
    def nuke_user_sessions(cls, user_id: int) -> None:
        session_keys = list(
            Session.objects.filter(
                user_id=user_id, is_active=True, expires_at__gt=timezone.now()
            ).values_list("key", flat=True)
        )
        Session.objects.filter(user_id=user_id, is_active=True).update(is_active=False)
        for sk in session_keys:
            CacheService.delete(f"session:{sk}")
        cls.invalidate_user_cache(user_id)

    @classmethod
    def assign_role_to_user(cls, user_id: int, role_id: int, assigned_by=None) -> tuple:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        _, created = UserRole.objects.get_or_create(
            user=user, role=role,
            defaults={"assigned_by": assigned_by},
        )

        if not created:
            return ServiceResponse.error("User already has this role")

        cls.invalidate_user_cache(user_id)

        return ServiceResponse.success("Role assigned successfully")

    @classmethod
    def remove_role_from_user(cls, user_id: int, role_id: int) -> tuple:
        deleted, _ = UserRole.objects.filter(user_id=user_id, role_id=role_id).delete()

        if not deleted:
            return ServiceResponse.not_found("User does not have this role")

        cls.invalidate_user_cache(user_id)

        return ServiceResponse.success("Role removed successfully")

    @classmethod
    def set_role_permissions(cls, role_id: int, permission_ids: list) -> tuple:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        valid_perms = set(
            Permission.objects.filter(pk__in=permission_ids).values_list("pk", flat=True)
        )
        invalid = [pid for pid in permission_ids if pid not in valid_perms]
        if invalid:
            return ServiceResponse.error(f"Permissions not found: {invalid}")

        existing = set(
            RolePermission.objects.filter(role=role, permission_id__in=permission_ids)
            .values_list("permission_id", flat=True)
        )

        new_rps = [
            RolePermission(role=role, permission_id=pid)
            for pid in valid_perms if pid not in existing
        ]

        if new_rps:
            RolePermission.objects.bulk_create(new_rps)

        cls._invalidate_role_users(role_id)

        return ServiceResponse.success(
            f"Assigned {len(new_rps)} permissions, {len(existing)} already existed",
            data={"assigned": len(new_rps), "skipped": len(existing)},
        )

    @classmethod
    def unset_role_permissions(cls, role_id: int, permission_ids: list) -> tuple:
        try:
            Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        deleted, _ = RolePermission.objects.filter(
            role_id=role_id, permission_id__in=permission_ids
        ).delete()

        if not deleted:
            return ServiceResponse.not_found("None of the given permissions were assigned")

        cls._invalidate_role_users(role_id)

        return ServiceResponse.success(
            f"Removed {deleted} permissions",
            data={"removed": deleted},
        )

    @classmethod
    def assign_permission_to_role(cls, role_id: int, permission_id: int) -> tuple:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        try:
            permission = Permission.objects.get(pk=permission_id)
        except Permission.DoesNotExist:
            return ServiceResponse.not_found("Permission not found")

        _, created = RolePermission.objects.get_or_create(role=role, permission=permission)

        if not created:
            return ServiceResponse.error("Permission already assigned to this role")

        cls._invalidate_role_users(role_id)

        return ServiceResponse.success("Permission assigned successfully")

    @classmethod
    def remove_permission_from_role(cls, role_id: int, permission_id: int) -> tuple:
        deleted, _ = RolePermission.objects.filter(
            role_id=role_id, permission_id=permission_id
        ).delete()

        if not deleted:
            return ServiceResponse.not_found("Permission not assigned to this role")

        cls._invalidate_role_users(role_id)

        return ServiceResponse.success("Permission removed successfully")

    @classmethod
    def _invalidate_role_users(cls, role_id: int) -> None:
        user_ids = UserRole.objects.filter(role_id=role_id).values_list("user_id", flat=True)
        for uid in user_ids:
            cls.invalidate_user_cache(uid)
