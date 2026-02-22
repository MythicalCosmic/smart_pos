import uuid as uuid_lib

from django.conf import settings
from django.db import models



class StockLocation(models.Model):
    class LocationType(models.TextChoices):
        WAREHOUSE = "WAREHOUSE", "Warehouse"
        KITCHEN = "KITCHEN", "Kitchen"
        BAR = "BAR", "Bar"
        STORAGE = "STORAGE", "Storage"
        PREP = "PREP", "Prep Area"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=LocationType.choices)
    parent_location = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    is_default = models.BooleanField(default=False)
    is_production_area = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class StockUnit(models.Model):
    class UnitType(models.TextChoices):
        WEIGHT = "WEIGHT", "Weight"
        VOLUME = "VOLUME", "Volume"
        COUNT = "COUNT", "Count"
        LENGTH = "LENGTH", "Length"
        TIME = "TIME", "Time"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=10)
    unit_type = models.CharField(max_length=20, choices=UnitType.choices)
    is_base_unit = models.BooleanField(default=False)
    base_unit = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_units",
        help_text="The base unit this unit converts to (e.g. gram for kilogram)",
    )
    conversion_factor = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        default=1,
        help_text="Multiply by this factor to convert to base unit",
    )
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        help_text="Number of decimal places to display for this unit",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["unit_type", "name"]

    def __str__(self):
        return f"{self.name} ({self.short_name})"


