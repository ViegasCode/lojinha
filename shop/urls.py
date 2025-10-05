from django.urls import path
from . import views

urlpatterns = [
    path("", views.catalog_view, name="catalog"),
    path("p/<slug:slug>/", views.product_detail, name="product_detail"),
    path("api/checkout", views.create_checkout, name="create_checkout"),
    path("webhooks/mercadopago", views.mp_webhook, name="mp_webhook"),
    path("pedido/<str:public_token>/", views.order_status, name="order_status"),
    path("api/orders/lookup", views.orders_lookup, name="orders_lookup"),
    path("api/orders/verify-otp", views.verify_otp, name="verify_otp"),
    path("checkout/sucesso", views.checkout_success, name="checkout_success"),
    path("meu-pedido/", views.order_lookup_page, name="order_lookup_page"),
    path("carrinho/", views.cart_view, name="cart_view"),
    path("api/cart/add", views.api_cart_add, name="api_cart_add"),
    path("api/cart/update", views.api_cart_update, name="api_cart_update"),
    path("api/cart/clear", views.api_cart_clear, name="api_cart_clear"),
    path("api/checkout/cart", views.checkout_from_cart, name="checkout_from_cart"),

]
