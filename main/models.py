from django.db import models

class User(models.Model):
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


    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('password'):
            obj.set_password(form.cleaned_data['password']) 
        super().save_model(request, obj, form, change)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Session(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.CharField(max_length=20)
    user_agent = models.CharField(max_length=30, null=True, blank=True, default='Chrome')
    payload = models.CharField(max_length=20, null=True, blank=True)
    last_activity = models.DateTimeField(auto_now_add=True)


class Category(models.Model):
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

    def __str__(self):
        return self.name


class Product(models.Model):
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
    
    def __str__(self):
        return self.name


class Order(models.Model):
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

    def __str__(self):
        return f"Order #{self.display_id} - {self.order_type} - {self.status}"


class OrderItem(models.Model):
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
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class CashRegister(models.Model):
    current_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cash_register'
    
    def __str__(self):
        return f"Cash Register: {self.current_balance}"


class Inkassa(models.Model):
    cashier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inkassas"
    )

    class InkassType(models.TextChoices):
        CASH = "CASH", "Cash"
        UZCARD = "UZCARD", "Uzcard"
        HUMO = "HUMO" "Humo"
        PAYME = "PAYME" "Payme"

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
    
    def __str__(self):
        return f"Inkassa #{self.id} - {self.amount} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"