class StockCategory(models.Model):
    class CategoryType(models.TextChoices):
        RAW_MATERIAL = "RAW_MATERIAL", "Raw Material"
        SEMI_FINISHED = "SEMI_FINISHED", "Semi-Finished"
        FINISHED_GOOD = "FINISHED_GOOD", "Finished Good"
        PACKAGING = "PACKAGING", "Packaging"
        CONSUMABLE = "CONSUMABLE", "Consumable"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    type = models.CharField(max_length=20, choices=CategoryType.choices)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "stock categories"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class StockItem(models.Model):
    class ItemType(models.TextChoices):
        RAW = "RAW", "Raw Material"
        SEMI = "SEMI", "Semi-Finished"
        FINISHED = "FINISHED", "Finished Good"
        PACKAGING = "PACKAGING", "Packaging"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    category = models.ForeignKey(
        StockCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    base_unit = models.ForeignKey(
        StockUnit,
        on_delete=models.PROTECT,
        related_name="stock_items",
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)

    # Stock thresholds
    min_stock_level = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    max_stock_level = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    reorder_point = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Cost tracking
    cost_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    avg_cost_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    last_cost_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Flags
    is_purchasable = models.BooleanField(default=True)
    is_sellable = models.BooleanField(default=False)
    is_producible = models.BooleanField(default=False)
    track_batches = models.BooleanField(default=False)
    track_expiry = models.BooleanField(default=False)
    default_expiry_days = models.PositiveIntegerField(null=True, blank=True)
    storage_conditions = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockItemUnit(models.Model):
    """
    Alternative units for a stock item.
    E.g. a flour item's base unit is gram but it can also be tracked in kg or bags.
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="alternative_units"
    )
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT)
    is_default = models.BooleanField(default=False)
    conversion_to_base = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        help_text="Multiply qty in this unit by this factor to get base unit qty",
    )
    barcode = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("stock_item", "unit")]

    def __str__(self):
        return f"{self.stock_item.name} – {self.unit.short_name}"



class Recipe(models.Model):
    class RecipeType(models.TextChoices):
        PRODUCTION = "PRODUCTION", "Production"
        ASSEMBLY = "ASSEMBLY", "Assembly"
        PREPARATION = "PREPARATION", "Preparation"
        DISASSEMBLY = "DISASSEMBLY", "Disassembly"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)

    output_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="recipes_as_output"
    )
    output_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    output_unit = models.ForeignKey(
        StockUnit, on_delete=models.PROTECT, related_name="+"
    )

    recipe_type = models.CharField(max_length=20, choices=RecipeType.choices)
    version = models.PositiveIntegerField(default=1)
    is_active_version = models.BooleanField(default=True)
    parent_recipe = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions",
    )

    yield_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=100
    )
    estimated_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    difficulty_level = models.PositiveSmallIntegerField(
        default=1, help_text="1 (easy) to 5 (hard)"
    )
    production_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recipes",
    )
    instructions = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    is_scalable = models.BooleanField(default=True)
    min_batch_size = models.DecimalField(
        max_digits=15, decimal_places=4, default=1
    )
    max_batch_size = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_recipes",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_recipes",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class RecipeIngredient(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="ingredients"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="used_in_recipes"
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    is_optional = models.BooleanField(default=False)
    is_scalable = models.BooleanField(default=True)
    waste_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    prep_instructions = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    substitute_group = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.stock_item.name} × {self.quantity}"


class RecipeIngredientSubstitute(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    recipe_ingredient = models.ForeignKey(
        RecipeIngredient, on_delete=models.CASCADE, related_name="substitutes"
    )
    substitute_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="substitute_for"
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    conversion_note = models.TextField(blank=True, default="")
    priority = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"Sub: {self.substitute_item.name}"


class RecipeByProduct(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="by_products"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="byproduct_of"
    )
    expected_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    is_waste = models.BooleanField(default=False)
    value_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{'Waste' if self.is_waste else 'By-product'}: {self.stock_item.name}"


class RecipeStep(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="steps"
    )
    step_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    temperature = models.CharField(max_length=50, blank=True, default="")
    equipment_needed = models.TextField(blank=True, default="")
    is_checkpoint = models.BooleanField(default=False)
    photo_url = models.URLField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["step_number"]
        unique_together = [("recipe", "step_number")]

    def __str__(self):
        return f"Step {self.step_number}: {self.title}"



class ProductStockLink(models.Model):
    """
    Links a POS product to either a recipe, a direct stock item, or
    a set of components. This drives automatic stock deduction on sale.
    """

    class LinkType(models.TextChoices):
        RECIPE = "RECIPE", "Recipe"
        DIRECT_ITEM = "DIRECT_ITEM", "Direct Item"
        COMPONENT_BASED = "COMPONENT_BASED", "Component Based"

    class DeductOn(models.TextChoices):
        CREATED = "CREATED", "Order Created"
        PREPARING = "PREPARING", "Preparing"
        READY = "READY", "Ready"
        PAID = "PAID", "Paid"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    # NOTE: Replace 'main.Product' with your actual Product model path
    product = models.OneToOneField(
        "main.Product",
        on_delete=models.CASCADE,
        related_name="stock_link",
    )
    link_type = models.CharField(max_length=20, choices=LinkType.choices)
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_links",
    )
    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_links",
    )
    quantity_per_sale = models.DecimalField(
        max_digits=15, decimal_places=4, default=1
    )
    unit = models.ForeignKey(
        StockUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    deduct_on_status = models.CharField(
        max_length=20, choices=DeductOn.choices, default=DeductOn.PREPARING
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Link: Product#{self.product_id} → {self.get_link_type_display()}"


class ProductComponentStock(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    product_stock_link = models.ForeignKey(
        ProductStockLink, on_delete=models.CASCADE, related_name="components"
    )
    component_name = models.CharField(max_length=100)
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    is_default = models.BooleanField(default=True)
    is_addable = models.BooleanField(default=True)
    is_removable = models.BooleanField(default=True)
    price_modifier = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.component_name



class Supplier(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True, default="")
    contact_person = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    mobile = models.CharField(max_length=50, blank=True, default="")
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    tax_id = models.CharField(max_length=50, blank=True, default="")

    payment_terms_days = models.PositiveIntegerField(default=30)
    credit_limit = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    current_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=0
    )
    currency = models.CharField(max_length=3, default="UZS")
    lead_time_days = models.PositiveIntegerField(default=1)
    minimum_order_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1 to 5"
    )

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupplierStockItem(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="stock_items"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="suppliers"
    )
    supplier_sku = models.CharField(max_length=50, blank=True, default="")
    supplier_name = models.CharField(
        max_length=200, blank=True, default="",
        help_text="What the supplier calls this item",
    )
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    price = models.DecimalField(max_digits=15, decimal_places=4)
    currency = models.CharField(max_length=3, default="UZS")
    min_order_qty = models.DecimalField(
        max_digits=15, decimal_places=4, default=1
    )
    pack_size = models.DecimalField(max_digits=15, decimal_places=4, default=1)
    lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    is_preferred = models.BooleanField(default=False)
    last_price_update = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("supplier", "stock_item")]

    def __str__(self):
        return f"{self.supplier.name} → {self.stock_item.name}"


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PARTIAL = "PARTIAL", "Partially Received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partial"
        PAID = "PAID", "Paid"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    order_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    delivery_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    order_date = models.DateField()
    expected_date = models.DateTimeField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="UZS")

    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    payment_due_date = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_purchase_orders",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_purchase_orders",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order_date"]

    def __str__(self):
        return f"PO-{self.order_number}"


class PurchaseOrderItem(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    supplier_stock_item = models.ForeignKey(
        SupplierStockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    quantity_ordered = models.DecimalField(max_digits=15, decimal_places=4)
    quantity_received = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    unit_price = models.DecimalField(max_digits=15, decimal_places=4)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=15, decimal_places=4)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock_item.name} × {self.quantity_ordered}"


class PurchaseReceiving(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COMPLETED = "COMPLETED", "Completed"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    receiving_number = models.CharField(max_length=50, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receivings"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="+"
    )
    received_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"RCV-{self.receiving_number}"


class PurchaseReceivingItem(models.Model):
    class QualityStatus(models.TextChoices):
        PASSED = "PASSED", "Passed"
        FAILED = "FAILED", "Failed"
        PENDING = "PENDING", "Pending"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    receiving = models.ForeignKey(
        PurchaseReceiving, on_delete=models.CASCADE, related_name="items"
    )
    po_item = models.ForeignKey(
        PurchaseOrderItem, on_delete=models.PROTECT, related_name="receiving_items"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    quantity_received = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    batch_number = models.CharField(max_length=100, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=4)
    quality_status = models.CharField(
        max_length=20,
        choices=QualityStatus.choices,
        default=QualityStatus.PASSED,
    )
    notes = models.TextField(blank=True, default="")
    # Set after batch is created during receiving
    batch_created = models.ForeignKey(
        "StockBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock_item.name} × {self.quantity_received}"


class StockLevel(models.Model):
    """
    Denormalized current stock level per item per location.
    Updated by stock transactions.
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="stock_levels"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.CASCADE, related_name="stock_levels"
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    reserved_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    pending_in_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    pending_out_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    last_counted_at = models.DateTimeField(null=True, blank=True)
    last_restocked_at = models.DateTimeField(null=True, blank=True)
    last_movement_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("stock_item", "location")]

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    def __str__(self):
        return f"{self.stock_item.name} @ {self.location.name}: {self.quantity}"


