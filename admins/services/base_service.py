from typing import Any, Optional

from django.core.cache import cache
from django.http import JsonResponse


class ServiceResponse:
    """base response builder -- no more raw dicts everywhere"""

    @staticmethod
    def success(message: str = "OK", data: Any = None, status: int = 200) -> dict:
        response = {"success": True, "message": message}
        if data is not None:
            response["data"] = data
        return response, status

    @staticmethod
    def error(message: str = "Something went wrong", status: int = 400) -> dict:
        return {"success": False, "message": message}, status

    @staticmethod
    def unauthorized(message: str = "Unauthorized") -> dict:
        return {"success": False, "message": message}, 401

    @staticmethod
    def forbidden(message: str = "Forbidden") -> dict:
        return {"success": False, "message": message}, 403

    @staticmethod
    def not_found(message: str = "Not found") -> dict:
        return {"success": False, "message": message}, 404

    @staticmethod
    def to_json(result: tuple) -> JsonResponse:
        """convert (data, status) tuple to JsonResponse"""
        data, status = result
        return JsonResponse(data, status=status)


class Validator:
    """reusable validation -- call chain style"""

    def __init__(self):
        self._errors = []

    def required(self, value: Any, field_name: str) -> "Validator":
        if value is None or (isinstance(value, str) and not value.strip()):
            self._errors.append(f"{field_name} is required")
        return self

    def min_length(self, value: str, length: int, field_name: str) -> "Validator":
        if value and len(value.strip()) < length:
            self._errors.append(f"{field_name} must be at least {length} characters")
        return self

    def max_length(self, value: str, length: int, field_name: str) -> "Validator":
        if value and len(value.strip()) > length:
            self._errors.append(f"{field_name} cannot exceed {length} characters")
        return self

    def email(self, value: str) -> "Validator":
        if value and ("@" not in value or "." not in value.split("@")[-1]):
            self._errors.append("Invalid email format")
        return self

    def password_strength(self, value: str) -> "Validator":
        if not value:
            return self
        if len(value) < 8:
            self._errors.append("Password must be at least 8 characters")
        if not any(c.isupper() for c in value):
            self._errors.append("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            self._errors.append("Password must contain at least one digit")
        return self

    @property
    def is_valid(self) -> bool:
        return len(self._errors) == 0

    @property
    def errors(self) -> str:
        return "; ".join(self._errors)


class CacheService:
    """thin wrapper over django cache with prefixing"""

    PREFIX = "logistics"

    @classmethod
    def _key(cls, key: str) -> str:
        return f"{cls.PREFIX}:{key}"

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        return cache.get(cls._key(key))

    @classmethod
    def set(cls, key: str, value: Any, ttl: int = 300) -> None:
        cache.set(cls._key(key), value, ttl)

    @classmethod
    def delete(cls, key: str) -> None:
        cache.delete(cls._key(key))

    @classmethod
    def delete_pattern(cls, pattern: str) -> None:
        """delete keys matching pattern -- works with redis and locmem backends"""
        full_pattern = cls._key(pattern)
        try:
            # django-redis provides delete_pattern which handles KEY_PREFIX correctly
            cache.delete_pattern(full_pattern)
        except AttributeError:
            # LocMemCache / DummyCache fallback -- scan internal cache
            cls._locmem_delete_pattern(full_pattern)

    @classmethod
    def _locmem_delete_pattern(cls, pattern: str) -> None:
        """Fallback pattern delete for non-redis backends (LocMemCache)."""
        try:
            base = pattern.replace("*", "")
            # LocMemCache stores keys in _cache dict with version-prefixed keys
            internal = getattr(cache, '_cache', None)
            if internal is None:
                return
            keys_to_delete = [k for k in list(internal.keys()) if base in k]
            for k in keys_to_delete:
                internal.pop(k, None)
                expire_info = getattr(cache, '_expire_info', {})
                expire_info.pop(k, None)
        except Exception:
            pass

    @classmethod
    def get_or_set(cls, key: str, callback, ttl: int = 300) -> Any:
        """get from cache or compute and store"""
        value = cls.get(key)
        if value is None:
            value = callback()
            cls.set(key, value, ttl)
        return value