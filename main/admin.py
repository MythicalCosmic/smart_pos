from django.contrib import admin

# Register your models here.
from .models import User, Session, Category, Product, Order



admin.site.register(User)
admin.site.register(Session)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Order)
