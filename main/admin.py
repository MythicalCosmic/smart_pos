from django.contrib import admin
from django.db.models import Sum, Count, Avg, Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django import forms
from django.contrib.auth.hashers import make_password
from django.utils.text import slugify
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from unfold.contrib.filters.admin import (
    RangeDateFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
    SingleNumericFilter,
    TextFilter,
)
from .models import User, Session, Category, Product, Order, OrderItem, CashRegister, Inkassa, DeliveryPerson
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.safestring import mark_safe


class CustomRangeDateFilter(RangeDateFilter):
    pass


class CustomRangeDateTimeFilter(RangeDateTimeFilter):
    pass


class CustomRangeNumericFilter(RangeNumericFilter):
    pass


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
        if self.instance and self.instance.pk:
            self.fields['password'].required = False
            self.fields['password'].help_text = _(
                "Leave blank to keep the current password. Enter a new password to change it."
            )
            self.fields['password'].widget.attrs['placeholder'] = 'Leave blank to keep current password'
        else:
            self.fields['password'].required = True
            self.fields['password'].help_text = _("Enter a strong password for the new user.")
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if self.instance.pk and not password:
            return None
        
        if password and len(password) < 4:
            raise forms.ValidationError(_("Password must be at least 4 characters long."))
        
        return password
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
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

    @display(description=_("Role"))
    def role_badge(self, obj):
        colors = {
            'ADMIN': 'danger',
            'CASHIER': 'success',
            'USER': 'info',
        }
        return colors.get(obj.role, 'info'), obj.get_role_display()
    
    @display(description=_("Status"))
    def status_badge(self, obj):
        if obj.status == 'ACTIVE':
            return 'success', obj.get_status_display()
        return 'danger', obj.get_status_display()


@admin.register(Session)
class SessionAdmin(ModelAdmin):
    list_display = ['id', 'user_link', 'ip_address', 'user_agent', 'last_activity']
    list_filter = []
    search_fields = ['ip_address', 'user_agent']
    list_filter_submit = True
    readonly_fields = ['last_activity']
    
    @display(description=_("User"))
    def user_link(self, obj):
        if obj.user_id:
            url = reverse('admin:main_user_change', args=[obj.user_id.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user_id)
        return "-"


class MultiColorWidget(forms.Widget):
    
    template_name = None 
    
    def render(self, name, value, attrs=None, renderer=None):
        widget_id = attrs.get('id', name) if attrs else name
        
        colors = []
        if value:
            colors = [c.strip() for c in value.split(',') if c.strip() and c.strip().startswith('#')]
        
        color_inputs = ''
        for i, color in enumerate(colors):
            color_inputs += f'''
            <div class="color-item" style="display: inline-flex; align-items: center; gap: 4px;">
                <input type="color" value="{color}" 
                       style="width: 40px; height: 40px; border: none; border-radius: 6px; 
                              cursor: pointer; padding: 0; background: none;"
                       onchange="updateColorValue_{widget_id}()">
                <button type="button" onclick="removeColor_{widget_id}(this)" 
                        style="background: #dc3545; color: white; border: none; border-radius: 4px; 
                               width: 20px; height: 20px; cursor: pointer; font-size: 12px; 
                               display: flex; align-items: center; justify-content: center;">×</button>
            </div>
            '''
        
        html = f'''
        <div id="{widget_id}_container" style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
            {color_inputs}
            <button type="button" onclick="addColor_{widget_id}()" 
                    style="width: 40px; height: 40px; border: 2px dashed #666; border-radius: 6px; 
                           background: transparent; cursor: pointer; font-size: 20px; color: #666;
                           display: flex; align-items: center; justify-content: center;">+</button>
        </div>
        <input type="hidden" name="{name}" id="{widget_id}" value="{value or ''}">
        
        <script>
        function updateColorValue_{widget_id}() {{
            var container = document.getElementById('{widget_id}_container');
            var colorInputs = container.querySelectorAll('input[type="color"]');
            var colors = [];
            colorInputs.forEach(function(input) {{
                colors.push(input.value);
            }});
            document.getElementById('{widget_id}').value = colors.join(', ');
        }}
        
        function addColor_{widget_id}() {{
            var container = document.getElementById('{widget_id}_container');
            var addBtn = container.querySelector('button[onclick="addColor_{widget_id}()"]');
            
            var div = document.createElement('div');
            div.className = 'color-item';
            div.style.cssText = 'display: inline-flex; align-items: center; gap: 4px;';
            div.innerHTML = '<input type="color" value="#3498db" ' +
                'style="width: 40px; height: 40px; border: none; border-radius: 6px; cursor: pointer; padding: 0; background: none;" ' +
                'onchange="updateColorValue_{widget_id}()">' +
                '<button type="button" onclick="removeColor_{widget_id}(this)" ' +
                'style="background: #dc3545; color: white; border: none; border-radius: 4px; ' +
                'width: 20px; height: 20px; cursor: pointer; font-size: 12px; ' +
                'display: flex; align-items: center; justify-content: center;">×</button>';
            
            container.insertBefore(div, addBtn);
            updateColorValue_{widget_id}();
        }}
        
        function removeColor_{widget_id}(btn) {{
            btn.parentElement.remove();
            updateColorValue_{widget_id}();
        }}
        </script>
        '''
        return mark_safe(html)
    
    def value_from_datadict(self, data, files, name):
        return data.get(name, '')


def generate_unique_slug(model_class, name, instance=None):
    base_slug = slugify(name, allow_unicode=True)
    if not base_slug:
        base_slug = 'item'
    
    slug = base_slug
    counter = 1
    
    while True:
        qs = model_class.objects.filter(slug=slug)
        if instance and instance.pk:
            qs = qs.exclude(pk=instance.pk)
        if not qs.exists():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


class CategoryAdminForm(forms.ModelForm):
    colors_input = forms.CharField(
        required=False,
        help_text=_("Ranglarni vergul bilan ajrating, masalan: #e74c3c, #3498db, #27ae60"),
        widget=MultiColorWidget()
    )
    
    class Meta:
        model = Category
        fields = ['name', 'slug', 'description', 'status', 'sort_order']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['slug'].help_text = _("Leave blank to auto-generate from name")
        if self.instance and self.instance.pk and self.instance.colors:
            self.fields['colors_input'].initial = ', '.join(self.instance.colors)
    
    def clean_colors_input(self):
        colors_str = self.cleaned_data.get('colors_input', '')
        if not colors_str:
            return []
        
        colors = []
        for color in colors_str.split(','):
            color = color.strip()
            if color:
                if not color.startswith('#'):
                    color = f'#{color}'
                if len(color) in [4, 7] and all(c in '0123456789abcdefABCDEF#' for c in color):
                    colors.append(color.lower())
                else:
                    raise forms.ValidationError(f"Invalid color format: {color}")
        return colors
    
    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        
        if name and not slug:
            cleaned_data['slug'] = generate_unique_slug(Category, name, self.instance)
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.colors = self.cleaned_data.get('colors_input', [])
        if commit:
            instance.save()
        return instance


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    form = CategoryAdminForm
    list_display = ['id', 'name', 'color_bars', 'slug', 'status_badge', 'sort_order', 'product_count', 'created_at']
    list_filter = ['status']
    search_fields = ['name', 'slug', 'description']
    list_filter_submit = True
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'slug', 'description')
        }),
        (_('Colors'), {
            'fields': ('colors_input',),
            'description': _("Select one or more colors for this category")
        }),
        (_('Settings'), {
            'fields': ('status', 'sort_order')
        }),
    )
    
    @display(description=_("Colors"))
    def color_bars(self, obj):
        if not obj.colors:
            return mark_safe('<span style="color: #999;">—</span>')
        
        bars_html = ''.join([
            f'<div style="width: 28px; height: 22px; background-color: {color}; '
            f'border-radius: 4px; border: 1px solid rgba(0,0,0,0.15); '
            f'display: inline-block;" title="{color}"></div>'
            for color in obj.colors
        ])
        
        return mark_safe(
            f'<div style="display: flex; gap: 4px; align-items: center;">{bars_html}</div>'
        )
    
    @display(description=_("Status"))
    def status_badge(self, obj):
        if obj.status == 'ACTIVE':
            return 'success', obj.get_status_display()
        return 'warning', obj.get_status_display()
    
    @display(description=_("Products"))
    def product_count(self, obj):
        return obj.products.count()


