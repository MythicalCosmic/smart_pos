from django.urls import path
from main.views import auth_views, category_views


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
]