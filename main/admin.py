from django.contrib import admin
from django.db.models import Sum, Count, Avg, Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django import forms
from django.contrib.auth.hashers import make_password
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import (
    RangeDateFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
    SingleNumericFilter,
    TextFilter,
)
from .models import User, Session, Category, Product, Order, OrderItem, CashRegister, Inkassa
from datetime import datetime, timedelta
from django.utils import timezone


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    fields = ('product', 'quantity', 'price', 'subtotal')
    readonly_fields = ('subtotal',)
    
    @display(description=_("Subtotal"))
    def subtotal(self, obj):
        if obj.pk:
            return f"${obj.price * obj.quantity:.2f}"
        return "-"


class UserAdminForm(forms.ModelForm):
    """Custom form for User model with password handling"""
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Enter password',
        }),
        help_text=_("Enter a strong password. It will be securely hashed."),
        required=False,
    )
    
    class Meta:
        model = User
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing existing user, make password optional
        if self.instance and self.instance.pk:
            self.fields['password'].required = False
            self.fields['password'].help_text = _(
                "Leave blank to keep the current password. Enter a new password to change it."
            )
            self.fields['password'].widget.attrs['placeholder'] = 'Leave blank to keep current password'
        else:
            # For new user, password is required
            self.fields['password'].required = True
            self.fields['password'].help_text = _("Enter a strong password for the new user.")
    
    def clean_password(self):
        """Clean and validate password"""
        password = self.cleaned_data.get('password')
        
        # If editing and password is empty, return None (don't change password)
        if self.instance.pk and not password:
            return None
        
        # Validate password length
        if password and len(password) < 4:
            raise forms.ValidationError(_("Password must be at least 4 characters long."))
        
        return password
    
    def save(self, commit=True):
        """Override save to hash password"""
        user = super().save(commit=False)
        
        # Hash password if provided
        password = self.cleaned_data.get('password')
        if password:
            user.password = make_password(password)
        
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(ModelAdmin):
    form = UserAdminForm
    list_display = ['id', 'full_name', 'email', 'role_badge', 'status_badge', 'last_login_at']
    list_filter = [
        'role',
        'status',
        ('last_login_at', RangeDateTimeFilter),
    ]
    search_fields = ['first_name', 'last_name', 'email']
    list_filter_submit = True
    list_fullwidth = True
    
    fieldsets = (
        (_('Personal Information'), {
            'fields': ('first_name', 'last_name', 'email'),
            'classes': ['tab'],
        }),
        (_('Access & Security'), {
            'fields': ('role', 'status', 'password'),
            'classes': ['tab'],
            'description': _('Set user role, status, and password. Password will be securely hashed.')
        }),
        (_('Activity Tracking'), {
            'fields': ('last_login_at', 'last_login_api'),
            'classes': ['tab'],
        }),
    )
    
    @display(description=_("Name"), ordering='first_name')
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    
    @display(description=_("Role"), label=True)
    def role_badge(self, obj):
        colors = {
            'ADMIN': 'danger',
            'CASHIER': 'success',
            'USER': 'info',
        }
        return colors.get(obj.role, 'info'), obj.get_role_display()
    
    @display(description=_("Status"), label=True)
    def status_badge(self, obj):
        if obj.status == 'ACTIVE':
            return 'success', obj.get_status_display()
        return 'danger', obj.get_status_display()


