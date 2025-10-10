from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('painel/', include('shop.painel_urls')),
    path("", include("shop.urls")),
]