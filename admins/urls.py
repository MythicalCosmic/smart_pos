from admins.views import auth_views
from django.urls import path

app_name = 'admins'


urlpatterns = [
    path("login", auth_views.login, name="auth_login"),
    path("logout", auth_views.logout, name="auth_logout"),
    path("logout/all", auth_views.logout_all, name="auth_logout_all"),
    path("me", auth_views.me, name="auth_me"),
    path("password/change", auth_views.change_password, name="auth_change_password"),
]