@admin.register(Session)
class SessionAdmin(ModelAdmin):
    list_display = ['id', 'user_link', 'ip_address', 'user_agent', 'last_activity']
    list_filter = [
        ('last_activity', RangeDateTimeFilter),
    ]
    search_fields = ['ip_address', 'user_agent']
    list_filter_submit = True
    readonly_fields = ['last_activity']
    
    @display(description=_("User"))
    def user_link(self, obj):
        if obj.user_id:
            url = reverse('admin:main_user_change', args=[obj.user_id.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user_id)
        return "-"


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['id', 'name', 'slug', 'status_badge', 'sort_order', 'product_count', 'created_at']
    list_filter = [
        'status',
        ('created_at', RangeDateFilter),
    ]
    search_fields = ['name', 'slug', 'description']
    list_filter_submit = True
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'slug', 'description')
        }),
        (_('Settings'), {
            'fields': ('status', 'sort_order')
        }),
    )
    
    @display(description=_("Status"), label=True)
    def status_badge(self, obj):
        if obj.status == 'ACTIVE':
            return 'success', obj.get_status_display()
        return 'warning', obj.get_status_display()
    
    @display(description=_("Products"))
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['id', 'name', 'category_link', 'price_display', 'times_ordered', 'created_at']
    list_filter = [
        'category',
        ('price', RangeNumericFilter),
        ('created_at', RangeDateFilter),
    ]
    search_fields = ['name', 'description']
    list_filter_submit = True
    list_fullwidth = True
    
    fieldsets = (
        (_('Product Information'), {
            'fields': ('name', 'description', 'category')
        }),
        (_('Pricing'), {
            'fields': ('price',)
        }),
    )
    
    @display(description=_("Category"))
    def category_link(self, obj):
        url = reverse('admin:main_category_change', args=[obj.category.pk])
        return format_html('<a href="{}">{}</a>', url, obj.category.name)
    
    @display(description=_("Price"), ordering='price')
    def price_display(self, obj):
        return f"${obj.price:.2f}"
    
    @display(description=_("Times Ordered"))
    def times_ordered(self, obj):
        return OrderItem.objects.filter(product=obj).aggregate(
            total=Sum('quantity')
        )['total'] or 0


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ['display_id', 'user_link', 'cashier_link', 'status_badge', 
                    'total_amount_display', 'items_count', 'created_at']
    list_filter = [
        'status',
        ('created_at', RangeDateTimeFilter),
        ('total_amount', RangeNumericFilter),
        'cashier',
    ]
    search_fields = ['display_id', 'user__first_name', 'user__last_name', 'user__email']
    list_filter_submit = True
    list_fullwidth = True
    inlines = [OrderItemInline]
    readonly_fields = ['display_id', 'created_at', 'updated_at', 'ready_at']
    
    fieldsets = (
        (_('Order Information'), {
            'fields': ('display_id', 'user', 'cashier', 'status')
        }),
        (_('Financial'), {
            'fields': ('total_amount',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at', 'ready_at')
        }),
    )
    
    @display(description=_("ID"), ordering='display_id')
    def display_id(self, obj):
        return f"#{obj.display_id}"
    
    @display(description=_("Customer"))
    def user_link(self, obj):
        url = reverse('admin:main_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, f"{obj.user.first_name} {obj.user.last_name}")
    
    @display(description=_("Cashier"))
    def cashier_link(self, obj):
        if obj.cashier:
            url = reverse('admin:main_user_change', args=[obj.cashier.pk])
            return format_html('<a href="{}">{}</a>', url, f"{obj.cashier.first_name} {obj.cashier.last_name}")
        return "-"
    
    @display(description=_("Status"), label=True)
    def status_badge(self, obj):
        colors = {
            'OPEN': 'info',
            'PAID': 'success',
            'READY': 'warning',
            'CANCELED': 'danger',
        }
        return colors.get(obj.status, 'info'), obj.get_status_display()
    
    @display(description=_("Total"), ordering='total_amount')
    def total_amount_display(self, obj):
        return f"${obj.total_amount:.2f}"
    
    @display(description=_("Items"))
    def items_count(self, obj):
        return obj.items.count()


@admin.register(CashRegister)
class CashRegisterAdmin(ModelAdmin):
    list_display = ['id', 'current_balance_display', 'last_updated']
    readonly_fields = ['current_balance', 'last_updated']
    
    def has_add_permission(self, request):
        return not CashRegister.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    @display(description=_("Current Balance"))
    def current_balance_display(self, obj):
        return f"${obj.current_balance:.2f}"


@admin.register(Inkassa)
class InkassaAdmin(ModelAdmin):
    list_display = ['id', 'cashier_link', 'amount_display', 'balance_before_display', 
                    'balance_after_display', 'period_duration', 'total_orders', 'created_at']
    list_filter = [
        'cashier',
        ('created_at', RangeDateTimeFilter),
        ('amount', RangeNumericFilter),
    ]
    search_fields = ['notes', 'cashier__first_name', 'cashier__last_name']
    list_filter_submit = True
    list_fullwidth = True
    readonly_fields = ['cashier', 'amount', 'balance_before', 'balance_after', 
                      'period_start', 'period_end', 'total_orders', 'total_revenue', 'created_at']
    
    fieldsets = (
        (_('Inkassa Information'), {
            'fields': ('cashier', 'amount', 'balance_before', 'balance_after')
        }),
        (_('Period'), {
            'fields': ('period_start', 'period_end')
        }),
        (_('Statistics'), {
            'fields': ('total_orders', 'total_revenue')
        }),
        (_('Notes'), {
            'fields': ('notes',)
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    @display(description=_("Cashier"))
    def cashier_link(self, obj):
        if obj.cashier:
            url = reverse('admin:main_user_change', args=[obj.cashier.pk])
            return format_html('<a href="{}">{}</a>', url, f"{obj.cashier.first_name} {obj.cashier.last_name}")
        return "-"
    
    @display(description=_("Amount Withdrawn"), ordering='amount')
    def amount_display(self, obj):
        return f"${obj.amount:.2f}"
    
    @display(description=_("Balance Before"), ordering='balance_before')
    def balance_before_display(self, obj):
        return f"${obj.balance_before:.2f}"
    
    @display(description=_("Balance After"), ordering='balance_after')
    def balance_after_display(self, obj):
        return f"${obj.balance_after:.2f}"
    
    @display(description=_("Period"))
    def period_duration(self, obj):
        if obj.period_start:
            duration = obj.period_end - obj.period_start
            hours = int(duration.total_seconds() // 3600)
            return f"{hours}h"
        return "-"