from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    # Main display page
    path('', views.client_display, name='display'),
    
    # AJAX endpoint for real-time data updates
    path('api/orders/', views.get_orders_data, name='orders_data'),
]