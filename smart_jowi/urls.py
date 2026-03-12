"""
URL configuration for smart_jowi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.template.response import TemplateResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)


def ai_assistant_view(request):
    context = {
        **admin.site.each_context(request),
        'title': 'AI Stock Assistant',
    }
    return TemplateResponse(request, 'admin/stock/ai_assistant.html', context)


# Inject custom URL into admin site so it resolves under the "admin:" namespace
_original_get_urls = admin.site.get_urls

def custom_admin_urls():
    custom = [
        path('stock/ai-assistant/', admin.site.admin_view(ai_assistant_view), name='stock_ai_assistant'),
    ]
    return custom + _original_get_urls()

admin.site.get_urls = custom_admin_urls


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('main.urls')),
    path('', include('client.urls')),
    path('', include('stock.urls')),
    path('admins-api/', include('admins.urls')),
    # path('i18n/', include('django.conf.urls.i18n')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
