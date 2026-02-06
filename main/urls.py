from django.urls import path, include
from main.views import auth_views, category_views, product_views, user_views, order_views, inkassa_views, role_views
from main.views.sync_views import *


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
    path('categories/<int:category_id>/restore', category_views.restore_deleted_category, name='restore-category'),
    path('categories/<int:category_id>/status', category_views.update_category_status, name='update_category_status'),
    path('categories/reorder', category_views.reorder_categories, name='reorder_categories'),
    path('categories/stats', category_views.get_stats, name='get_category_stats'),

    path('users', user_views.list_users, name='user-list'),
    path('users/stats', user_views.get_stats, name='user-stats'),
    path('users/search', user_views.search_users, name='user-search'),
    path('users/deleted', user_views.get_deleted_users, name='user-deleted'),
    path('users/cashiers', user_views.get_cashiers, name='user-cashiers'),
    path('users/admins', user_views.get_admins, name='user-admins'),
    path('users/check-username', user_views.check_username_available, name='user-check-username'),
    path('users/preview-username', user_views.preview_username, name='user-preview-username'),
    path('users/bulk/status', user_views.bulk_update_status, name='user-bulk-status'),
    path('users/bulk/delete', user_views.bulk_delete, name='user-bulk-delete'),
    path('isers/bulk/restore', user_views.bulk_restore, name='user-bulk-restore'),
    path('users/role/<str:role>', user_views.get_users_by_role, name='user-by-role'),
    path('users/username/<str:username>', user_views.get_user_by_username, name='user-by-username'),
    path('users/<int:user_id>', user_views.get_user, name='user-detail'),
    path('users/<int:user_id>/update', user_views.update_user, name='user-update'),
    path('users/<int:user_id>/delete', user_views.delete_user, name='user-delete'),
    path('users/<int:user_id>/restore', user_views.restore_user, name='user-restore'),
    path('users/<int:user_id>/status', user_views.update_user_status, name='user-status'),
    path('users/<int:user_id>/role', user_views.update_user_role, name='user-role'),
    path('users/<int:user_id>/change-password', user_views.change_password, name='user-change-password'),
    path('users/<int:user_id>/reset-password', user_views.reset_password, name='user-reset-password'),
    path('users/create', user_views.create_user, name='user-create'),

    path('', role_views.list_roles, name='role-list'),
    path('stats', role_views.get_role_stats, name='role-stats'),
    path('validate', role_views.validate_role, name='role-validate'),
    path('<str:role_code>', role_views.get_role, name='role-detail'),
    path('<str:role_code>/permissions', role_views.get_role_permissions, name='role-permissions'),
    path('<str:role_code>/manageable', role_views.get_manageable_roles, name='role-manageable'),
    path('<str:role_code>/check/<str:permission>', role_views.check_permission, name='role-check-permission'),

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
    path('orders/<int:order_id>/add-item', order_views.add_item, name='add_order_item'),
    path('orders/<int:order_id>/items/<int:item_id>/update', order_views.update_item, name='update_order_item'),
    path('orders/<int:order_id>/items/<int:item_id>/remove', order_views.remove_item, name='remove_order_item'),
    path('orders/<int:order_id>/status', order_views.update_status, name='update_order_status'),
    path('orders/<int:order_id>/pay', order_views.pay_order, name='pay_order'),
    path('orders/<int:order_id>/ready', order_views.mark_ready, name='mark_order_ready'),
    path('orders/<int:order_id>/cancel', order_views.cancel_order, name='cancel_order'),
    path('orders/<int:order_id>/items/<int:item_id>/ready', order_views.mark_item_ready, name='mark_item_ready'),
    path('orders/<int:order_id>/items/<int:item_id>/unready', order_views.unmark_item_ready, name='unmark_item_ready'),
    path('orders/stats', order_views.get_stats, name='order_stats'),

    path('inkassa/balance', inkassa_views.get_cash_balance, name='cash_balance'),
    path('inkassa/stats', inkassa_views.get_current_stats, name='current_period_stats'),
    path('inkassa/perform', inkassa_views.perform_inkassa, name='perform_inkassa'),
    path('inkassa/history', inkassa_views.get_inkassa_history, name='inkassa_history'),
    path('inkassa/<int:inkassa_id>', inkassa_views.get_inkassa, name='get_inkassa'),
    
    path('display/client', order_views.client_display, name='client_display'),
    path('display/chef', order_views.chef_display, name='chef_display'),


    path('health', SyncHealthView.as_view(), name='sync-health'),
    path('receive', SyncReceiveView.as_view(), name='sync-receive'),
    path('status', SyncStatusView.as_view(), name='sync-status'),
    path('trigger', SyncTriggerView.as_view(), name='sync-trigger'),
    path('queue', SyncQueueView.as_view(), name='sync-queue'),
]