class StockBatch(models.Model):
    class BatchStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        RESERVED = "RESERVED", "Reserved"
        QUARANTINE = "QUARANTINE", "Quarantine"
        EXPIRED = "EXPIRED", "Expired"
        CONSUMED = "CONSUMED", "Consumed"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    batch_number = models.CharField(max_length=100)
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="batches"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="batches"
    )
    initial_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    current_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    reserved_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, default=0
    )
    unit_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    manufactured_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
    )
    production_order = models.ForeignKey(
        "ProductionOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="output_batches",
    )

    status = models.CharField(
        max_length=20, choices=BatchStatus.choices, default=BatchStatus.AVAILABLE
    )
    quality_status = models.CharField(max_length=20, default="PASSED")
    notes = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("batch_number", "stock_item")]
        verbose_name_plural = "stock batches"

    def __str__(self):
        return f"Batch {self.batch_number} – {self.stock_item.name}"


class StockTransaction(models.Model):
    class MovementType(models.TextChoices):
        PURCHASE_IN = "PURCHASE_IN", "Purchase In"
        SALE_OUT = "SALE_OUT", "Sale Out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
        PRODUCTION_IN = "PRODUCTION_IN", "Production In"
        PRODUCTION_OUT = "PRODUCTION_OUT", "Production Out"
        ADJUSTMENT_PLUS = "ADJUSTMENT_PLUS", "Adjustment +"
        ADJUSTMENT_MINUS = "ADJUSTMENT_MINUS", "Adjustment −"
        WASTE = "WASTE", "Waste"
        SPOILAGE = "SPOILAGE", "Spoilage"
        RETURN_FROM_CUSTOMER = "RETURN_FROM_CUSTOMER", "Return from Customer"
        RETURN_TO_SUPPLIER = "RETURN_TO_SUPPLIER", "Return to Supplier"
        COUNT_ADJUSTMENT = "COUNT_ADJUSTMENT", "Count Adjustment"
        OPENING_BALANCE = "OPENING_BALANCE", "Opening Balance"
        RESERVATION = "RESERVATION", "Reservation"
        RESERVATION_RELEASE = "RESERVATION_RELEASE", "Reservation Release"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    transaction_number = models.CharField(max_length=50, unique=True)
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="transactions"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="transactions"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    movement_type = models.CharField(
        max_length=30, choices=MovementType.choices, db_index=True
    )

    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    base_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    quantity_before = models.DecimalField(max_digits=15, decimal_places=4)
    quantity_after = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Generic reference to source document
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.PositiveIntegerField(null=True, blank=True)

    # Explicit FKs for the most common reference types
    order = models.ForeignKey(
        "main.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )
    production_order = models.ForeignKey(
        "ProductionOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )
    transfer = models.ForeignKey(
        "StockTransfer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_transactions",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stock_item", "created_at"]),
            models.Index(fields=["movement_type", "created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.transaction_number} | {self.get_movement_type_display()}"


class ProductionOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        ON_HOLD = "ON_HOLD", "On Hold"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    order_number = models.CharField(max_length=50, unique=True)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT, related_name="production_orders"
    )
    batch_multiplier = models.DecimalField(
        max_digits=10, decimal_places=4, default=1
    )
    expected_output_qty = models.DecimalField(max_digits=15, decimal_places=4)
    actual_output_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    output_unit = models.ForeignKey(
        StockUnit, on_delete=models.PROTECT, related_name="+"
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )

    source_location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="production_orders_source",
    )
    output_location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="production_orders_output",
    )

    planned_start = models.DateTimeField(null=True, blank=True)
    planned_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_production_orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_production_orders",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PROD-{self.order_number}"


class ProductionOrderIngredient(models.Model):
    class IngredientStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ALLOCATED = "ALLOCATED", "Allocated"
        CONSUMED = "CONSUMED", "Consumed"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name="ingredients"
    )
    recipe_ingredient = models.ForeignKey(
        RecipeIngredient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    planned_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    actual_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    batch_used = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    variance = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    variance_reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=IngredientStatus.choices,
        default=IngredientStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock_item.name} (planned: {self.planned_quantity})"


class ProductionOrderOutput(models.Model):
    class QualityStatus(models.TextChoices):
        PASSED = "PASSED", "Passed"
        FAILED = "FAILED", "Failed"
        PENDING = "PENDING", "Pending"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name="outputs"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    is_primary_output = models.BooleanField(default=True)
    is_byproduct = models.BooleanField(default=False)
    is_waste = models.BooleanField(default=False)
    batch_created = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    quality_status = models.CharField(
        max_length=20,
        choices=QualityStatus.choices,
        default=QualityStatus.PENDING,
    )
    quality_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        label = "Primary" if self.is_primary_output else "By-product"
        return f"{label}: {self.stock_item.name} × {self.quantity}"


class ProductionOrderStep(models.Model):
    class StepStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        SKIPPED = "SKIPPED", "Skipped"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name="steps"
    )
    recipe_step = models.ForeignKey(
        RecipeStep, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(
        max_length=20, choices=StepStatus.choices, default=StepStatus.PENDING
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True, default="")
    checkpoint_passed = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Step {self.recipe_step.step_number}: {self.get_status_display()}"

class StockTransfer(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REQUESTED = "REQUESTED", "Requested"
        APPROVED = "APPROVED", "Approved"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    class TransferType(models.TextChoices):
        INTERNAL = "INTERNAL", "Internal"
        BRANCH_TO_BRANCH = "BRANCH_TO_BRANCH", "Branch to Branch"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    transfer_number = models.CharField(max_length=50, unique=True)
    from_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="transfers_out"
    )
    to_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="transfers_in"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    transfer_type = models.CharField(
        max_length=20,
        choices=TransferType.choices,
        default=TransferType.INTERNAL,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_transfers",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_transfers",
    )
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipped_transfers",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_transfers",
    )

    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"TRF-{self.transfer_number}"


