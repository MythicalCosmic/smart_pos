"""
Smart Jowi Models with Sync Support
"""

import uuid
from django.db import models
from django.conf import settings


# =============================================================================
# SYNC MIXIN - Add to all models that need syncing
# =============================================================================

class SyncMixin(models.Model):
    """
    Mixin that adds sync tracking to any model.
    """
    
    uuid = models.UUIDField(
        default=uuid.uuid4, 
        unique=True, 
        editable=False,
        db_index=True,
    )
    
    synced_at = models.DateTimeField(
        null=True, 
        blank=True,
        db_index=True,
    )
    
    sync_version = models.PositiveIntegerField(default=1)
    
    is_deleted = models.BooleanField(default=False, db_index=True)
    
    branch_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        # Set branch_id on creation
        if not self.branch_id and hasattr(settings, 'BRANCH_ID'):
            self.branch_id = settings.BRANCH_ID
        
        # Increment version on updates
        if self.pk:
            self.sync_version += 1
        
        # Clear synced_at to mark as needing sync (only in local mode)
        if getattr(settings, 'DEPLOYMENT_MODE', 'local') == 'local':
            update_fields = kwargs.get('update_fields')
            if update_fields is None or any(f not in ['synced_at', 'sync_version'] for f in update_fields):
                self.synced_at = None
        
        super().save(*args, **kwargs)
        
        # Queue for sync if enabled
        if getattr(settings, 'SYNC_ON_SAVE', False) and self.synced_at is None:
            self._queue_for_sync()
    
    def delete(self, *args, **kwargs):
        """Soft delete by default."""
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
        """Convert to dictionary for sync."""
        data = {
            'uuid': str(self.uuid),
            'sync_version': self.sync_version,
            'is_deleted': self.is_deleted,
            'branch_id': self.branch_id,
        }
        
        # Add all concrete fields
        for field in self._meta.get_fields():
            if field.concrete and not field.is_relation:
                if field.name not in ['id', 'uuid', 'synced_at', 'sync_version', 'is_deleted', 'branch_id']:
                    value = getattr(self, field.name, None)
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    data[field.name] = value
        
        return data
    
    @classmethod
    def from_sync_dict(cls, data: dict, branch_id: str = None):
        """Create or update from sync data."""
        from django.utils import timezone
        
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
                instance.synced_at = timezone.now()
                instance.save()
            
            return instance, 'updated'
            
        except cls.DoesNotExist:
            instance = cls(
                uuid=uuid_val,
                sync_version=sync_version,
                is_deleted=is_deleted,
                branch_id=incoming_branch,
            )
            for key, value in data.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            instance.save()
            return instance, 'created'


class SyncQuerySet(models.QuerySet):
    """Custom QuerySet with sync-aware methods."""
    
    def unsynced(self):
        return self.filter(
            models.Q(synced_at__isnull=True) |
            models.Q(synced_at__lt=models.F('updated_at'))
        )
    
    def from_branch(self, branch_id):
        return self.filter(branch_id=branch_id)
    
    def active(self):
        return self.filter(is_deleted=False)


class SyncManager(models.Manager):
    """Manager that uses SyncQuerySet."""
    
    def get_queryset(self):
        return SyncQuerySet(self.model, using=self._db)
    
    def unsynced(self):
        return self.get_queryset().unsynced()
    
    def active(self):
        return self.get_queryset().active()


# =============================================================================
# MODELS
# =============================================================================

class User(SyncMixin, models.Model):
    class RoleChoices(models.TextChoices):
        USER = "USER", "User"
        ADMIN = "ADMIN", "Admin"
        CASHIER = "CASHIER", "Cashier"

    class UserStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    first_name = models.CharField(max_length=25)
    last_name = models.CharField(max_length=25)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)

    role = models.CharField(
        max_length=10,
        choices=RoleChoices.choices,
        default=RoleChoices.USER
    )

    status = models.CharField(
        max_length=10,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE
    )

    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_api = models.CharField(max_length=20, null=True, blank=True)

    objects = SyncManager()

    def to_sync_dict(self) -> dict:
        data = super().to_sync_dict()
        # Don't sync password for security
        data.pop('password', None)
        return data

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Session(models.Model):
    """Sessions don't need sync - they're local only."""
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.CharField(max_length=20)
    user_agent = models.CharField(max_length=30, null=True, blank=True, default='Chrome')
    payload = models.CharField(max_length=20, null=True, blank=True)
    last_activity = models.DateTimeField(auto_now_add=True)


