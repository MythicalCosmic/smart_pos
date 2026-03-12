from django.contrib import admin
from django.db.models import Sum, Count, Q, F
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display
from unfold.contrib.filters.admin import (
    RangeDateFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from datetime import timedelta

from django.shortcuts import redirect

from .models import (
    StockLocation, StockUnit, StockCategory, StockItem, StockItemUnit,
    StockLevel, StockBatch, StockTransaction,
    Supplier, SupplierStockItem,
    PurchaseOrder, PurchaseOrderItem, PurchaseReceiving, PurchaseReceivingItem,
    Recipe, RecipeIngredient, RecipeIngredientSubstitute, RecipeByProduct, RecipeStep,
    ProductionOrder, ProductionOrderIngredient, ProductionOrderOutput, ProductionOrderStep,
    ProductStockLink, ProductComponentStock,
    StockTransfer, StockTransferItem,
    StockCount, StockCountItem, VarianceReasonCode,
    StockSettings,
)


# ─────────────────────────────────────────────
# LOCATIONS
# ─────────────────────────────────────────────
@admin.register(StockLocation)
class StockLocationAdmin(ModelAdmin):
    list_display = ['name', 'type_badge', 'parent_link', 'is_default_badge', 'is_production_badge', 'is_active_badge', 'sort_order']
    list_filter = ['type', 'is_active', 'is_default', 'is_production_area']
    search_fields = ['name']
    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        (_('Location Info'), {
            'fields': ('name', 'type', 'parent_location', 'sort_order'),
            'classes': ['tab'],
        }),
        (_('Flags'), {
            'fields': ('is_default', 'is_production_area', 'is_active'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Type"))
    def type_badge(self, obj):
        colors = {
            'WAREHOUSE': 'info', 'KITCHEN': 'warning',
            'BAR': 'success', 'STORAGE': 'info', 'PREP': 'warning',
        }
        return colors.get(obj.type, 'info'), obj.get_type_display()

    @display(description=_("Parent"))
    def parent_link(self, obj):
        if obj.parent_location:
            url = reverse('admin:stock_stocklocation_change', args=[obj.parent_location.pk])
            return format_html('<a href="{}">{}</a>', url, obj.parent_location.name)
        return "-"

    @display(description=_("Default"), boolean=True)
    def is_default_badge(self, obj):
        return obj.is_default

    @display(description=_("Production"), boolean=True)
    def is_production_badge(self, obj):
        return obj.is_production_area

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# UNITS
# ─────────────────────────────────────────────
@admin.register(StockUnit)
class StockUnitAdmin(ModelAdmin):
    list_display = ['name', 'short_name', 'unit_type_badge', 'is_base_badge', 'conversion_factor', 'is_active_badge']
    list_filter = ['unit_type', 'is_base_unit', 'is_active']
    search_fields = ['name', 'short_name']
    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        (_('Unit Info'), {
            'fields': ('name', 'short_name', 'unit_type'),
            'classes': ['tab'],
        }),
        (_('Conversion'), {
            'fields': ('is_base_unit', 'base_unit', 'conversion_factor', 'decimal_places'),
            'classes': ['tab'],
        }),
        (_('Status'), {
            'fields': ('is_active',),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Type"))
    def unit_type_badge(self, obj):
        colors = {
            'WEIGHT': 'warning', 'VOLUME': 'info',
            'COUNT': 'success', 'LENGTH': 'danger', 'TIME': 'warning',
        }
        return colors.get(obj.unit_type, 'info'), obj.get_unit_type_display()

    @display(description=_("Base Unit"), boolean=True)
    def is_base_badge(self, obj):
        return obj.is_base_unit

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# STOCK CATEGORIES
# ─────────────────────────────────────────────
@admin.register(StockCategory)
class StockCategoryAdmin(ModelAdmin):
    list_display = ['name', 'type_badge', 'parent_link', 'items_count', 'is_active_badge', 'sort_order']
    list_filter = ['type', 'is_active']
    search_fields = ['name']
    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        (_('Category Info'), {
            'fields': ('name', 'type', 'parent', 'sort_order'),
        }),
        (_('Status'), {
            'fields': ('is_active',),
        }),
    )

    @display(description=_("Type"))
    def type_badge(self, obj):
        colors = {
            'RAW_MATERIAL': 'warning', 'SEMI_FINISHED': 'info',
            'FINISHED_GOOD': 'success', 'PACKAGING': 'danger', 'CONSUMABLE': 'warning',
        }
        return colors.get(obj.type, 'info'), obj.get_type_display()

    @display(description=_("Parent"))
    def parent_link(self, obj):
        if obj.parent:
            url = reverse('admin:stock_stockcategory_change', args=[obj.parent.pk])
            return format_html('<a href="{}">{}</a>', url, obj.parent.name)
        return "-"

    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# STOCK ITEMS
# ─────────────────────────────────────────────
class StockItemUnitInline(TabularInline):
    model = StockItemUnit
    extra = 0
    fields = ('unit', 'conversion_to_base', 'is_default', 'barcode')


@admin.register(StockItem)
class StockItemAdmin(ModelAdmin):
    list_display = ['name', 'sku', 'category_link', 'item_type_badge', 'base_unit_display',
                    'cost_display', 'reorder_point', 'stock_status', 'is_active_badge']
    list_filter = ['item_type', 'is_active', 'is_purchasable', 'is_producible', 'category']
    search_fields = ['name', 'sku', 'barcode']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [StockItemUnitInline]

    fieldsets = (
        (_('Basic Info'), {
            'fields': ('name', 'sku', 'barcode', 'category', 'base_unit', 'item_type'),
            'classes': ['tab'],
        }),
        (_('Stock Thresholds'), {
            'fields': ('min_stock_level', 'max_stock_level', 'reorder_point'),
            'classes': ['tab'],
        }),
        (_('Cost Tracking'), {
            'fields': ('cost_price', 'avg_cost_price', 'last_cost_price'),
            'classes': ['tab'],
        }),
        (_('Flags'), {
            'fields': ('is_purchasable', 'is_sellable', 'is_producible',
                       'track_batches', 'track_expiry', 'default_expiry_days',
                       'storage_conditions', 'is_active'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Category"))
    def category_link(self, obj):
        if obj.category:
            url = reverse('admin:stock_stockcategory_change', args=[obj.category.pk])
            return format_html('<a href="{}">{}</a>', url, obj.category.name)
        return "-"

    @display(description=_("Type"))
    def item_type_badge(self, obj):
        colors = {
            'RAW': 'warning', 'SEMI': 'info',
            'FINISHED': 'success', 'PACKAGING': 'danger',
        }
        return colors.get(obj.item_type, 'info'), obj.get_item_type_display()

    @display(description=_("Unit"))
    def base_unit_display(self, obj):
        return obj.base_unit.short_name

    @display(description=_("Avg Cost"))
    def cost_display(self, obj):
        return f"{obj.avg_cost_price:,.0f} UZS"

    @display(description=_("Stock"))
    def stock_status(self, obj):
        total = StockLevel.objects.filter(stock_item=obj).aggregate(t=Sum('quantity'))['t'] or 0
        if total <= 0:
            return 'danger', f"OUT ({total:,.1f})"
        if total <= float(obj.reorder_point):
            return 'warning', f"LOW ({total:,.1f})"
        return 'success', f"OK ({total:,.1f})"

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# STOCK LEVELS
# ─────────────────────────────────────────────
@admin.register(StockLevel)
class StockLevelAdmin(ModelAdmin):
    list_display = ['item_link', 'location_link', 'quantity_display', 'reserved_display',
                    'available_display', 'level_status', 'last_movement_at']
    list_filter = ['location', 'stock_item__category']
    search_fields = ['stock_item__name', 'location__name']
    list_filter_submit = True
    list_fullwidth = True
    readonly_fields = ['quantity', 'reserved_quantity', 'pending_in_quantity',
                       'pending_out_quantity', 'last_counted_at', 'last_restocked_at', 'last_movement_at']

    @display(description=_("Item"))
    def item_link(self, obj):
        url = reverse('admin:stock_stockitem_change', args=[obj.stock_item.pk])
        return format_html('<a href="{}">{}</a>', url, obj.stock_item.name)

    @display(description=_("Location"))
    def location_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @display(description=_("Qty"), ordering='quantity')
    def quantity_display(self, obj):
        return f"{obj.quantity:,.2f} {obj.stock_item.base_unit.short_name}"

    @display(description=_("Reserved"))
    def reserved_display(self, obj):
        if obj.reserved_quantity > 0:
            return f"{obj.reserved_quantity:,.2f}"
        return "-"

    @display(description=_("Available"))
    def available_display(self, obj):
        return f"{obj.available_quantity:,.2f}"

    @display(description=_("Status"))
    def level_status(self, obj):
        item = obj.stock_item
        if obj.quantity <= 0:
            return 'danger', "OUT OF STOCK"
        if obj.quantity <= float(item.reorder_point):
            return 'warning', "LOW"
        return 'success', "OK"


# ─────────────────────────────────────────────
# STOCK BATCHES
# ─────────────────────────────────────────────
@admin.register(StockBatch)
class StockBatchAdmin(ModelAdmin):
    list_display = ['batch_number', 'item_link', 'location_link', 'quantity_display',
                    'status_badge', 'expiry_badge', 'cost_display', 'created_at']
    list_filter = ['status', 'location', 'stock_item__category']
    search_fields = ['batch_number', 'stock_item__name']
    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        (_('Batch Info'), {
            'fields': ('batch_number', 'stock_item', 'location', 'status'),
            'classes': ['tab'],
        }),
        (_('Quantities'), {
            'fields': ('initial_quantity', 'current_quantity', 'reserved_quantity'),
            'classes': ['tab'],
        }),
        (_('Cost'), {
            'fields': ('unit_cost', 'total_cost'),
            'classes': ['tab'],
        }),
        (_('Dates'), {
            'fields': ('manufactured_date', 'expiry_date', 'received_at'),
            'classes': ['tab'],
        }),
        (_('Source'), {
            'fields': ('supplier', 'purchase_order', 'production_order'),
            'classes': ['tab'],
        }),
        (_('Notes'), {
            'fields': ('quality_status', 'notes'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Item"))
    def item_link(self, obj):
        url = reverse('admin:stock_stockitem_change', args=[obj.stock_item.pk])
        return format_html('<a href="{}">{}</a>', url, obj.stock_item.name)

    @display(description=_("Location"))
    def location_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @display(description=_("Qty"))
    def quantity_display(self, obj):
        return f"{obj.current_quantity:,.2f} / {obj.initial_quantity:,.2f}"

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            'AVAILABLE': 'success', 'RESERVED': 'warning',
            'QUARANTINE': 'danger', 'EXPIRED': 'danger', 'CONSUMED': 'info',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Expiry"))
    def expiry_badge(self, obj):
        if not obj.expiry_date:
            return "-"
        today = timezone.now().date()
        days = (obj.expiry_date - today).days
        if days < 0:
            return 'danger', f"EXPIRED ({abs(days)}d ago)"
        if days <= 7:
            return 'danger', f"{days}d left"
        if days <= 14:
            return 'warning', f"{days}d left"
        return 'success', f"{days}d left"

    @display(description=_("Cost"))
    def cost_display(self, obj):
        return f"{obj.total_cost:,.0f} UZS"


# ─────────────────────────────────────────────
# STOCK TRANSACTIONS
# ─────────────────────────────────────────────
@admin.register(StockTransaction)
class StockTransactionAdmin(ModelAdmin):
    list_display = ['transaction_number', 'item_link', 'movement_badge', 'quantity_display',
                    'before_after', 'location_link', 'cost_display', 'created_at']
    list_filter = ['movement_type', 'location']
    search_fields = ['transaction_number', 'stock_item__name']
    list_filter_submit = True
    list_fullwidth = True
    readonly_fields = ['transaction_number', 'stock_item', 'location', 'batch',
                       'movement_type', 'quantity', 'unit', 'base_quantity',
                       'quantity_before', 'quantity_after', 'unit_cost', 'total_cost',
                       'reference_type', 'reference_id', 'order', 'production_order',
                       'transfer', 'user', 'notes', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Item"))
    def item_link(self, obj):
        url = reverse('admin:stock_stockitem_change', args=[obj.stock_item.pk])
        return format_html('<a href="{}">{}</a>', url, obj.stock_item.name)

    @display(description=_("Movement"))
    def movement_badge(self, obj):
        in_types = ['PURCHASE_IN', 'TRANSFER_IN', 'PRODUCTION_IN', 'ADJUSTMENT_PLUS',
                    'RETURN_FROM_CUSTOMER', 'OPENING_BALANCE', 'RESERVATION_RELEASE']
        out_types = ['SALE_OUT', 'TRANSFER_OUT', 'PRODUCTION_OUT', 'ADJUSTMENT_MINUS',
                     'WASTE', 'SPOILAGE', 'RETURN_TO_SUPPLIER', 'RESERVATION']
        if obj.movement_type in in_types:
            return 'success', obj.get_movement_type_display()
        if obj.movement_type in out_types:
            return 'danger', obj.get_movement_type_display()
        return 'info', obj.get_movement_type_display()

    @display(description=_("Qty"))
    def quantity_display(self, obj):
        sign = "+" if obj.base_quantity > 0 else ""
        return f"{sign}{obj.base_quantity:,.2f} {obj.unit.short_name}"

    @display(description=_("Before / After"))
    def before_after(self, obj):
        return f"{obj.quantity_before:,.2f} -> {obj.quantity_after:,.2f}"

    @display(description=_("Location"))
    def location_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @display(description=_("Cost"))
    def cost_display(self, obj):
        if obj.total_cost:
            return f"{obj.total_cost:,.0f} UZS"
        return "-"


# ─────────────────────────────────────────────
# SUPPLIERS
# ─────────────────────────────────────────────
class SupplierStockItemInline(TabularInline):
    model = SupplierStockItem
    extra = 0
    fields = ('stock_item', 'unit', 'price', 'min_order_qty', 'is_preferred')


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'lead_time_display',
                    'rating_display', 'balance_display', 'is_active_badge']
    list_filter = ['is_active', 'city', 'country']
    search_fields = ['name', 'legal_name', 'contact_person', 'phone', 'email']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [SupplierStockItemInline]

    fieldsets = (
        (_('Company Info'), {
            'fields': ('name', 'legal_name', 'code', 'tax_id'),
            'classes': ['tab'],
        }),
        (_('Contact'), {
            'fields': ('contact_person', 'email', 'phone', 'mobile', 'address', 'city', 'country'),
            'classes': ['tab'],
        }),
        (_('Terms'), {
            'fields': ('payment_terms_days', 'credit_limit', 'current_balance',
                       'currency', 'lead_time_days', 'minimum_order_value', 'rating'),
            'classes': ['tab'],
        }),
        (_('Status'), {
            'fields': ('is_active', 'notes'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Lead Time"))
    def lead_time_display(self, obj):
        return f"{obj.lead_time_days}d"

    @display(description=_("Rating"))
    def rating_display(self, obj):
        if obj.rating:
            stars = obj.rating
            return mark_safe(f'<span style="color:#f59e0b;">{"*" * stars}</span><span style="color:#ccc;">{"*" * (5-stars)}</span>')
        return "-"

    @display(description=_("Balance"))
    def balance_display(self, obj):
        return f"{obj.current_balance:,.0f} {obj.currency}"

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# PURCHASE ORDERS
# ─────────────────────────────────────────────
class PurchaseOrderItemInline(TabularInline):
    model = PurchaseOrderItem
    extra = 0
    fields = ('stock_item', 'quantity_ordered', 'quantity_received', 'unit', 'unit_price', 'total_price')
    readonly_fields = ('quantity_received',)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display = ['order_number', 'supplier_link', 'status_badge', 'payment_badge',
                    'total_display', 'order_date', 'expected_date', 'items_count']
    list_filter = ['status', 'payment_status', 'supplier']
    search_fields = ['order_number', 'supplier__name']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [PurchaseOrderItemInline]

    fieldsets = (
        (_('Order Info'), {
            'fields': ('order_number', 'supplier', 'delivery_location', 'status'),
            'classes': ['tab'],
        }),
        (_('Dates'), {
            'fields': ('order_date', 'expected_date', 'received_date'),
            'classes': ['tab'],
        }),
        (_('Financial'), {
            'fields': ('subtotal', 'tax_amount', 'shipping_cost', 'discount', 'total', 'currency',
                       'payment_status', 'payment_due_date'),
            'classes': ['tab'],
        }),
        (_('People'), {
            'fields': ('created_by', 'approved_by'),
            'classes': ['tab'],
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Supplier"))
    def supplier_link(self, obj):
        url = reverse('admin:stock_supplier_change', args=[obj.supplier.pk])
        return format_html('<a href="{}">{}</a>', url, obj.supplier.name)

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            'DRAFT': 'info', 'SENT': 'warning', 'CONFIRMED': 'success',
            'PARTIAL': 'warning', 'RECEIVED': 'success', 'CANCELLED': 'danger',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Payment"))
    def payment_badge(self, obj):
        colors = {'UNPAID': 'danger', 'PARTIAL': 'warning', 'PAID': 'success'}
        return colors.get(obj.payment_status, 'info'), obj.get_payment_status_display()

    @display(description=_("Total"), ordering='total')
    def total_display(self, obj):
        return f"{obj.total:,.0f} {obj.currency}"

    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()


# ─────────────────────────────────────────────
# PURCHASE RECEIVING
# ─────────────────────────────────────────────
class PurchaseReceivingItemInline(TabularInline):
    model = PurchaseReceivingItem
    extra = 0
    fields = ('stock_item', 'quantity_received', 'unit', 'unit_cost', 'batch_number',
              'expiry_date', 'quality_status')


@admin.register(PurchaseReceiving)
class PurchaseReceivingAdmin(ModelAdmin):
    list_display = ['receiving_number', 'po_link', 'status_badge', 'location_link',
                    'received_date', 'received_by_display', 'items_count']
    list_filter = ['status', 'location']
    search_fields = ['receiving_number', 'purchase_order__order_number']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [PurchaseReceivingItemInline]

    @display(description=_("PO"))
    def po_link(self, obj):
        url = reverse('admin:stock_purchaseorder_change', args=[obj.purchase_order.pk])
        return format_html('<a href="{}">{}</a>', url, obj.purchase_order.order_number)

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {'DRAFT': 'warning', 'COMPLETED': 'success'}
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Location"))
    def location_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @display(description=_("Received By"))
    def received_by_display(self, obj):
        return str(obj.received_by) if obj.received_by else "-"

    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()


# ─────────────────────────────────────────────
# RECIPES
# ─────────────────────────────────────────────
class RecipeIngredientInline(TabularInline):
    model = RecipeIngredient
    extra = 0
    fields = ('stock_item', 'quantity', 'unit', 'is_optional', 'waste_percentage', 'sort_order')


class RecipeStepInline(TabularInline):
    model = RecipeStep
    extra = 0
    fields = ('step_number', 'title', 'duration_minutes', 'temperature', 'is_checkpoint')


class RecipeByProductInline(TabularInline):
    model = RecipeByProduct
    extra = 0
    fields = ('stock_item', 'expected_quantity', 'unit', 'is_waste', 'value_percentage')


@admin.register(Recipe)
class RecipeAdmin(ModelAdmin):
    list_display = ['name', 'code', 'type_badge', 'output_display', 'ingredients_count',
                    'difficulty_display', 'time_display', 'is_active_badge']
    list_filter = ['recipe_type', 'is_active', 'difficulty_level']
    search_fields = ['name', 'code']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [RecipeIngredientInline, RecipeStepInline, RecipeByProductInline]

    fieldsets = (
        (_('Recipe Info'), {
            'fields': ('name', 'code', 'recipe_type', 'version', 'is_active_version', 'parent_recipe'),
            'classes': ['tab'],
        }),
        (_('Output'), {
            'fields': ('output_item', 'output_quantity', 'output_unit', 'yield_percentage'),
            'classes': ['tab'],
        }),
        (_('Production'), {
            'fields': ('estimated_time_minutes', 'difficulty_level', 'production_location',
                       'is_scalable', 'min_batch_size', 'max_batch_size'),
            'classes': ['tab'],
        }),
        (_('Details'), {
            'fields': ('instructions', 'notes'),
            'classes': ['tab'],
        }),
        (_('Audit'), {
            'fields': ('created_by', 'approved_by', 'approved_at', 'is_active'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Type"))
    def type_badge(self, obj):
        colors = {
            'PRODUCTION': 'success', 'ASSEMBLY': 'info',
            'PREPARATION': 'warning', 'DISASSEMBLY': 'danger',
        }
        return colors.get(obj.recipe_type, 'info'), obj.get_recipe_type_display()

    @display(description=_("Output"))
    def output_display(self, obj):
        unit = obj.output_unit.short_name if obj.output_unit else ""
        return f"{obj.output_quantity:,.2f} {unit} of {obj.output_item.name}"

    @display(description=_("Ingredients"))
    def ingredients_count(self, obj):
        return obj.ingredients.count()

    @display(description=_("Difficulty"))
    def difficulty_display(self, obj):
        labels = {1: 'Easy', 2: 'Medium', 3: 'Hard', 4: 'Expert', 5: 'Master'}
        colors = {1: 'success', 2: 'info', 3: 'warning', 4: 'danger', 5: 'danger'}
        return colors.get(obj.difficulty_level, 'info'), labels.get(obj.difficulty_level, str(obj.difficulty_level))

    @display(description=_("Time"))
    def time_display(self, obj):
        if obj.estimated_time_minutes:
            if obj.estimated_time_minutes >= 60:
                h = obj.estimated_time_minutes // 60
                m = obj.estimated_time_minutes % 60
                return f"{h}h {m}m" if m else f"{h}h"
            return f"{obj.estimated_time_minutes}m"
        return "-"

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# PRODUCTION ORDERS
# ─────────────────────────────────────────────
class ProductionOrderIngredientInline(TabularInline):
    model = ProductionOrderIngredient
    extra = 0
    fields = ('stock_item', 'planned_quantity', 'actual_quantity', 'unit', 'status')
    readonly_fields = ('actual_quantity',)


class ProductionOrderOutputInline(TabularInline):
    model = ProductionOrderOutput
    extra = 0
    fields = ('stock_item', 'quantity', 'unit', 'is_primary_output', 'is_byproduct', 'quality_status')


@admin.register(ProductionOrder)
class ProductionOrderAdmin(ModelAdmin):
    list_display = ['order_number', 'recipe_link', 'status_badge', 'priority_badge',
                    'output_display', 'assigned_display', 'planned_start', 'created_at']
    list_filter = ['status', 'priority', 'recipe']
    search_fields = ['order_number', 'recipe__name']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [ProductionOrderIngredientInline, ProductionOrderOutputInline]

    fieldsets = (
        (_('Order Info'), {
            'fields': ('order_number', 'recipe', 'batch_multiplier', 'status', 'priority'),
            'classes': ['tab'],
        }),
        (_('Output'), {
            'fields': ('expected_output_qty', 'actual_output_qty', 'output_unit'),
            'classes': ['tab'],
        }),
        (_('Locations'), {
            'fields': ('source_location', 'output_location'),
            'classes': ['tab'],
        }),
        (_('Schedule'), {
            'fields': ('planned_start', 'planned_end', 'actual_start', 'actual_end'),
            'classes': ['tab'],
        }),
        (_('People'), {
            'fields': ('assigned_to', 'created_by'),
            'classes': ['tab'],
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Recipe"))
    def recipe_link(self, obj):
        url = reverse('admin:stock_recipe_change', args=[obj.recipe.pk])
        return format_html('<a href="{}">{}</a>', url, obj.recipe.name)

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            'DRAFT': 'info', 'PLANNED': 'warning', 'IN_PROGRESS': 'warning',
            'COMPLETED': 'success', 'CANCELLED': 'danger', 'ON_HOLD': 'info',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Priority"))
    def priority_badge(self, obj):
        colors = {
            'LOW': 'info', 'NORMAL': 'success',
            'HIGH': 'warning', 'URGENT': 'danger',
        }
        return colors.get(obj.priority, 'info'), obj.get_priority_display()

    @display(description=_("Output"))
    def output_display(self, obj):
        return f"{obj.expected_output_qty:,.2f} {obj.output_unit.short_name}"

    @display(description=_("Assigned To"))
    def assigned_display(self, obj):
        return str(obj.assigned_to) if obj.assigned_to else "-"


# ─────────────────────────────────────────────
# TRANSFERS
# ─────────────────────────────────────────────
class StockTransferItemInline(TabularInline):
    model = StockTransferItem
    extra = 0
    fields = ('stock_item', 'requested_qty', 'approved_qty', 'shipped_qty', 'received_qty', 'unit')


@admin.register(StockTransfer)
class StockTransferAdmin(ModelAdmin):
    list_display = ['transfer_number', 'from_link', 'to_link', 'status_badge',
                    'type_badge', 'items_count', 'requested_by_display', 'created_at']
    list_filter = ['status', 'transfer_type', 'from_location', 'to_location']
    search_fields = ['transfer_number']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [StockTransferItemInline]

    fieldsets = (
        (_('Transfer Info'), {
            'fields': ('transfer_number', 'from_location', 'to_location', 'status', 'transfer_type'),
            'classes': ['tab'],
        }),
        (_('People'), {
            'fields': ('requested_by', 'approved_by', 'shipped_by', 'received_by'),
            'classes': ['tab'],
        }),
        (_('Timestamps'), {
            'fields': ('requested_at', 'approved_at', 'shipped_at', 'received_at'),
            'classes': ['tab'],
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ['tab'],
        }),
    )

    @display(description=_("From"))
    def from_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.from_location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.from_location.name)

    @display(description=_("To"))
    def to_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.to_location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.to_location.name)

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            'DRAFT': 'info', 'REQUESTED': 'warning', 'APPROVED': 'success',
            'IN_TRANSIT': 'warning', 'RECEIVED': 'success', 'CANCELLED': 'danger',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Type"))
    def type_badge(self, obj):
        return ('info' if obj.transfer_type == 'INTERNAL' else 'warning'), obj.get_transfer_type_display()

    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()

    @display(description=_("Requested By"))
    def requested_by_display(self, obj):
        return str(obj.requested_by) if obj.requested_by else "-"


# ─────────────────────────────────────────────
# STOCK COUNTS
# ─────────────────────────────────────────────
class StockCountItemInline(TabularInline):
    model = StockCountItem
    extra = 0
    fields = ('stock_item', 'system_quantity', 'counted_quantity', 'variance', 'unit')
    readonly_fields = ('system_quantity', 'variance')


@admin.register(StockCount)
class StockCountAdmin(ModelAdmin):
    list_display = ['count_number', 'location_link', 'count_type_badge', 'status_badge',
                    'items_count', 'counted_by_display', 'started_at', 'created_at']
    list_filter = ['status', 'count_type', 'location']
    search_fields = ['count_number']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [StockCountItemInline]

    fieldsets = (
        (_('Count Info'), {
            'fields': ('count_number', 'location', 'count_type', 'category_filter', 'status'),
            'classes': ['tab'],
        }),
        (_('People'), {
            'fields': ('counted_by', 'approved_by'),
            'classes': ['tab'],
        }),
        (_('Schedule'), {
            'fields': ('started_at', 'completed_at'),
            'classes': ['tab'],
        }),
        (_('Options'), {
            'fields': ('auto_adjust', 'notes'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Location"))
    def location_link(self, obj):
        url = reverse('admin:stock_stocklocation_change', args=[obj.location.pk])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @display(description=_("Type"))
    def count_type_badge(self, obj):
        colors = {'FULL': 'danger', 'PARTIAL': 'warning', 'CYCLE': 'info', 'SPOT': 'success'}
        return colors.get(obj.count_type, 'info'), obj.get_count_type_display()

    @display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            'DRAFT': 'info', 'IN_PROGRESS': 'warning',
            'PENDING_APPROVAL': 'warning', 'APPROVED': 'success', 'CANCELLED': 'danger',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()

    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()

    @display(description=_("Counted By"))
    def counted_by_display(self, obj):
        return str(obj.counted_by) if obj.counted_by else "-"


# ─────────────────────────────────────────────
# VARIANCE REASON CODES
# ─────────────────────────────────────────────
@admin.register(VarianceReasonCode)
class VarianceReasonCodeAdmin(ModelAdmin):
    list_display = ['code', 'name', 'requires_approval_badge', 'is_active_badge']
    list_filter = ['is_active', 'requires_approval']
    search_fields = ['code', 'name']
    list_filter_submit = True

    @display(description=_("Approval Required"), boolean=True)
    def requires_approval_badge(self, obj):
        return obj.requires_approval

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# PRODUCT STOCK LINKS
# ─────────────────────────────────────────────
class ProductComponentStockInline(TabularInline):
    model = ProductComponentStock
    extra = 0
    fields = ('component_name', 'stock_item', 'quantity', 'unit', 'is_default', 'price_modifier')


@admin.register(ProductStockLink)
class ProductStockLinkAdmin(ModelAdmin):
    list_display = ['product_display', 'link_type_badge', 'recipe_display',
                    'stock_item_display', 'qty_per_sale', 'deduct_on_badge', 'is_active_badge']
    list_filter = ['link_type', 'deduct_on_status', 'is_active']
    search_fields = ['product__name']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [ProductComponentStockInline]

    fieldsets = (
        (_('Link Info'), {
            'fields': ('product', 'link_type', 'deduct_on_status', 'is_active'),
            'classes': ['tab'],
        }),
        (_('Stock Source'), {
            'fields': ('recipe', 'stock_item', 'quantity_per_sale', 'unit'),
            'classes': ['tab'],
        }),
    )

    @display(description=_("Product"))
    def product_display(self, obj):
        return str(obj.product)

    @display(description=_("Link Type"))
    def link_type_badge(self, obj):
        colors = {'RECIPE': 'success', 'DIRECT_ITEM': 'info', 'COMPONENT_BASED': 'warning'}
        return colors.get(obj.link_type, 'info'), obj.get_link_type_display()

    @display(description=_("Recipe"))
    def recipe_display(self, obj):
        if obj.recipe:
            url = reverse('admin:stock_recipe_change', args=[obj.recipe.pk])
            return format_html('<a href="{}">{}</a>', url, obj.recipe.name)
        return "-"

    @display(description=_("Stock Item"))
    def stock_item_display(self, obj):
        if obj.stock_item:
            url = reverse('admin:stock_stockitem_change', args=[obj.stock_item.pk])
            return format_html('<a href="{}">{}</a>', url, obj.stock_item.name)
        return "-"

    @display(description=_("Qty/Sale"))
    def qty_per_sale(self, obj):
        unit = obj.unit.short_name if obj.unit else ""
        return f"{obj.quantity_per_sale:,.2f} {unit}"

    @display(description=_("Deduct On"))
    def deduct_on_badge(self, obj):
        colors = {'CREATED': 'info', 'PREPARING': 'warning', 'READY': 'success', 'PAID': 'success'}
        return colors.get(obj.deduct_on_status, 'info'), obj.get_deduct_on_status_display()

    @display(description=_("Active"), boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active


# ─────────────────────────────────────────────
# STOCK SETTINGS (singleton)
# ─────────────────────────────────────────────
@admin.register(StockSettings)
class StockSettingsAdmin(ModelAdmin):
    list_display = ['__str__', 'stock_enabled_badge', 'auto_deduct_badge',
                    'deduct_on_display', 'costing_method', 'production_badge', 'purchasing_badge']
    list_fullwidth = True

    fieldsets = (
        (_('Master Controls'), {
            'fields': ('stock_enabled', 'production_enabled', 'purchasing_enabled', 'multi_location_enabled'),
            'classes': ['tab'],
        }),
        (_('Sale Deduction'), {
            'fields': ('auto_deduct_on_sale', 'deduct_on_order_status', 'reserve_on_order_create',
                       'allow_negative_stock', 'auto_create_production'),
            'classes': ['tab'],
        }),
        (_('Tracking'), {
            'fields': ('track_cost', 'track_batches', 'track_expiry', 'track_serial_numbers'),
            'classes': ['tab'],
        }),
        (_('Costing'), {
            'fields': ('costing_method', 'include_waste_in_cost'),
            'classes': ['tab'],
        }),
        (_('Alerts'), {
            'fields': ('low_stock_alert_enabled', 'expiry_alert_enabled',
                       'expiry_alert_days', 'negative_stock_alert'),
            'classes': ['tab'],
        }),
    )

    def changelist_view(self, request, extra_context=None):
        obj = StockSettings.load()
        return redirect(reverse('admin:stock_stocksettings_change', args=[obj.pk]))

    def has_add_permission(self, request):
        return not StockSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Stock System"), boolean=True)
    def stock_enabled_badge(self, obj):
        return obj.stock_enabled

    @display(description=_("Auto Deduct"), boolean=True)
    def auto_deduct_badge(self, obj):
        return obj.auto_deduct_on_sale

    @display(description=_("Deduct On"))
    def deduct_on_display(self, obj):
        colors = {'PREPARING': 'warning', 'READY': 'success', 'PAID': 'info', 'CREATED': 'danger'}
        return colors.get(obj.deduct_on_order_status, 'info'), obj.deduct_on_order_status

    @display(description=_("Production"), boolean=True)
    def production_badge(self, obj):
        return obj.production_enabled

    @display(description=_("Purchasing"), boolean=True)
    def purchasing_badge(self, obj):
        return obj.purchasing_enabled


# ─────────────────────────────────────────────
# AI ASSISTANT (custom admin view)
# ─────────────────────────────────────────────
class AIAssistantAdmin(admin.ModelAdmin):
    """Proxy admin just to get a URL in the admin for the AI assistant page."""

    def has_module_permission(self, request):
        return False


class StockAdminSite:
    """Mixin to add custom AI assistant URL to admin."""

    @staticmethod
    def get_ai_urls():
        return [
            path('stock/ai-assistant/', admin.site.admin_view(StockAdminSite.ai_assistant_view), name='stock_ai_assistant'),
        ]

    @staticmethod
    def ai_assistant_view(request):
        context = {
            **admin.site.each_context(request),
            'title': 'AI Stock Assistant',
            'opts': {'app_label': 'stock'},
        }
        return TemplateResponse(request, 'admin/stock/ai_assistant.html', context)