class StockTransferItem(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.CASCADE, related_name="items"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    requested_qty = models.DecimalField(max_digits=15, decimal_places=4)
    approved_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    shipped_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    received_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    unit = models.ForeignKey(StockUnit, on_delete=models.PROTECT, related_name="+")
    variance_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock_item.name} × {self.requested_qty}"


class VarianceReasonCode(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    requires_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code}: {self.name}"


class StockCount(models.Model):
    class CountType(models.TextChoices):
        FULL = "FULL", "Full Count"
        PARTIAL = "PARTIAL", "Partial Count"
        CYCLE = "CYCLE", "Cycle Count"
        SPOT = "SPOT", "Spot Check"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        CANCELLED = "CANCELLED", "Cancelled"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    count_number = models.CharField(max_length=50, unique=True)
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="stock_counts"
    )
    count_type = models.CharField(max_length=20, choices=CountType.choices)
    category_filter = models.ForeignKey(
        StockCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="If set, only items in this category will be counted",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_counts",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_stock_counts",
    )
    auto_adjust = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CNT-{self.count_number}"


class StockCountItem(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    stock_count = models.ForeignKey(
        StockCount, on_delete=models.CASCADE, related_name="items"
    )
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="+"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    system_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    counted_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    variance = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    variance_percentage = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    variance_cost = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    reason_code = models.ForeignKey(
        VarianceReasonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True, default="")
    is_adjusted = models.BooleanField(default=False)
    adjustment_transaction = models.ForeignKey(
        StockTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock_item.name}: system={self.system_quantity}, counted={self.counted_quantity}"


class StockSettings(models.Model):
    """
    Singleton settings table. Use StockSettings.load() to get the instance.
    """

    # Master controls
    stock_enabled = models.BooleanField(default=False)
    production_enabled = models.BooleanField(default=False)
    purchasing_enabled = models.BooleanField(default=False)
    multi_location_enabled = models.BooleanField(default=False)

    # Tracking options
    track_cost = models.BooleanField(default=True)
    track_batches = models.BooleanField(default=False)
    track_expiry = models.BooleanField(default=False)
    track_serial_numbers = models.BooleanField(default=False)

    # Behavior
    allow_negative_stock = models.BooleanField(default=False)
    auto_deduct_on_sale = models.BooleanField(default=True)
    deduct_on_order_status = models.CharField(max_length=20, default="PREPARING")
    reserve_on_order_create = models.BooleanField(default=False)
    auto_create_production = models.BooleanField(default=False)

    # Costing
    class CostingMethod(models.TextChoices):
        FIFO = "FIFO", "First In, First Out"
        LIFO = "LIFO", "Last In, First Out"
        AVERAGE = "AVERAGE", "Weighted Average"
        SPECIFIC = "SPECIFIC", "Specific Identification"

    costing_method = models.CharField(
        max_length=20, choices=CostingMethod.choices, default=CostingMethod.FIFO
    )
    include_waste_in_cost = models.BooleanField(default=True)

    # Alerts
    low_stock_alert_enabled = models.BooleanField(default=True)
    expiry_alert_enabled = models.BooleanField(default=True)
    expiry_alert_days = models.PositiveIntegerField(default=7)
    negative_stock_alert = models.BooleanField(default=True)

    # Defaults
    default_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    default_production_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    default_receiving_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # Approvals
    require_po_approval = models.BooleanField(default=False)
    require_transfer_approval = models.BooleanField(default=False)
    require_adjustment_approval = models.BooleanField(default=False)
    require_count_approval = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "stock settings"
        verbose_name_plural = "stock settings"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Stock Settings"


class StockAlertConfig(models.Model):
    class AlertType(models.TextChoices):
        LOW_STOCK = "LOW_STOCK", "Low Stock"
        EXPIRING = "EXPIRING", "Expiring"
        NEGATIVE = "NEGATIVE", "Negative Stock"
        OVERSTOCK = "OVERSTOCK", "Overstock"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    notify_email = models.BooleanField(default=False)
    notify_telegram = models.BooleanField(default=True)
    notify_in_app = models.BooleanField(default=True)
    threshold_value = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Alert: {self.get_alert_type_display()}"