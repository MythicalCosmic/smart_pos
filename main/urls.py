from django.urls import path
from main.views import auth_views, category_views, product_views, user_views, order_views, inkassa_views


app_name = 'main'


urlpatterns = [
    path('auth-register', auth_views.register, name='register'),
    path('auth-login', auth_views.login, name='login'),
    path('auth-logout', auth_views.logout, name='logout'),
    path('auth-refresh', auth_views.refresh_token, name='refresh_token'),
    path('auth-me', auth_views.me, name='me'),

    path('categories', category_views.list_categories, name='list_categories'),
    path('categories/<int:category_id>', category_views.get_category, name='get_category'),
    path('categories/create', category_views.create_category, name='create_category'),
    path('categories/<int:category_id>/update', category_views.update_category, name='update_category'),
    path('categories/<int:category_id>/delete', category_views.delete_category, name='delete_category'),
    path('categories/<int:category_id>/status', category_views.update_category_status, name='update_category_status'),
    path('categories/reorder', category_views.reorder_categories, name='reorder_categories'),
    path('categories/stats', category_views.get_stats, name='get_category_stats'),

    path('users', user_views.list_users, name='list_users'),
    path('users/<int:user_id>', user_views.get_user, name='get_user'),
    path('users/create', user_views.create_user, name='create_user'),
    path('users/<int:user_id>/update', user_views.update_user, name='update_user'),
    path('users/<int:user_id>/delete', user_views.delete_user, name='delete_user'),
    path('users/<int:user_id>/status', user_views.update_user_status, name='update_user_status'),
    path('users/<int:user_id>/role', user_views.update_user_role, name='update_user_role'),
    path('stats', user_views.get_stats, name='get_stats'),

    path('products', product_views.list_products, name='list_products'),
    path('products/<int:product_id>', product_views.get_product, name='get_product'),
    path('products/create', product_views.create_product, name='create_product'),
    path('products/<int:product_id>/update', product_views.update_product, name='update_product'),
    path('products/<int:product_id>/delete', product_views.delete_product, name='delete_product'),
    path('products/stats', product_views.get_stats, name='product_stats'),
    path('products/category/<int:category_id>', product_views.get_products_by_category, name='products_by_category'),
    
    path('orders', order_views.list_orders, name='list_orders'),
    path('orders/<int:order_id>', order_views.get_order, name='get_order'),
    path('orders/create', order_views.create_order, name='create_order'),
    path('orders/category/<int:category_id>', order_views.get_orders_by_category, name='orders_by_category'),
    path('orders/<int:order_id>/add-item', order_views.add_item, name='add_order_item'),
    path('orders/<int:order_id>/items/<int:item_id>/update', order_views.update_item, name='update_order_item'),
    path('orders/<int:order_id>/items/<int:item_id>/remove', order_views.remove_item, name='remove_order_item'),
    path('orders/<int:order_id>/status', order_views.update_status, name='update_order_status'),
    path('orders/<int:order_id>/pay', order_views.pay_order, name='pay_order'),
    path('orders/<int:order_id>/ready', order_views.mark_ready, name='mark_order_ready'),
    path('orders/<int:order_id>/cancel', order_views.cancel_order, name='cancel_order'),
    path('orders/stats', order_views.get_stats, name='order_stats'),

    path('inkassa/balance', inkassa_views.get_cash_balance, name='cash_balance'),
    path('inkassa/stats', inkassa_views.get_current_stats, name='current_period_stats'),
    path('inkassa/perform', inkassa_views.perform_inkassa, name='perform_inkassa'),
    path('inkassa/history', inkassa_views.get_inkassa_history, name='inkassa_history'),
    path('inkassa/<int:inkassa_id>', inkassa_views.get_inkassa, name='get_inkassa'),
    
    path('display/client', order_views.client_display, name='client_display'),
    path('display/chef', order_views.chef_display, name='chef_display'),
]