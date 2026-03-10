from admins.views import auth_views
from django.urls import path

app_name = 'admins'


urlpatterns = [
    path("login", auth_views.login, name="auth_login"),
    path("logout", auth_views.logout, name="auth_logout"),
    path("logout/all", auth_views.logout_all, name="auth_logout_all"),
    path("me", auth_views.me, name="auth_me"),
    path("password/change", auth_views.change_password, name="auth_change_password"),
    path("password/reset", auth_views.password_reset_request, name="auth_password_reset"),
    path("password/reset/confirm", auth_views.password_reset_confirm, name="auth_password_reset_confirm"),
    path("sessions", auth_views.sessions, name="auth_sessions"),
]