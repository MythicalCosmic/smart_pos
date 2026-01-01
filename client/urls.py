from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    # Client display page
    path('', views.client_display, name='display'),
    
    # AJAX endpoint for client display
    path('api/orders/', views.get_orders_data, name='orders_data'),
    
    # Chef display page
    path('chef/', views.chef_display, name='chef_display'),
    
    # AJAX endpoint for chef display
    path('api/chef/orders/', views.get_chef_orders_data, name='chef_orders_data'),
    
    # Mark order ready (no auth for chef display)
    path('api/chef/orders/<int:order_id>/ready/', views.chef_mark_ready, name='chef_mark_ready'),
]