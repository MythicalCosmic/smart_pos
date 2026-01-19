import uuid
from django.db import models
from django.conf import settings


class SyncMixin(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4, 
        unique=True, 
        editable=False,
        db_index=True,
        help_text="Global unique identifier for sync"
    )
    
    synced_at = models.DateTimeField(
        null=True, 
        blank=True,
        db_index=True,
        help_text="Last successful sync timestamp"
    )
    
    sync_version = models.PositiveIntegerField(
        default=1,
        help_text="Increments on each update for conflict detection"
    )
    
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag - record will be synced as deleted"
    )
    
    branch_id = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text="Branch that created/owns this record"
    )
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        if not self.branch_id and hasattr(settings, 'BRANCH_ID'):
            self.branch_id = settings.BRANCH_ID
        
        if self.pk:
            self.sync_version += 1
        if hasattr(settings, 'DEPLOYMENT_MODE') and settings.DEPLOYMENT_MODE == 'local':
            update_fields = kwargs.get('update_fields')
            if update_fields is None or any(f not in ['synced_at', 'sync_version'] for f in update_fields):
                self.synced_at = None
        
        super().save(*args, **kwargs)
        
        if getattr(settings, 'SYNC_ON_SAVE', False) and self.synced_at is None:
            self._queue_for_sync()
    
    def delete(self, *args, **kwargs):
        hard_delete = kwargs.pop('hard_delete', False)
        
        if hard_delete:
            super().delete(*args, **kwargs)
        else:
            self.is_deleted = True
            self.save(update_fields=['is_deleted', 'synced_at', 'sync_version'])
    
    def hard_delete(self):
        super().delete()
    
    def _queue_for_sync(self):
        try:
            from main.services.sync_service import SyncService
            SyncService.queue_record(self)
        except Exception:
            pass  
    
    def to_sync_dict(self) -> dict:
            from decimal import Decimal
            from datetime import datetime, date
            
            def serialize_value(value):
                if value is None:
                    return None
                if isinstance(value, Decimal):
                    return str(value) 
                if isinstance(value, (datetime, date)):
                    return value.isoformat()
                if isinstance(value, uuid.UUID):
                    return str(value)
                return value
            
            data = {
                'uuid': str(self.uuid),
                'sync_version': self.sync_version,
                'is_deleted': self.is_deleted,
                'branch_id': self.branch_id,
            }
            for field in self._meta.get_fields():
                if field.concrete and not field.is_relation:
                    if field.name not in ['id', 'uuid', 'synced_at', 'sync_version', 'is_deleted', 'branch_id']:
                        value = getattr(self, field.name, None)
                        data[field.name] = serialize_value(value)
            
            return data
    
    @classmethod
    def get_unsynced(cls, limit=100):
        return cls.objects.filter(
            models.Q(synced_at__isnull=True) | 
            models.Q(synced_at__lt=models.F('updated_at'))
        ).order_by('updated_at')[:limit]
    
    @classmethod
    def from_sync_dict(cls, data: dict, branch_id: str = None):
        uuid_val = data.pop('uuid')
        sync_version = data.pop('sync_version', 1)
        is_deleted = data.pop('is_deleted', False)
        incoming_branch = data.pop('branch_id', branch_id)
        
        try:
            instance = cls.objects.get(uuid=uuid_val)
            if sync_version >= instance.sync_version:
                for key, value in data.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                instance.sync_version = sync_version
                instance.is_deleted = is_deleted
                instance.synced_at = models.functions.Now()
                instance.save()
            
            return instance, 'updated'
            
        except cls.DoesNotExist:
            instance = cls(
                uuid=uuid_val,
                sync_version=sync_version,
                is_deleted=is_deleted,
                branch_id=incoming_branch,
                **data
            )
            instance.save()
            return instance, 'created'


class SyncQuerySet(models.QuerySet):
    def unsynced(self):
        return self.filter(
            models.Q(synced_at__isnull=True) |
            models.Q(synced_at__lt=models.F('updated_at'))
        )
    
    def from_branch(self, branch_id):
        return self.filter(branch_id=branch_id)
    
    def active(self):
        return self.filter(is_deleted=False)
    
    def delete(self):
        return self.update(is_deleted=True)
    
    def hard_delete(self):
        return super().delete()


class SyncManager(models.Manager):
    def get_queryset(self):
        return SyncQuerySet(self.model, using=self._db)
    
    def unsynced(self):
        return self.get_queryset().unsynced()
    
    def from_branch(self, branch_id):
        return self.get_queryset().from_branch(branch_id)
    
    def active(self):
        return self.get_queryset().active()