class Category(SyncMixin, models.Model):
    name = models.CharField(max_length=50)
    sort_order = models.IntegerField(default=0)
    colors = models.JSONField(default=list, blank=True, help_text="Colors: ['#e74c3c', '#3498db']")
    status = models.CharField(
        max_length=10,
        choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')],
        default='ACTIVE'
    )
    slug = models.SlugField(unique=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SyncManager()

    def __str__(self):
        return self.name


class Product(SyncMixin, models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products"
    )
    colors = models.JSONField(default=list, blank=True, help_text="Colors: ['#e74c3c', '#3498db']")
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = SyncManager()

    def to_sync_dict(self) -> dict:
        data = super().to_sync_dict()
        data['category_uuid'] = str(self.category.uuid) if self.category else None
        return data
    

    @classmethod
    def from_sync_dict(cls, data: dict, branch_id: str = None):
        """Handle category foreign key."""
        from django.utils import timezone
        
        data = data.copy()
        category_uuid = data.pop('category_uuid', None)
        
        uuid_val = data.pop('uuid')
        sync_version = data.pop('sync_version', 1)
        is_deleted = data.pop('is_deleted', False)
        incoming_branch = data.pop('branch_id', branch_id)
        
        category = None
        if category_uuid:
            try:
                category = Category.objects.get(uuid=category_uuid)
            except Category.DoesNotExist:
                pass
        
        try:
            instance = cls.objects.get(uuid=uuid_val)
            
            if sync_version >= instance.sync_version:
                for key, value in data.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                if category:
                    instance.category = category
                instance.sync_version = sync_version
                instance.is_deleted = is_deleted
                instance.synced_at = timezone.now()
                instance.save()
            
            return instance, 'updated'
            
        except cls.DoesNotExist:
            instance = cls(
                uuid=uuid_val,
                sync_version=sync_version,
                is_deleted=is_deleted,
                branch_id=incoming_branch,
                category=category,
            )
            for key, value in data.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            instance.save()
            return instance, 'created'
    
    def __str__(self):
        return self.name


class DeliveryPerson(SyncMixin, models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    phone_number = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SyncManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Order(SyncMixin, models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"                     
        PREPARING = "PREPARING", "Preparing"       
        READY = "READY", "Ready"                   
        COMPLETED = "COMPLETED", "Completed" 
        CANCELED = "CANCELED", "Canceled"         

    class OrderType(models.TextChoices):
        HALL = "HALL", "Hall (Dine-in)"
        DELIVERY = "DELIVERY", "Delivery"
        PICKUP = "PICKUP", "Pickup"

    delivery_person = models.ForeignKey(
        DeliveryPerson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries"
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    cashier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_orders"
    )

    display_id = models.IntegerField(default=1)
    
    order_type = models.CharField(
        max_length=10,
        choices=OrderType.choices,
        default=OrderType.HALL
    )
    
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    
    description = models.TextField(null=True, blank=True)
    
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.OPEN
    )

    is_paid = models.BooleanField(default=False)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ready_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    objects = SyncManager()

    def to_sync_dict(self) -> dict:
        data = super().to_sync_dict()
        data['user_uuid'] = str(self.user.uuid) if self.user else None
        data['cashier_uuid'] = str(self.cashier.uuid) if self.cashier else None
        data['delivery_person_uuid'] = str(self.delivery_person.uuid) if self.delivery_person else None
        return data
    
    @classmethod
    def from_sync_dict(cls, data: dict, branch_id: str = None):
        from django.utils import timezone
        
        data = data.copy()
        user_uuid = data.pop('user_uuid', None)
        cashier_uuid = data.pop('cashier_uuid', None)
        delivery_person_uuid = data.pop('delivery_person_uuid', None)
        
        uuid_val = data.pop('uuid')
        sync_version = data.pop('sync_version', 1)
        is_deleted = data.pop('is_deleted', False)
        incoming_branch = data.pop('branch_id', branch_id)
        
        # Find related objects by UUID
        user = None
        cashier = None
        delivery_person = None
        
        if user_uuid:
            try:
                user = User.objects.get(uuid=user_uuid)
            except User.DoesNotExist:
                raise ValueError(f"User with UUID {user_uuid} not found")
        
        if cashier_uuid:
            try:
                cashier = User.objects.get(uuid=cashier_uuid)
            except User.DoesNotExist:
                pass
        
        if delivery_person_uuid:
            try:
                delivery_person = DeliveryPerson.objects.get(uuid=delivery_person_uuid)
            except DeliveryPerson.DoesNotExist:
                pass
        
        # Can't create order without user
        if not user:
            raise ValueError(f"User with UUID {user_uuid} not found - sync User first")
        
        try:
            instance = cls.objects.get(uuid=uuid_val)
            
            if sync_version >= instance.sync_version:
                for key, value in data.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                instance.user = user
                instance.cashier = cashier
                instance.delivery_person = delivery_person
                instance.sync_version = sync_version
                instance.is_deleted = is_deleted
                instance.synced_at = timezone.now()
                instance.save()
            
            return instance, 'updated'
            
        except cls.DoesNotExist:
            instance = cls(
                uuid=uuid_val,
                sync_version=sync_version,
                is_deleted=is_deleted,
                branch_id=incoming_branch,
                user=user,
                cashier=cashier,
                delivery_person=delivery_person,
            )
            for key, value in data.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            instance.save()
            return instance, 'created'

        def __str__(self):
            return f"Order #{self.display_id} - {self.order_type} - {self.status}"


class OrderItem(SyncMixin, models.Model):
    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField()
    detail = models.TextField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    objects = SyncManager()

    def to_sync_dict(self) -> dict:
        data = super().to_sync_dict()
        data['order_uuid'] = str(self.order.uuid) if self.order else None
        data['product_uuid'] = str(self.product.uuid) if self.product else None
        return data

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class CashRegister(SyncMixin, models.Model):
    current_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    last_updated = models.DateTimeField(auto_now=True)
    
    objects = SyncManager()
    
    class Meta:
        db_table = 'cash_register'
    
    def __str__(self):
        return f"Cash Register: {self.current_balance}"


class Inkassa(SyncMixin, models.Model):
    cashier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inkassas"
    )

    class InkassType(models.TextChoices):
        CASH = "CASH", "Cash"
        UZCARD = "UZCARD", "Uzcard"
        HUMO = "HUMO", "Humo"
        PAYME = "PAYME", "Payme"

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    inkass_type = models.CharField(
        max_length=10,
        choices=InkassType.choices
    )

    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(auto_now_add=True)
    
    total_orders = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    objects = SyncManager()

    def to_sync_dict(self) -> dict:
        data = super().to_sync_dict()
        data['cashier_uuid'] = str(self.cashier.uuid) if self.cashier else None
        return data
    
    def __str__(self):
        return f"Inkassa #{self.id} - {self.amount} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"