from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Model, Q
from django.utils import timezone
import uuid


class ServiceError(Exception):
    def __init__(self, message: str, code: str = "ERROR", details: Dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class ValidationError(ServiceError):
    def __init__(self, message: str, field: str = None, details: Dict = None):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field


class NotFoundError(ServiceError):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            f"{resource} not found: {identifier}",
            "NOT_FOUND",
            {"resource": resource, "identifier": str(identifier)}
        )


class BusinessRuleError(ServiceError):
    def __init__(self, message: str, rule: str = None):
        super().__init__(message, "BUSINESS_RULE_VIOLATION", {"rule": rule})


class InsufficientStockError(ServiceError):
    def __init__(self, item_name: str, required: Decimal, available: Decimal):
        super().__init__(
            f"Insufficient stock for {item_name}: required {required}, available {available}",
            "INSUFFICIENT_STOCK",
            {"item": item_name, "required": str(required), "available": str(available)}
        )


def success_response(data: Any = None, message: str = "Success") -> Dict:
    response = {"success": True, "message": message}
    if data is not None:
        if isinstance(data, dict):
            response.update(data)
        else:
            response["data"] = data
    return response


def error_response(message: str, code: str = "ERROR", details: Dict = None) -> Dict:
    return {
        "success": False,
        "message": message,
        "error_code": code,
        "details": details or {}
    }


def paginate_queryset(queryset, page: int = 1, per_page: int = 20) -> Tuple[List, Dict]:
    page = max(1, page)
    per_page = min(max(1, per_page), 100)
    
    total = queryset.count()
    total_pages = (total + per_page - 1) // per_page
    
    offset = (page - 1) * per_page
    items = list(queryset[offset:offset + per_page])
    
    return items, {
        "page": page,
        "per_page": per_page,
        "total_items": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except:
        return default


def round_decimal(value: Decimal, places: int = 4) -> Decimal:
    if value is None:
        return Decimal("0")
    quantize_str = "0." + "0" * places
    return value.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def generate_number(prefix: str, model_class: Model, field: str = "order_number") -> str:
    today = timezone.now()
    date_part = today.strftime("%Y%m%d")
    filter_kwargs = {f"{field}__startswith": f"{prefix}-{date_part}"}
    last = model_class.objects.filter(**filter_kwargs).order_by(f"-{field}").first()
    
    if last:
        last_num = getattr(last, field)
        try:
            seq = int(last_num.split("-")[-1]) + 1
        except:
            seq = 1
    else:
        seq = 1
    
    return f"{prefix}-{date_part}-{seq:04d}"


def get_date_range(period: str) -> Tuple[date, date]:
    today = timezone.now().date()
    
    if period == "today":
        return today, today
    elif period == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, today
    elif period == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end
    elif period == "this_month":
        return today.replace(day=1), today
    elif period == "last_month":
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    elif period == "this_year":
        return today.replace(month=1, day=1), today
    elif period.startswith("last_") and period.endswith("_days"):
        try:
            days = int(period.replace("last_", "").replace("_days", ""))
            return today - timedelta(days=days), today
        except:
            pass
    
    return today, today


class BaseService:
    model = None
    
    @classmethod
    def get_by_id(cls, id: int) -> Optional[Model]:
        try:
            return cls.model.objects.get(id=id)
        except cls.model.DoesNotExist:
            return None
    
    @classmethod
    def get_by_uuid(cls, uuid_str: str) -> Optional[Model]:
        try:
            return cls.model.objects.get(uuid=uuid_str)
        except (cls.model.DoesNotExist, ValueError):
            return None
    
    @classmethod
    def get_or_404(cls, id: int) -> Model:
        obj = cls.get_by_id(id)
        if not obj:
            raise NotFoundError(cls.model.__name__, id)
        return obj
    
    @classmethod
    def exists(cls, id: int) -> bool:
        return cls.model.objects.filter(id=id).exists()
    
    @classmethod
    def get_active(cls):
        if hasattr(cls.model, 'is_active'):
            return cls.model.objects.filter(is_active=True)
        return cls.model.objects.all()