class ProductAdminForm(forms.ModelForm):
    colors_input = forms.CharField(
        required=False,
        label=_("Colors"),
        help_text=_("Select one or more colors for this product"),
        widget=MultiColorWidget()
    )
    
    class Meta:
        model = Product
        fields = ['name', 'description', 'category', 'price']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.colors:
            self.fields['colors_input'].initial = ', '.join(self.instance.colors)
    
    def clean_colors_input(self):
        colors_str = self.cleaned_data.get('colors_input', '')
        if not colors_str:
            return []
        
        colors = []
        for color in colors_str.split(','):
            color = color.strip()
            if color:
                if not color.startswith('#'):
                    color = f'#{color}'
                if len(color) in [4, 7] and all(c in '0123456789abcdefABCDEF#' for c in color):
                    colors.append(color.lower())
                else:
                    raise forms.ValidationError(f"Invalid color format: {color}")
        return colors
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.colors = self.cleaned_data.get('colors_input', [])
        if commit:
            instance.save()
        return instance


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    form = ProductAdminForm
    list_display = ['id', 'name', 'color_bars', 'category_link', 'price_display', 'times_ordered', 'created_at']
    list_filter = ['category']
    search_fields = ['name', 'description']
    list_filter_submit = True
    list_fullwidth = True
    
    fieldsets = (
        (_('Product Information'), {
            'fields': ('name', 'description', 'category')
        }),
        (_('Colors'), {
            'fields': ('colors_input',),
            'description': _("Select one or more colors for this product")
        }),
        (_('Pricing'), {
            'fields': ('price',)
        }),
    )
    
    @display(description=_("Colors"))
    def color_bars(self, obj):
        if not obj.colors:
            return mark_safe('<span style="color: #999;">—</span>')
        
        bars_html = ''.join([
            f'<div style="width: 28px; height: 22px; background-color: {color}; '
            f'border-radius: 4px; border: 1px solid rgba(0,0,0,0.15); '
            f'display: inline-block;" title="{color}"></div>'
            for color in obj.colors
        ])
        
        return mark_safe(
            f'<div style="display: flex; gap: 4px; align-items: center;">{bars_html}</div>'
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
    list_filter = ['status', 'cashier']
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
    
    @display(description=_("Status"))
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
        return f"{obj.current_balance:.2f} UZS"


@admin.register(Inkassa)
class InkassaAdmin(ModelAdmin):
    list_display = ['id', 'cashier_link', 'amount_display', 'balance_before_display', 
                    'balance_after_display', 'period_duration', 'total_orders', 'created_at']
    list_filter = ['cashier']
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