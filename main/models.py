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

    last_login_at = models.DateTimeField(auto_now_add=True)
    last_login_api = models.CharField(max_length=20, null=True, blank=True)

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
    status = models.CharField(
        max_length=10,
        choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')],
        default='ACTIVE'
    )
    slug = models.SlugField(unique=True)
    description = models.TextField()
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
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"              # Cashier is creating the order
        PAID = "PAID", "Paid"              # Customer paid, waiting for chef
        READY = "READY", "Ready"           # Chef finished preparing
        CANCELED = "CANCELED", "Canceled"  # Order was canceled

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    cashier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_orders"
    )

    # Display ID that cycles from 1-100
    display_id = models.IntegerField(default=1)
    
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN
    )

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Track when order was marked as ready
    ready_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Order #{self.display_id} - {self.status}"


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
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"