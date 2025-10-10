from django.contrib import admin
from .models import Product, Order, OrderItem, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "featured")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "price_cents", "stock", "active", "featured", "category", "created_at")
    list_filter = ("active", "featured", "category")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'qty', 'unit_price_cents') 

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "short_code", "status", "customer_email", "total_cents", "created_at")
    list_filter = ("status",)
    search_fields = ("short_code", "customer_email")
    inlines = (OrderItemInline,)
    readonly_fields = ('created_at', 'total_cents', 'customer_email', 'customer_phone', 'public_token', 'short_code') 

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "qty", "unit_price_cents")