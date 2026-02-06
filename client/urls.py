from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    path('display', views.client_display, name='display'),
    path('api/orders/', views.get_orders_data, name='orders_data'),
    path('chef/', views.chef_display, name='chef_display'),
    path('api/chef/orders/', views.get_chef_orders_data, name='chef_orders_data'),
    path('api/chef/orders/<int:order_id>/ready/', views.chef_mark_ready, name='chef_mark_ready'),
    path('', views.return_teapot, name='i am a teampot')
]