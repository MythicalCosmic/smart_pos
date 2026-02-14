from typing import Dict, Any, Optional
from django.db import transaction

from stock.models import StockSettings, StockLocation, StockAlertConfig
from stock.services.base_service import (
    BaseService, success_response, error_response,
    ValidationError, to_decimal
)


class StockSettingsService(BaseService):
    model = StockSettings
    
    @classmethod
    def load(cls) -> StockSettings:
        return StockSettings.load()
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Chexck if stock system is enabled"""
        return cls.load().stock_enabled
    
    @classmethod
    def is_production_enabled(cls) -> bool:
        settings = cls.load()
        return settings.stock_enabled and settings.production_enabled
    
    @classmethod
    def is_purchasing_enabled(cls) -> bool:
        settings = cls.load()
        return settings.stock_enabled and settings.purchasing_enabled
    
    @classmethod
    def is_multi_location_enabled(cls) -> bool:
        settings = cls.load()
        return settings.stock_enabled and settings.multi_location_enabled
    
    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        settings = cls.load()
        
        return {
            "stock_enabled": settings.stock_enabled,
            "production_enabled": settings.production_enabled,
            "purchasing_enabled": settings.purchasing_enabled,
            "multi_location_enabled": settings.multi_location_enabled,
            
            "track_cost": settings.track_cost,
            "track_batches": settings.track_batches,
            "track_expiry": settings.track_expiry,
            "track_serial_numbers": settings.track_serial_numbers,
            
            "allow_negative_stock": settings.allow_negative_stock,
            "auto_deduct_on_sale": settings.auto_deduct_on_sale,
            "deduct_on_order_status": settings.deduct_on_order_status,
            "reserve_on_order_create": settings.reserve_on_order_create,
            "auto_create_production": settings.auto_create_production,
            
            "costing_method": settings.costing_method,
            "include_waste_in_cost": settings.include_waste_in_cost,
            
            "low_stock_alert_enabled": settings.low_stock_alert_enabled,
            "expiry_alert_enabled": settings.expiry_alert_enabled,
            "expiry_alert_days": settings.expiry_alert_days,
            "negative_stock_alert": settings.negative_stock_alert,
            
            "default_location_id": settings.default_location_id,
            "default_production_location_id": settings.default_production_location_id,
            "default_receiving_location_id": settings.default_receiving_location_id,
            
            "require_po_approval": settings.require_po_approval,
            "require_transfer_approval": settings.require_transfer_approval,
            "require_adjustment_approval": settings.require_adjustment_approval,
            "require_count_approval": settings.require_count_approval,
        }
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        settings = cls.load()
        
        return {
            "enabled": settings.stock_enabled,
            "modules": {
                "production": settings.production_enabled,
                "purchasing": settings.purchasing_enabled,
                "multi_location": settings.multi_location_enabled,
            },
            "tracking": {
                "cost": settings.track_cost,
                "batches": settings.track_batches,
                "expiry": settings.track_expiry,
            },
            "costing_method": settings.costing_method,
            "allow_negative": settings.allow_negative_stock,
        }
    
    @classmethod
    @transaction.atomic
    def update(cls, **kwargs) -> Dict[str, Any]:
        settings = cls.load()
        valid_fields = {
            "stock_enabled", "production_enabled", "purchasing_enabled", "multi_location_enabled",
            "track_cost", "track_batches", "track_expiry", "track_serial_numbers",
            "allow_negative_stock", "auto_deduct_on_sale", "deduct_on_order_status",
            "reserve_on_order_create", "auto_create_production",
            "costing_method", "include_waste_in_cost",
            "low_stock_alert_enabled", "expiry_alert_enabled", "expiry_alert_days",
            "negative_stock_alert",
            "default_location_id", "default_production_location_id", "default_receiving_location_id",
            "require_po_approval", "require_transfer_approval", 
            "require_adjustment_approval", "require_count_approval",
        }
        
        if "costing_method" in kwargs:
            valid_methods = [c[0] for c in StockSettings.CostingMethod.choices]
            if kwargs["costing_method"] not in valid_methods:
                raise ValidationError(f"Invalid costing method. Valid: {valid_methods}", "costing_method")
        
        if "deduct_on_order_status" in kwargs:
            valid_statuses = ["CREATED", "PREPARING", "READY", "PAID"]
            if kwargs["deduct_on_order_status"] not in valid_statuses:
                raise ValidationError(f"Invalid status. Valid: {valid_statuses}", "deduct_on_order_status")
        for loc_field in ["default_location_id", "default_production_location_id", "default_receiving_location_id"]:
            if loc_field in kwargs and kwargs[loc_field]:
                if not StockLocation.objects.filter(id=kwargs[loc_field], is_active=True).exists():
                    raise ValidationError(f"Location not found or inactive", loc_field)
        
        updated = []
        for field, value in kwargs.items():
            if field in valid_fields:
                setattr(settings, field, value)
                updated.append(field)
        
        if updated:
            settings.save()
        
        return success_response({
            "updated_fields": updated,
            "settings": cls.get_all()
        }, f"Updated {len(updated)} setting(s)")
    
    @classmethod
    @transaction.atomic
    def toggle_stock(cls, enabled: bool) -> Dict[str, Any]:
        settings = cls.load()
        settings.stock_enabled = enabled
        settings.save(update_fields=["stock_enabled", "updated_at"])
        
        return success_response({
            "stock_enabled": enabled
        }, f"Stock system {'enabled' if enabled else 'disabled'}")
    
    @classmethod
    @transaction.atomic
    def toggle_module(cls, module: str, enabled: bool) -> Dict[str, Any]:
        settings = cls.load()
        
        module_fields = {
            "production": "production_enabled",
            "purchasing": "purchasing_enabled",
            "multi_location": "multi_location_enabled",
        }
        
        if module not in module_fields:
            raise ValidationError(f"Invalid module. Valid: {list(module_fields.keys())}", "module")
        
        field = module_fields[module]
        setattr(settings, field, enabled)
        settings.save(update_fields=[field, "updated_at"])
        
        return success_response({
            "module": module,
            "enabled": enabled
        }, f"{module.replace('_', ' ').title()} module {'enabled' if enabled else 'disabled'}")
    
    
    @classmethod
    def get_default_location(cls) -> Optional[StockLocation]:
        settings = cls.load()
        return settings.default_location
    
    @classmethod
    def get_default_location_id(cls) -> Optional[int]:
        settings = cls.load()
        return settings.default_location_id
    
    @classmethod
    def get_production_location(cls) -> Optional[StockLocation]:
        settings = cls.load()
        return settings.default_production_location
    
    @classmethod
    def get_receiving_location(cls) -> Optional[StockLocation]:
        settings = cls.load()
        return settings.default_receiving_location


class AlertConfigService(BaseService):
    
    model = StockAlertConfig
    
    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        configs = cls.model.objects.all()
        
        return {
            "alerts": [
                {
                    "id": c.id,
                    "uuid": str(c.uuid),
                    "alert_type": c.alert_type,
                    "alert_type_display": c.get_alert_type_display(),
                    "notify_email": c.notify_email,
                    "notify_telegram": c.notify_telegram,
                    "notify_in_app": c.notify_in_app,
                    "threshold_value": str(c.threshold_value) if c.threshold_value else None,
                    "is_active": c.is_active,
                }
                for c in configs
            ],
            "count": configs.count()
        }
    
    @classmethod
    def get_by_type(cls, alert_type: str) -> Optional[StockAlertConfig]:
        try:
            return cls.model.objects.get(alert_type=alert_type)
        except cls.model.DoesNotExist:
            return None
    
    @classmethod
    @transaction.atomic
    def create_or_update(cls, alert_type: str, **kwargs) -> Dict[str, Any]:
        valid_types = [c[0] for c in StockAlertConfig.AlertType.choices]
        if alert_type not in valid_types:
            raise ValidationError(f"Invalid alert type. Valid: {valid_types}", "alert_type")
        
        config, created = cls.model.objects.get_or_create(
            alert_type=alert_type,
            defaults={
                "notify_email": kwargs.get("notify_email", False),
                "notify_telegram": kwargs.get("notify_telegram", True),
                "notify_in_app": kwargs.get("notify_in_app", True),
                "threshold_value": kwargs.get("threshold_value"),
                "is_active": kwargs.get("is_active", True),
            }
        )
        
        if not created:
            for field in ["notify_email", "notify_telegram", "notify_in_app", "threshold_value", "is_active"]:
                if field in kwargs:
                    setattr(config, field, kwargs[field])
            config.save()
        
        return success_response({
            "id": config.id,
            "created": created,
            "alert_type": config.alert_type,
        }, f"Alert config {'created' if created else 'updated'}")
    
    @classmethod
    def is_alert_enabled(cls, alert_type: str) -> bool:
        config = cls.get_by_type(alert_type)
        return config.is_active if config else False